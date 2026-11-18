import ast,base64,concurrent.futures,json,os,pathlib,sys
import repair_dispatch_fleet as base
base.TAG='void-fix-20261009'
HOSTS=['192.168.13.'+str(n) for n in [24,19,17,11,15,13,16,14,26,25,12]]+['192.168.11.147','192.168.10.167','192.168.11.20']
local=pathlib.Path('client/client.py').read_text(encoding='utf-8-sig')
def method(text,name):
 tree=ast.parse(text);n=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name);lines=text.splitlines(True);return ''.join(lines[n.lineno-1:n.end_lineno])
def stage(host):
 c=base.paramiko.SSHClient();c.load_system_host_keys();c.set_missing_host_key_policy(base.paramiko.AutoAddPolicy())
 try:
  c.connect(host,username='user',password=os.environ['PI_PASSWORD'],timeout=6,look_for_keys=False,allow_agent=False)
  s=c.open_sftp();old=s.open(base.ROOT+'/client.py').read().decode('utf-8');new=old
  for name in ['_void_pack_scan','_void_product_part_scan','_void_butal_scan','_merge_matching_recovery_snapshots']:
   new=new.replace(method(new,name),method(local,name),1)
  anchor='                event_type = "PACK_VOID" if voided_kind == "PACK" else "PRODUCT_PART_VOID"'
  a=new.index(anchor);b=new.index('                return',a)
  la=local.index(anchor);lb=local.index('                return',la)
  new=new[:a]+local[la:lb]+new[b:]
  before='                self.push_event({"type": "BUTAL_VOID"}, "BUTAL VOID", defer_snapshot=True)'
  la=local.index('                self.push_event(\n',local.index('if not self._void_butal_scan(raw_s'))
  lb=local.index('                return',la)
  assert before in new;new=new.replace(before,local[la:lb].rstrip(),1)
  before='                self.push_event({"type": "PRODUCT_PART_VOID"}, "PRODUCT PART VOID", defer_snapshot=True)'
  la=local.index('                self.push_event({\n                    "type": "PRODUCT_PART_VOID"')
  lb=local.index('                return',la)
  assert before in new;new=new.replace(before,local[la:lb].rstrip(),1)
  # The October 3 builds also need the already-tested exception-path initialization.
  marker='                    response_body: Dict[str, Any] = {}\n';anchor='            last_error: Any = ""\n'
  if marker in new:
   assert new.count(marker)==1 and new.count(anchor)==1
   new=new.replace(marker,'').replace(anchor,anchor+'            response_body: Dict[str, Any] = {}\n')
  compile(new,'client.py','exec')
  backup=base.ROOT+'/client.py.'+base.TAG+'.bak'
  try:s.stat(backup);raise RuntimeError('Backup already exists; stage not repeated')
  except IOError:pass
  with s.open(backup,'w') as f:f.write(old)
  with s.open(base.ROOT+'/client.py','w') as f:f.write(new)
  script=f'''#!/bin/bash
set -eu
cd {base.ROOT}
.venv/bin/python -m py_compile client.py
.venv/bin/python -m PyInstaller --noconfirm --distpath dist-{base.TAG} --workpath build-{base.TAG} client_pi.spec
test -x dist-{base.TAG}/RaspberryMachineClient
touch /tmp/{base.TAG}.ready
'''
  with s.open('/tmp/'+base.TAG+'.sh','w') as f:f.write(script)
  base.run(c,f'nohup bash /tmp/{base.TAG}.sh >/tmp/{base.TAG}.log 2>&1 </dev/null &')
  return host+' BUILD_STARTED'
 except Exception as e:return host+' ERROR '+str(e)
 finally:c.close()
if __name__=='__main__':
 mode=sys.argv[1];hosts=sys.argv[2:] or HOSTS
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
  for r in pool.map(stage if mode=='stage' else base.one,hosts):print(r,flush=True)
