import fs from "node:fs";
import process from "node:process";

const path = "src/modules/academy/AcademyWorkspace.jsx";
const source = fs.readFileSync(path, "utf8");

const required = [
  ["data-eay-product-state=\"loading\"", "loading product-state marker"],
  ["aria-busy=\"true\"", "loading busy semantics"],
  ["aria-live=\"polite\"", "polite async announcement"],
  ["aria-atomic=\"true\"", "atomic state announcement"],
  ["data-eay-product-state=\"error\"", "error product-state marker"],
  ["role=\"alert\"", "assertive error semantics"],
  ["data-eay-product-state=\"empty\"", "empty product-state marker"],
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

if (!source.includes('aria-busy={loading ? "true" : "false"}')) {
  console.error("Academy main workspace must expose busy state during authoritative reloads.");
  process.exit(1);
}

console.log("Academy loading/error/empty/ready product-state contract: PASS");
