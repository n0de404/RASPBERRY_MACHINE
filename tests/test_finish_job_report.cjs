const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../server/server.py"), "utf8");
const start = source.indexOf("  function finishJobShiftRows(row){");
const end = source.indexOf("  function renderSummaryMetricsHtml(row){", start);
assert.ok(start >= 0 && end > start, "Finish Job report functions were not found");

let finishedJobsState = [];
let finishedShiftState = [];
const isShiftPartialRecord = row => String(row?.record_type || "").toUpperCase() === "SHIFT_PARTIAL";
const jobKeyOf = row => [
  row.finished_at_utc || "", row.machine_code || "", row.job_code || "", row.operator_id || "",
  row.pack_count ?? "", row.good_total ?? "", row.butal_total ?? "", row.reject_total ?? "",
].join("|");
const firstValue = (...values) => values.find(value =>
  value !== undefined && value !== null && String(value).trim() !== ""
) ?? "";
const fmtDateLocal = value => value || "";
const displayNameForId = value => value;
const esc = value => String(value);
const materialKeyText = value => String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
const jobDisplayName = row => row.job_name || row.job_code || "-";
const skuNameHoverHtml = (sku, name) => `${sku}: ${name}`;

eval(source.slice(start, end));

const priorShift = {
  record_type: "SHIFT_PARTIAL", machine_code: "M00001", job_code: "12345",
  finished_at_utc: "2026-11-23T01:00:00Z", pack_count: 12, good_total: 144,
  total_good: 144, butal_total: 0, reject_total: 2, operator_id: "Operator A",
};
const finalShift = {
  record_type: "FINAL_JOB", machine_code: "M00001", machine_name: "IMM 301",
  job_code: "12345", job_name: "Sample Job", finished_at_utc: "2026-11-24T01:00:00Z",
  pack_count: 15, good_total: 180, total_good: 181, butal_total: 1, reject_total: 3,
  operator_id: "Operator B", production_shift_summaries: [priorShift],
  approved_by: "Supervisor One", approved_by_code: "80001", approved_by_role: "SUPERVISOR",
  approved_at_utc: "2026-11-24T01:02:00Z",
  return_inventory_logs: [{
    return_type: "PRODUCT PART", sku: "PART-1", name: "Sample Part", unit: "pc",
    expected_balance_qty: 30, actual_count_qty: 12.5, difference_qty: -17.5,
    printed_quantity: 12.5, quantity_source: "ACTUAL_COUNT",
  }],
  raw_material_logs: [{material_sku: "PART-1", qty: 100}],
  job_inventory_totals: [{
    sku: "PART-1", name: "Sample Part", unit: "pc",
    total_scanned: 250, total_used: 220, balance: 30,
  }],
};

finishedJobsState = [finalShift];
finishedShiftState = [priorShift];

const shiftRows = finishJobShiftRows(finalShift);
assert.equal(shiftRows.length, 2);
const productionHtml = finishJobProductionSummaryHtml(finalShift);
assert.match(productionHtml, /TOTAL PACKS/);
assert.match(productionHtml, />27</);
assert.doesNotMatch(productionHtml, /raw_scan|Scanned Pack QR|Product Part QR History/);

const inventoryRows = finishJobReturnInventoryRows(finalShift);
assert.equal(inventoryRows.length, 2, "Butal and product-part excess must share one summary");
assert.equal(inventoryRows[0].type, "BUTAL PACK");
assert.equal(inventoryRows[1].used, 220);
assert.equal(inventoryRows[1].scanned, 250);
assert.equal(inventoryRows[1].balance, 30);
assert.equal(inventoryRows[1].actual, 12.5);
assert.equal(inventoryRows[1].difference, -17.5);
const inventoryHtml = finishJobReturnInventoryHtml(finalShift);
assert.match(inventoryHtml, /Expected Excess/);
assert.match(inventoryHtml, /Total Scanned/);
assert.match(inventoryHtml, /12\.50 pc/);
assert.doesNotMatch(inventoryHtml, /qr_payload|raw_scan/);
const detailsHtml = finishJobDetailsHtml(finalShift);
assert.match(detailsHtml, /Supervisor One/);
assert.match(detailsHtml, /80001/);

console.log("PASS: Finish Job report shows per-shift totals and summarized excess only");
