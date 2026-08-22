import React, { useCallback, useMemo, useState } from "react";
import { BrainCircuit, ShieldCheck } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translatePlanogramScannedOptimizer } from "../../platform/i18n/planogramScannedOptimizerMessages.js";
import PlanogramDigitalTwin from "./PlanogramDigitalTwin.jsx";
import PlanogramPickerEyePreview from "./PlanogramPickerEyePreview.jsx";
import { safePlanogramScannedOptimizerPreview } from "./planogramScannedOptimizer.js";
import "./planogram-scanned-optimizer.css";

function objectiveComparator(left, right) {
  const a = Array.isArray(left?.objective_key) ? left.objective_key : [];
  const b = Array.isArray(right?.objective_key) ? right.objective_key : [];
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    const delta = Number(a[index] ?? 0) - Number(b[index] ?? 0);
    if (Math.abs(delta) > 1e-9) return delta;
  }
  return String(left?.profile_id || "").localeCompare(String(right?.profile_id || ""));
}

function representativeRouteOverlay(evidence, selectedP95) {
  if (!evidence?.available || !Array.isArray(evidence?.explained_orders)) return null;
  const rows = evidence.explained_orders.filter((row) => Array.isArray(row?.segments));
  if (!rows.length) return null;
  const target = Number(selectedP95 || 0);
  const representative = [...rows].sort((left, right) => {
    const leftGap = Math.abs(Number(left?.distance_m || 0) - target);
    const rightGap = Math.abs(Number(right?.distance_m || 0) - target);
    if (Math.abs(leftGap - rightGap) > 1e-9) return leftGap - rightGap;
    return Number(right?.distance_m || 0) - Number(left?.distance_m || 0);
  })[0];
  const path = [];
  for (const segment of representative.segments) {
    for (const point of segment?.path_m || []) {
      if (!Array.isArray(point) || point.length < 2) continue;
      const next = [Number(point[0]), Number(point[1])];
      if (!Number.isFinite(next[0]) || !Number.isFinite(next[1])) continue;
      const previous = path[path.length - 1];
      if (!previous || previous[0] !== next[0] || previous[1] !== next[1]) path.push(next);
    }
  }
  if (path.length < 2) return null;
  return {
    contract: "architecture-polygon-astar-v2",
    available: true,
    preview_only: true,
    distance_m: Number(representative.distance_m || 0),
    path_m: path.slice(0, 160),
    representative_basket_ref: representative.basket_ref,
  };
}

