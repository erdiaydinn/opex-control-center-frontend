import React, { useMemo, useState } from "react";
import { Box, Cuboid, Footprints, Grid2X2, Rotate3D, Route, ScanLine } from "lucide-react";

import { translatePlanogramDigitalTwin } from "../../platform/i18n/planogramDigitalTwinMessages.js";
import { translatePlanogramWalkthrough } from "../../platform/i18n/planogramWalkthroughMessages.js";
import PlanogramFirstPersonWalkthrough from "./PlanogramFirstPersonWalkthrough.jsx";
import PlanogramTwinSceneRenderer from "./PlanogramTwinSceneRenderer.jsx";
import {
  buildPlanogramDigitalTwinModel,
  PLANOGRAM_DIGITAL_TWIN_LIMITS,
} from "./planogramDigitalTwinModel.js";
import {
  engineeringScaleBar,
  metricGridStep,
  rotatedRectSvgPoints,
  svgPointString,
} from "./planogramEngineering2D.js";
import { buildPlanogramUnifiedTwinScene } from "./planogramUnifiedTwinScene.js";
import { buildPlanogramVisualDeliveryPlan } from "./planogramVisualDeliveryModel.js";
import { buildPlanogramVisualQualityPlan } from "./planogramVisualQualityModel.js";
import "./planogram-digital-twin.css";
import "./planogram-scanned-twin.css";

const SVG_WIDTH = 1000;
const SVG_MAX_HEIGHT = 620;
const SVG_MIN_HEIGHT = 360;
const VISIBLE_ROUTE_PATHS = 3;
const VISIBLE_ROUTE_ROWS = 5;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function fixtureClass(type) {
  const normalized = String(type || "").toLowerCase();
  if (normalized.includes("pallet")) return "pallet";
  if (normalized.includes("frozen") || normalized.includes("freezer")) return "frozen";
  if (normalized.includes("chilled") || normalized.includes("cooler")) return "chilled";
  return "regular";
}

function architectureClass(type) {
  return String(type || "unknown").replace(/[^a-z0-9_-]/gi, "-").toLowerCase();
}

