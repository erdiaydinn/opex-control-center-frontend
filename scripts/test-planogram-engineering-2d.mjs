import {
  engineeringScaleBar,
  rotatedRectSvgPoints,
  rotatedRectWorldCorners,
  svgPointString,
} from "../src/modules/planogram/planogramEngineering2D.js";

function fail(message) {
  console.error(message);
  process.exit(1);
}

function closeTo(actual, expected, tolerance = 1e-6) {
  return Math.abs(actual - expected) <= tolerance;
}

const corners = rotatedRectWorldCorners({
  centerXM: 6,
  centerYM: 3.1,
  widthM: 2,
  depthM: 0.2,
  rotationDeg: 17,
});
if (corners.length !== 4) fail("Rotated rectangle must preserve four physical corners.");

const xs = corners.map(([x]) => x);
const ys = corners.map(([, y]) => y);
const width = Math.max(...xs) - Math.min(...xs);
const depth = Math.max(...ys) - Math.min(...ys);
const radians = (17 * Math.PI) / 180;
const expectedWidth = 2 * Math.abs(Math.cos(radians)) + 0.2 * Math.abs(Math.sin(radians));
const expectedDepth = 2 * Math.abs(Math.sin(radians)) + 0.2 * Math.abs(Math.cos(radians));
if (!closeTo(width, expectedWidth) || !closeTo(depth, expectedDepth)) {
  fail("17-degree engineering polygon does not match oriented physical geometry.");
}

const projected = rotatedRectSvgPoints(
  { centerXM: 6, centerYM: 3.1, widthM: 2, depthM: 0.2, rotationDeg: 17 },
  { offsetX: 20, offsetY: 30, floorDepthM: 8, scale: 50 }
);
if (projected.length !== 4) fail("SVG projection dropped rotated corners.");
if (new Set(projected.map(([, y]) => y.toFixed(4))).size < 3) {
  fail("17-degree wall collapsed back into an axis-aligned SVG rectangle.");
}
const pointString = svgPointString(projected);
if (pointString.split(" ").length !== 4) fail("SVG polygon point serialization drifted.");

const orthogonal = rotatedRectWorldCorners({
  centerXM: 1,
  centerYM: 1,
  widthM: 2,
  depthM: 1,
  rotationDeg: 90,
});
const orthogonalXs = orthogonal.map(([x]) => x);
const orthogonalYs = orthogonal.map(([, y]) => y);
if (!closeTo(Math.max(...orthogonalXs) - Math.min(...orthogonalXs), 1)) {
  fail("90-degree engineering geometry no longer swaps width exactly.");
}
if (!closeTo(Math.max(...orthogonalYs) - Math.min(...orthogonalYs), 2)) {
  fail("90-degree engineering geometry no longer swaps depth exactly.");
}

const bar = engineeringScaleBar({ floorWidthM: 12, scale: 60 });
if (!(bar.meters > 0 && bar.pixels > 0 && bar.pixels <= 150)) {
  fail("Engineering scale bar must be visible and bounded.");
}

console.log("Planogram engineering 2D arbitrary-angle geometry and scale contract: PASS");
