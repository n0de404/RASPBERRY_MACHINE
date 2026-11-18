const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../server/server.py'), 'utf8');
const start = source.indexOf('  const PDR_EXCEL_HEADERS =');
const end = source.indexOf('  function renderFinishedShiftPdr(rows){', start);
assert.ok(start >= 0 && end > start, 'PDR helpers are present');
const helpers = new Function('pdrAmBoundaryHour', 'pdrNightBoundaryHour', 'extractJobRecord', 'extractJobDetailsRecord', 'jobKeyOf', 'MACHINE_NAME_MAP', 'displayNameForId', 'fmtDateLocal', 'esc', `${source.slice(start, end)}; return {PDR_EXCEL_HEADERS,pdrShiftBucket,pdrGroupRows,pdrValues};`)(
  7, 19, row => row.job || {}, row => row.details || {}, row => row.job_key, {}, value => value, value => value || '-', value => String(value),
);
const {PDR_EXCEL_HEADERS, pdrShiftBucket, pdrGroupRows, pdrValues} = helpers;

assert.equal(PDR_EXCEL_HEADERS.length, 101);
assert.equal(PDR_EXCEL_HEADERS.filter(x => x === 'REMARKS').length, 2);
assert.equal(PDR_EXCEL_HEADERS.filter(x => x === 'Machine Operator').length, 2);

assert.deepEqual(pdrShiftBucket({started_at_utc:'2026-10-05T23:00:00Z'}), {
  key:'2026-10-06|AM', date:'2026-10-06', shift:'AM', order:0, fallback:false,
});
assert.equal(pdrShiftBucket({started_at_utc:'2026-10-06T11:00:00Z'}).key, '2026-10-06|Night');
assert.equal(pdrShiftBucket({started_at_utc:'2026-10-06T22:59:59Z'}).key, '2026-10-06|Night');
assert.equal(pdrShiftBucket({started_at_utc:'2026-10-06T23:00:00Z'}).key, '2026-10-07|AM');

const grouped = pdrGroupRows([
  {job_key:'a', machine_code:'M2', started_at_utc:'2026-10-06T00:00:00Z'},
  {job_key:'b', machine_code:'M2', started_at_utc:'2026-10-06T01:00:00Z'},
  {job_key:'b', machine_code:'M2', started_at_utc:'2026-10-06T01:00:00Z'},
  {job_key:'c', machine_code:'M3', started_at_utc:'2026-10-06T12:00:00Z'},
]);
assert.equal(grouped.length, 2, 'one aggregate row per machine/shift');
assert.equal(grouped[0].rows.length, 2, 'machine segments retained and duplicate job key removed');
assert.equal(grouped[1].bucket.shift, 'Night');
const values = pdrValues({bucket:{date:'2026-10-06',shift:'AM'}, rows:[
  {job_key:'main',machine_code:'M2',good_total:12,reject_total:2,downtime_total_seconds:900,job_code:'WO-1'},
  {job_key:'linked',machine_code:'M2',linkage_role:'LINKED',good_total:12,reject_total:2,downtime_total_seconds:900,job_code:'WO-2'},
]});
assert.equal(values[38], 12, 'linked snapshot does not double-count good output');
assert.equal(values[39], 2, 'linked snapshot does not double-count rejects');
assert.equal(values[76], '-', 'cumulative downtime is not summed across segments');
assert.equal(values[9], 'WO-1; WO-2', 'all contributing work orders remain visible');
assert.equal(values[0], '-', 'unknown total shift running is not inferred from record count');
assert.match(values[83], /^07:00.19:00$/);
assert.equal(values[100], '-', 'GC REPORT is not repurposed for UI drill-down');
console.log('PASS: PDR headers and real-shift machine grouping');
