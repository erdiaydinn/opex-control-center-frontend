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
const assuranceWorkspace = fs.readFileSync("src/modules/audit/AuditAssuranceWorkspace.jsx", "utf8");
const actionsWorkspace = fs.readFileSync("src/modules/audit/AuditActionsWorkspace.jsx", "utf8");
const evidenceWorkspace = fs.readFileSync("src/modules/audit/AuditEvidenceWorkspace.jsx", "utf8");
const css = fs.readFileSync("src/modules/audit/AuditCommandCenter.css", "utf8");
const liveCss = fs.readFileSync("src/modules/audit/AuditLiveTruth.css", "utf8");
const assuranceCss = fs.readFileSync("src/modules/audit/AuditAssuranceWorkspace.css", "utf8");
const permissions = fs.readFileSync("services/core-api/app/core/permission_catalog.py", "utf8");
const routes = fs.readFileSync("services/core-api/app/modules/audit/routes.py", "utf8");
const evidenceRoutes = fs.readFileSync("services/core-api/app/modules/audit/evidence_object_routes.py", "utf8");
const intelligenceRoutes = fs.readFileSync("services/core-api/app/modules/audit/intelligence_routes.py", "utf8");
const intelligenceAuthority = fs.readFileSync("services/core-api/app/modules/audit/intelligence.py", "utf8");
const assuranceAuthority = fs.readFileSync("services/core-api/app/modules/audit/assurance.py", "utf8");
const accountabilityAuthority = fs.readFileSync("services/core-api/app/modules/audit/accountability.py", "utf8");
const runAuthority = fs.readFileSync("services/core-api/app/modules/audit/run_authority.py", "utf8");
const schemas = fs.readFileSync("services/core-api/app/modules/audit/schemas.py", "utf8");
const resourceScope = fs.readFileSync("services/core-api/app/modules/audit/resource_scope.py", "utf8");
const budgetMain = fs.readFileSync("services/core-api/app/budget_main.py", "utf8");
const migration = fs.readFileSync("services/core-api/alembic/versions/0046_audit_operating_system.py", "utf8");
const privacyMigration = fs.readFileSync("services/core-api/alembic/versions/0047_audit_privacy_verification.py", "utf8");
const assuranceMigration = fs.readFileSync("services/core-api/alembic/versions/0048_audit_assurance_routing.py", "utf8");
const accountabilityMigration = fs.readFileSync("services/core-api/alembic/versions/0049_audit_location_accountability.py", "utf8");

requireCondition(app.includes('lazy(() => import("./modules/audit/AuditCommandCenter.jsx"))'), "Audit workspace must remain lazy-loaded");
requireCondition(app.includes('path="/audit"'), "Audit route is missing");
requireCondition(app.includes('<ProtectedRoute moduleKey="audit">'), "Audit route must use dedicated central authorization");
requireCondition(catalog.includes('id: "audit", moduleKey: "audit"') && catalog.includes('route: "/audit"'), "Audit command-center module must use the dedicated audit permission");
requireCondition(permissions.includes('"audit"') && permissions.includes('module_permission("audit")'), "Server permission catalog must know the Audit module");
requireCondition(permissions.includes('"audit_auditor"') && permissions.includes('"audit_manager"') && permissions.includes('"audit_standards"'), "Audit role policy is incomplete");
requireCondition(migration.includes('revision: str = "0046_audit_operating_system"'), "Audit authority migration is missing");
requireCondition(migration.includes('"audit_redaction_receipts"'), "Audit privacy receipt authority is missing");
requireCondition(migration.includes('"audit_item_decision_events"'), "Audit decision history authority is missing");
requireCondition(migration.includes('"audit_assurance_reviews"'), "Audit assurance history authority is missing");
requireCondition(migration.includes('processed_frame_count = frame_count'), "Video redaction coverage must fail closed in the database");
requireCondition(privacyMigration.includes('"audit_redaction_verification_events"'), "Server privacy-verification authority is missing");
requireCondition(assuranceMigration.includes('revision: str = "0048_audit_assurance_routing"'), "Current-state assurance routing migration is missing");
requireCondition(assuranceMigration.includes('"audit_assurance_cases"'), "Assurance current-state authority is missing");
requireCondition(assuranceMigration.includes("MANAGER_UNASSIGNED") && assuranceMigration.includes("OPERATIONS_STANDARDS_UNASSIGNED"), "Missing assurance owners must fail visibly closed");
requireCondition(accountabilityMigration.includes('revision: str = "0049_audit_location_accountability"'), "Audit location accountability migration is missing");
requireCondition(accountabilityMigration.includes("audit_location_manager_assignments"), "Location-manager authority is missing");
requireCondition(accountabilityMigration.includes("REVOKE DELETE ON TABLE audit_location_manager_assignments"), "Manager accountability must not be silently deleted");

