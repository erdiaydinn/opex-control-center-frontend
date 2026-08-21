import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  BadgeCheck,
  ClipboardCheck,
  RefreshCw,
  Send,
  ShieldAlert,
  Warehouse,
  XCircle,
} from "lucide-react";

import { apiGet, apiPost } from "../../api/client.js";
import { translatePlanogramOperations } from "../../platform/i18n/planogramOperationsMessages.js";
import "./planogram-operations.css";

const ACTIVE_ASSIGNMENT_STATUSES = new Set(["assigned", "acknowledged"]);

function readableDate(value, locale) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(locale || "en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export default function PlanogramOperationsPanel({ locale, formatNumber, canAction }) {
  const t = useMemo(
    () => (key) => translatePlanogramOperations(locale, key),
    [locale]
  );
  const canCreate = canAction("planogram", "create");
  const canEdit = canAction("planogram", "edit");
  const canApprove = canAction("planogram", "approve");

  const [workspace, setWorkspace] = useState(null);
  const [plans, setPlans] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [storeCode, setStoreCode] = useState("");
  const [storeName, setStoreName] = useState("");
  const [notes, setNotes] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextWorkspace, planResult, assignmentResult] = await Promise.all([
        apiGet("/v1/planogram/store-dna/workspace"),
        apiGet("/v1/planogram/execution/plans"),
        apiGet("/v1/planogram/execution/assignments"),
      ]);
      setWorkspace(nextWorkspace);
      setPlans(Array.isArray(planResult?.items) ? planResult.items : []);
      setAssignments(Array.isArray(assignmentResult?.items) ? assignmentResult.items : []);
    } catch {
      setWorkspace(null);
      setPlans([]);
      setAssignments([]);
      setError(t("loadError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    load();
  }, [load]);

  const mutate = useCallback(async (key, request) => {
    if (busy) return;
    setBusy(key);
    setError("");
    setNotice("");
    try {
      await request();
      setNotice(t("operationSuccess"));
      await load();
    } catch {
      setError(t("operationError"));
    } finally {
      setBusy("");
    }
  }, [busy, load, t]);

  const bootstrap = useCallback(async (event) => {
    event.preventDefault();
    if (!storeCode.trim()) return;
    await mutate("bootstrap", () => apiPost("/v1/planogram/store-dna/bootstrap", {
      store_code: storeCode.trim(),
      store_name: storeName.trim() || null,
      source: "warehouse_bootstrap",
    }));
  }, [mutate, storeCode, storeName]);

  const runVersionAction = useCallback(async (version, action) => {
    const note = String(notes[version.id] || "").trim();
    if ((action === "reject" || action === "revise") && note.length < 3) {
      setError(t("reasonRequired"));
      return;
    }
    const payload = action === "approve"
      ? { note: note || null }
      : action === "reject" || action === "revise"
        ? { reason: note }
        : {};
    await mutate(`${version.id}:${action}`, () => (
      apiPost(`/v1/planogram/store-dna/${version.id}/${action}`, payload)
    ));
  }, [mutate, notes, t]);

  const runAssignmentAction = useCallback(async (assignment, action) => {
    await mutate(`${assignment.id}:${action}`, () => (
      apiPost(`/v1/planogram/execution/assignments/${assignment.id}/${action}`, {})
    ));
  }, [mutate]);

  const versions = Array.isArray(workspace?.versions) ? workspace.versions : [];
  const capabilities = workspace?.capabilities || {};

  return (
    <section className="eay-planogram-operations" aria-busy={loading ? "true" : "false"}>
      <header className="eay-planogram-operations-head">
        <div>
          <span>{t("makerChecker")}</span>
          <h2>{t("operationsTitle")}</h2>
          <p>{t("operationsSubtitle")}</p>
        </div>
        <button type="button" onClick={load} disabled={loading || Boolean(busy)}>
          <RefreshCw size={17} aria-hidden="true" />
          {t("retry")}
        </button>
      </header>

      {loading ? (
        <div className="eay-planogram-operations-state" role="status" aria-live="polite">
          <RefreshCw className="spin" size={18} aria-hidden="true" />
          {t("loading")}
        </div>
      ) : null}
      {error ? (
        <div className="eay-planogram-operations-state is-error" role="alert">
          <ShieldAlert size={18} aria-hidden="true" />
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="eay-planogram-operations-state is-success" role="status" aria-live="polite">
          <BadgeCheck size={18} aria-hidden="true" />
          {notice}
        </div>
      ) : null}

      {!loading && workspace ? (
        <div className="eay-planogram-operations-grid">
          <article className="eay-planogram-operations-card">
            <header>
              <div>
                <Warehouse size={20} aria-hidden="true" />
                <div><h3>{t("storeDnaTitle")}</h3><p>{t("storeDnaSubtitle")}</p></div>
              </div>
              <strong>{t("topology")}</strong>
            </header>

            {canCreate && capabilities.create ? (
              <form className="eay-planogram-operations-form" onSubmit={bootstrap}>
                <label>
                  <span>{t("storeCode")}</span>
                  <input value={storeCode} onChange={(event) => setStoreCode(event.target.value)} required />
                </label>
                <label>
                  <span>{t("storeName")}</span>
                  <input value={storeName} onChange={(event) => setStoreName(event.target.value)} />
                </label>
                <button type="submit" disabled={busy === "bootstrap" || !storeCode.trim()}>
                  <Warehouse size={17} aria-hidden="true" />
                  {busy === "bootstrap" ? t("creating") : t("createStoreDna")}
                </button>
              </form>
            ) : null}

            <div className="eay-planogram-operations-list">
              <h4>{t("versions")}</h4>
              {versions.length === 0 ? <p>{t("noVersions")}</p> : versions.map((version) => (
                <div className="eay-planogram-operation-row" key={version.id}>
                  <div>
                    <strong>{version.store_code}</strong>
                    <span>{t("version")} {formatNumber(version.version_number)}</span>
                    <span>{t("status")}: {String(version.status).toUpperCase()}</span>
                    <span>
                      {t("geometry")}: {version.geometry_attested ? t("attested") : t("notAttested")}
                    </span>
                  </div>
                  <label className="eay-planogram-operation-note">
                    <span>{t("reason")}</span>
                    <input
                      value={notes[version.id] || ""}
                      onChange={(event) => setNotes((current) => ({
                        ...current,
                        [version.id]: event.target.value,
                      }))}
                    />
                  </label>
                  <div className="eay-planogram-operation-actions">
                    {version.status === "draft" && canEdit && capabilities.submit ? (
                      <button type="button" onClick={() => runVersionAction(version, "submit")} disabled={Boolean(busy)}>
                        <Send size={16} aria-hidden="true" />{t("submit")}
                      </button>
                    ) : null}
                    {version.status === "submitted" && canApprove && capabilities.approve ? (
                      <>
                        <button type="button" onClick={() => runVersionAction(version, "approve")} disabled={Boolean(busy)}>
                          <BadgeCheck size={16} aria-hidden="true" />{t("approve")}
                        </button>
                        <button type="button" onClick={() => runVersionAction(version, "reject")} disabled={Boolean(busy)}>
                          <XCircle size={16} aria-hidden="true" />{t("reject")}
                        </button>
                      </>
                    ) : null}
                    {["approved", "rejected", "superseded"].includes(version.status) && canEdit ? (
                      <button type="button" onClick={() => runVersionAction(version, "revise")} disabled={Boolean(busy)}>
                        <ClipboardCheck size={16} aria-hidden="true" />{t("revise")}
                      </button>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </article>

          <article className="eay-planogram-operations-card">
            <header>
              <div>
                <ClipboardCheck size={20} aria-hidden="true" />
                <div><h3>{t("executionTitle")}</h3><p>{t("executionSubtitle")}</p></div>
              </div>
              <strong>{t("externalRequired")}</strong>
            </header>

            <div className="eay-planogram-operations-list">
              <h4>{t("plans")}</h4>
              {plans.length === 0 ? <p>{t("noPlans")}</p> : plans.map((planVersion) => (
                <div className="eay-planogram-operation-row compact" key={planVersion.id}>
                  <div>
                    <strong>{planVersion.store_code}</strong>
                    <span>{t("plan")} v{formatNumber(planVersion.version_number)}</span>
                    <span>{t("status")}: {String(planVersion.status).toUpperCase()}</span>
                    <span>
                      {t("evidence")}: {planVersion.physical_truth_attested ? t("attested") : t("externalRequired")}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            <div className="eay-planogram-operations-list">
              <h4>{t("assignments")}</h4>
              {assignments.length === 0 ? <p>{t("noAssignments")}</p> : assignments.map((assignment) => (
                <div className="eay-planogram-operation-row" key={assignment.id}>
                  <div>
                    <strong>{assignment.store_code}</strong>
                    <span>{t("status")}: {String(assignment.status).toUpperCase()}</span>
                    <span>{t("observations")}: {formatNumber(assignment.observation_count || 0)}</span>
                    <span>{t("compliant")}: {formatNumber(assignment.compliant_count || 0)}</span>
                    <span>{t("deviations")}: {formatNumber(assignment.deviation_count || 0)}</span>
                    <span>{t("due")}: {readableDate(assignment.due_at, locale)}</span>
                  </div>
                  <div className="eay-planogram-operation-actions">
                    {assignment.status === "assigned" && canEdit ? (
                      <button type="button" onClick={() => runAssignmentAction(assignment, "acknowledge")} disabled={Boolean(busy)}>
                        <BadgeCheck size={16} aria-hidden="true" />{t("acknowledge")}
                      </button>
                    ) : null}
                    {ACTIVE_ASSIGNMENT_STATUSES.has(assignment.status) && canApprove ? (
                      <button type="button" onClick={() => runAssignmentAction(assignment, "close")} disabled={Boolean(busy)}>
                        <XCircle size={16} aria-hidden="true" />{t("close")}
                      </button>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </article>
        </div>
      ) : null}
    </section>
  );
}