function Twin2D({ model, t, formatNumber }) {
  const ratio = model.floor.depthM / Math.max(model.floor.widthM, 0.1);
  const height = clamp(Math.round(SVG_WIDTH * ratio), SVG_MIN_HEIGHT, SVG_MAX_HEIGHT);
  const padding = 56;
  const usableWidth = SVG_WIDTH - padding * 2;
  const usableHeight = height - padding * 2;
  const scale = Math.min(
    usableWidth / Math.max(model.floor.widthM, 0.1),
    usableHeight / Math.max(model.floor.depthM, 0.1)
  );
  const offsetX = (SVG_WIDTH - model.floor.widthM * scale) / 2;
  const offsetY = (height - model.floor.depthM * scale) / 2;
  const y = (value) => offsetY + (model.floor.depthM - value) * scale;
  const projection = { offsetX, offsetY, floorDepthM: model.floor.depthM, scale };
  const routeHotspots = model.route?.available ? model.route.hotspots.slice(0, VISIBLE_ROUTE_PATHS) : [];
  const floorRightX = offsetX + model.floor.widthM * scale;
  const floorBottomY = offsetY + model.floor.depthM * scale;
  const widthDimensionY = Math.min(height - 18, floorBottomY + 24);
  const depthDimensionX = Math.max(18, offsetX - 24);
  const scaleBar = engineeringScaleBar({ floorWidthM: model.floor.widthM, scale });
  const grid = metricGridStep({ scale });
  const majorGridPixels = grid.pixels * 5;
  const scaleBarStartX = floorRightX - scaleBar.pixels;
  const scaleBarY = offsetY + 18;

  return (
    <div className="eay-twin-2d-wrap">
      <svg className="eay-twin-2d" viewBox={`0 0 ${SVG_WIDTH} ${height}`} role="img" aria-label={t("view2d")}>
        <defs>
          <pattern id="eay-twin-grid-minor" width={grid.pixels} height={grid.pixels} patternUnits="userSpaceOnUse">
            <path d={`M ${grid.pixels} 0 L 0 0 0 ${grid.pixels}`} className="eay-twin-grid-line" fill="none" vectorEffect="non-scaling-stroke" />
          </pattern>
          <pattern id="eay-twin-grid-major" width={majorGridPixels} height={majorGridPixels} patternUnits="userSpaceOnUse">
            <path d={`M ${majorGridPixels} 0 L 0 0 0 ${majorGridPixels}`} className="eay-twin-grid-line eay-twin-grid-line-major" fill="none" vectorEffect="non-scaling-stroke" />
          </pattern>
        </defs>
        <rect x={offsetX} y={offsetY} width={model.floor.widthM * scale} height={model.floor.depthM * scale} className="eay-twin-floor" />
        <rect x={offsetX} y={offsetY} width={model.floor.widthM * scale} height={model.floor.depthM * scale} fill="url(#eay-twin-grid-minor)" pointerEvents="none" />
        <rect x={offsetX} y={offsetY} width={model.floor.widthM * scale} height={model.floor.depthM * scale} fill="url(#eay-twin-grid-major)" pointerEvents="none" />

        <g className="eay-twin-engineering-dimensions" aria-hidden="true">
          <line x1={offsetX} y1={floorBottomY} x2={offsetX} y2={widthDimensionY} />
          <line x1={floorRightX} y1={floorBottomY} x2={floorRightX} y2={widthDimensionY} />
          <line x1={offsetX} y1={widthDimensionY} x2={floorRightX} y2={widthDimensionY} />
          <text x={(offsetX + floorRightX) / 2} y={widthDimensionY - 5}>{formatNumber(model.floor.widthM)} m</text>
          <line x1={offsetX} y1={offsetY} x2={depthDimensionX} y2={offsetY} />
          <line x1={offsetX} y1={floorBottomY} x2={depthDimensionX} y2={floorBottomY} />
          <line x1={depthDimensionX} y1={offsetY} x2={depthDimensionX} y2={floorBottomY} />
          <text
            x={depthDimensionX - 6}
            y={(offsetY + floorBottomY) / 2}
            transform={`rotate(-90 ${depthDimensionX - 6} ${(offsetY + floorBottomY) / 2})`}
          >{formatNumber(model.floor.depthM)} m</text>
          <line className="eay-twin-scale-bar" x1={scaleBarStartX} y1={scaleBarY} x2={floorRightX} y2={scaleBarY} />
          <line className="eay-twin-scale-tick" x1={scaleBarStartX} y1={scaleBarY - 5} x2={scaleBarStartX} y2={scaleBarY + 5} />
          <line className="eay-twin-scale-tick" x1={floorRightX} y1={scaleBarY - 5} x2={floorRightX} y2={scaleBarY + 5} />
          <text x={(scaleBarStartX + floorRightX) / 2} y={scaleBarY - 7}>{formatNumber(scaleBar.meters)} m</text>
        </g>

        {model.elements.map((element) => {
          const points = svgPointString(rotatedRectSvgPoints({
            centerXM: element.centerXM,
            centerYM: element.centerYM,
            widthM: element.widthM,
            depthM: element.depthM,
            rotationDeg: element.rotationDeg,
          }, projection));
          const clearancePoints = element.type === "emergency_exit" && element.clearanceM > 0
            ? svgPointString(rotatedRectSvgPoints({
              centerXM: element.centerXM,
              centerYM: element.centerYM,
              widthM: element.widthM + element.clearanceM * 2,
              depthM: element.depthM + element.clearanceM * 2,
              rotationDeg: element.rotationDeg,
            }, projection))
            : "";
          return (
            <g key={`element-${element.id}`} data-rotation-deg={element.rotationDeg}>
              {clearancePoints ? <polygon points={clearancePoints} className="eay-twin-egress-clearance" /> : null}
              <polygon points={points} className={`eay-twin-architecture eay-twin-architecture--${architectureClass(element.type)}`} />
              <title>{`${t("architecture")}: ${element.type} · ${element.id}`}</title>
            </g>
          );
        })}

        {routeHotspots.map((hotspot) => {
          const points = hotspot.pathM.map(([xM, yM]) => `${offsetX + xM * scale},${y(yM)}`).join(" ");
          return points ? (
            <polyline
              key={`route-${hotspot.moduleId}`}
              points={points}
              className="eay-twin-route-path"
              data-route-rank={hotspot.rank}
              vectorEffect="non-scaling-stroke"
            ><title>{`${hotspot.moduleId} · ${formatNumber(hotspot.distanceM)} m`}</title></polyline>
          ) : null;
        })}
        {model.route?.pickerEntryM ? (
          <circle
            cx={offsetX + model.route.pickerEntryM[0] * scale}
            cy={y(model.route.pickerEntryM[1])}
            r="7"
            className="eay-twin-route-origin"
            vectorEffect="non-scaling-stroke"
          />
        ) : null}

        {model.modules.map((module) => {
          const points = svgPointString(rotatedRectSvgPoints({
            centerXM: module.centerXM,
            centerYM: module.centerYM,
            widthM: module.widthM,
            depthM: module.depthM,
            rotationDeg: module.rotationDeg,
          }, projection));
          const labelX = offsetX + module.centerXM * scale;
          const labelY = y(module.centerYM);
          const visibleSize = Math.max(module.widthM * scale, module.depthM * scale);
          return (
            <g key={module.key} data-rotation-deg={module.rotationDeg}>
              <polygon
                points={points}
                className={`eay-twin-module eay-twin-module--${fixtureClass(module.fixtureType)}${module.routeHotspot ? " is-route-hotspot" : ""}`}
                data-coordinate-authority={module.coordinateAuthority}
                data-route-rank={module.routeHotspot?.rank || undefined}
              />
              {visibleSize > 54 ? <text x={labelX} y={labelY + 4} className="eay-twin-module-label">{module.aisleId} · {module.moduleId}</text> : null}
              <title>{`${module.aisleId} / ${module.moduleId} · ${t("products")}: ${formatNumber(module.productCount)}${module.routeDistanceM != null ? ` · ${formatNumber(module.routeDistanceM)} m` : ""}`}</title>
            </g>
          );
        })}
      </svg>
      <div className="eay-twin-legend" aria-label={t("fixture")}>
        <span><i className="regular" />{t("fixtureRegular")}</span>
        <span><i className="chilled" />{t("fixtureChilled")}</span>
        <span><i className="frozen" />{t("fixtureFrozen")}</span>
        <span><i className="pallet" />{t("fixturePallet")}</span>
      </div>
    </div>
  );
}

