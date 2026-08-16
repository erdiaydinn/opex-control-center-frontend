import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const workflowDir = ".github/workflows";
const workflowPaths = fs
  .readdirSync(workflowDir)
  .filter((name) => name.endsWith(".yml") || name.endsWith(".yaml"))
  .sort()
  .map((name) => path.join(workflowDir, name));

if (!workflowPaths.length) {
  console.error("No GitHub Actions workflows were found for provenance validation.");
  process.exit(1);
}

const usesPattern = /^\s*-?\s*uses:\s*([^\s#]+)(?:\s*#.*)?$/gm;
const externalUses = [];

for (const workflowPath of workflowPaths) {
  const source = fs.readFileSync(workflowPath, "utf8");
  for (const match of source.matchAll(usesPattern)) {
    const target = match[1];
    if (target.startsWith("./") || target.startsWith("docker://")) continue;
    externalUses.push({ workflowPath, target });
  }
}

if (!externalUses.length) {
  console.error("Repository workflows must declare external actions explicitly.");
  process.exit(1);
}

const violations = [];
for (const { workflowPath, target } of externalUses) {
  const at = target.lastIndexOf("@");
  const action = at > 0 ? target.slice(0, at) : target;
  const ref = at > 0 ? target.slice(at + 1) : "";
  if (!/^[0-9a-f]{40}$/.test(ref)) {
    violations.push(
      `${workflowPath}: ${action} must be pinned to an immutable 40-character commit SHA, received ${ref || "<missing>"}`,
    );
  }
}

if (violations.length) {
  for (const violation of violations) console.error(violation);
  console.error(
    `GitHub Action pinning contract: FAIL (${violations.length} mutable external action reference(s))`,
  );
  process.exit(1);
}

console.log(
  `GitHub Action pinning contract: PASS (${externalUses.length} immutable external actions across ${workflowPaths.length} workflows)`,
);
