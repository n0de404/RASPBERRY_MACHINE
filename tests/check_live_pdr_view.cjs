const fs = require('node:fs');
const assert = require('node:assert/strict');
const source = fs.readFileSync(require('node:path').join(__dirname, '../server/server.py'), 'utf8');
const weightHelpers = ['firstValue','jobPartIsActive','rawPartRows','derivedJobApiPartRate','standardJobApiPartRate','isRawMaterialPart'].map(name => {
  const from = source.indexOf(`  function ${name}(`);
  return source.slice(from, source.indexOf('\n  function ', from + 1));
}).join('\n');
const start = source.indexOf('  const PDR_EXCEL_HEADERS =');
const end = source.indexOf('  function renderFinishedShiftPdr(rows){', start);
const key = row => [row.finished_at_utc || '',row.machine_code || '',row.job_code || '',row.operator_id || '',row.pack_count ?? '',row.good_total ?? '',row.butal_total ?? '',row.reject_total ?? ''].join('|');
const helpers = new Function('pdrAmBoundaryHour','pdrNightBoundaryHour','extractJobRecord','extractJobDetailsRecord','jobKeyOf','MACHINE_NAME_MAP','displayNameForId',weightHelpers + source.slice(start,end) + ';return {pdrGroupRows,pdrValues};')(7,19,r => r.job_payload?.data?.job || {},r => r.job_payload?.data?.job_details || {},key,{},v => v);
for (const [row, expected] of [
  [{operator_id:'OP1', manpower_count:3}, 1],
  [{operator_id:'OP1'}, 1],
  [{operator_id:'OP1', crew_members:[{operator_id:'OP2'}]}, 2],
  [{operator_id:'OP1', _crew_member_count:2, manpower_count:'null'}, 1],
  [{manpower_count:0}, 0],
]) {
  const values = helpers.pdrValues({bucket:{date:'2026-10-07',shift:'AM'},rows:[row]});
  assert.equal(values[1], expected, 'total actual manpower counts displayed people');
  assert.equal(values[24], expected, 'actual manpower agrees with total');
}
const crewValues = helpers.pdrValues({bucket:{date:'2026-10-07',shift:'AM'},rows:[
  {operator_id:'OP1', operator_name:'Rose Marie', crew_members:[
    {operator_id:'OP2',operator_name:'Nikka Lynne Logatoc'},
    {code:'OP3',name:'Helper Two'},
    {operator_id:'OP4'},
  ]},
]});
assert.equal(crewValues[25], 'Rose Marie');
assert.deepEqual(crewValues.slice(26,29), ['Nikka Lynne Logatoc','Helper Two','OP4']);
const noHelpers = helpers.pdrValues({bucket:{date:'2026-10-07',shift:'AM'},rows:[
  {operator_name:'Rose Marie'}, {operator_name:'Nikka Lynne Logatoc'},
]});
assert.equal(noHelpers[25], 'Rose Marie', 'first operator is displayed as main');
assert.deepEqual(noHelpers.slice(26,29), ['Nikka Lynne Logatoc','-','-']);
const mixedCrew = helpers.pdrValues({bucket:{date:'2026-10-07',shift:'AM'},rows:[
  {operator_id:'26-00825',crew_members:[{operator_id:'26-00630 - Loriely Azuela',operator_name:'Loriely Azuela'},{code:'H2',name:'Helper Two'},{code:'H3',name:'Helper Three'},{code:'H4',name:'Helper Four'}]},
  {operator_id:'26-00630',operator_name:'Loriely Azuela'},
  {operator_id:'26-00825'},
]});
assert.deepEqual(mixedCrew.slice(25,29), ['26-00825','Loriely Azuela','Helper Two','Helper Three; Helper Four']);
assert.equal(mixedCrew[80], mixedCrew[25]);
assert.equal(noHelpers[1], 2, 'one main plus one additional operator counts as two');
assert.equal(noHelpers[24], 2);
assert.equal(crewValues[1], 4, 'main plus three helpers counts as four');
assert.equal(mixedCrew[1], 5, 'duplicates are excluded and overflow helpers are counted');
(async () => {
  const log = {downtime_index:1,started_at_utc:'2026-10-07T00:00:00Z',duration_seconds:300,reason_segments:[{reason_code:'01',duration_seconds:120},{reason_code:'07',duration_seconds:180}]};
  const downtime = helpers.pdrValues({bucket:{date:'2026-10-07',shift:'AM'},rows:[
    {machine_code:'M1',pdr_downtime_logs:[log]},
    {machine_code:'M1',pdr_downtime_logs:[log]},
    {machine_code:'M1',linkage_role:'LINKED',pdr_downtime_logs:[log]},
  ]});
  assert.equal(downtime[61], '00:02:00');
  assert.equal(downtime[67], '00:03:00');
  assert.equal(downtime[62], '00:00:00');
  assert.equal(downtime[76], '00:05:00', 'repeated and linked snapshots do not inflate downtime');
  const response = await fetch('http://127.0.0.1:8000/api/finished-jobs?page_size=200');
  const data = await response.json();
  const row = data.items.find(r => r.record_type === 'SHIFT_PARTIAL');
  assert.ok(row);
  const detailResponse = await fetch('http://127.0.0.1:8000/api/finished-jobs/detail?job_key=' + encodeURIComponent(key(row)));
  const detail = await detailResponse.json();
  assert.ok(detail.ok && detail.item);
  const groups = helpers.pdrGroupRows([detail.item]);
  const values = helpers.pdrValues(groups[0]);
  assert.equal(values.length,101);
  assert.equal(Number(values[38]),Number(detail.item.good_total));
  assert.ok(values[4] !== '-');
  assert.notEqual(values[1], '-', 'live record displays actual manpower');
  console.log('Live record verified:', values[4], values[6], values[7], 'good output:', values[38], 'manpower:', values[1]);
})().catch(error => {console.error(error);process.exitCode=1;});
