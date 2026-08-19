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

requireCondition(app.includes('lazy(() => import("./modules/audit/AuditCommandCenter.jsx"))'), "Audit workspace must remain lazy-loaded");
requireCondition(app.includes('path="/audit"'), "Audit route is missing");
requireCondition(app.includes('moduleKey="field_intelligence"'), "Audit foundation route must stay permission-bound");
requireCondition(catalog.includes('id: "audit"') && catalog.includes('route: "/audit"'), "Audit command-center module is missing");
requireCondition(workspace.includes('data-audit-truth-state="unbound"'), "Audit UI must expose its live-truth boundary");
requireCondition(workspace.includes("Live truth required"), "Empty KPI state must not be replaced with synthetic business metrics");
requireCondition(css.includes("prefers-reduced-motion"), "Audit experience must respect reduced motion");

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
