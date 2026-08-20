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
import PlanogramDigitalTwin from "./PlanogramDigitalTwin.jsx";
import PlanogramOperationsPanel from "./PlanogramOperationsPanel.jsx";
import "./planogram-native.css";
import "./planogram-operations.css";
import "./planogram-preview.css";

const PLANOGRAM_FEATURES = ["layoutView", "layoutEdit", "fixtureEdit", "ruleEdit", "productAssign", "aiRecommend"];
const PLANOGRAM_ACTIONS = ["view", "create", "edit", "approve", "export", "delete", "acceptFieldEvidence"];
const PREVIEW_MODES = new Set(["HYBRID", "CATEGORY", "ABC", "BRAND"]);
const MAX_PREVIEW_FILE_BYTES = 10 * 1024 * 1024;

// Phase 1 Security Quarantine remains the canonical boundary: no legacy iframe/token bridge.
export const PLANOGRAM_SECURITY_CONTRACT = Object.freeze({
  features: PLANOGRAM_FEATURES,
  actions: PLANOGRAM_ACTIONS,
  legacyBridgeAllowed: false,
});

function normalizeCandidateBundle(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  if (!Array.isArray(payload.products) || payload.products.length === 0) return null;
  if (!payload.layout || typeof payload.layout !== "object" || Array.isArray(payload.layout)) return null;
  if (!payload.store_dna || typeof payload.store_dna !== "object" || Array.isArray(payload.store_dna)) return null;

  const mode = payload.mode == null ? "HYBRID" : String(payload.mode).trim().toUpperCase();
  if (!PREVIEW_MODES.has(mode)) return null;

  return {
    products: payload.products,
    layout: payload.layout,
    store_dna: payload.store_dna,
    mode,
  };
}

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

    let parsed;
    try {
      parsed = JSON.parse(await file.text());
    } catch {
      setCandidateError(p("invalidJson"));
      event.target.value = "";
      return;
    }

    const normalized = normalizeCandidateBundle(parsed);
    if (!normalized) {
      setCandidateError(p("invalidBundle"));
      event.target.value = "";
      return;
    }

    setCandidate(normalized);
    setCandidateName(file.name);
  }, [p]);

  const runPreview = useCallback(async () => {
    if (!candidate || !canCreatePreview) return;
    setPreviewRunning(true);
    setPreviewError("");
    try {
      setPreview(await apiPost("/v1/planogram/preview", candidate));
    } catch {
      setPreview(null);
      setPreviewError(p("previewError"));
    } finally {
      setPreviewRunning(false);
    }
  }, [candidate, canCreatePreview, p]);

  const runOptimizer = useCallback(async () => {
    if (!candidate || !canCreatePreview) return;
    setOptimizerRunning(true);
    setPreviewError("");
    try {
      const response = await apiPost("/v1/planogram/optimize-preview", candidate);
      setPreview(
        response?.optimizer_result
          ? { ...response, engine_result: response.optimizer_result }
          : response
      );
    } catch {
      setPreview(null);
      setPreviewError(p("optimizerFailed"));
    } finally {
      setOptimizerRunning(false);
    }
  }, [candidate, canCreatePreview, p]);

  const productState = loading ? "loading" : error ? "error" : data ? "ready" : "empty";
  const engineResult = preview?.engine_result || null;

  return (
    <main
      className="planogram-native"
      data-testid="planogram-studio"
      data-eay-product-state={productState}
      aria-busy={loading ? "true" : "false"}
    >
      <header className="planogram-native__header">
        <div>
          <button className="planogram-native__back" type="button" onClick={() => navigate("/")}>
            <ArrowLeft className="eay-planogram-back-icon" size={18} aria-hidden="true" />
            <span>{t("back")}</span>
          </button>
          {/* i18n-brand-literal: canonical EAY Planogram product label is intentionally locale-invariant. */}
          <p className="planogram-native__eyebrow">EAY · Planogram</p>
          <h1>{t("title")}</h1>
          <p>{t("subtitle")}</p>
        </div>
        <button className="planogram-native__refresh" type="button" onClick={load}>
          <RefreshCw size={18} aria-hidden="true" />
          <span>{t("refresh")}</span>
        </button>
      </header>

      {loading ? (
        <div
          className="planogram-native__state"
          data-eay-product-state="loading"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          <RefreshCw className="spin" size={20} aria-hidden="true" />
          <span>{t("loading")}</span>
        </div>
      ) : null}

      {!loading && error ? (
        <div
          className="planogram-native__state planogram-native__state--error"
          data-eay-product-state="error"
          role="alert"
          aria-atomic="true"
        >
          <TriangleAlert size={20} aria-hidden="true" />
          <span>{error}</span>
          <button type="button" onClick={load}>{t("retry")}</button>
        </div>
      ) : null}

      {!loading && !error && !data ? (
        <div
          className="planogram-native__state"
          data-eay-product-state="empty"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          <span>{t("loadError")}</span>
          <button type="button" onClick={load}>{t("retry")}</button>
        </div>
      ) : null}

      {!loading && !error && data ? (
        <div data-eay-product-state="ready">
          <section className="planogram-native__grid">
            <article className="planogram-native__card">
              <ShieldCheck size={22} aria-hidden="true" />
              <span>{t("auth")}</span>
              <strong>{data.auth_mode || "—"}</strong>
            </article>
            <article className="planogram-native__card">
              <LockKeyhole size={22} aria-hidden="true" />
              <span>{t("tenant")}</span>
              <strong>{data.tenant_isolation || "—"}</strong>
            </article>
            <article className="planogram-native__card">
              <Boxes size={22} aria-hidden="true" />
              <span>{t("catalog")}</span>
              <strong>{formatNumber(data.catalog_rows || 0)}</strong>
            </article>
            <article className="planogram-native__card">
              <Ruler size={22} aria-hidden="true" />
              <span>{t("engine")}</span>
              <strong>{data.engine_version || "—"}</strong>
            </article>
            <article className="planogram-native__card">
              <LockKeyhole size={22} aria-hidden="true" />
              <span>{t("productionBlocked")}</span>
              <strong>{data.production_ready ? "READY" : "BLOCKED"}</strong>
            </article>
          </section>

          <section className="planogram-native__workspace">
            <div className="planogram-native__upload">
              <div>
                <p className="planogram-native__eyebrow">{p("candidateEyebrow")}</p>
                <h2>{p("candidateTitle")}</h2>
                <p>{p("candidateDescription")}</p>
              </div>
              <label className="planogram-native__file">
                <FileJson2 size={20} aria-hidden="true" />
                <span>{p("chooseFile")}</span>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/json,.json"
                  onChange={readCandidate}
                />
              </label>
              {candidateName ? <p>{p("selectedFile", { name: candidateName })}</p> : null}
              {candidateError ? <p role="alert">{candidateError}</p> : null}
              {candidate ? (
                <div className="planogram-native__candidate-actions">
                  <button type="button" onClick={clearCandidate}>{p("clear")}</button>
                  <button
                    type="button"
                    disabled={!canCreatePreview || previewRunning}
                    onClick={runPreview}
                  >
                    <CheckCircle2 size={18} aria-hidden="true" />
                    {previewRunning ? p("running") : p("runPreview")}
                  </button>
                  <button
                    type="button"
                    disabled={!canCreatePreview || optimizerRunning}
                    onClick={runOptimizer}
                  >
                    <CheckCircle2 size={18} aria-hidden="true" />
                    {optimizerRunning ? p("running") : p("runOptimizer")}
                  </button>
                </div>
              ) : null}
              {!canCreatePreview ? <p role="status">{p("createPermissionRequired")}</p> : null}
              {previewError ? <p role="alert">{previewError}</p> : null}
            </div>

            {engineResult?.planogram ? (
              <div role="status" aria-live="polite" aria-atomic="true">
                <p>{p("productionReleaseBlocked")}</p>
                <PlanogramDigitalTwin
                  engineResult={engineResult}
                  candidate={candidate}
                  locale={locale}
                  formatNumber={formatNumber}
                />
              </div>
            ) : preview ? (
              <div className="planogram-native__preview-empty" role="status" aria-live="polite" aria-atomic="true">
                <p>{p("productionReleaseBlocked")}</p>
                <p>{p("previewEmpty")}</p>
              </div>
            ) : (
              <div className="planogram-native__preview-empty">
                <p>{p("previewEmpty")}</p>
              </div>
            )}
          </section>

          <PlanogramOperationsPanel data={data} t={o} />
        </div>
      ) : null}
    </main>
  );
}
