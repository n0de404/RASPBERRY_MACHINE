const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../server/server.py'), 'utf8');
const start = source.indexOf('  async function openMachineCard(code){');
const end = source.indexOf('  // Use the stable grid', start);
assert.ok(start >= 0 && end > start);
const detail = {
  machine_code: 'M00009', job_code: '119034',
  product_pack_history_logs: [{pack_key: 'PACK-1'}],
  raw_material_logs: [{qty: 25}],
  pdr_downtime_logs: [{duration_seconds: 120}],
};
let latestState = {sessions: [{machine_code: 'M00009', summary_only: true}]};
const MACHINE_NAME_MAP = {};
const machineDetailOverlay = {classList: {contains: () => true}};
let activeMachineDetailCode = 'M00009';
const rendered = [];
const openMachineDetail = row => rendered.push(row);
const machineDetailSessionForDisplayedJob = row => row;
const window = {setTimeout, clearTimeout};
const fetch = async url => {
  assert.equal(url, '/api/active-sessions/M00009');
  return {ok: true, json: async () => ({ok: true, item: detail})};
};
eval(source.slice(start, end));
(async () => {
  await openMachineCard('M00009');
  assert.equal(rendered.length, 2);
  const full = rendered.at(-1);
  assert.equal(full.summary_only, false);
  for (const key of ['product_pack_history_logs', 'raw_material_logs', 'pdr_downtime_logs']) {
    assert.deepEqual(full[key], detail[key]);
    assert.deepEqual(latestState.sessions[0][key], detail[key]);
  }
  console.log('PASS: machine detail loads pack, material, and downtime records from item response');
})().catch(error => {console.error(error); process.exitCode = 1;});