function RouteHotspots({ model, formatNumber, t }) {
  const rows = model.route?.available ? model.route.hotspots.slice(0, VISIBLE_ROUTE_ROWS) : [];
  if (!rows.length) return null;
  return (
    <section className="eay-twin-route-hotspots" aria-label={t("route")}>
      <header><Route size={16} aria-hidden="true" /><strong>{t("route")}</strong></header>
      <ol>
        {rows.map((row) => (
          <li key={row.moduleId}>
            <span className="eay-twin-route-rank">{row.rank}</span>
            <code>{row.moduleId}</code>
            <span>{formatNumber(row.distanceM)} m</span>
            <strong>Σ {formatNumber(row.weightedCost)}</strong>
          </li>
        ))}
      </ol>
    </section>
  );
}

export default function PlanogramDigitalTwin({ engineResult, candidate, locale, formatNumber }) {
  const [view, setView] = useState("2d");
  const [cameraPreset, setCameraPreset] = useState("overview");
  const t = useMemo(() => (key) => translatePlanogramDigitalTwin(locale, key), [locale]);
  const walkT = useMemo(() => (key) => translatePlanogramWalkthrough(locale, key), [locale]);
  const numberFormat = useMemo(() => {
    if (typeof formatNumber === "function") return formatNumber;
    const formatter = new Intl.NumberFormat(locale || "en");
    return (value) => formatter.format(Number(value || 0));
  }, [formatNumber, locale]);
  const model = useMemo(() => buildPlanogramDigitalTwinModel(engineResult, candidate), [candidate, engineResult]);
  const assetManifest = candidate?.asset_manifest || null;
  const visualPlan = useMemo(
    () => buildPlanogramVisualQualityPlan(model, assetManifest),
    [assetManifest, model]
  );
  const deliveryPlan = useMemo(
    () => buildPlanogramVisualDeliveryPlan(model, assetManifest, { ktx2: true, textureAtlas: true }),
    [assetManifest, model]
  );
  const sceneModel = useMemo(
    () => buildPlanogramUnifiedTwinScene({ authoredModel: model }),
    [model]
  );

  if (!model || !sceneModel) {
    return <section className="eay-twin-empty" role="status"><ScanLine size={20} aria-hidden="true" />{t("noGeometry")}</section>;
  }

  const measured = model.geometryAuthority === "measured";
  const routeText = model.route?.available ? `${numberFormat(model.route.value)} m` : t("routeUnavailable");
  const walking = cameraPreset === "walk";

  return (
    <section
      className="eay-twin"
      data-geometry-authority={model.geometryAuthority}
      data-scene-contract={sceneModel.contract}
      data-visual-quality-contract={visualPlan?.contract || "metric-fallback-only"}
      data-visual-delivery-contract={deliveryPlan?.contract || "packshot-only"}
      data-product-instance-cap={PLANOGRAM_DIGITAL_TWIN_LIMITS.maxProductInstances3d}
      data-walkthrough-active={walking ? "true" : "false"}
    >
      <header className="eay-twin-head">
        <div className="eay-twin-title"><Cuboid size={24} aria-hidden="true" /><div><h3>{t("title")}</h3><p>{t("subtitle")}</p></div></div>
        <div className="eay-twin-tabs" role="tablist" aria-label={t("title")}>
          <button type="button" role="tab" aria-selected={view === "2d"} onClick={() => setView("2d")}><Grid2X2 size={17} aria-hidden="true" />{t("view2d")}</button>
          <button type="button" role="tab" aria-selected={view === "3d"} onClick={() => setView("3d")}><Box size={17} aria-hidden="true" />{t("view3d")}</button>
        </div>
      </header>

      <div className={`eay-twin-truth ${measured ? "is-measured" : "is-topology"}`} role="status">
        <strong>{measured ? t("measured") : t("topology")}</strong>
        <span>{measured ? t("measuredHint") : t("topologyWarning")}</span>
        {model.architectureSourceRef ? <code>{model.architectureSourceRef}</code> : null}
      </div>

      <div className="eay-twin-kpis">
        <div><span>{t("modules")}</span><strong>{numberFormat(model.stats.moduleCount)}</strong></div>
        <div><span>{t("products")}</span><strong>{numberFormat(model.stats.placedProductCount)}</strong></div>
        <div><span>{t("facings")}</span><strong>{numberFormat(model.stats.facingCount)}</strong></div>
        <div><span>{t("coordinates")}</span><strong>{numberFormat(model.stats.measuredCoordinatePct)}%</strong></div>
        <div><span><Route size={15} aria-hidden="true" />{t("route")}</span><strong>{routeText}</strong></div>
      </div>
      <RouteHotspots model={model} formatNumber={numberFormat} t={t} />

      {view === "2d" ? <Twin2D model={model} t={t} formatNumber={numberFormat} /> : null}
      {view === "3d" ? <>
        <div className="eay-twin-camera-bar" aria-label={t("view3d")}>
          <button type="button" aria-pressed={cameraPreset === "overview"} onClick={() => setCameraPreset("overview")}><Rotate3D size={16} aria-hidden="true" />{t("perspective")}</button>
          <button type="button" aria-pressed={cameraPreset === "top"} onClick={() => setCameraPreset("top")}>{t("top")}</button>
          <button type="button" aria-pressed={cameraPreset === "front"} onClick={() => setCameraPreset("front")}>{t("front")}</button>
          <button type="button" aria-pressed={walking} onClick={() => setCameraPreset("walk")}><Footprints size={16} aria-hidden="true" />{walkT("walk")}</button>
          <button type="button" onClick={() => setCameraPreset("overview")}>{t("reset")}</button>
        </div>
        <div className="eay-twin-3d-shell">
          {walking ? (
            <PlanogramFirstPersonWalkthrough
              sceneModel={sceneModel}
              visualPlan={visualPlan}
              deliveryPlan={deliveryPlan}
              ariaLabel={walkT("canvasLabel")}
              loadingLabel={t("threeLoading")}
              errorLabel={t("threeError")}
            />
          ) : (
            <PlanogramTwinSceneRenderer
              sceneModel={sceneModel}
              visualPlan={visualPlan}
              deliveryPlan={deliveryPlan}
              preset={cameraPreset}
              ariaLabel={t("canvasLabel")}
              loadingLabel={t("threeLoading")}
              errorLabel={t("threeError")}
            />
          )}
        </div>
        <p className="eay-twin-interaction-hint">{walking ? walkT("hint") : t("interactionHint")}</p>
      </> : null}
    </section>
  );
}
