function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function safePlanogramScannedOptimizerPreview(response, expectedScanFingerprint) {
  const result = response?.result;
  const optimizer = result?.optimizer;
  const scannedLayout = result?.scanned_layout;
  if (!isPlainObject(response) || !isPlainObject(result)) return null;
  const expected = String(expectedScanFingerprint ?? "").trim().toLowerCase();
  const actual = String(scannedLayout?.scan_fingerprint ?? "").trim().toLowerCase();
  const requiredFalse = [
    response.store_dna_approval_allowed,
    response.physical_layout_release_allowed,
    response.production_release_allowed,
    response.installation_approval_allowed,
    response.relocation_execution_allowed,
    response.capex_approval_allowed,
    response.global_optimum_claim,
    response.field_evidence,
    result.production_authority,
    result.store_dna_authority,
    result.physical_layout_authority,
    result.installation_approved,
    result.relocation_execution_allowed,
    result.capex_approved,
    result.global_optimum_claim,
    result.field_evidence,
  ];
  if (
    response.preview_only !== true ||
    response.input_authority !== "fingerprint_bound_scanned_v2_optimizer_unattested" ||
    !expected || actual !== expected ||
    requiredFalse.some((value) => value !== false)
  ) return null;
  if (result.available && (!isPlainObject(optimizer) || optimizer.allowed !== true)) return null;
  if (optimizer) {
    for (const key of [
      "production_authority",
      "store_dna_authority",
      "installation_approved",
      "relocation_execution_allowed",
      "capex_approved",
      "global_optimum_claim",
      "field_evidence",
    ]) {
      if (optimizer[key] !== false) return null;
    }
  }
  return response;
}
