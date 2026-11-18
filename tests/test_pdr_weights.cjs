const fs = require('node:fs');
const assert = require('node:assert/strict');
const source = fs.readFileSync(require('node:path').join(__dirname, '../server/server.py'), 'utf8');
function extract(name) {
  const start = source.indexOf(`  function ${name}(`);
  const end = source.indexOf('\n  function ', start + 1);
  assert.ok(start >= 0 && end > start);
  return source.slice(start, end);
}
const calculate = new Function(['firstValue', 'jobPartIsActive', 'rawPartRows', 'derivedJobApiPartRate', 'standardJobApiPartRate', 'isRawMaterialPart', 'pdrWeightValues'].map(extract).join('\n') + '\nreturn pdrWeightValues;')();
const row = {
  external_average_weight_grams: 210,
  job_payload: {data: {job: {approve_qty: '1000'}, job_details: {parts: [
    {sku: 'Z-RM-RESIN', approve_part_qty: '190'},
    {sku: 'Z-RM-ADDITIVE', part_qty_per_unit: '0.01'},
    {sku: 'STICKER', part_qty_per_unit: '1'}
  ]}}}
};
assert.deepEqual(calculate(row), ['200', '10', '5%']);
assert.deepEqual(calculate({...row, external_average_weight_grams: 190}), ['200', '-10', '-5%']);
assert.deepEqual(calculate({...row, external_average_weight_grams: 200}), ['200', '0', '0%']);
assert.deepEqual(calculate({...row, external_average_weight_grams: null}), ['200', '-', '-']);
assert.deepEqual(calculate({...row, standard_product_weight_kg: 0.21}), ['210', '0', '0%']);
assert.deepEqual(calculate({external_average_weight_grams: 210}), ['-', '-', '-']);
assert.deepEqual(calculate({...row, _pdr_machine_status: true}), ['-', '-', '-']);
assert.deepEqual(calculate({...row, external_average_weight_grams: 'bad'}), ['200', '-', '-']);
assert.ok(source.includes('const weights = production.map(pdrWeightValues);'));
console.log('PASS: PDR API weights, kg-to-grams, signed variations, and missing values');
