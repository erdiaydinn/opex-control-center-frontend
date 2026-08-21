const OFFICIAL_RELEASE_STATES = new Set(["OFFICIAL_VERIFIED", "HUMAN_WITNESSED_ATTESTED"]);

export function isEvidenceMalwareCleared(evidence) {
  return evidence?.contentSafetyState === "MALWARE_CLEARED";
}

export function candidateEvidenceGate(evidence = []) {
  const items = Array.isArray(evidence) ? evidence : [];
  const unsafeCount = items.filter((item) => !isEvidenceMalwareCleared(item)).length;
  const officialUnresolvedCount = items.filter(
    (item) => item?.requiresOfficialVerification && !OFFICIAL_RELEASE_STATES.has(item?.verificationState),
  ).length;

  return {
    evidenceCount: items.length,
    unsafeCount,
    officialUnresolvedCount,
    canApprove: items.length > 0 && unsafeCount === 0 && officialUnresolvedCount === 0,
  };
}
