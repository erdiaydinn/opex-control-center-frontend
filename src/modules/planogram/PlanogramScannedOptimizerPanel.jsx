import React, { useCallback, useMemo, useState } from "react";
import { BrainCircuit, ShieldCheck } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translatePlanogramScannedOptimizer } from "../../platform/i18n/planogramScannedOptimizerMessages.js";
import PlanogramDigitalTwin from "./PlanogramDigitalTwin.jsx";
import PlanogramPickerEyePreview from "./PlanogramPickerEyePreview.jsx";
import { safePlanogramScannedOptimizerPreview } from "./planogramScannedOptimizer.js";
import "./planogram-scanned-optimizer.css";

export default function PlanogramScannedOptimizerPanel({
  scanBundle,
  scanResponse,
  classifications,
  operationalElements,
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
  ]);

  const result = response?.result || null;
  const optimizer = result?.optimizer || null;
  const scannedLayout = result?.scanned_layout || null;
  const twinCandidate = optimizer?.planogram && scannedLayout
    ? {
        ...optimizationCandidate,
        layout: scannedLayout.physical_layout_preview,
        store_dna: scannedLayout.reviewed_store_dna_v2_preview,
      }
    : null;
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

          {optimizer.allowed && twinCandidate ? (
            <div className="eay-scanned-optimizer-twin">
              <h4>{t("twin")}</h4>
              <PlanogramDigitalTwin
                engineResult={optimizer}
                candidate={twinCandidate}
                locale={locale}
                formatNumber={numberFormat}
              />
              <PlanogramPickerEyePreview
                engineResult={optimizer}
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