export default function PlanogramScannedOptimizerPanel({
  scanBundle,
  scanResponse,
  classifications,
  operationalElements,
  uncertaintyResolutions,
  fixtureBindings,
  reviewNote,
  optimizationCandidate,
  locale,
  formatNumber,
  canCreate,
}) {
  const t = useMemo(
    () => (key) => translatePlanogramScannedOptimizer(locale, key),
    [locale]
  );
  const scan = scanResponse?.store_scan || null;
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [response, setResponse] = useState(null);
  const baskets = optimizationCandidate?.order_baskets || [];
  const products = optimizationCandidate?.products || [];
  const evidenceReady = Boolean(products.length && baskets.length && fixtureBindings?.length);

  const run = useCallback(async () => {
    if (!scanBundle || !scan?.scan_fingerprint || !evidenceReady || running || !canCreate) return;
    setRunning(true);
    setResponse(null);
    setError("");
    try {
      const raw = await apiPost("/v1/planogram/store-scan/optimize-preview", {
        scan: scanBundle,
        expected_scan_fingerprint: scan.scan_fingerprint,
        classifications,
        operational_elements: operationalElements,
        uncertainty_resolutions: uncertaintyResolutions || [],
        fixture_bindings: fixtureBindings,
        products,
        order_baskets: baskets,
        mode: optimizationCandidate?.mode || "HYBRID",
        review_note: reviewNote || null,
      });
      const safe = safePlanogramScannedOptimizerPreview(raw, scan.scan_fingerprint);
      if (!safe) throw new Error("scanned_optimizer_truth_boundary_failed");
      setResponse(safe);
    } catch {
      setError(t("unavailable"));
    } finally {
      setRunning(false);
    }
  }, [
    baskets,
    canCreate,
    classifications,
    evidenceReady,
    fixtureBindings,
    operationalElements,
    optimizationCandidate?.mode,
    products,
    reviewNote,
    running,
    scan?.scan_fingerprint,
    scanBundle,
    t,
    uncertaintyResolutions,
  ]);

  const result = response?.result || null;
  const optimizer = result?.optimizer || null;
  const scannedLayout = result?.scanned_layout || null;
  const routeOverlay = representativeRouteOverlay(
    optimizer?.picker_tour_evidence_v2,
    optimizer?.selected_tour?.p95_m
  );
  const twinEngineResult = optimizer
    ? {
        ...optimizer,
        ...(routeOverlay ? { architecture_route_objective_v2: routeOverlay } : {}),
      }
    : null;
  const twinCandidate = optimizer?.planogram && scannedLayout
    ? {
        ...optimizationCandidate,
        layout: scannedLayout.physical_layout_preview,
        store_dna: scannedLayout.reviewed_store_dna_v2_preview,
      }
    : null;
  const rankedCandidates = useMemo(
    () => [...(optimizer?.candidates || [])].sort(objectiveComparator).slice(0, 4),
    [optimizer?.candidates]
  );
  const numberFormat = typeof formatNumber === "function"
    ? formatNumber
    : (value) => new Intl.NumberFormat(locale || "en").format(Number(value || 0));

  return (
    <section className="eay-scanned-optimizer" aria-busy={running ? "true" : "false"}>
      <header>
        <div><BrainCircuit size={20} aria-hidden="true" /><div><h3>{t("title")}</h3><p>{t("subtitle")}</p></div></div>
        <span>{t("previewOnly")}</span>
      </header>

      <button type="button" onClick={run} disabled={!evidenceReady || !canCreate || running}>
        {running ? t("running") : t("run")}
      </button>
      {!optimizationCandidate ? <p className="eay-scanned-optimizer-note">{t("candidateRequired")}</p> : null}
      {optimizationCandidate && !baskets.length ? <p className="eay-scanned-optimizer-note">{t("basketsRequired")}</p> : null}
      {error ? <p className="eay-scanned-optimizer-error" role="alert">{error}</p> : null}

      {optimizer ? (
        <div className="eay-scanned-optimizer-result">
          <div className="eay-scanned-optimizer-boundary">
            <ShieldCheck size={18} aria-hidden="true" />
            <div><strong>{optimizer.allowed ? t("ready") : t("blocked")}</strong><span>{t("boundary")}</span></div>
          </div>
          <div className="eay-scanned-optimizer-metrics">
            <div><span>{t("candidateCount")}</span><strong>{numberFormat(optimizer.candidate_count || 0)}</strong></div>
            <div><span>{t("p95")}</span><strong>{numberFormat(optimizer.selected_tour?.p95_m || 0)} m</strong></div>
            <div><span>{t("average")}</span><strong>{numberFormat(optimizer.selected_tour?.average_m || 0)} m</strong></div>
            <div><span>{t("unplaced")}</span><strong>{numberFormat(optimizer.unplaced_skus?.length || 0)}</strong></div>
            <div><span>{t("global")}</span><strong>{t("globalNo")}</strong></div>
          </div>
          <div className="eay-scanned-optimizer-fingerprint"><span>{t("fingerprint")}</span><code>{optimizer.optimizer_fingerprint}</code></div>

          {rankedCandidates.length ? (
            <div className="eay-scanned-optimizer-candidates">
              <strong>{t("candidateCount")}</strong>
              <div>
                {rankedCandidates.map((candidate, index) => (
                  <article key={candidate.profile_id} data-selected={candidate.profile_id === optimizer.selected_profile_id ? "true" : "false"}>
                    <code>#{index + 1} · {candidate.profile_id}</code>
                    <span>{t("p95")}: {numberFormat(candidate.tour?.p95_m || 0)} m</span>
                    <span>{t("average")}: {numberFormat(candidate.tour?.average_m || 0)} m</span>
                    <span>{t("unplaced")}: {numberFormat(candidate.unplaced_skus?.length || 0)}</span>
                  </article>
                ))}
              </div>
            </div>
          ) : null}

          {optimizer.allowed && twinCandidate && twinEngineResult ? (
            <div className="eay-scanned-optimizer-twin">
              <h4>{t("twin")}</h4>
              <PlanogramDigitalTwin
                engineResult={twinEngineResult}
                candidate={twinCandidate}
                locale={locale}
                formatNumber={numberFormat}
              />
              <PlanogramPickerEyePreview
                engineResult={twinEngineResult}
                candidate={twinCandidate}
                locale={locale}
                formatNumber={numberFormat}
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
