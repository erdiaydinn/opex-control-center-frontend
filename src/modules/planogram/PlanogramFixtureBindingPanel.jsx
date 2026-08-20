import React, { useCallback, useMemo, useRef, useState } from "react";
import { Boxes, FileCog, ShieldCheck, TriangleAlert } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translatePlanogramFixtureBinding } from "../../platform/i18n/planogramFixtureBindingMessages.js";
import { rotatedRectSvgPoints, svgPointString } from "./planogramEngineering2D.js";
import {
  normalizePlanogramFixtureBindings,
  safePlanogramFixtureLayoutPreview,
} from "./planogramFixtureBindings.js";
import PlanogramScannedOptimizerPanel from "./PlanogramScannedOptimizerPanel.jsx";
import "./planogram-fixture-binding.css";

const MAX_BINDING_FILE_BYTES = 4 * 1024 * 1024;
const SVG_WIDTH = 920;
const SVG_HEIGHT = 520;

function buildProjection(scan) {
  const architecture = scan?.architecture_v2_preview;
  if (!architecture) return null;
  const padding = 38;
  const scale = Math.min(
    (SVG_WIDTH - padding * 2) / architecture.floor_width_m,
    (SVG_HEIGHT - padding * 2) / architecture.floor_depth_m
  );
  return {
    architecture,
    offsetX: (SVG_WIDTH - architecture.floor_width_m * scale) / 2,
    offsetY: (SVG_HEIGHT - architecture.floor_depth_m * scale) / 2,
    floorDepthM: architecture.floor_depth_m,
    scale,
  };
}

