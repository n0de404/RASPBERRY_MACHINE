"""Restore IMM 315's verified pre-restart session after its queue drains."""
import base64
import os
import paramiko

SCRIPT = r'''
import json, os, pathlib, signal, sqlite3, subprocess, time, urllib.request
data=pathlib.Path('/home/user/.local/share/raspberry-machine-client')
root=pathlib.Path('/home/user/Raspberry_Machine/client')
db=data/'client_runtime.sqlite3'
backup=data/'client_runtime.dispatch-fix-20261005.bak.sqlite3'
src=sqlite3.connect('file:'+str(backup)+'?mode=ro',uri=True)
row=src.execute("select client_id,production_session_id,updated_at_utc,payload_json from active_sessions where machine_code='M00015'").fetchone()
src.close()
assert row and row[1]=='PS-1259C25D716B41439BB980B111D12292'
with urllib.request.urlopen('http://192.168.10.49:8000/api/active-sessions/M00015',timeout=8) as r:
 result=json.load(r)
print('SERVER_KEYS',list(result))
server=result.get('item') or result.get('session') or result
assert server.get('production_session_id')==row[1], 'Server changed session; stop for inspection'
processes=[];env=None
binary=str(root/'dist/RaspberryMachineClient')
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  if (p/'cmdline').read_bytes().split(b'\0')[0].decode()!=binary:continue
  processes.append(int(p.name))
  env=dict(x.decode().split('=',1) for x in (p/'environ').read_bytes().split(b'\0') if b'=' in x)
 except (OSError,UnicodeError):pass
assert env and processes
env={k:v for k,v in env.items() if not k.startswith('_PYI') and k not in ('_MEIPASS2','LD_LIBRARY_PATH')}
for pid in sorted(processes,reverse=True):
 try:os.kill(pid,signal.SIGTERM)
 except ProcessLookupError:pass
time.sleep(3)
assert not any(pathlib.Path('/proc/'+str(pid)).exists() for pid in processes)
c=sqlite3.connect(db)
dst=sqlite3.connect(data/'client_runtime.before-315-session-repair.sqlite3')
c.backup(dst);dst.close()
assert c.execute('select count(*) from event_outbox').fetchone()[0]==0, 'Pending scans require review'
c.execute('update active_sessions set client_id=?,production_session_id=?,updated_at_utc=?,payload_json=? where machine_code=?',(*row,'M00015'))
c.commit();c.close()
log=open('/home/user/.local/state/raspberry-machine-client/client.log','ab',buffering=0)
p=subprocess.Popen([binary],cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
time.sleep(5)
assert p.poll() is None
print('RECOVERED NEW JOB 119366 PID='+str(p.pid))
'''

if __name__ == '__main__':
    c=paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect('192.168.13.14',username='user',password=os.environ['PI_PASSWORD'],timeout=8)
    encoded=base64.b64encode(SCRIPT.encode()).decode()
    _,out,err=c.exec_command('python3 -c "import base64;exec(base64.b64decode(\''+encoded+'\'))"',timeout=30)
    print(out.read().decode());print(err.read().decode())
    code=out.channel.recv_exit_status();c.close()
    raise SystemExit(code)
