import fs from "node:fs";
import process from "node:process";

const workflowPath = ".github/workflows/product-quality-contract.yml";
const source = fs.readFileSync(workflowPath, "utf8");
const usesPattern = /^\s*-?\s*uses:\s*([^\s#]+)(?:\s*#.*)?$/gm;
const externalUses = [];

for (const match of source.matchAll(usesPattern)) {
  const target = match[1];
  if (target.startsWith("./") || target.startsWith("docker://")) continue;
  externalUses.push(target);
}

if (!externalUses.length) {
  console.error("Product Quality workflow must declare external actions explicitly.");
  process.exit(1);
}

for (const target of externalUses) {
  const at = target.lastIndexOf("@");
  const action = at > 0 ? target.slice(0, at) : target;
  const ref = at > 0 ? target.slice(at + 1) : "";
  if (!/^[0-9a-f]{40}$/.test(ref)) {
    console.error(`${action}: external GitHub Action must be pinned to an immutable 40-character commit SHA, received ${ref || "<missing>"}`);
    process.exit(1);
  }
}

console.log(`GitHub Action pinning contract: PASS (${externalUses.length} immutable external actions)`);