function LayoutOverlay({ result, scan, t }) {
  const projection = buildProjection(scan);
  const modules = (result?.physical_layout_preview?.aisles || []).flatMap((aisle) =>
    (aisle.modules || []).map((module) => ({ ...module, aisle_id: aisle.aisle_id }))
  );
  if (!projection || !modules.length) return null;
  return (
    <div className="eay-fixture-binding-layout">
      <strong>{t("layout")}</strong>
      <svg viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`} role="img" aria-label={t("layout")}>
        <rect
          x={projection.offsetX}
          y={projection.offsetY}
          width={projection.architecture.floor_width_m * projection.scale}
          height={projection.architecture.floor_depth_m * projection.scale}
          className="eay-fixture-binding-floor"
        />
        {modules.map((module) => (
          <polygon
            key={`${module.aisle_id}-${module.module_id}`}
            points={svgPointString(rotatedRectSvgPoints({
              centerXM: module.x_m,
              centerYM: module.y_m,
              widthM: module.width_m,
              depthM: module.depth_m,
              rotationDeg: module.rotation_deg,
            }, projection))}
            className={`eay-fixture-binding-module eay-fixture-binding-module--${String(module.storage_type || "ambient").toLowerCase()}`}
          >
            <title>{`${module.module_id} · ${module.fixture_type} · ${module.aisle_id}/${module.side}/${module.position}`}</title>
          </polygon>
        ))}
      </svg>
    </div>
  );
}

export default function PlanogramFixtureBindingPanel({
  scanBundle,
  scanResponse,
  classifications,
  operationalElements,
  reviewNote,
  locale,
  formatNumber,
  canCreate,
  optimizationCandidate,
}) {
  const inputRef = useRef(null);
  const t = useMemo(
    () => (key, params) => translatePlanogramFixtureBinding(locale, key, params),
    [locale]
  );
  const scan = scanResponse?.store_scan || null;
  const recognized = Array.isArray(scan?.recognized_fixtures)
    ? scan.recognized_fixtures
    : [];
  const recognizedIds = useMemo(
    () => recognized.map((row) => row.element_id),
    [recognized]
  );
  const [bindings, setBindings] = useState(null);
  const [fileName, setFileName] = useState("");
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [response, setResponse] = useState(null);

  const readBindings = useCallback(async (event) => {
    const file = event.target.files?.[0];
    setBindings(null);
    setFileName("");
    setResponse(null);
    setError("");
    if (!file) return;
    if (file.size > MAX_BINDING_FILE_BYTES) {
      setError(t("invalid"));
      event.target.value = "";
      return;
    }
    try {
      const parsed = JSON.parse(await file.text());
      const normalized = normalizePlanogramFixtureBindings(parsed, recognizedIds);
      if (!normalized) throw new Error("invalid_fixture_bindings");
      setBindings(normalized);
      setFileName(file.name);
    } catch {
      setError(t("invalid"));
      event.target.value = "";
    }
  }, [recognizedIds, t]);

  const run = useCallback(async () => {
    if (!scanBundle || !scan?.scan_fingerprint || !bindings || running || !canCreate) return;
    setRunning(true);
    setResponse(null);
    setError("");
    try {
      const raw = await apiPost("/v1/planogram/store-scan/fixture-layout-preview", {
        scan: scanBundle,
        expected_scan_fingerprint: scan.scan_fingerprint,
        classifications,
        operational_elements: operationalElements,
        fixture_bindings: bindings,
        review_note: reviewNote || null,
      });
      const safe = safePlanogramFixtureLayoutPreview(raw, scan.scan_fingerprint);
      if (!safe) throw new Error("fixture_layout_authority_boundary_failed");
      setResponse(safe);
    } catch {
      setError(t("unavailable"));
    } finally {
      setRunning(false);
    }
  }, [bindings, canCreate, classifications, operationalElements, reviewNote, running, scan?.scan_fingerprint, scanBundle, t]);

  if (!scan || !recognized.length) return null;
  const result = response?.result || null;
  const numberFormat = typeof formatNumber === "function"
    ? formatNumber
    : (value) => new Intl.NumberFormat(locale || "en").format(Number(value || 0));

  return (
    <section className="eay-fixture-binding">
      <header>
        <div><Boxes size={20} aria-hidden="true" /><div><h3>{t("title")}</h3><p>{t("subtitle")}</p></div></div>
        <span>{t("previewOnly")}</span>
      </header>

      <div className="eay-fixture-binding-detected">
        <strong>{t("detected")}</strong>
        <div>
          {recognized.map((fixture) => (
            <article key={fixture.element_id}>
              <code>{fixture.element_id}</code>
              <span>{fixture.label || "—"}</span>
              <span>{t("dimensions")}: {numberFormat(fixture.width_m)} × {numberFormat(fixture.depth_m)} m</span>
              <span>{t("confidence")}: {numberFormat(Number(fixture.confidence || 0) * 100)}%</span>
            </article>
          ))}
        </div>
      </div>

      <div className="eay-fixture-binding-controls">
        <label>
          <FileCog size={17} aria-hidden="true" />
          <span>{t("upload")}</span>
          <input ref={inputRef} type="file" accept="application/json,.json" onChange={readBindings} />
        </label>
        <div role="status" aria-live="polite">
          {bindings ? t("loaded", { name: fileName }) : t("noFile")}
        </div>
        <button type="button" onClick={run} disabled={!bindings || !canCreate || running}>
          {running ? t("running") : t("run")}
        </button>
      </div>
      {error ? <p className="eay-fixture-binding-error" role="alert">{error}</p> : null}

      {result ? (
        <div className="eay-fixture-binding-result">
          <div className="eay-fixture-binding-boundary">
            <ShieldCheck size={18} aria-hidden="true" />
            <div><strong>{t("authority")}</strong><span>{t("bridge")}</span></div>
          </div>
          <div className="eay-fixture-binding-metrics">
            <div><span>{t("bindingCoverage")}</span><strong>{numberFormat(result.fixture_binding_coverage_pct || 0)}%</strong></div>
            <div><span>{t("modules")}</span><strong>{numberFormat(result.bound_fixture_count || 0)}</strong></div>
            <div><span>{result.layout_draft_ready ? t("layoutReady") : t("layoutBlocked")}</span><strong>{result.layout_draft_ready ? "✓" : "!"}</strong></div>
          </div>
          <LayoutOverlay result={result} scan={scan} t={t} />
          <div className="eay-fixture-binding-blockers">
            <header><TriangleAlert size={17} aria-hidden="true" /><strong>{t("blockers")}</strong></header>
            {result.blockers?.length ? <ul>{result.blockers.map((row) => <li key={row}><code>{row}</code></li>)}</ul> : <p>{t("none")}</p>}
          </div>

          {result.layout_draft_ready ? (
            <PlanogramScannedOptimizerPanel
              scanBundle={scanBundle}
              scanResponse={scanResponse}
              classifications={classifications}
              operationalElements={operationalElements}
              fixtureBindings={bindings}
              reviewNote={reviewNote}
              optimizationCandidate={optimizationCandidate}
              locale={locale}
              formatNumber={numberFormat}
              canCreate={canCreate}
            />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
