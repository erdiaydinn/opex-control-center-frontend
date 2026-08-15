import fs from "node:fs";
import process from "node:process";

const path = "src/modules/planogram/PlanogramStudio.jsx";
const source = fs.readFileSync(path, "utf8");

const required = [
  ["data-eay-product-state", "explicit product-state marker"],
  ["aria-busy", "busy semantics"],
  ["aria-live=\"polite\"", "polite async announcement"],
  ["aria-atomic=\"true\"", "atomic state announcement"],
  ["data-eay-product-state=\"error\"", "error product-state marker"],
  ["role=\"alert\"", "assertive error semantics"],
  ["data-eay-product-state=\"ready\"", "ready product-state marker"],
  ["t(\"retry\")", "localized retry action"],
];

for (const [needle, label] of required) {
  if (!source.includes(needle)) {
    console.error(`${path}: missing ${label}: ${needle}`);
    process.exit(1);
  }
}

if (/error\.message|error\.stack|JSON\.stringify\(error/.test(source)) {
  console.error(`${path}: raw error details must not be rendered into the product surface.`);
  process.exit(1);
}

if (!source.includes('/v1/planogram/readiness')) {
  console.error("Planogram readiness must remain server-authoritative.");
  process.exit(1);
}
if (!source.includes('data.production_ready?\"READY\":\"BLOCKED\"')) {
  console.error("Planogram must preserve explicit fail-closed production readiness rendering.");
  process.exit(1);
}
if (!source.includes('legacyBridgeAllowed: false')) {
  console.error("Planogram legacy bridge quarantine must remain enforced.");
  process.exit(1);
}

console.log("Planogram loading/error/ready product-state contract: PASS");
