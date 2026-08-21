import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Boxes,
  CheckCircle2,
  FileJson2,
  LockKeyhole,
  RefreshCw,
  Ruler,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { apiGet, apiPost } from "../../api/client.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { translatePlanogram } from "../../platform/i18n/planogramMessages.js";
import { translatePlanogramOperations } from "../../platform/i18n/planogramOperationsMessages.js";
import { translatePlanogramPreview } from "../../platform/i18n/planogramPreviewMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import PlanogramArchitecturalAuthoring from "./PlanogramArchitecturalAuthoring.jsx";
import { candidateFromReviewedStoreScan } from "./planogramAuthoringModel.js";
import PlanogramCadExport from "./PlanogramCadExport.jsx";
import { normalizeCandidateBundle } from "./planogramCandidateBundle.js";
import PlanogramDigitalTwin from "./PlanogramDigitalTwin.jsx";
import PlanogramEconomicsPanel from "./PlanogramEconomicsPanel.jsx";
import PlanogramOperationsPanel from "./PlanogramOperationsPanel.jsx";
import PlanogramPickerEyePreview from "./PlanogramPickerEyePreview.jsx";
import PlanogramRetailIntelligencePanel from "./PlanogramRetailIntelligencePanel.jsx";
import PlanogramScenarioPortfolio from "./PlanogramScenarioPortfolio.jsx";
import PlanogramStoreScanPanel from "./PlanogramStoreScanPanel.jsx";
import "./planogram-native.css";
import "./planogram-operations.css";
import "./planogram-preview.css";

const PLANOGRAM_FEATURES = ["layoutView", "layoutEdit", "fixtureEdit", "ruleEdit", "productAssign", "aiRecommend"];
const PLANOGRAM_ACTIONS = [
  "view",
  "create",
  "edit",
  "approve",
  "export",
  "delete",
  "acceptFieldEvidence",
];
const MAX_PREVIEW_FILE_BYTES = 10 * 1024 * 1024;

// Phase 1 Security Quarantine remains canonical: no legacy iframe/token bridge.
export const PLANOGRAM_SECURITY_CONTRACT = Object.freeze({
  features: PLANOGRAM_FEATURES,
  actions: PLANOGRAM_ACTIONS,
  legacyBridgeAllowed: false,
});

