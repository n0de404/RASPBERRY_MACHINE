"""Deploy the minimal dispatcher fix with recoverable source/binary backups."""
import concurrent.futures
import difflib
import os
import sys
import paramiko

HOSTS = ['192.168.13.19', '192.168.13.17', '192.168.13.11', '192.168.13.15',
         '192.168.11.147', '192.168.13.13', '192.168.13.16', '192.168.10.167',
         '192.168.13.14', '192.168.13.26', '192.168.13.25']
ROOT = '/home/user/Raspberry_Machine/client'
TAG = os.environ.get('PI_REPAIR_TAG', 'dispatch-fix-20261005')

def run(c, command):
    _, out, err = c.exec_command(command, timeout=30)
    result = out.read().decode(errors='replace')
    errors = err.read().decode(errors='replace')
    code = out.channel.recv_exit_status()
    if code:
        raise RuntimeError(f'{code}: {result} {errors}')
    return result.strip()

def one(host):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        c.connect(host, username='user', password=os.environ['PI_PASSWORD'], timeout=8)
        mode = sys.argv[1]
        if mode == 'stage':
            sftp = c.open_sftp()
            with sftp.open(ROOT+'/client.py') as f:
                old = f.read().decode('utf-8')
            marker = '                    response_body: Dict[str, Any] = {}\n'
            anchor = '            last_error: Any = ""\n'
            if TAG == 'review-name-fix-20261005':
                before = '        code = self._clean_badge_scan_code(raw)\n        if not code:\n'
                after = '        code = self._clean_badge_scan_code(raw)\n        if not code or code.lower() == "svisorreview~1":\n'
                start = old.index('    def _authorized_person_from_scan(')
                assert before in old[start:]
                new = old[:start] + old[start:].replace(before, after, 1)
            else:
                assert old.count(marker) == 1 and old.count(anchor) == 1
                new = old.replace(marker, '').replace(anchor, anchor+'            response_body: Dict[str, Any] = {}\n')
            patch = ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile='client.py', tofile='client.py'))
            with sftp.open('/tmp/'+TAG+'.patch', 'w') as f:
                f.write(patch)
            run(c, f'cd {ROOT} && cp -p client.py client.py.{TAG}.bak && patch --forward client.py /tmp/{TAG}.patch && .venv/bin/python -m py_compile client.py')
            script = f'''#!/bin/bash
set -eu
cd {ROOT}
.venv/bin/python -m PyInstaller --noconfirm --distpath dist-{TAG} --workpath build-{TAG} client_pi.spec
test -x dist-{TAG}/RaspberryMachineClient
touch /tmp/{TAG}.ready
'''
            with sftp.open('/tmp/'+TAG+'.sh', 'w') as f:
                f.write(script)
            sftp.close()
            run(c, f'nohup bash /tmp/{TAG}.sh >/tmp/{TAG}.log 2>&1 </dev/null &')
            return host+' BUILD_STARTED'
        if mode == 'status':
            return host+' '+run(c, f'if test -f /tmp/{TAG}.ready; then echo READY; else tail -n 2 /tmp/{TAG}.log; fi')
        if mode == 'verify':
            import base64
            script = '''
import json, pathlib, sqlite3, urllib.request
data=pathlib.Path('/home/user/.local/share/raspberry-machine-client')
c=sqlite3.connect('file:'+str(data/'client_runtime.sqlite3')+'?mode=ro',uri=True)
rows=[json.loads(r[0]) for r in c.execute('select payload_json from active_sessions')]
queue=c.execute('select count(*) from event_outbox').fetchone()[0]
errors=c.execute("select event_type,last_error from event_outbox where last_error<>'' limit 2").fetchall()
with urllib.request.urlopen('http://192.168.10.49:8000/api/active-sessions',timeout=8) as response:
 server={r['machine_code']:r for r in json.load(response)['items']}
for row in rows:
 remote=server.get(row.get('machine_code'),{})
 keys=['job_code','job_name','operator_id','production_session_id','pack_total','good_total','reject_total']
 print(json.dumps({'machine':row.get('machine_code'),'queue':queue,'errors':errors,'local':{k:row.get(k) for k in keys},'server':{k:remote.get(k) for k in keys}}))
log=pathlib.Path('/home/user/.local/state/raspberry-machine-client/client.log').read_text(errors='replace').split('DISPATCH_FIX_20261005_RESTART')[-1]
print('NEW_TRACEBACK='+str('Traceback' in log))
if 'Traceback' in log: print(log[-2000:])
'''
            encoded=base64.b64encode(script.encode()).decode()
            return host+' '+run(c, 'python3 -c "import base64;exec(base64.b64decode(\''+encoded+'\'))"')
        if mode == 'activate':
            # Save the exact running kiosk environment before stopping its app.
            script = f'''
import os, pathlib, signal, subprocess, time, sqlite3, shutil
root=pathlib.Path({ROOT!r})
tag={TAG!r}
assert pathlib.Path('/tmp/'+tag+'.ready').exists()
binary=str(root/'dist/RaspberryMachineClient')
processes=[]
env=None
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit(): continue
 try:
  args=(p/'cmdline').read_bytes().split(b'\\0')
  if args[0].decode()!=binary: continue
  processes.append(int(p.name))
  candidate=dict(entry.decode().split('=',1) for entry in (p/'environ').read_bytes().split(b'\\0') if b'=' in entry)
  if 'MACHINE_DATA_DIR' in candidate: env=candidate
 except (OSError,UnicodeError): pass
assert env and processes, 'No running client environment found'
# Do not carry the old PyInstaller extraction environment into the new build.
env={{k:v for k,v in env.items() if not k.startswith('_PYI') and k not in ('_MEIPASS2','LD_LIBRARY_PATH')}}
data=pathlib.Path(env['MACHINE_DATA_DIR'])
db=data/'client_runtime.sqlite3'
if db.exists():
 src=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
 dst=sqlite3.connect(str(data/('client_runtime.'+tag+'.bak.sqlite3')))
 src.backup(dst);dst.close();src.close()
else:
 for name in ('client_active_machine_sessions.json','server_event_queue.json','server_confirmed_sessions.json'):
  path=data/name
  if path.exists(): shutil.copy2(path,data/(name+'.'+tag+'.bak'))
for pid in sorted(processes,reverse=True):
 try: os.kill(pid,signal.SIGTERM)
 except ProcessLookupError: pass
time.sleep(3)
assert not any(pathlib.Path('/proc/'+str(pid)).exists() for pid in processes), 'Client did not stop'
backup=root/('dist/RaspberryMachineClient.'+tag+'.bak')
assert not backup.exists(), 'Already activated'
os.rename(binary,backup)
os.rename(root/('dist-'+tag+'/RaspberryMachineClient'),binary)
log=open('/home/user/.local/state/raspberry-machine-client/client.log','ab',buffering=0)
log.write(b'\\nDISPATCH_FIX_20261005_RESTART\\n')
p=subprocess.Popen([binary],cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
time.sleep(5)
assert p.poll() is None, 'New client exited'
print('ACTIVATED PID='+str(p.pid))
'''
            import base64
            encoded=base64.b64encode(script.encode()).decode()
            return host+' '+run(c, 'python3 -c "import base64;exec(base64.b64decode(\''+encoded+'\'))"')
    except Exception as e:
        return host+' ERROR '+str(e)
    finally:
        c.close()

if __name__ == '__main__':
    targets=sys.argv[2:] or HOSTS
    with concurrent.futures.ThreadPoolExecutor(max_workers=11) as pool:
        for result in pool.map(one, targets):
            print(result, flush=True)