requireCondition(workspace.includes('apiGet("/v1/audit/programs")'), "Desktop Audit must read authoritative program truth");
requireCondition(workspace.includes('apiGet("/v1/audit/runs?limit=100")'), "Desktop Audit must read authoritative run truth");
requireCondition(workspace.includes('apiPost("/v1/audit/runs"'), "Desktop Audit must start an audit through server authority");
requireCondition(workspace.includes('canAction("audit", "startAudit")'), "Start Audit UI must honor central action permission");
requireCondition(!workspace.includes("manager_subject:"), "Start Audit UI must not supply manager authority");
requireCondition(workspace.includes('apiFetchWithStatus("/v1/audit/intelligence/summary"'), "Desktop Audit must read the deterministic intelligence receipt");
requireCondition(workspace.includes('payload?.llm_computed_metrics !== false'), "Desktop Audit must reject an intelligence payload that does not prove deterministic metrics");
requireCondition(workspace.includes("<AuditAssuranceWorkspace"), "Desktop Audit must compose the live assurance workspace");
requireCondition(workspace.includes("<AuditActionsWorkspace"), "Desktop Audit must compose the executable Actions workspace");
requireCondition(workspace.includes("<AuditEvidenceWorkspace"), "Desktop Audit must compose the controlled private-evidence handoff");
requireCondition(actionsWorkspace.includes('apiGet("/v1/audit/actions?limit=200")'), "Actions workspace must read server-authoritative actions");
requireCondition(actionsWorkspace.includes("expected_version: selected.version"), "Action mutation must preserve optimistic version authority");
requireCondition(actionsWorkspace.includes("closure_evidence_ref:"), "Action closure must submit an evidence reference");
requireCondition(actionsWorkspace.includes("verification_receipt_ref:"), "Verified closure must submit a verification receipt reference");
requireCondition(actionsWorkspace.includes("origin_field"), "Action detail must expose its governed original question context");
requireCondition(!actionsWorkspace.includes("assignee_subject:"), "Action UI must not spoof assignee identity while advancing state");
requireCondition(evidenceWorkspace.includes('"X-EAY-Content-SHA256"'), "Evidence handoff must hash-bind uploaded bytes");
requireCondition(evidenceWorkspace.includes("client_submission_id="), "Evidence handoff must use an idempotent client submission identity");
requireCondition(evidenceWorkspace.includes("field_evidence_receipt_id:"), "Redaction claim must bind a server-issued private receipt");
requireCondition(evidenceWorkspace.includes('file.type === "image/jpeg"'), "Unsupported media must fail closed before upload");
requireCondition(evidenceWorkspace.includes("canonicalFrames") && evidenceWorkspace.includes("processedFrames"), "Guided evidence must expose complete canonical-frame redaction coverage");
requireCondition(evidenceWorkspace.includes('t("privacyHold")'), "Client binding must remain visibly held pending server privacy authority");
requireCondition(!evidenceWorkspace.includes("public_url"), "Evidence UI must not mint or consume public evidence URLs");
requireCondition(workspace.includes('data-audit-truth-state={live.state}'), "Audit UI must expose live truth state without inventing connection");
requireCondition(workspace.includes('data-audit-intelligence-state={intelligence.state}'), "Audit UI must expose intelligence connection state");
requireCondition(workspace.includes('t("noLiveData")'), "Empty KPI state must remain localized and truth-bound rather than synthetic");
requireCondition(workspace.includes('state: "error", programs: [], runs: []'), "Audit live-data failure must fail visibly closed");
requireCondition(css.includes("prefers-reduced-motion") && liveCss.includes("prefers-reduced-motion") && assuranceCss.includes("prefers-reduced-motion"), "Audit experience must respect reduced motion");

requireCondition(assuranceWorkspace.includes('apiGet("/v1/audit/assurance/cases?limit=200")'), "Assurance UI must read current cases from server authority");
requireCondition(assuranceWorkspace.includes('apiGet("/v1/audit/assurance/auditors")'), "Auditor calibration must be server-derived");
requireCondition(assuranceWorkspace.includes("selectedCase.manager_subject === user?.subject"), "Manager decisions must be hidden unless the current actor is the assigned manager");
requireCondition(assuranceWorkspace.includes('canAction("audit", "reviewDisagreement")'), "Manager UI must honor central action permission");
requireCondition(assuranceWorkspace.includes('canAction("audit", "manageStandards")'), "Standards UI must honor central action permission");
requireCondition(assuranceWorkspace.includes("/manager-decision") && assuranceWorkspace.includes("/standards-decision"), "Assurance decisions must use governed server endpoints");
requireCondition(!assuranceWorkspace.includes("Math.random"), "Assurance workspace must not synthesize data");

