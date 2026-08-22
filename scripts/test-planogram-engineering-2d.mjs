import fs from "node:fs";

import { SUPPORTED_LOCALES } from "../src/platform/i18n/messages.js";
import { PLANOGRAM_CAD_MESSAGES } from "../src/platform/i18n/planogramCadMessages.js";
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

const renderer = fs.readFileSync("src/modules/planogram/PlanogramDigitalTwin.jsx", "utf8");
const css = fs.readFileSync("src/modules/planogram/planogram-digital-twin.css", "utf8");
for (const [needle, label] of [
  ["rotatedRectSvgPoints", "true rotated SVG projection"],
  ["svgPointString", "polygon serialization"],
  ["<polygon points={points}", "polygon architecture/fixture rendering"],
  ["data-rotation-deg", "rotation evidence in rendered groups"],
  ["eay-twin-engineering-dimensions", "floor dimension overlay"],
  ["eay-twin-scale-bar", "engineering scale bar"],
]) {
  if (!renderer.includes(needle)) fail(`Interactive 2D renderer missing ${label}: ${needle}`);
}
if (renderer.includes("const width = element.footprintWidthM * scale")) {
  fail("Interactive Architecture V2 must not regress to AABB element rendering.");
}
if (renderer.includes("const width = Math.max(module.footprintWidthM * scale, 10)")) {
  fail("Interactive Architecture V2 must not regress to AABB fixture rendering.");
}
for (const rule of [
  ".eay-twin-engineering-dimensions line",
  ".eay-twin-engineering-dimensions text",
  ".eay-twin-scale-bar",
  ".eay-twin-scale-tick",
]) {
  if (!css.includes(rule)) fail(`Engineering 2D styling missing: ${rule}`);
}

const cad = fs.readFileSync("src/modules/planogram/PlanogramCadExport.jsx", "utf8");
const studio = fs.readFileSync("src/modules/planogram/PlanogramStudio.jsx", "utf8");
const cadCss = fs.readFileSync("src/modules/planogram/planogram-cad-export.css", "utf8");
for (const [needle, label] of [
  ["/v1/planogram/cad-preview?include_dxf=", "canonical CAD preview endpoint"],
  ["assertCadAuthorityBoundary", "client-side authority validation"],
  ["response?.preview_only !== true", "preview-only response enforcement"],
  ["response?.production_release_allowed !== false", "production release denial enforcement"],
  ["response?.installation_approval_allowed !== false", "installation denial enforcement"],
  ["drawing.production_authority !== false", "drawing production authority denial"],
  ["drawing.installation_approved !== false", "drawing installation approval denial"],
  ["canExport", "export permission gate"],
  ["optimizerMeta", "optimizer-result availability gate"],
]) {
  if (!cad.includes(needle)) fail(`CAD export boundary missing ${label}: ${needle}`);
}
if (!studio.includes("<PlanogramCadExport")) fail("Planogram Studio does not mount CAD export.");
if (!studio.includes('canAction("planogram", "export")')) {
  fail("Planogram Studio CAD export is not permission-gated.");
}
if (!cadCss.includes(".eay-planogram-cad-actions button:focus-visible")) {
  fail("CAD export focus-visible accessibility rule missing.");
}

const localeCodes = SUPPORTED_LOCALES.map((item) => item.code);
const expectedCadKeys = Object.keys(PLANOGRAM_CAD_MESSAGES.en).sort();
for (const locale of localeCodes) {
  const messages = PLANOGRAM_CAD_MESSAGES[locale];
  if (!messages) fail(`CAD export locale missing: ${locale}`);
  const keys = Object.keys(messages).sort();
  if (JSON.stringify(keys) !== JSON.stringify(expectedCadKeys)) {
    fail(`CAD export translation key drift for ${locale}.`);
  }
  for (const key of expectedCadKeys) {
    if (typeof messages[key] !== "string" || !messages[key].trim()) {
      fail(`CAD export translation missing ${locale}.${key}`);
    }
  }
}

console.log("Planogram engineering 2D, localized CAD export and authority boundary contract: PASS");
