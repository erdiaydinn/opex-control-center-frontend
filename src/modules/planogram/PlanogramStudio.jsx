import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  BadgeCheck,
  Boxes,
  CheckCircle2,
  ClipboardCheck,
  CopyPlus,
  LockKeyhole,
  RefreshCw,
  Ruler,
  Send,
  ShieldCheck,
  TriangleAlert,
  Warehouse,
  XCircle,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { apiGet, apiPost } from "../../api/client.js";
import { translatePlanogram } from "../../platform/i18n/planogramMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import "./planogram-native.css";

const PLANOGRAM_FEATURES = [
  "layoutView",
  "layoutEdit",
  "fixtureEdit",
  "ruleEdit",
  "productAssign",
  "aiRecommend",
];
const PLANOGRAM_ACTIONS = [
  "view",
  "create",
  "edit",
  "approve",
  "export",
  "delete",
];

export const PLANOGRAM_SECURITY_CONTRACT = Object.freeze({
  features: PLANOGRAM_FEATURES,
  actions: PLANOGRAM_ACTIONS,
  legacyBridgeAllowed: false,
});

const STATUS_KEYS = Object.freeze({
  draft: "statusDraft",
  submitted: "statusSubmitted",
  approved: "statusApproved",
  rejected: "statusRejected",
  superseded: "statusSuperseded",
});

function operationErrorKey(error) {
  const code = String(error?.message || "");
  if (code.includes("maker_checker_required")) return "makerCheckerError";
  if (code.includes("active_draft_or_submission_exists")) return "activeDraftExists";
  return "operationError";
}