export default function PlanogramStudio() {
  const navigate = useNavigate();
  const { canAction } = useAuth();
  const { locale, formatNumber } = usePlatformPreferences();
  const fileInputRef = useRef(null);
  const t = useMemo(() => (key) => translatePlanogram(locale, key), [locale]);
  const p = useMemo(
    () => (key, params) => translatePlanogramPreview(locale, key, params),
    [locale]
  );
  const o = useMemo(
    () => (key) => translatePlanogramOperations(locale, key),
    [locale]
  );
  const canCreatePreview = canAction("planogram", "create");
  const canEditArchitecture = canAction("planogram", "edit");
  const canApprovePreview = canAction("planogram", "approve");

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [candidate, setCandidate] = useState(null);
  const [candidateName, setCandidateName] = useState("");
  const [candidateError, setCandidateError] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewRunning, setPreviewRunning] = useState(false);
  const [optimizerRunning, setOptimizerRunning] = useState(false);
  const [previewError, setPreviewError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await apiGet("/v1/planogram/readiness"));
    } catch {
      setData(null);
      setError(t("loadError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const clearCandidate = useCallback(() => {
    setCandidate(null);
    setCandidateName("");
    setCandidateError("");
    setPreview(null);
    setPreviewError("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  const openReviewedScanDraft = useCallback((reviewedResult) => {
    const base = candidate || { products: [], layout: {}, mode: "HYBRID", store_dna: {} };
    const next = candidateFromReviewedStoreScan(base, reviewedResult);
    if (!next) return;
    setCandidate(next);
    setCandidateName("");
    setCandidateError("");
    setPreviewError("");
  }, [candidate]);

  const updateAuthoredCandidate = useCallback((nextCandidate) => {
    if (!nextCandidate) return;
    setCandidate(nextCandidate);
    setCandidateError("");
  }, []);

  const readCandidate = useCallback(async (event) => {
    const file = event.target.files?.[0];
    setCandidate(null);
    setCandidateName("");
    setCandidateError("");
    setPreview(null);
    setPreviewError("");

    if (!file) return;
    if (file.size > MAX_PREVIEW_FILE_BYTES) {
      setCandidateError(p("fileTooLarge"));
      event.target.value = "";
      return;
    }

    try {
      const parsed = JSON.parse(await file.text());
      const normalized = normalizeCandidateBundle(parsed);
      if (!normalized) throw new Error("invalid_bundle");
      setCandidate(normalized);
      setCandidateName(file.name);
    } catch {
      setCandidateError(p("fileInvalid"));
      event.target.value = "";
    }
  }, [p]);

  const runPreview = useCallback(async () => {
    if (!candidate || !canCreatePreview || previewRunning || optimizerRunning) return;
    setPreviewRunning(true);
    setPreview(null);
    setPreviewError("");
    try {
      setPreview(await apiPost("/v1/planogram/preview", candidate));
    } catch {
      setPreviewError(p("previewError"));
    } finally {
      setPreviewRunning(false);
    }
  }, [canCreatePreview, candidate, optimizerRunning, p, previewRunning]);

  const runOptimizerPreview = useCallback(async () => {
    if (!candidate || !canCreatePreview || previewRunning || optimizerRunning) return;
    setOptimizerRunning(true);
    setPreview(null);
    setPreviewError("");
    try {
      setPreview(await apiPost("/v1/planogram/optimize-preview", candidate));
    } catch {
      setPreviewError(p("previewError"));
    } finally {
      setOptimizerRunning(false);
    }
  }, [canCreatePreview, candidate, optimizerRunning, p, previewRunning]);

  const productState = loading ? "loading" : error ? "error" : data ? "ready" : "empty";
  const engineResult = preview?.engine_result || preview?.optimizer_result || null;
  const optimizerMeta = preview?.optimizer_result?.optimizer || null;
  const blockers = Array.isArray(engineResult?.physical_truth?.blockers)
    ? engineResult.physical_truth.blockers
    : [];

  return (
    <main
      className="eay-planogram-native"
      data-testid="planogram-studio"
      aria-busy={loading ? "true" : "false"}
      data-eay-product-state={productState}
    >
      <header className="eay-planogram-head">
        <button type="button" onClick={() => navigate("/")} aria-label={t("back")}>
          <ArrowLeft className="eay-planogram-back-icon" size={18} aria-hidden="true" />
          {t("back")}
        </button>
        <div>
          <span>{t("coreAuthority")}</span>
          <h1>{t("title")}</h1>
          <p>{t("subtitle")}</p>
        </div>
        <span className="eay-planogram-gate">
          <ShieldCheck size={17} aria-hidden="true" />
          {t("securityBoundary")}
        </span>
      </header>

      {loading ? (
        <section className="eay-planogram-state" data-eay-product-state="loading" role="status" aria-live="polite" aria-atomic="true">
          <RefreshCw className="spin" size={20} aria-hidden="true" />
          {t("loading")}
        </section>
      ) : null}

      {!loading && error ? (
        <section className="eay-planogram-state" data-eay-product-state="error" role="alert" aria-atomic="true">
          <span>{error}</span>
          <button type="button" onClick={load}>{t("retry")}</button>
        </section>
      ) : null}

      {!loading && !error && !data ? (
        <section className="eay-planogram-state" data-eay-product-state="empty" role="status" aria-live="polite" aria-atomic="true">
          <span>{t("loadError")}</span>
          <button type="button" onClick={load}>{t("retry")}</button>
        </section>
      ) : null}

      {data && !loading && !error ? (
        <div data-eay-product-state="ready">
          <section className="eay-planogram-summary">
            <article>
              <Boxes size={21} aria-hidden="true" />
              <span>{t("engine")}</span>
              <strong>{data.engine?.contract}</strong>
              <small>{t("libraryMode")}</small>
            </article>
            <article>
              <LockKeyhole size={21} aria-hidden="true" />
              <span>{t("productionBlocked")}</span>
              <strong>{data.production_ready ? "READY" : "BLOCKED"}</strong>
              <small>{t("solverBlocked")}</small>
            </article>
            <article>
              <CheckCircle2 size={21} aria-hidden="true" />
              <span>{t("securityBoundary")}</span>
              <strong>{data.engine?.legacy_bridge_enabled ? "LEGACY" : "CORE"}</strong>
              <small>{t("legacyOff")}</small>
            </article>
          </section>

          <section className="eay-planogram-evidence">
            <header>
              <div><Ruler size={22} aria-hidden="true" /><span>{t("physicalTruth")}</span></div>
              <strong>{t("externalRequired")}</strong>
            </header>
            <div className="eay-planogram-evidence-grid">
              {(data.physical_truth?.required_evidence || []).map((item) => (
                <article key={item}><TriangleAlert size={18} aria-hidden="true" /><span>{t(item)}</span></article>
              ))}
            </div>
          </section>

          <section className="eay-planogram-generation">
            <LockKeyhole size={24} aria-hidden="true" />
            <div><strong>{t("generationBlocked")}</strong><p>{t("requiredEvidence")}</p></div>
            <button type="button" disabled>{t("solverBlocked")}</button>
          </section>

          <PlanogramOperationsPanel locale={locale} formatNumber={formatNumber} canAction={canAction} />

          <PlanogramStoreScanPanel
            locale={locale}
            formatNumber={formatNumber}
            canCreate={canCreatePreview}
            optimizationCandidate={candidate}
            onOpenEditableModel={openReviewedScanDraft}
          />

          {candidate?.store_dna?.architecture ? (
            <PlanogramArchitecturalAuthoring
              candidate={candidate}
              locale={locale}
              canEdit={canEditArchitecture}
              onCandidateChange={updateAuthoredCandidate}
            />
          ) : null}

          <PlanogramRetailIntelligencePanel candidate={candidate} locale={locale} formatNumber={formatNumber} canCreate={canCreatePreview} />

          <section className="eay-planogram-preview" aria-busy={previewRunning || optimizerRunning ? "true" : "false"}>
            <header>
              <div><FileJson2 size={22} aria-hidden="true" /><div><h2>{p("candidatePreview")}</h2><p>{p("candidateHint")}</p></div></div>
              <span>{p("previewOnly")}</span>
            </header>

            <div className="eay-planogram-preview-controls">
              <label className="eay-planogram-file-control">
                <span>{p("uploadBundle")}</span>
                <input ref={fileInputRef} type="file" accept="application/json,.json" onChange={readCandidate} />
              </label>
              <div className="eay-planogram-file-state" role="status" aria-live="polite">
                {candidate
                  ? p("fileLoaded", { name: candidateName, products: formatNumber(candidate?.products?.length || 0) })
                  : p("noFile")}
              </div>
              <button type="button" onClick={clearCandidate} disabled={!candidate && !candidateError && !preview}>{p("clear")}</button>
              <button type="button" className="eay-planogram-preview-run" onClick={runPreview} disabled={!candidate || !canCreatePreview || previewRunning || optimizerRunning}>
                {previewRunning ? p("runningPreview") : p("runPreview")}
              </button>
              <button type="button" className="eay-planogram-preview-run" onClick={runOptimizerPreview} disabled={!candidate || !canCreatePreview || previewRunning || optimizerRunning}>
                {optimizerRunning ? o("optimizerRunning") : o("optimizerPreview")}
              </button>
            </div>

            {!canCreatePreview ? <p className="eay-planogram-preview-note">{p("createPermissionRequired")}</p> : null}
            {candidateError ? <p className="eay-planogram-preview-error" role="alert">{candidateError}</p> : null}
            {previewError ? <p className="eay-planogram-preview-error" role="alert">{previewError}</p> : null}

            {preview ? (
              <div className="eay-planogram-preview-result" role="status" aria-live="polite" aria-atomic="true">
                <div className="eay-planogram-preview-truth">
                  <strong>{p("previewReady")}</strong>
                  <span>{p("unattested")}</span>
                  <span>{p("productionReleaseBlocked")}</span>
                  {optimizerMeta ? <span>{o("previewStillUnattested")}</span> : null}
                </div>
                <div className="eay-planogram-preview-metrics">
                  <div><span>{p("productsCount")}</span><strong>{formatNumber(candidate?.products?.length || 0)}</strong></div>
                  <div><span>{p("placed")}</span><strong>{formatNumber(engineResult?.summary?.placed || 0)}</strong></div>
                  <div><span>{p("unplaced")}</span><strong>{formatNumber(engineResult?.summary?.unplaced || 0)}</strong></div>
                  <div><span>{p("mode")}</span><strong>{candidate?.mode || "—"}</strong></div>
                  {optimizerMeta ? (
                    <>
                      <div><span>{o("optimizerStrategy")}</span><strong>{optimizerMeta.selected_strategy}</strong></div>
                      <div><span>{o("optimizerCandidates")}</span><strong>{formatNumber(optimizerMeta.candidate_count || 0)}</strong></div>
                    </>
                  ) : null}
                </div>
                {optimizerMeta ? (
                  <p className="eay-planogram-preview-note">
                    {optimizerMeta.allowed ? (optimizerMeta.improved ? o("optimizerImproved") : o("optimizerBaseline")) : o("optimizerBlocked")}
                  </p>
                ) : null}
                {optimizerMeta ? (
                  <PlanogramScenarioPortfolio candidate={candidate} locale={locale} formatNumber={formatNumber} canCreate={canCreatePreview} canApprove={canApprovePreview} />
                ) : null}
                {optimizerMeta ? (
                  <PlanogramCadExport candidate={candidate} optimizerMeta={optimizerMeta} locale={locale} canExport={canAction("planogram", "export")} />
                ) : null}
                {optimizerMeta ? (
                  <PlanogramEconomicsPanel candidate={candidate} locale={locale} formatNumber={formatNumber} canCreate={canCreatePreview} canApprove={canApprovePreview} />
                ) : null}
                {engineResult?.planogram ? (
                  <PlanogramDigitalTwin engineResult={engineResult} candidate={candidate} locale={locale} formatNumber={formatNumber} />
                ) : null}
                {engineResult?.planogram ? (
                  <PlanogramPickerEyePreview engineResult={engineResult} candidate={candidate} locale={locale} formatNumber={formatNumber} />
                ) : null}
                <div className="eay-planogram-preview-blockers">
                  <strong>{p("blockers")}</strong>
                  {blockers.length ? (
                    <ul>{blockers.map((blocker) => <li key={blocker}><code>{blocker}</code></li>)}</ul>
                  ) : <p>{p("noBlockers")}</p>}
                </div>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </main>
  );
}
