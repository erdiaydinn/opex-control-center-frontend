const DEG_TO_RAD = Math.PI / 180;

function finite(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function rotatedRectWorldCorners({
  centerXM,
  centerYM,
  widthM,
  depthM,
  rotationDeg = 0,
}) {
  const cx = finite(centerXM);
  const cy = finite(centerYM);
  const width = Math.max(0, finite(widthM));
  const depth = Math.max(0, finite(depthM));
  const radians = finite(rotationDeg) * DEG_TO_RAD;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  const halfWidth = width / 2;
  const halfDepth = depth / 2;

  return [
    [-halfWidth, -halfDepth],
    [halfWidth, -halfDepth],
    [halfWidth, halfDepth],
    [-halfWidth, halfDepth],
  ].map(([localX, localY]) => [
    cx + localX * cos - localY * sin,
    cy + localX * sin + localY * cos,
  ]);
}

export function worldCornersToSvgPoints(
  corners,
  { offsetX, offsetY, floorDepthM, scale }
) {
  const ox = finite(offsetX);
  const oy = finite(offsetY);
  const floorDepth = Math.max(0, finite(floorDepthM));
  const pixelsPerMeter = Math.max(0, finite(scale));
  return (corners || []).map(([xM, yM]) => [
    ox + finite(xM) * pixelsPerMeter,
    oy + (floorDepth - finite(yM)) * pixelsPerMeter,
  ]);
}

export function rotatedRectSvgPoints(rect, projection) {
  return worldCornersToSvgPoints(rotatedRectWorldCorners(rect), projection);
}

export function svgPointString(points, precision = 2) {
  return (points || [])
    .map(([x, y]) => `${finite(x).toFixed(precision)},${finite(y).toFixed(precision)}`)
    .join(" ");
}

export function engineeringScaleBar({
  floorWidthM,
  scale,
  maxPixelWidth = 150,
}) {
  const width = Math.max(0.1, finite(floorWidthM, 0.1));
  const pixelsPerMeter = Math.max(0.1, finite(scale, 0.1));
  const candidates = [20, 10, 5, 2, 1, 0.5, 0.25, 0.1];
  const floorCap = Math.max(0.1, width / 3);
  const meters = candidates.find(
    (candidate) => candidate <= floorCap && candidate * pixelsPerMeter <= maxPixelWidth
  ) || 0.1;
  return {
    meters,
    pixels: meters * pixelsPerMeter,
  };
}


export function metricGridStep({ scale, targetPixelSize = 32 }) {
  const pixelsPerMeter = finite(scale);
  const targetPixels = finite(targetPixelSize);
  if (pixelsPerMeter <= 0 || targetPixels <= 0) {
    throw new TypeError("scale and targetPixelSize must be positive finite numbers");
  }
  const rawMeters = targetPixels / pixelsPerMeter;
  const exponent = 10 ** Math.floor(Math.log10(rawMeters));
  const normalized = rawMeters / exponent;
  const multiplier = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  const meters = multiplier * exponent;
  return {
    meters,
    pixels: meters * pixelsPerMeter,
  };
}
