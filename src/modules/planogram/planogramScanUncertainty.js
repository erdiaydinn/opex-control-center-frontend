export const PLANOGRAM_SCAN_UNCERTAINTY_TYPES = Object.freeze([
  "wall",
  "column",
  "door",
  "opening",
  "chiller",
  "freezer",
  "fixture",
]);

const CONFIRMABLE_TYPES = new Set(PLANOGRAM_SCAN_UNCERTAINTY_TYPES);

function finiteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

export function defaultPlanogramUncertaintyType(region) {
  const sourceType = String(region?.source_element_type || "").trim().toLowerCase();
  return CONFIRMABLE_TYPES.has(sourceType) ? sourceType : "";
}

export function isPlanogramUncertaintyChoiceComplete(region, choice) {
  const decision = String(choice?.decision || "").trim().toLowerCase();
  if (decision === "reject") return true;
  if (decision !== "confirm") return false;
  const classifiedType = String(
    choice?.classified_type || defaultPlanogramUncertaintyType(region)
  ).trim().toLowerCase();
  return CONFIRMABLE_TYPES.has(classifiedType);
}

export function isPlanogramUncertaintyReviewComplete(regions, choices) {
  const rows = Array.isArray(regions) ? regions : [];
  return rows.every((region) =>
    isPlanogramUncertaintyChoiceComplete(region, choices?.[region.element_id])
  );
}

export function buildPlanogramUncertaintyResolutions(regions, choices) {
  const rows = Array.isArray(regions) ? regions : [];
  const result = [];
  for (const region of rows) {
    const elementId = String(region?.element_id || "").trim();
    if (!elementId) continue;
    const choice = choices?.[elementId] || {};
    const decision = String(choice.decision || "").trim().toLowerCase();
    if (decision === "reject") {
      result.push(Object.freeze({ element_id: elementId, decision: "reject" }));
      continue;
    }
    if (decision !== "confirm") continue;
    const classifiedType = String(
      choice.classified_type || defaultPlanogramUncertaintyType(region)
    ).trim().toLowerCase();
    if (!CONFIRMABLE_TYPES.has(classifiedType)) continue;
    result.push(Object.freeze({
      element_id: elementId,
      decision: "confirm",
      classified_type: classifiedType,
      clearance_m: Math.max(0, Math.min(20, finiteNumber(choice.clearance_m, 0))),
    }));
  }
  return Object.freeze(result);
}
