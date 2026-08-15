import fs from "node:fs";
import process from "node:process";

const app = fs.readFileSync("src/App.jsx", "utf8");
const boundary = fs.readFileSync("src/modules/workforce/WorkforceBootstrapBoundary.jsx", "utf8");

const requiredApp = [
  'lazy(() => import("./modules/workforce/WorkforceBootstrapBoundary.jsx"))',
  '<WorkforceBootstrapBoundary />',
];
for (const needle of requiredApp) {
  if (!app.includes(needle)) {
    console.error(`Workforce route must stay behind bootstrap boundary: ${needle}`);
    process.exit(1);
  }
}

const requiredBoundary = [
  'await loadAdminWorkforce()',
  'setStatus("ready")',
  'setStatus("error")',
  'data-eay-product-state="loading"',
  'aria-busy="true"',
  'aria-live="polite"',
  'aria-atomic="true"',
  'data-eay-product-state="error"',
  'role="alert"',
  't("retry")',
  'return <WorkforceControl />',
];
for (const needle of requiredBoundary) {
  if (!boundary.includes(needle)) {
    console.error(`Workforce bootstrap contract missing: ${needle}`);
    process.exit(1);
  }
}

if (/error\.message|error\.stack|JSON\.stringify\(error/.test(boundary)) {
  console.error("Workforce bootstrap boundary must never render raw backend errors.");
  process.exit(1);
}

const readyIndex = boundary.indexOf('return <WorkforceControl />');
const bootstrapIndex = boundary.indexOf('await loadAdminWorkforce()');
if (readyIndex < bootstrapIndex) {
  console.error("WorkforceControl must not render before authoritative bootstrap is attempted.");
  process.exit(1);
}

console.log("Workforce fail-closed bootstrap product-state contract: PASS");