export default function PlanogramStudio() {
  const navigate = useNavigate();
  const { locale } = usePlatformPreferences();
  const t = useMemo(() => (key) => translatePlanogram(locale, key), [locale]);
  const [readiness, setReadiness] = useState(null);
  const [workspace, setWorkspace] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [storeCode, setStoreCode] = useState("");
  const [storeName, setStoreName] = useState("");
  const [notes, setNotes] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextReadiness, nextWorkspace] = await Promise.all([
        apiGet("/v1/planogram/readiness"),
        apiGet("/v1/planogram/store-dna/workspace"),
      ]);
      setReadiness(nextReadiness);
      setWorkspace(nextWorkspace);
    } catch {
      setError(t("loadError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const runMutation = useCallback(
    async (busyKey, request, successKey) => {
      setBusy(busyKey);
      setError("");
      setNotice("");
      try {
        await request();
        setNotice(t(successKey));
        await load();
      } catch (mutationError) {
        setError(t(operationErrorKey(mutationError)));
      } finally {
        setBusy("");
      }
    },
    [load, t],
  );

  const bootstrap = async (event) => {
    event.preventDefault();
    const code = storeCode.trim();
    if (!code) {
      setError(t("storeCodeRequired"));
      return;
    }
    await runMutation(
      "bootstrap",
      () =>
        apiPost("/v1/planogram/store-dna/bootstrap", {
          store_code: code,
          store_name: storeName.trim() || null,
          source: "warehouse_bootstrap",
        }),
      "draftCreated",
    );
  };

  const versionAction = async (version, action) => {
    const value = (notes[version.id] || "").trim();
    let payload = {};
    if (action === "reject" || action === "revise") {
      if (value.length < 3) {
        setError(t("reasonRequired"));
        return;
      }
      payload = { reason: value };
    } else if (action === "approve") {
      payload = { note: value || null };
    }
    await runMutation(
      `${version.id}:${action}`,
      () => apiPost(`/v1/planogram/store-dna/${version.id}/${action}`, payload),
      action === "submit"
        ? "submittedSuccess"
        : action === "approve"
          ? "approvedSuccess"
          : action === "reject"
            ? "rejectedSuccess"
            : "revisionCreated",
    );
  };

  const template = workspace?.template;
  const versions = workspace?.versions || [];
  const capabilities = workspace?.capabilities || {};
  const currentSubject = workspace?.subject;

  return (
    <main className="eay-planogram-native">
      <header className="eay-planogram-head">
        <button type="button" onClick={() => navigate("/")} aria-label={t("back")}>
          <ArrowLeft size={18} />
          {t("back")}
        </button>
        <div>
          <span>{t("coreAuthority")}</span>
          <h1>{t("title")}</h1>
          <p>{t("subtitle")}</p>
        </div>
        <span className="eay-planogram-gate">
          <ShieldCheck size={17} />
          {t("securityBoundary")}
        </span>
      </header>

      {loading ? (
        <section className="eay-planogram-state" role="status" aria-live="polite">
          <RefreshCw className="spin" size={20} />
          {t("loading")}
        </section>
      ) : null}
      {error ? (
        <section className="eay-planogram-state eay-planogram-state-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => { setError(""); load(); }}>
            {t("retry")}
          </button>
        </section>
      ) : null}
      {notice ? (
        <section className="eay-planogram-state eay-planogram-state-success" role="status">
          <CheckCircle2 size={19} />
          <span>{notice}</span>
        </section>
      ) : null}

      {readiness && workspace && !loading ? (
        <>
          <section className="eay-planogram-summary" aria-label={t("evidenceState")}>
            <article>
              <Boxes size={21} />
              <span>{t("engine")}</span>
              <strong>{readiness.engine?.contract}</strong>
              <small>{t("libraryMode")}</small>
            </article>
            <article>
              <LockKeyhole size={21} />
              <span>{t("productionBlocked")}</span>
              <strong>{readiness.production_ready ? t("ready") : t("blocked")}</strong>
              <small>{t("solverBlocked")}</small>
            </article>
            <article>
              <CheckCircle2 size={21} />
              <span>{t("securityBoundary")}</span>
              <strong>{readiness.engine?.legacy_bridge_enabled ? t("legacy") : t("core")}</strong>
              <small>{t("legacyOff")}</small>
            </article>
          </section>

          <section className="eay-planogram-store-dna" aria-labelledby="store-dna-title">
            <header className="eay-planogram-section-head">
              <div>
                <span className="eay-planogram-kicker">{t("storeDnaKicker")}</span>
                <h2 id="store-dna-title">{t("storeDnaWorkspace")}</h2>
                <p>{t("storeDnaDescription")}</p>
              </div>
              <span className="eay-planogram-policy">
                <ClipboardCheck size={18} />
                {t("makerChecker")}
              </span>
            </header>

            <div className="eay-planogram-template-grid">
              <article><strong>{template?.aisle_count ?? 11}</strong><span>{t("aisles")}</span></article>
              <article><strong>{(template?.modules_per_side ?? 6) * 2}</strong><span>{t("modulesPerAisle")}</span></article>
              <article><strong>{template?.shelves_per_module ?? 6}</strong><span>{t("shelvesPerModule")}</span></article>
              <article><strong>{template?.module_total ?? 132}</strong><span>{t("totalModules")}</span></article>
              <article><strong>{template?.shelf_total ?? 792}</strong><span>{t("totalShelves")}</span></article>
              <article><strong>{template?.pallet_count ?? 6}</strong><span>{t("palletAreas")}</span></article>
            </div>

            <div className="eay-planogram-callout" role="note">
              <TriangleAlert size={19} />
              <div>
                <strong>{t("topologyNotGeometry")}</strong>
                <p>{t("topologyNotGeometryDetail")}</p>
              </div>
            </div>

            {capabilities.create ? (
              <form className="eay-planogram-bootstrap" onSubmit={bootstrap}>
                <div>
                  <label htmlFor="planogram-store-code">{t("storeCode")}</label>
                  <input
                    id="planogram-store-code"
                    value={storeCode}
                    onChange={(event) => setStoreCode(event.target.value)}
                    placeholder={t("storeCodePlaceholder")}
                    autoComplete="off"
                  />
                </div>
                <div>
                  <label htmlFor="planogram-store-name">{t("storeName")}</label>
                  <input
                    id="planogram-store-name"
                    value={storeName}
                    onChange={(event) => setStoreName(event.target.value)}
                    placeholder={t("storeNamePlaceholder")}
                    autoComplete="off"
                  />
                </div>
                <button type="submit" disabled={busy === "bootstrap"}>
                  <Warehouse size={18} />
                  {busy === "bootstrap" ? t("creating") : t("createStoreDna")}
                </button>
              </form>
            ) : null}

            <div className="eay-planogram-versions">
              <header>
                <div>
                  <h3>{t("versions")}</h3>
                  <p>{t("versionsDescription")}</p>
                </div>
                <button type="button" onClick={load} aria-label={t("refresh")}>
                  <RefreshCw size={17} />
                  {t("refresh")}
                </button>
              </header>

              {versions.length === 0 ? (
                <div className="eay-planogram-empty">
                  <Warehouse size={22} />
                  <strong>{t("noStoreDna")}</strong>
                  <span>{t("noStoreDnaDetail")}</span>
                </div>
              ) : (
                <div className="eay-planogram-version-list">
                  {versions.map((version) => {
                    const ownSubmission =
                      version.status === "submitted" &&
                      version.submitted_by === currentSubject;
                    const isBusy = busy.startsWith(`${version.id}:`);
                    const canRevise =
                      capabilities.edit &&
                      ["rejected", "approved", "superseded"].includes(version.status);
                    return (
                      <article className="eay-planogram-version" key={version.id}>
                        <div className="eay-planogram-version-main">
                          <div className="eay-planogram-version-title">
                            <div>
                              <strong>{version.store_name || version.store_code}</strong>
                              <span>{version.store_code} · {t("versionShort")} {version.version_number}</span>
                            </div>
                            <span className={`eay-planogram-status is-${version.status}`}>
                              {t(STATUS_KEYS[version.status] || "statusUnknown")}
                            </span>
                          </div>
                          <div className="eay-planogram-version-metrics">
                            <span>{version.summary?.aisles ?? 0} {t("aisles")}</span>
                            <span>{version.summary?.modules ?? 0} {t("modules")}</span>
                            <span>{version.summary?.shelves ?? 0} {t("shelves")}</span>
                            <span>{version.summary?.pallets ?? 0} {t("pallets")}</span>
                          </div>
                          <div className={`eay-planogram-attestation ${version.geometry_attested ? "is-attested" : "is-blocked"}`}>
                            {version.geometry_attested ? <BadgeCheck size={18} /> : <Ruler size={18} />}
                            <div>
                              <strong>{version.geometry_attested ? t("geometryAttested") : t("geometryMissing")}</strong>
                              <span>{version.geometry_attested ? t("geometryAttestedDetail") : t("geometryMissingDetail")}</span>
                            </div>
                          </div>
                          {version.rejection_reason ? (
                            <div className="eay-planogram-rejection">
                              <XCircle size={17} />
                              <span>{version.rejection_reason}</span>
                            </div>
                          ) : null}
                        </div>

                        <div className="eay-planogram-version-actions">
                          {(version.status === "submitted" && capabilities.approve) || canRevise ? (
                            <label>
                              <span>{canRevise ? t("revisionReason") : t("reviewNote")}</span>
                              <input
                                value={notes[version.id] || ""}
                                onChange={(event) =>
                                  setNotes((current) => ({ ...current, [version.id]: event.target.value }))
                                }
                                placeholder={canRevise ? t("revisionReasonPlaceholder") : t("reviewNotePlaceholder")}
                              />
                            </label>
                          ) : null}

                          {version.status === "draft" && capabilities.submit ? (
                            <button type="button" disabled={isBusy} onClick={() => versionAction(version, "submit")}>
                              <Send size={17} />
                              {t("submitForApproval")}
                            </button>
                          ) : null}

                          {version.status === "submitted" && capabilities.approve ? (
                            <>
                              {ownSubmission ? <small>{t("anotherApprover")}</small> : null}
                              <button
                                type="button"
                                className="is-primary"
                                disabled={isBusy || ownSubmission}
                                onClick={() => versionAction(version, "approve")}
                              >
                                <BadgeCheck size={17} />
                                {t("approve")}
                              </button>
                              <button
                                type="button"
                                className="is-danger"
                                disabled={isBusy}
                                onClick={() => versionAction(version, "reject")}
                              >
                                <XCircle size={17} />
                                {t("reject")}
                              </button>
                            </>
                          ) : null}

                          {canRevise ? (
                            <button type="button" disabled={isBusy} onClick={() => versionAction(version, "revise")}>
                              <CopyPlus size={17} />
                              {t("createRevision")}
                            </button>
                          ) : null}
                        </div>
                      </article>
                    );
                  })}
                </div>
              )}
            </div>
          </section>

          <section className="eay-planogram-evidence">
            <header>
              <div><Ruler size={22} /><span>{t("physicalTruth")}</span></div>
              <strong>{t("externalRequired")}</strong>
            </header>
            <div className="eay-planogram-evidence-grid">
              {(readiness.physical_truth?.required_evidence || []).map((item) => (
                <article key={item}><TriangleAlert size={18} /><span>{t(item)}</span></article>
              ))}
            </div>
          </section>

          <section className="eay-planogram-generation">
            <LockKeyhole size={24} />
            <div><strong>{t("generationBlocked")}</strong><p>{t("requiredEvidence")}</p></div>
            <button type="button" disabled>{t("solverBlocked")}</button>
          </section>
        </>
      ) : null}
    </main>
  );
}
