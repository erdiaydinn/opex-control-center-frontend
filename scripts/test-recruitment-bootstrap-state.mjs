import fs from "node:fs";
import process from "node:process";

const app = fs.readFileSync("src/App.jsx", "utf8");
const boundary = fs.readFileSync("src/modules/recruitment/RecruitmentBootstrapBoundary.jsx", "utf8");
const api = fs.readFileSync("src/modules/recruitment/recruitmentApi.js", "utf8");

const requiredApp = [
  'import("./modules/recruitment/RecruitmentBootstrapBoundary.jsx")',
  '<RecruitmentBootstrapBoundary />',
];
for (const needle of requiredApp) {
  if (!app.includes(needle)) {
    console.error(`Recruitment route must remain behind authoritative bootstrap boundary: ${needle}`);
    process.exit(1);
  }
}

for (const [needle, label] of [
  ["await loadRecruitment()", "authoritative bootstrap load"],
  ["primeRecruitmentBootstrap(snapshot)", "one-shot authoritative handoff"],
  ['data-eay-product-state="loading"', "loading state marker"],
  ['aria-busy="true"', "loading busy semantics"],
  ['aria-live="polite"', "polite loading announcement"],
  ['data-eay-product-state="error"', "error state marker"],
  ['role="alert"', "assertive error semantics"],
  ['t("retry")', "localized retry action"],
  ['data-eay-product-state="ready"', "ready state marker"],
  ["<RecruitmentControl", "RecruitmentControl composition after successful bootstrap"],
  ["<RecruitmentCandidateDocumentCenter", "candidate document trust composition"],
  ["<RecruitmentOrchestrationCenter", "onboarding orchestration composition"],
  ["<RecruitmentInterviewCenter", "interview authority composition"],
  ["<RecruitmentLifecycleCenter", "governed lifecycle composition"],
]) {
  if (!boundary.includes(needle)) {
    console.error(`Recruitment bootstrap boundary missing ${label}: ${needle}`);
    process.exit(1);
  }
}

if (/error\.message|error\.stack|err\.message|JSON\.stringify\(error/.test(boundary)) {
  console.error("Recruitment bootstrap boundary must not expose raw backend errors.");
  process.exit(1);
}

if (!api.includes("let primedRecruitmentBootstrap = null") || !api.includes("primedRecruitmentBootstrap = null")) {
  console.error("Recruitment bootstrap handoff must remain one-shot and non-persistent.");
  process.exit(1);
}

console.log("Recruitment authoritative bootstrap state and governed composition contract: PASS");
