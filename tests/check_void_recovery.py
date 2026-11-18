import ast,json,typing,unittest
from pathlib import Path
from datetime import datetime,timezone
from types import SimpleNamespace
src=ast.parse(Path('client/client.py').read_text(encoding='utf-8-sig'))
ns=dict(Dict=typing.Dict,Any=typing.Any,List=typing.List,Optional=typing.Optional,json=json,datetime=datetime,timezone=timezone,_canonical_reject_breakdown=lambda x:x or {})
for name in ['_merge_matching_recovery_snapshots','_snapshot_timestamp_value']:
 node=next(n for n in ast.walk(src) if isinstance(n,ast.FunctionDef) and n.name==name);exec(compile(ast.Module(body=[node],type_ignores=[]),'<test>','exec'),ns)
o=SimpleNamespace(_normalize_job_code=lambda x:str(x or ''),_crew_member_code=lambda x:x.get('operator_id',''))
o._snapshot_timestamp_value=lambda s:ns['_snapshot_timestamp_value'](o,s)
before={'production_session_id':'TEST','pack_count':2,'good_total':40,'product_pack_history_logs':[{'pack_key':'A'},{'pack_key':'B'}],'saved_at_utc':'2026-10-09T00:00:00Z'}
after={**before,'pack_count':1,'good_total':20,'product_pack_history_logs':[{'pack_key':'A'}],'saved_at_utc':'2026-10-09T00:01:00Z','production_adjustment_logs':[{'action':'VOID','logged_at':'2026-10-09T00:01:00Z'}]}
for a,b in [(before,after),(after,before)]:
 r=ns['_merge_matching_recovery_snapshots'](o,a,b);assert r['good_total']==20 and r['pack_count']==1 and len(r['product_pack_history_logs'])==1
later={**after,'pack_count':2,'good_total':40,'product_pack_history_logs':[{'pack_key':'A'},{'pack_key':'C'}],'saved_at_utc':'2026-10-09T00:02:00Z'}
for a,b in [(after,later),(later,after)]:assert ns['_merge_matching_recovery_snapshots'](o,a,b)==later
print('PASS: stale copies cannot resurrect void; later production retained in both argument orders')
