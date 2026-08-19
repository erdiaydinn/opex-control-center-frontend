import fs from "node:fs";
import { auditMessageCoverage } from "../src/modules/audit/auditMessages.js";
import {
  AUDIT_ACTION_STATES,
  AUDIT_ASSURANCE_STATES,
  AUDIT_MEDIA_STATES,
  canCloseAuditAction,
  canEnterAuditVisionPipeline,
  requiresAssuranceEscalation,
} from "../src/modules/audit/auditContracts.js";

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

const app = fs.readFileSync("src/App.jsx", "utf8");
const catalog = fs.readFileSync("src/modules/control-center/commandCenterModules.js", "utf8");
const workspace = fs.readFileSync("src/modules/audit/AuditCommandCenter.jsx", "utf8");
const css = fs.readFileSync("src/modules/audit/AuditCommandCenter.css", "utf8");
const liveCss = fs.readFileSync("src/modules/audit/AuditLiveTruth.css", "utf8");
const permissions = fs.readFileSync("services/core-api/app/core/permission_catalog.py", "utf8");
const routes = fs.readFileSync("services/core-api/app/modules/audit/routes.py", "utf8");
const resourceScope = fs.readFileSync("services/core-api/app/modules/audit/resource_scope.py", "utf8");
const migration = fs.readFileSync("services/core-api/alembic/versions/0046_audit_operating_system.py", "utf8");
const privacyMigration = fs.readFileSync("services/core-api/alembic/versions/0047_audit_privacy_verification.py", "utf8");

requireCondition(app.includes('lazy(() => import("./modules/audit/AuditCommandCenter.jsx"))'), "Audit workspace must remain lazy-loaded");
requireCondition(app.includes('path="/audit"'), "Audit route is missing");
requireCondition(app.includes('<ProtectedRoute moduleKey="audit">'), "Audit route must use dedicated central authorization");
requireCondition(catalog.includes('id: "audit", moduleKey: "audit"') && catalog.includes('route: "/audit"'), "Audit command-center module must use the dedicated audit permission");
requireCondition(permissions.includes('"audit"') && permissions.includes('module_permission("audit")'), "Server permission catalog must know the Audit module");
requireCondition(permissions.includes('"audit_auditor"') && permissions.includes('"audit_manager"') && permissions.includes('"audit_standards"'), "Audit role policy is incomplete");
requireCondition(migration.includes('revision: str = "0046_audit_operating_system"'), "Audit authority migration is missing");
requireCondition(migration.includes('"audit_redaction_receipts"'), "Audit privacy receipt authority is missing");
requireCondition(migration.includes('"audit_item_decision_events"'), "Audit decision history authority is missing");
requireCondition(migration.includes('"audit_assurance_reviews"'), "Audit assurance authority is missing");
requireCondition(migration.includes('processed_frame_count = frame_count'), "Video redaction coverage must fail closed in the database");
requireCondition(privacyMigration.includes('"audit_redaction_verification_events"'), "Server privacy-verification authority is missing");

requireCondition(workspace.includes('apiGet("/v1/audit/programs")'), "Desktop Audit must read authoritative program truth");
requireCondition(workspace.includes('apiGet("/v1/audit/runs?limit=100")'), "Desktop Audit must read authoritative run truth");
requireCondition(workspace.includes('data-audit-truth-state={live.state}'), "Audit UI must expose live truth state without inventing connection");
requireCondition(workspace.includes('t("noLiveData")'), "Empty KPI state must remain localized and truth-bound rather than synthetic");
requireCondition(workspace.includes('state: "error", programs: [], runs: []'), "Audit live-data failure must fail visibly closed");
requireCondition(css.includes("prefers-reduced-motion") && liveCss.includes("prefers-reduced-motion"), "Audit experience must respect reduced motion");

requireCondition(routes.includes("await _require_run_scope(principal, scope, audit_run_id)"), "Run-scoped Audit writes must enforce resource authorization");
requireCondition(routes.includes("await _require_action_scope(principal, scope, action_id)"), "Action updates must enforce resource authorization");
requireCondition(resourceScope.includes("JOIN audit_runs ar") && resourceScope.includes("JOIN field_locations fl"), "Audit resource scope must resolve from DB authority");
requireCondition(routes.includes('detail="Public action endpoint cannot assert AI verification authority"'), "Public humans must not spoof AI verification authority");
requireCondition(routes.includes('"action:audit:manageStandards"') && !routes.includes('"audit_standards" not in principal.roles'), "Standards escalation must use canonical permissions, not hard-coded role names");

const locales = ["tr", "en", "de", "ar", "fr", "es", "it", "nl", "pl", "pt-BR"];
const coverage = auditMessageCoverage(locales);
for (const locale of locales) {
  requireCondition((coverage.missing[locale] || []).length === 0, `Audit translations missing for ${locale}`);
  requireCondition((coverage.extra[locale] || []).length === 0, `Audit translation key drift for ${locale}`);
}

requireCondition(!canEnterAuditVisionPipeline(null), "Missing media receipt must fail closed");
requireCondition(!canEnterAuditVisionPipeline({ state: AUDIT_MEDIA_STATES.RECEIVED }), "Raw media must not enter audit vision");
requireCondition(canEnterAuditVisionPipeline({
  state: AUDIT_MEDIA_STATES.REDACTED,
  privacyRedactionPassed: true,
  redactedMediaRef: "media:redacted:1",
  sourceFingerprint: "sha256:source",
  capturedAt: "2026-08-19T19:48:00+03:00",
  locationRef: "location:test",
}), "Complete redaction receipt should admit governed vision inference");

requireCondition(!canCloseAuditAction({ state: AUDIT_ACTION_STATES.IN_PROGRESS }), "In-progress action cannot close");
requireCondition(canCloseAuditAction({
  state: AUDIT_ACTION_STATES.AI_VERIFIED,
  closureEvidenceRef: "evidence:closure:1",
  verificationReceiptRef: "receipt:verification:1",
}), "Verified closure evidence should permit close transition");

requireCondition(requiresAssuranceEscalation({ aiDecision: "FAIL", auditorDecision: "PASS" }) === AUDIT_ASSURANCE_STATES.MANAGER_REVIEW, "AI-auditor disagreement must route to manager review");
requireCondition(requiresAssuranceEscalation({ aiDecision: "FAIL", auditorDecision: "PASS", managerDecision: "PASS" }) === AUDIT_ASSURANCE_STATES.OPERATIONS_STANDARDS_REVIEW, "Manager-backed auditor override must route to Operations Standards");

console.log("EAY Audit product-state contracts: PASS");
