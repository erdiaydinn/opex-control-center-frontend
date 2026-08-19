export const AUDIT_MEDIA_STATES = Object.freeze({
  RECEIVED: "RECEIVED",
  REDACTION_REQUIRED: "REDACTION_REQUIRED",
  REDACTED: "REDACTED",
  EVIDENCE_READY: "EVIDENCE_READY",
  REJECTED: "REJECTED",
});

export const AUDIT_DECISION_STATES = Object.freeze({
  PASS: "PASS",
  FAIL: "FAIL",
  REVIEW_REQUIRED: "REVIEW_REQUIRED",
  INSUFFICIENT_EVIDENCE: "INSUFFICIENT_EVIDENCE",
  NOT_APPLICABLE: "NOT_APPLICABLE",
});

export const AUDIT_ACTION_STATES = Object.freeze({
  OPEN: "OPEN",
  IN_PROGRESS: "IN_PROGRESS",
  SUBMITTED_FOR_VERIFICATION: "SUBMITTED_FOR_VERIFICATION",
  AI_VERIFIED: "AI_VERIFIED",
  HUMAN_VERIFIED: "HUMAN_VERIFIED",
  REJECTED: "REJECTED",
  CLOSED: "CLOSED",
});

export const AUDIT_ASSURANCE_STATES = Object.freeze({
  ALIGNED: "ALIGNED",
  AUDITOR_OVERRIDE: "AUDITOR_OVERRIDE",
  MANAGER_REVIEW: "MANAGER_REVIEW",
  OPERATIONS_STANDARDS_REVIEW: "OPERATIONS_STANDARDS_REVIEW",
  RESOLVED: "RESOLVED",
});

export function canEnterAuditVisionPipeline(mediaReceipt) {
  if (!mediaReceipt || typeof mediaReceipt !== "object") return false;
  if (mediaReceipt.privacyRedactionPassed !== true) return false;
  if (!mediaReceipt.redactedMediaRef) return false;
  if (!mediaReceipt.sourceFingerprint) return false;
  if (!mediaReceipt.capturedAt) return false;
  if (!mediaReceipt.locationRef) return false;
  return mediaReceipt.state === AUDIT_MEDIA_STATES.REDACTED || mediaReceipt.state === AUDIT_MEDIA_STATES.EVIDENCE_READY;
}

export function canCloseAuditAction(action) {
  if (!action || typeof action !== "object") return false;
  const verified = action.state === AUDIT_ACTION_STATES.AI_VERIFIED || action.state === AUDIT_ACTION_STATES.HUMAN_VERIFIED;
  return verified && Boolean(action.closureEvidenceRef) && Boolean(action.verificationReceiptRef);
}

export function requiresAssuranceEscalation({ aiDecision, auditorDecision, managerDecision }) {
  if (!aiDecision || !auditorDecision || aiDecision === auditorDecision) return AUDIT_ASSURANCE_STATES.ALIGNED;
  if (!managerDecision) return AUDIT_ASSURANCE_STATES.MANAGER_REVIEW;
  if (managerDecision === auditorDecision) return AUDIT_ASSURANCE_STATES.OPERATIONS_STANDARDS_REVIEW;
  return AUDIT_ASSURANCE_STATES.RESOLVED;
}

export const AUDIT_EVIDENCE_CONTRACT = Object.freeze({
  redactionBeforeInference: true,
  faceRecognitionAllowed: false,
  rawMediaRetentionDefault: "EPHEMERAL",
  requiredProvenance: [
    "sourceFingerprint",
    "capturedAt",
    "locationRef",
    "redactedMediaRef",
    "modelOrRuleRef",
    "decision",
  ],
});
