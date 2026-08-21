import React, { useCallback, useMemo, useRef, useState } from "react";
import { FileScan, ScanLine, ShieldCheck, TriangleAlert } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translatePlanogramStoreScan } from "../../platform/i18n/planogramStoreScanMessages.js";
import { rotatedRectSvgPoints, svgPointString } from "./planogramEngineering2D.js";
import PlanogramScanAnnotationWorkspace from "./PlanogramScanAnnotationWorkspace.jsx";
import {
  normalizePlanogramStoreScanBundle,
  safePlanogramStoreScanPreview,
} from "./planogramStoreScanBundle.js";
import "./planogram-store-scan.css";

const MAX_SCAN_FILE_BYTES = 8 * 1024 * 1024;
const SVG_WIDTH = 920;
const SVG_HEIGHT = 520;

function ScanGeometryPreview({ scan, t }) {
  const architecture = scan?.architecture_v2_preview;
  if (!architecture?.elements?.length) return null;
  const padding = 38;
  const scale = Math.min(
    (SVG_WIDTH - padding * 2) / architecture.floor_width_m,
    (SVG_HEIGHT - padding * 2) / architecture.floor_depth_m
  );
  const projection = {
    offsetX: (SVG_WIDTH - architecture.floor_width_m * scale) / 2,
    offsetY: (SVG_HEIGHT - architecture.floor_depth_m * scale) / 2,
    floorDepthM: architecture.floor_depth_m,
    scale,
  };
  const architectureIds = new Set(
    architecture.elements.map((element) => String(element.element_id || ""))
  );
  const fixtureRows = Array.isArray(scan.recognized_fixtures)
    ? scan.recognized_fixtures.filter(
        (fixture) => !architectureIds.has(String(fixture.element_id || ""))
      )
    : [];

  return (
    <div className="eay-store-scan-geometry">
      <strong>{t("geometryPreview")}</strong>
      <svg viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`} role="img" aria-label={t("geometryPreview")}>
        <rect
          x={projection.offsetX}
          y={projection.offsetY}
          width={architecture.floor_width_m * scale}
          height={architecture.floor_depth_m * scale}
          className="eay-store-scan-floor"
        />
        {architecture.elements.map((element) => (
          <polygon
            key={element.element_id}
            points={svgPointString(rotatedRectSvgPoints({
              centerXM: element.center_x_m,
              centerYM: element.center_y_m,
              widthM: element.width_m,
              depthM: element.depth_m,
              rotationDeg: element.rotation_deg,
            }, projection))}
            className={`eay-store-scan-element eay-store-scan-element--${element.element_type}`}
            data-rotation-deg={element.rotation_deg}
          >
            <title>{`${element.element_type} · ${element.element_id} · ${Math.round(element.scan_confidence * 100)}%`}</title>
          </polygon>
        ))}
        {fixtureRows.map((fixture) => (
          <polygon
            key={fixture.element_id}
            points={svgPointString(rotatedRectSvgPoints({
              centerXM: fixture.center_x_m,
              centerYM: fixture.center_y_m,
              widthM: fixture.width_m,
              depthM: fixture.depth_m,
              rotationDeg: fixture.rotation_deg,
            }, projection))}
            className="eay-store-scan-fixture"
            data-rotation-deg={fixture.rotation_deg}
          >
            <title>{`${fixture.label || fixture.element_id} · ${Math.round(fixture.confidence * 100)}%`}</title>
          </polygon>
        ))}
      </svg>
    </div>
  );
}

export default function PlanogramStoreScanPanel({
  locale,
  formatNumber,
  canCreate,
  optimizationCandidate,
  onOpenEditableModel,
}) {
  const inputRef = useRef(null);
  const t = useMemo(
    () => (key, params) => translatePlanogramStoreScan(locale, key, params),
    [locale]
  );
  const [bundle, setBundle] = useState(null);
  const [fileName, setFileName] = useState("");
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [response, setResponse] = useState(null);

  const readCapture = useCallback(async (event) => {
    const file = event.target.files?.[0];
    setBundle(null);
    setFileName("");
    setResponse(null);
    setError("");
    if (!file) return;
    if (file.size > MAX_SCAN_FILE_BYTES) {
      setError(t("invalidFile"));
      event.target.value = "";
      return;
    }
    try {
      const parsed = JSON.parse(await file.text());
      const normalized = normalizePlanogramStoreScanBundle(parsed);
      if (!normalized) throw new Error("invalid_store_scan_bundle");
      setBundle(normalized);
      setFileName(file.name);
    } catch {
      setError(t("invalidFile"));
      event.target.value = "";
    }
  }, [t]);

  const runReview = useCallback(async () => {
    if (!bundle || !canCreate || running) return;
    setRunning(true);
    setResponse(null);
    setError("");
    try {
      const raw = await apiPost("/v1/planogram/store-scan/normalize-preview", bundle);
      const safe = safePlanogramStoreScanPreview(raw);
      if (!safe) throw new Error("store_scan_truth_boundary_failed");
      setResponse(safe);
    } catch {
      setError(t("unavailable"));
    } finally {
      setRunning(false);
    }
  }, [bundle, canCreate, running, t]);

  const scan = response?.store_scan || null;
  const blockers = Array.isArray(scan?.blockers) ? scan.blockers : [];
  const warnings = Array.isArray(scan?.warnings) ? scan.warnings : [];

  return (
    <section className="eay-store-scan" aria-busy={running ? "true" : "false"}>
      <header>
        <div>
          <ScanLine size={21} aria-hidden="true" />
          <div><h2>{t("title")}</h2><p>{t("subtitle")}</p></div>
        </div>
        <span>{t("previewOnly")}</span>
      </header>

      <div className="eay-store-scan-controls">
        <label>
          <FileScan size={17} aria-hidden="true" />
          <span>{t("upload")}</span>
          <input ref={inputRef} type="file" accept="application/json,.json" onChange={readCapture} />
        </label>
        <div role="status" aria-live="polite">
          {bundle ? t("loaded", { name: fileName }) : t("noFile")}
        </div>
        <button type="button" onClick={runReview} disabled={!bundle || !canCreate || running}>
          {running ? t("running") : t("run")}
        </button>
      </div>
      {!canCreate ? <p className="eay-store-scan-note">{t("permissionRequired")}</p> : null}
      {error ? <p className="eay-store-scan-error" role="alert">{error}</p> : null}

      {scan ? (
        <div className="eay-store-scan-result">
          <div className="eay-store-scan-boundary">
            <ShieldCheck size={18} aria-hidden="true" />
            <div><strong>{t("rawMedia")}</strong><span>{t("notStoreDna")}</span></div>
          </div>
          <div className="eay-store-scan-metrics" aria-label={t("quality")}>
            <div><span>{t("provider")}</span><strong>{scan.provider}</strong></div>
            <div><span>{t("elements")}</span><strong>{formatNumber(scan.scan_element_count || 0)}</strong></div>
            <div><span>{t("fixtures")}</span><strong>{formatNumber(scan.recognized_fixture_count || 0)}</strong></div>
            <div><span>{t("lowConfidence")}</span><strong>{formatNumber(scan.low_confidence_count || 0)}</strong></div>
            <div><span>{t("preservedV2")}</span><strong>{formatNumber(scan.v2_preserved_element_count || 0)}</strong></div>
          </div>
          <div className="eay-store-scan-fingerprint"><span>{t("fingerprint")}</span><code>{scan.scan_fingerprint}</code></div>
          <ScanGeometryPreview scan={scan} t={t} />
          <div className="eay-store-scan-review-grid">
            <article>
              <header><TriangleAlert size={17} aria-hidden="true" /><strong>{t("blockers")}</strong></header>
              {blockers.length ? <ul>{blockers.map((row) => <li key={row}><code>{row}</code></li>)}</ul> : <p>{t("none")}</p>}
            </article>
            <article>
              <header><TriangleAlert size={17} aria-hidden="true" /><strong>{t("warnings")}</strong></header>
              {warnings.length ? <ul>{warnings.map((row) => <li key={row}><code>{row}</code></li>)}</ul> : <p>{t("none")}</p>}
            </article>
          </div>
          <PlanogramScanAnnotationWorkspace
            scanBundle={bundle}
            scanResponse={response}
            locale={locale}
            formatNumber={formatNumber}
            canCreate={canCreate}
            optimizationCandidate={optimizationCandidate}
            onOpenEditableModel={onOpenEditableModel}
          />
        </div>
      ) : null}
    </section>
  );
}
