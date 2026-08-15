import fs from "node:fs";
import process from "node:process";

const path = "config/repository_intelligence_registry.json";
const registry = JSON.parse(fs.readFileSync(path, "utf8"));

if (!Array.isArray(registry.entries) || registry.entries.length === 0) {
  console.error("Repository Intelligence registry must contain cumulative entries.");
  process.exit(1);
}

const allowed = new Set(["OWN", "IMPORTED", "DISCOVERED"]);
const ids = new Set();
for (const entry of registry.entries) {
  if (!entry.id || ids.has(entry.id)) {
    console.error(`Repository Intelligence entry id must be unique and non-empty: ${entry.id || "<missing>"}`);
    process.exit(1);
  }
  ids.add(entry.id);

  if (!allowed.has(entry.classification)) {
    console.error(`${entry.id}: invalid classification ${entry.classification}`);
    process.exit(1);
  }
  for (const field of ["source", "canonical_upstream", "relation", "ref", "commit_sha", "decision", "provenance"]) {
    if (!entry[field]) {
      console.error(`${entry.id}: missing required provenance field ${field}`);
      process.exit(1);
    }
  }
  if (!entry.license || !entry.license.status) {
    console.error(`${entry.id}: license status must be explicit, including pending when unresolved.`);
    process.exit(1);
  }
  if (!Array.isArray(entry.capabilities) || entry.capabilities.length === 0) {
    console.error(`${entry.id}: capability mapping must be explicit.`);
    process.exit(1);
  }
}

const mandatorySources = [
  "erdiaydinn/opex-control-center-frontend",
  "erdiaydinn/planai-audit",
  "erdiaydinn/Adaronya",
  "council-of-high-intelligence-main.zip",
  "CL4R1T4S-main.zip",
  "computer-lab-automation-master.zip",
  "Deep-Learning-Tutorials-master.zip",
  "impeccable-main.zip",
  "image_understanding / image_understanding-tthau",
  "all previously supplied JARVIS archives",
  "apache/superset",
  "Patika-Global-Technology/superset-tr",
];

const bySource = new Map(registry.entries.map((entry) => [entry.source, entry]));
for (const source of mandatorySources) {
  if (!bySource.has(source)) {
    console.error(`Repository Intelligence registry silently dropped mandatory source: ${source}`);
    process.exit(1);
  }
}

for (const source of [
  "erdiaydinn/opex-control-center-frontend",
  "erdiaydinn/planai-audit",
  "erdiaydinn/Adaronya",
]) {
  if (bySource.get(source)?.classification !== "OWN") {
    console.error(`${source}: mandatory EAY source must remain classified OWN.`);
    process.exit(1);
  }
}

if (bySource.get("apache/superset")?.relation !== "canonical analytics/BI upstream reference") {
  console.error("apache/superset must remain the canonical analytics upstream reference.");
  process.exit(1);
}
if (bySource.get("Patika-Global-Technology/superset-tr")?.canonical_upstream !== "apache/superset") {
  console.error("superset-tr must remain derivative/reference-bound to apache/superset.");
  process.exit(1);
}

const unresolvedIdentityEntries = registry.entries.filter((entry) =>
  String(entry.canonical_upstream).startsWith("pending") || String(entry.commit_sha).startsWith("pending")
);
for (const entry of unresolvedIdentityEntries) {
  if (!String(entry.provenance).toLowerCase().includes("pending") && !String(entry.provenance).toLowerCase().includes("unresolved")) {
    console.error(`${entry.id}: unresolved identity/SHA must be explicit in provenance.`);
    process.exit(1);
  }
}

console.log(`Repository Intelligence registry contract: PASS (${registry.entries.length} cumulative entries)`);
