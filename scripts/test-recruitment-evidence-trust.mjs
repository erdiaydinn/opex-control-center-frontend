import assert from "node:assert/strict";
import { candidateEvidenceGate, isEvidenceMalwareCleared } from "../src/modules/recruitment/recruitmentEvidenceTrust.js";

const clean = { contentSafetyState: "MALWARE_CLEARED", requiresOfficialVerification: false, verificationState: "NOT_REQUIRED" };
assert.equal(isEvidenceMalwareCleared(clean), true);
for (const state of [undefined, "STATIC_FORMAT_ACCEPTED_AV_PENDING", "MALWARE_DETECTED", "SCAN_FAILED"]) {
  assert.equal(isEvidenceMalwareCleared({ contentSafetyState: state }), false, `${state} must fail closed`);
}
assert.equal(candidateEvidenceGate([]).canApprove, false, "empty evidence must not release approval");
assert.equal(candidateEvidenceGate([clean]).canApprove, true);
assert.equal(candidateEvidenceGate([{ ...clean, contentSafetyState: "SCAN_FAILED" }]).canApprove, false);
assert.equal(candidateEvidenceGate([{ ...clean, requiresOfficialVerification: true, verificationState: "BARCODE_EXTRACTION_PENDING" }]).canApprove, false);
assert.equal(candidateEvidenceGate([{ ...clean, requiresOfficialVerification: true, verificationState: "OFFICIAL_VERIFIED" }]).canApprove, true);
assert.equal(candidateEvidenceGate([{ ...clean, requiresOfficialVerification: true, verificationState: "HUMAN_WITNESSED_ATTESTED" }]).canApprove, true);

console.log("Recruitment evidence trust contract: PASS");
