export const PLANOGRAM_WALKTHROUGH_NAVIGATION_CONTRACT = "eay.planogram.walkthrough-navigation.v1";
export const PLANOGRAM_WALKTHROUGH_DEFAULT_RADIUS_M = 0.3;
export const PLANOGRAM_WALKTHROUGH_DEFAULT_EYE_HEIGHT_M = 1.62;

const BLOCKING_ARCHITECTURE_TYPES = new Set([
  "wall",
  "window",
  "column",
  "no_go",
  "technical",
  "chiller",
  "freezer",
]);
const EPSILON = 1e-9;

function finite(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function rounded(value, precision = 4) {
  const factor = 10 ** precision;
  return Math.round(finite(value) * factor) / factor;
}

function normalizedObstacle(row, sourceKind) {
  return Object.freeze({
    id: String(row?.id || row?.moduleKey || `${sourceKind}-obstacle`).trim(),
    sourceKind,
    centerX: finite(row?.centerXM),
    centerY: finite(row?.centerYM),
    widthM: Math.max(0.01, finite(row?.widthM, 0.01)),
    depthM: Math.max(0.01, finite(row?.depthM, 0.01)),
    rotationDeg: finite(row?.rotationDeg),
  });
}

function pointInsideExpandedObstacle(point, obstacle, radiusM) {
  const radians = (-obstacle.rotationDeg * Math.PI) / 180;
  const dx = point.x - obstacle.centerX;
  const dy = point.y - obstacle.centerY;
  const localX = dx * Math.cos(radians) - dy * Math.sin(radians);
  const localY = dx * Math.sin(radians) + dy * Math.cos(radians);
  return Math.abs(localX) < obstacle.widthM / 2 + radiusM - EPSILON
    && Math.abs(localY) < obstacle.depthM / 2 + radiusM - EPSILON;
}

function clampToBounds(point, bounds) {
  return Object.freeze({
    x: rounded(Math.min(bounds.maxX, Math.max(bounds.minX, finite(point?.x)))),
    y: rounded(Math.min(bounds.maxY, Math.max(bounds.minY, finite(point?.y)))),
  });
}

export function isPlanogramWalkthroughPositionBlocked(navigation, point) {
  if (!navigation || !point) return true;
  const { bounds, radiusM, obstacles } = navigation;
  if (point.x < bounds.minX - EPSILON || point.x > bounds.maxX + EPSILON
    || point.y < bounds.minY - EPSILON || point.y > bounds.maxY + EPSILON) return true;
  return obstacles.some((obstacle) => pointInsideExpandedObstacle(point, obstacle, radiusM));
}

function safeStart(navigation, preferred) {
  const candidates = [];
  const clampedPreferred = clampToBounds(preferred, navigation.bounds);
  candidates.push(clampedPreferred);
  const center = clampToBounds({
    x: (navigation.bounds.minX + navigation.bounds.maxX) / 2,
    y: (navigation.bounds.minY + navigation.bounds.maxY) / 2,
  }, navigation.bounds);
  candidates.push(center);

  const offsets = [0.25, 0.5, 0.75, 1, 1.5, 2];
  for (const radius of offsets) {
    for (const [dx, dy] of [[radius, 0], [-radius, 0], [0, radius], [0, -radius], [radius, radius], [radius, -radius], [-radius, radius], [-radius, -radius]]) {
      candidates.push(clampToBounds({ x: clampedPreferred.x + dx, y: clampedPreferred.y + dy }, navigation.bounds));
    }
  }

  for (const candidate of candidates) {
    if (!isPlanogramWalkthroughPositionBlocked(navigation, candidate)) return candidate;
  }

  const step = 0.5;
  for (let y = navigation.bounds.minY; y <= navigation.bounds.maxY + EPSILON; y += step) {
    for (let x = navigation.bounds.minX; x <= navigation.bounds.maxX + EPSILON; x += step) {
      const candidate = { x: rounded(x), y: rounded(y) };
      if (!isPlanogramWalkthroughPositionBlocked(navigation, candidate)) return Object.freeze(candidate);
    }
  }
  return null;
}

export function buildPlanogramWalkthroughNavigation(sceneModel, options = {}) {
  if (!sceneModel?.floor) return null;
  const widthM = Math.max(0.5, finite(sceneModel.floor.widthM, 0.5));
  const depthM = Math.max(0.5, finite(sceneModel.floor.depthM, 0.5));
  const requestedRadius = Math.max(0.1, finite(options.radiusM, PLANOGRAM_WALKTHROUGH_DEFAULT_RADIUS_M));
  const radiusM = Math.min(requestedRadius, Math.max(0.1, Math.min(widthM, depthM) / 4));
  const bounds = Object.freeze({
    minX: rounded(radiusM),
    maxX: rounded(Math.max(radiusM, widthM - radiusM)),
    minY: rounded(radiusM),
    maxY: rounded(Math.max(radiusM, depthM - radiusM)),
  });
  const architectureObstacles = (sceneModel.architecture || [])
    .filter((row) => BLOCKING_ARCHITECTURE_TYPES.has(String(row?.type || "").toLowerCase()))
    .map((row) => normalizedObstacle(row, "architecture"));
  const fixtureObstacles = (sceneModel.fixtures || []).map((row) => normalizedObstacle(row, "fixture"));
  const pickerEntry = (sceneModel.architecture || []).find((row) => String(row?.type || "").toLowerCase() === "picker_entry");
  const navigation = {
    contract: PLANOGRAM_WALKTHROUGH_NAVIGATION_CONTRACT,
    geometryAuthority: String(sceneModel.geometryAuthority || "preview"),
    sourceKind: String(sceneModel.sourceKind || "unknown"),
    productionReleaseAllowed: false,
    radiusM: rounded(radiusM),
    eyeHeightM: rounded(Math.max(1.2, finite(options.eyeHeightM, PLANOGRAM_WALKTHROUGH_DEFAULT_EYE_HEIGHT_M))),
    bounds,
    obstacles: Object.freeze([...architectureObstacles, ...fixtureObstacles]),
  };
  const preferred = pickerEntry
    ? { x: finite(pickerEntry.centerXM), y: finite(pickerEntry.centerYM) }
    : { x: widthM / 2, y: depthM / 2 };
  const start = safeStart(navigation, preferred);
  if (!start) return null;
  return Object.freeze({ ...navigation, start });
}

export function resolvePlanogramWalkthroughStep(navigation, from, delta) {
  if (!navigation || !from || !delta) {
    return Object.freeze({ position: from || null, blocked: true, slid: false, reason: "invalid-navigation" });
  }
  const origin = clampToBounds(from, navigation.bounds);
  const requested = { x: origin.x + finite(delta.x), y: origin.y + finite(delta.y) };
  const full = clampToBounds(requested, navigation.bounds);
  const boundaryClamped = Math.abs(full.x - requested.x) > EPSILON || Math.abs(full.y - requested.y) > EPSILON;
  if (!isPlanogramWalkthroughPositionBlocked(navigation, full)) {
    return Object.freeze({
      position: full,
      blocked: boundaryClamped,
      slid: boundaryClamped,
      reason: boundaryClamped ? "floor-boundary-clamp" : "clear",
    });
  }

  const xOnly = clampToBounds({ x: origin.x + finite(delta.x), y: origin.y }, navigation.bounds);
  const yOnly = clampToBounds({ x: origin.x, y: origin.y + finite(delta.y) }, navigation.bounds);
  const axes = Math.abs(finite(delta.x)) >= Math.abs(finite(delta.y)) ? [xOnly, yOnly] : [yOnly, xOnly];
  for (const candidate of axes) {
    if ((candidate.x !== origin.x || candidate.y !== origin.y)
      && !isPlanogramWalkthroughPositionBlocked(navigation, candidate)) {
      return Object.freeze({ position: candidate, blocked: true, slid: true, reason: "collision-slide" });
    }
  }
  return Object.freeze({ position: origin, blocked: true, slid: false, reason: "collision-stop" });
}
