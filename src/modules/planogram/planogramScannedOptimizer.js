function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function safeV6RouteEvidence(value) {
  if (value == null) return true;
  if (!isPlainObject(value)) return false;
  if (value.preview_only !== true || value.production_evidence !== false) return false;
  const explained = value.explained_orders;
  if (!Array.isArray(explained) || explained.length > 3) return false;
  const serialized = JSON.stringify(explained);
  if (/"order_id"\s*:/.test(serialized)) return false;
  for (const row of explained) {
    if (!isPlainObject(row) || !String(row.basket_ref || "").startsWith("basket:")) return false;
    if (!Array.isArray(row.segments)) return false;
    for (const segment of row.segments) {
      if (!isPlainObject(segment) || !Array.isArray(segment.path_m)) return false;
      if (segment.path_m.length > 64) return false;
    }
  }
  return true;
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
    const candidateCount = Number(optimizer.candidate_count || 0);
    if (!Number.isFinite(candidateCount) || candidateCount < 0 || candidateCount > 24) return null;
    if (optimizer.candidates != null) {
      if (!Array.isArray(optimizer.candidates) || optimizer.candidates.length > 24) return null;
    }
    if (!safeV6RouteEvidence(optimizer.picker_tour_evidence_v2)) return null;
  }
  return response;
}