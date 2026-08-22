import React, { useCallback, useMemo, useRef, useState } from "react";
import { Boxes, FileCog, ShieldCheck, TriangleAlert } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translatePlanogramFixtureBinding } from "../../platform/i18n/planogramFixtureBindingMessages.js";
import { translatePlanogramFixtureCatalog } from "../../platform/i18n/planogramFixtureCatalogMessages.js";
import { rotatedRectSvgPoints, svgPointString } from "./planogramEngineering2D.js";
import {
  buildPlanogramFixtureBindingsFromSelections,
  normalizePlanogramFixtureBindings,
  normalizePlanogramFixtureCatalog,
  safePlanogramFixtureLayoutPreview,
  suggestPlanogramFixtureCatalogMatches,
} from "./planogramFixtureBindings.js";
import PlanogramScannedOptimizerPanel from "./PlanogramScannedOptimizerPanel.jsx";
import "./planogram-fixture-binding.css";

const MAX_BINDING_FILE_BYTES = 4 * 1024 * 1024;
const MAX_CATALOG_FILE_BYTES = 8 * 1024 * 1024;
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
  const modules = (result?.physical_layout_preview?.aisles || []).flatMap(
    (aisle) => (aisle.modules || []).map((module) => ({ ...module, aisle_id: aisle.aisle_id }))
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
  reviewedResult,
  classifications,
  operationalElements,
  uncertaintyResolutions,
  reviewNote,
  locale,
  formatNumber,
  canCreate,
  optimizationCandidate,
}) {
  const bindingInputRef = useRef(null);
  const catalogInputRef = useRef(null);
  const t = useMemo(
    () => (key, params) => translatePlanogramFixtureBinding(locale, key, params),
    [locale]
  );
  const c = useMemo(
    () => (key, params) => translatePlanogramFixtureCatalog(locale, key, params),
    [locale]
  );
  const scan = scanResponse?.store_scan || null;
  const reviewedFixtures = reviewedResult?.reviewed_recognized_fixtures;
  const recognized = Array.isArray(reviewedFixtures)
    ? reviewedFixtures
    : Array.isArray(scan?.recognized_fixtures)
      ? scan.recognized_fixtures
      : [];
  const recognizedIds = useMemo(() => recognized.map((row) => row.element_id), [recognized]);
  const [bindings, setBindings] = useState(null);
  const [bindingFileName, setBindingFileName] = useState("");
  const [catalog, setCatalog] = useState(null);
  const [catalogFileName, setCatalogFileName] = useState("");
  const [selections, setSelections] = useState({});
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [response, setResponse] = useState(null);

  const suggestions = useMemo(
    () => suggestPlanogramFixtureCatalogMatches(recognized, catalog || []),
    [catalog, recognized]
  );
  const suggestionById = useMemo(
    () => new Map(suggestions.map((row) => [row.scan_fixture_element_id, row])),
    [suggestions]
  );
  const interactiveBindings = useMemo(
    () => buildPlanogramFixtureBindingsFromSelections(recognized, catalog || [], selections),
    [catalog, recognized, selections]
  );
  const effectiveBindings = bindings || interactiveBindings;

  const readBindings = useCallback(async (event) => {
    const file = event.target.files?.[0];
    setBindings(null);
    setBindingFileName("");
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
      setBindingFileName(file.name);
    } catch {
      setError(t("invalid"));
      event.target.value = "";
    }
  }, [recognizedIds, t]);

  const readCatalog = useCallback(async (event) => {
    const file = event.target.files?.[0];
    setCatalog(null);
    setCatalogFileName("");
    setSelections({});
    setResponse(null);
    setError("");
    if (!file) return;
    if (file.size > MAX_CATALOG_FILE_BYTES) {
      setError(c("catalogInvalid"));
      event.target.value = "";
      return;
    }
    try {
      const parsed = JSON.parse(await file.text());
      const normalized = normalizePlanogramFixtureCatalog(parsed);
      if (!normalized) throw new Error("invalid_fixture_catalog");
      const initialSuggestions = suggestPlanogramFixtureCatalogMatches(recognized, normalized);
      const initialSelections = Object.fromEntries(
        recognized.map((fixture) => {
          const match = initialSuggestions.find((row) => row.scan_fixture_element_id === fixture.element_id);
          return [fixture.element_id, {
            fixture_id: match?.recommendation_safe ? match.recommended_fixture_id : "",
            aisle_id: "",
            side: "",
            position: "",
          }];
        })
      );
      setBindings(null);
      setBindingFileName("");
      setCatalog(normalized);
      setCatalogFileName(file.name);
      setSelections(initialSelections);
    } catch {
      setError(c("catalogInvalid"));
      event.target.value = "";
    }
  }, [c, recognized]);

  const updateSelection = useCallback((fixtureId, field, value) => {
    setBindings(null);
    setBindingFileName("");
    setResponse(null);
    setError("");
    setSelections((current) => ({
      ...current,
      [fixtureId]: { ...(current[fixtureId] || {}), [field]: value },
    }));
  }, []);

  const run = useCallback(async () => {
    if (!scanBundle || !scan?.scan_fingerprint || !effectiveBindings || running || !canCreate) return;
    setRunning(true);
    setResponse(null);
    setError("");
    try {
      const raw = await apiPost("/v1/planogram/store-scan/fixture-layout-preview", {
        scan: scanBundle,
        expected_scan_fingerprint: scan.scan_fingerprint,
        classifications,
        operational_elements: operationalElements,
        uncertainty_resolutions: uncertaintyResolutions || [],
        fixture_bindings: effectiveBindings,
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
  }, [canCreate, classifications, effectiveBindings, operationalElements, reviewNote, running, scan?.scan_fingerprint, scanBundle, t, uncertaintyResolutions]);

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
          <span>{c("catalogUpload")}</span>
          <input ref={catalogInputRef} type="file" accept="application/json,.json" onChange={readCatalog} />
        </label>
        <label>
          <FileCog size={17} aria-hidden="true" />
          <span>{c("advancedImport")}</span>
          <input ref={bindingInputRef} type="file" accept="application/json,.json" onChange={readBindings} />
        </label>
        <div role="status" aria-live="polite">
          {bindings
            ? t("loaded", { name: bindingFileName })
            : interactiveBindings
              ? c("interactiveReady")
              : catalog
                ? c("catalogLoaded", { name: catalogFileName })
                : c("catalogNoFile")}
        </div>
        <button type="button" onClick={run} disabled={!effectiveBindings || !canCreate || running}>{running ? t("running") : t("run")}</button>
      </div>
      {error ? <p className="eay-fixture-binding-error" role="alert">{error}</p> : null}

      {catalog ? (
        <div className="eay-fixture-binding-assistant">
          {recognized.map((fixture) => {
            const suggestion = suggestionById.get(fixture.element_id);
            const selection = selections[fixture.element_id] || {};
            const candidates = suggestion?.candidates || [];
            const status = suggestion?.recommendation_safe
              ? c("suggested")
              : suggestion?.ambiguous
                ? c("ambiguous")
                : c("reviewRequired");
            return (
              <article key={fixture.element_id}>
                <header><code>{fixture.element_id}</code><span>{status}</span></header>
                <label>
                  <span>{c("catalogFixture")}</span>
                  <select value={selection.fixture_id || ""} onChange={(event) => updateSelection(fixture.element_id, "fixture_id", event.target.value)}>
                    <option value="">—</option>
                    {candidates.map((candidate) => (
                      <option key={candidate.fixture.fixture_id} value={candidate.fixture.fixture_id}>
                        {candidate.fixture.fixture_id} · {candidate.fixture.fixture_type} · {candidate.fixture.storage_type}
                      </option>
                    ))}
                  </select>
                </label>
                <label><span>{c("aisle")}</span><input value={selection.aisle_id || ""} maxLength={40} onChange={(event) => updateSelection(fixture.element_id, "aisle_id", event.target.value)} /></label>
                <label>
                  <span>{c("side")}</span>
                  <select value={selection.side || ""} onChange={(event) => updateSelection(fixture.element_id, "side", event.target.value)}>
                    <option value="">—</option>
                    {/* i18n-data-literal: fixture side protocol values stored as L/R machine codes */}
                    <option value="L">L</option><option value="R">R</option>
                  </select>
                </label>
                <label><span>{c("position")}</span><input type="number" min="1" max="500" step="1" value={selection.position || ""} onChange={(event) => updateSelection(fixture.element_id, "position", event.target.value)} /></label>
              </article>
            );
          })}
        </div>
      ) : null}

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
              uncertaintyResolutions={uncertaintyResolutions}
              fixtureBindings={effectiveBindings}
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
