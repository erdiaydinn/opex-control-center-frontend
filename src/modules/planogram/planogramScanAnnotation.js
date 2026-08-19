const TOOL_DEFAULTS = Object.freeze({
  picker_entry: { widthM: 0.4, depthM: 0.4 },
  picker_exit: { widthM: 0.4, depthM: 0.4 },
  inbound: { widthM: 1.5, depthM: 1.5 },
  dispatch: { widthM: 1.5, depthM: 1.5 },
  no_go: { widthM: 1, depthM: 1 },
  technical: { widthM: 1, depthM: 1 },
  emergency_exit: { widthM: 1, depthM: 0.3 },
});

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function annotationToolDefaults(tool) {
  return TOOL_DEFAULTS[tool] || TOOL_DEFAULTS.no_go;
}

export function safePlanogramScanAnnotationPreview(response, expectedFingerprint) {
  const result = response?.result;
  if (!isPlainObject(response) || !isPlainObject(result)) return null;
  const expected = String(expectedFingerprint || "").trim().toLowerCase();
  const actual = String(result.scan_fingerprint || "").trim().toLowerCase();
  const requiredFalse = [
    response.store_dna_approval_allowed,
    response.production_release_allowed,
    response.installation_approval_allowed,
    result.store_dna_authority,
    result.maker_checker_approved,
    result.production_authority,
    result.installation_approval_allowed,
    result.auto_store_dna_promotion_allowed,
  ];
  if (
    response.preview_only !== true ||
    response.input_authority !== "fingerprint_bound_human_review_unattested" ||
    !expected || actual !== expected ||
    requiredFalse.some((value) => value !== false)
  ) {
    return null;
  }
  return response;
}

export const PLANOGRAM_SCAN_ANNOTATION_TOOLS = Object.freeze(Object.keys(TOOL_DEFAULTS));
