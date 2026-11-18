import base64,concurrent.futures,json,os,pathlib
import repair_dispatch_fleet as base
from rollout_void_fix import HOSTS
script=r'''
import pathlib,json,sqlite3,marshal,types,hashlib
from PyInstaller.archive.readers import CArchiveReader
root=pathlib.Path('/home/user/Raspberry_Machine/client');binary=root/'dist/RaspberryMachineClient'
a=CArchiveReader(str(binary));code=marshal.loads(a.extract('client'));functions={}
def walk(c):
 if not isinstance(c,types.CodeType):return
 functions[c.co_name]=c
 for x in c.co_consts:walk(x)
walk(code)
assert 'post_good_total' in repr(functions['on_scanned'].co_consts)
assert any(isinstance(x,types.CodeType) and x.co_name=='latest_void' for x in functions['_merge_matching_recovery_snapshots'].co_consts)
processes=[];data=None
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  if (p/'exe').resolve()!=binary:continue
  processes.append(int(p.name))
  for entry in (p/'environ').read_bytes().split(b'\0'):
   if entry.startswith(b'MACHINE_DATA_DIR='):data=pathlib.Path(entry.split(b'=',1)[1].decode())
 except OSError:pass
assert processes,'Updated executable is not running'
out={'pids':processes,'fixed_binary':True,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()[:16],'data':str(data)}
if data and (data/'client_runtime.sqlite3').exists():
 c=sqlite3.connect('file:'+str(data/'client_runtime.sqlite3')+'?mode=ro',uri=True,timeout=5);c.execute('PRAGMA query_only=ON')
 out['queue']=c.execute('select count(*) from event_outbox').fetchone()[0]
 out['queue_errors']=c.execute("select event_type,attempts,last_error from event_outbox where last_error<>'' limit 2").fetchall()
 out['sessions']=[{k:r.get(k) for k in ['machine_code','job_code','pack_count','good_total']} for r in [json.loads(x[0]) for x in c.execute('select payload_json from active_sessions')]]
 c.close()
log=pathlib.Path('/home/user/.local/state/raspberry-machine-client/client.log')
if log.exists():
 with log.open('rb') as f:f.seek(max(0,log.stat().st_size-40000));tail=f.read().decode(errors='replace')
 tail=tail.split('DISPATCH_FIX_20261005_RESTART')[-1]
 out['traceback_after_restart']='Traceback' in tail
 if out['traceback_after_restart']:out['log_tail']=tail[-1800:]
print(json.dumps(out))
'''
def verify(host):
 c=base.paramiko.SSHClient();c.load_system_host_keys();c.set_missing_host_key_policy(base.paramiko.AutoAddPolicy())
 try:
  c.connect(host,username='user',password=os.environ['PI_PASSWORD'],timeout=6,look_for_keys=False,allow_agent=False)
  command='/home/user/Raspberry_Machine/client/.venv/bin/python -c '+"\"import base64;exec(base64.b64decode('"+base64.b64encode(script.encode()).decode()+"'))\""
  return {'host':host,'result':json.loads(base.run(c,command))}
 except Exception as e:return {'host':host,'error':str(e)}
 finally:c.close()
if __name__=='__main__':
 import sys
 hosts=sys.argv[1:] or HOSTS
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as p:results=list(p.map(verify,hosts))
 for row in results:print(json.dumps(row))
 pathlib.Path('.fleet-debug/void-rollout-verification.json').write_text(json.dumps(results,indent=2))
