const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../server/server.py"), "utf8");
const start = source.indexOf("  function productCatalogSku(productId){");
const end = source.indexOf("  function jobDisplayName(row", start);
assert.ok(start >= 0 && end > start, "Dashboard SKU helpers were not found");

let productItems = [];
const firstValue = (...values) => values.find(value =>
  value !== undefined && value !== null && String(value).trim() !== ""
) ?? "";

eval(source.slice(start, end));

assert.equal(
  jobSku({job_name: "3-26-1732-2", job_code: "122669"}),
  "",
  "Job name must never be presented as the SKU",
);

const liveSession = {
  job_name: "3-26-1732-2",
  job_code: "122669",
  product_sku: "W-1714-COVER",
};
const displayedJob = {
  job_name: "3-26-1732-2",
  job_code: "122669",
};
const skuName = firstValue(jobSku(displayedJob), liveSession.product_sku, "-");
assert.equal(skuName, "W-1714-COVER");

productItems = [{id: "809", sku: "W-1714-COVER"}];
assert.equal(jobSku({product_id: "809"}), "W-1714-COVER");

console.log("PASS: dashboard SKU never falls back to the job name");
