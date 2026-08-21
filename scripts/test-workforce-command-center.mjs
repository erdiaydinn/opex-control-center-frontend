import fs from "node:fs";

import { workforceCommandCenterMessage } from "../src/platform/i18n/workforceCommandCenterMessages.js";


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

const actionCodes = [
  "AUTHORITY_INTERVAL_NOT_CURRENT",
  "SCHEDULE_SNAPSHOT_DRIFT",
  "CAPACITY_SHORTAGE",
  "SKILL_DEFICIT",
  "NO_SHOW",
  "DAILY_LIMIT_BREACH",
  "REST_RULE_BREACH",
  "KPI_PRESSURE",
  "PENDING_REPLAN",
  "PENDING_SHIFT_TRADE",
];
const localizedLocales = ["de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
for (const locale of localizedLocales) {
  for (const code of actionCodes) {
    for (const suffix of ["TITLE", "DETAIL"]) {
      const key = `${code}_${suffix}`;
      const params = { count: 7, minutes: 15, time: "10:30" };
      const localized = workforceCommandCenterMessage(locale, key, params);
      const english = workforceCommandCenterMessage("en", key, params);
      if (!localized || localized === key) {
        throw new Error(`Command Center ${locale}: missing ${key}`);
      }
      if (localized === english) {
        throw new Error(`Command Center ${locale}: ${key} still falls back to English`);
      }
      if (localized.includes("{count}")) {
        throw new Error(`Command Center ${locale}: ${key} did not format count placeholder`);
      }
    }
  }
}

if (/mock|fixture|syntheticData/i.test(component)) {
  throw new Error("Command Center UI must not ship with mock/fixture operational data");
}

console.log("Workforce Command Center contract: OK");