requireCondition(routes.includes("await _require_run_scope(principal, scope, audit_run_id)"), "Run-scoped Audit writes must enforce resource authorization");
requireCondition(routes.includes("await _require_action_scope(principal, scope, action_id)"), "Action updates must enforce resource authorization");
requireCondition(routes.includes('@router.get("/actions")'), "Audit must expose a scoped Actions list endpoint");
requireCondition(routes.includes('@router.get("/actions/{action_id}")'), "Audit must expose a scoped Action detail endpoint");
requireCondition(routes.includes("await _require_assurance_case_scope(principal, scope, case_id)"), "Assurance decisions must enforce resource authorization");
requireCondition(routes.includes("start_authoritative_run"), "Audit run creation must use server-authoritative accountability");
requireCondition(routes.includes('"action:audit:manageLocations"') && routes.includes('"/locations/{location_id}/manager-assignment"'), "Manager assignment must use governed location administration");
requireCondition(resourceScope.includes("JOIN audit_runs ar") && resourceScope.includes("JOIN field_locations fl"), "Audit resource scope must resolve from DB authority");
requireCondition(routes.includes('detail="Public action endpoint cannot assert AI verification authority"'), "Public humans must not spoof AI verification authority");
requireCondition(routes.includes('"action:audit:manageStandards"') && !routes.includes('"audit_standards" not in principal.roles'), "Standards escalation must use canonical permissions, not hard-coded route role names");
requireCondition(assuranceAuthority.includes("platform_notification_outbox"), "Assurance routing must reuse the shared notification outbox");
requireCondition(assuranceAuthority.includes("membership_roles") && assuranceAuthority.includes("r.key = 'audit_standards'"), "Operations Standards routing must resolve current canonical membership authority");
requireCondition(assuranceAuthority.includes("run.auditor_subject != actor_subject"), "Auditors must not decide another auditor's run through the assurance path");
requireCondition(accountabilityAuthority.includes("m.status = 'active'") && accountabilityAuthority.includes("r.key = 'audit_manager'"), "Location manager must resolve from an active canonical Audit Manager membership");
requireCondition(runAuthority.includes("resolve_location_manager_subject") && runAuthority.includes('"manager_subject": manager_subject'), "Audit run must snapshot server-resolved manager identity");
requireCondition(!runAuthority.includes("payload.manager_subject"), "Audit run authority must never trust caller manager identity");
requireCondition(schemas.includes("manager_subject: None = None"), "Legacy manager field must remain null-only to reject spoofed identities");

requireCondition(intelligenceRoutes.includes('prefix="/v1/audit/intelligence"'), "Audit deterministic intelligence route is missing");
requireCondition(intelligenceRoutes.includes('require_audit_scope(principal, "feature:audit:analytics")'), "Audit intelligence must use analytics scope");
requireCondition(intelligenceAuthority.includes('"llm_computed_metrics": False'), "Audit metrics must not be computed by an LLM");
requireCondition(intelligenceAuthority.includes('"calculation_version": "audit.intelligence.summary.v2"'), "Audit metric calculation version is missing");
requireCondition(intelligenceAuthority.includes("official_compliance_eligible IS TRUE") && intelligenceAuthority.includes('"official_compliance_only": True') && intelligenceAuthority.includes('"non_official_score_modes": ["FOCUS_SCORE"]'), "Audit intelligence must fence official compliance from focus visit scores");
requireCondition(intelligenceAuthority.includes("COUNT(DISTINCT aa.audit_run_id) >= 2"), "Repeat finding calculation must require multiple runs");
requireCondition(intelligenceAuthority.includes("verification_status = 'verified'"), "Evidence coverage must require server privacy verification");
requireCondition(intelligenceAuthority.includes("receipt_fingerprint"), "Audit intelligence must produce a fingerprinted receipt");

requireCondition(evidenceRoutes.includes('prefix="/v1/audit"'), "Audit private evidence route is missing");
requireCondition(evidenceRoutes.includes('require_audit_scope(principal, "action:audit:submitEvidence")'), "Audit evidence upload must use submitEvidence scope");
requireCondition(evidenceRoutes.includes("scope_allows_location"), "Audit evidence upload must reuse canonical Audit scope mapping");
requireCondition(evidenceRoutes.includes("ar.field_mission_id") && evidenceRoutes.includes("ar.location_id"), "Audit evidence upload must derive mission/location from server run authority");
requireCondition(evidenceRoutes.includes("upload_private_evidence_object"), "Audit evidence upload must reuse the private Field evidence store authority");
requireCondition(evidenceRoutes.includes('"client_redaction_claim_only": True'), "Client redaction must remain a claim until server verification");
requireCondition(evidenceRoutes.includes('"server_privacy_verified": False') && evidenceRoutes.includes('"vision_inference_authorized": False'), "Storage receipt must not authorize vision inference");
requireCondition(evidenceRoutes.includes('"public_url": None'), "Audit evidence must not expose a public URL");
requireCondition(budgetMain.includes("audit_evidence_object_router") && budgetMain.includes("app.include_router(audit_evidence_object_router)"), "Audit evidence router must be composed into Platform Core ASGI");

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
