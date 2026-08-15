import fs from "node:fs";
import process from "node:process";

const files = [
  "src/modules/intelligence/InsightWorkspace.jsx",
  "src/modules/intelligence/JarvisWorkspace.jsx",
];

for (const path of files) {
  const source = fs.readFileSync(path, "utf8");
  const required = [
    ["data-eay-product-state=\"loading\"", "loading product-state marker"],
    ["aria-busy=\"true\"", "loading busy semantics"],
    ["aria-live=\"polite\"", "polite async announcement"],
    ["aria-atomic=\"true\"", "atomic state announcement"],
    ["data-eay-product-state=\"error\"", "error product-state marker"],
    ["role=\"alert\"", "assertive error semantics"],
    ["data-eay-product-state=\"empty\"", "empty product-state marker"],
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
}

const insight = fs.readFileSync(files[0], "utf8");
if (!insight.includes("metrics.length === 0") || !insight.includes("metrics.length > 0")) {
  console.error("Insight must distinguish an empty authoritative metric response from a populated response.");
  process.exit(1);
}

const jarvis = fs.readFileSync(files[1], "utf8");
if (!jarvis.includes("!features.length") || !jarvis.includes("!tools.length")) {
  console.error("Jarvis must expose explicit empty states for capabilities and governed tools.");
  process.exit(1);
}

console.log("Intelligence loading/error/empty product-state contract: PASS");
