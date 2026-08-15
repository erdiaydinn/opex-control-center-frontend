import fs from "node:fs";
import process from "node:process";

const path = "src/modules/budget-intelligence/BudgetIntelligence.jsx";
const source = fs.readFileSync(path, "utf8");

const required = [
  ['data-eay-product-state="loading"', "loading product-state marker"],
  ['data-eay-product-state="error"', "error product-state marker"],
  ['data-eay-product-state="empty"', "empty product-state marker"],
  ['data-eay-product-state="ready"', "ready product-state marker"],
  ['aria-busy="true"', "busy semantics"],
  ['role="status"', "async status semantics"],
  ['aria-live="polite"', "polite async announcement"],
  ['aria-atomic="true"', "atomic announcement semantics"],
  ['role="alert"', "assertive error semantics"],
  ['setReloadKey(v=>v+1)', "explicit retry action"],
  ['!loading&&!apiError&&!noData', "fail-closed ready rendering"],
  ['t("loading")', "localized loading copy"],
  ['t("errorTitle")', "localized error copy"],
  ['t("retry")', "localized retry copy"],
  ['t("emptyTitle")', "localized empty copy"],
];

for (const [needle, label] of required) {
  if (!source.includes(needle)) {
    console.error(`${path}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}

if (/\.catch\(error|error\.message|error\.stack|JSON\.stringify\(error/.test(source)) {
  console.error(`${path}: raw backend error details must not be rendered into the Budget product surface.`);
  process.exit(1);
}

if (!source.includes("setData(EMPTY_DATA)") || !source.includes("setApiError(true)")) {
  console.error(`${path}: failed Budget reads must clear stale decision data and enter a fail-closed error state.`);
  process.exit(1);
}

console.log("Budget loading/error/empty/ready product-state contract: PASS");
