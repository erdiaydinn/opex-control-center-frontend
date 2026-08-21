import fs from "node:fs";


function read(path) {
  return fs.readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
}

function requireText(source, text, label) {
  if (!source.includes(text)) throw new Error(`${label}: missing ${text}`);
}

const component = read("src/modules/workforce/WorkforceCommandCenter.jsx");
const boundary = read("src/modules/workforce/WorkforceBootstrapBoundary.jsx");
const api = read("src/modules/workforce/workforceCommandCenterApi.js");
const router = read("backend/app/modules/workforce/command_center_router.py");
const service = read("backend/app/modules/workforce/command_center.py");
const repository = read("backend/app/modules/workforce/command_center_repository.py");

requireText(boundary, "<WorkforceCommandCenter />", "manager surface");
requireText(api, "/workforce/command-center/", "frontend authority route");
requireText(router, "workforce.pressure.read", "read permission");
requireText(repository, "d.snapshot_fingerprint=p.demand_snapshot_fingerprint", "exact demand lineage");
requireText(repository, "c.snapshot_fingerprint=p.capacity_snapshot_fingerprint", "exact capacity lineage");
requireText(repository, "s.baseline_dpi_snapshot_fingerprint=p.snapshot_fingerprint", "coherent replan lineage");
requireText(service, '"automatic_schedule_apply_permitted": False', "human-in-loop boundary");
requireText(service, '"schedule_mutation_performed": False', "read-only boundary");
requireText(service, '"repository_or_synthetic_evidence_is_field_proof": False', "evidence truth boundary");
requireText(component, 'data?.interval?.relation === "CURRENT"', "live-label guard");
requireText(component, "action.requiresHumanApproval", "human approval UI");

if (/mock|fixture|syntheticData/i.test(component)) {
  throw new Error("Command Center UI must not ship with mock/fixture operational data");
}

console.log("Workforce Command Center contract: OK");
