import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bot,
  CheckCircle2,
  ClipboardCheck,
  RefreshCw,
  Scale,
  ShieldAlert,
  ShieldCheck,
  UserRoundCheck,
} from "lucide-react";

import { apiGet, apiPost } from "../../api/client.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import "./AuditAssuranceWorkspace.css";

const MANAGER_STATES = new Set(["MANAGER_REVIEW", "MANAGER_UNASSIGNED"]);
const STANDARDS_STATES = new Set([
  "OPERATIONS_STANDARDS_REVIEW",
  "OPERATIONS_STANDARDS_UNASSIGNED",
]);

function humanState(value) {
  return String(value || "—").replaceAll("_", " ");
}

function percentage(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Number(value).toFixed(1)}%`;
}

function caseTone(state) {
  if (state === "RESOLVED") return "resolved";
  if (String(state || "").includes("UNASSIGNED")) return "unassigned";
  if (String(state || "").includes("STANDARDS")) return "standards";
  return "manager";
}

function AssuranceStatePill({ state }) {
  return <span className={`audit-assurance-pill audit-assurance-pill--${caseTone(state)}`}>{humanState(state)}</span>;
}

function AuditorCalibrationTable({ rows, t }) {
  if (!rows.length) {
    return <div className="audit-assurance-empty">{t("assuranceNoCalibration")}</div>;
  }

  return (
    <div className="audit-assurance-table-wrap">
      <table className="audit-assurance-table">
        <thead>
          <tr>
            <th>{t("assuranceAuditor")}</th>
            <th>{t("assuranceComparable")}</th>
            <th>{t("assuranceAgreement")}</th>
            <th>{t("assuranceDisagreements")}</th>
            <th>{t("assuranceManagerAi")}</th>
            <th>{t("assuranceManagerAuditor")}</th>
            <th>{t("assuranceStandardsReviewed")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.auditor_subject}>
              <td><strong>{row.auditor_subject || "—"}</strong></td>
              <td>{row.comparable_items ?? 0}</td>
              <td><span className="audit-assurance-score">{percentage(row.agreement_percent)}</span></td>
              <td>{row.disagreements ?? 0}</td>
              <td>{row.manager_ai_confirmed ?? 0}</td>
              <td>{row.manager_auditor_confirmed ?? 0}</td>
              <td>{row.standards_reviewed ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DecisionComposer({ selectedCase, onSaved, t }) {
  const { user, canAction } = useAuth();
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setReason("");
    setError("");
  }, [selectedCase?.id]);

  if (!selectedCase) {
    return (
      <div className="audit-assurance-decision audit-assurance-decision--empty">
        <ShieldCheck size={24} />
        <strong>{t("assuranceSelectCase")}</strong>
        <p>{t("assuranceSelectCaseBody")}</p>
      </div>
    );
  }

  const isAssignedManager =
    selectedCase.state === "MANAGER_REVIEW" &&
    selectedCase.manager_subject &&
    selectedCase.manager_subject === user?.subject &&
    canAction("audit", "reviewDisagreement");
  const canStandardsReview =
    STANDARDS_STATES.has(selectedCase.state) &&
    canAction("audit", "manageStandards");

  async function submit(disposition) {
    if (!reason.trim() || saving) return;
    setSaving(true);
    setError("");
    try {
      const endpoint = isAssignedManager
        ? `/v1/audit/assurance/cases/${selectedCase.id}/manager-decision`
        : `/v1/audit/assurance/cases/${selectedCase.id}/standards-decision`;
      await apiPost(endpoint, {
        expected_version: selectedCase.version,
        disposition,
        reason: reason.trim(),
      });
      setReason("");
      await onSaved();
    } catch (requestError) {
      setError(requestError?.message || t("assuranceSaveError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="audit-assurance-decision">
      <div className="audit-assurance-decision__head">
        <div>
          <span>{selectedCase.location_name || selectedCase.location_id || "—"}</span>
          <strong>{selectedCase.item_key}</strong>
        </div>
        <AssuranceStatePill state={selectedCase.state} />
      </div>

      <div className="audit-assurance-compare">
        <article>
          <Bot size={18} />
          {/* i18n-data-literal: canonical decision-source identifier emitted by the Audit API. */}
          <span>AI</span>
          <strong>{selectedCase.ai_decision || "—"}</strong>
        </article>
        <Scale className="audit-assurance-compare__vs" size={18} aria-hidden="true" />
        <article>
          <ClipboardCheck size={18} />
          <span>{t("assuranceAuditor")}</span>
          <strong>{selectedCase.auditor_decision || "—"}</strong>
        </article>
      </div>

      <dl className="audit-assurance-meta">
        <div><dt>{t("assuranceAuditor")}</dt><dd>{selectedCase.auditor_subject || "—"}</dd></div>
        <div><dt>{t("assuranceManager")}</dt><dd>{selectedCase.manager_subject || t("assuranceUnassigned")}</dd></div>
        <div><dt>{t("locations")}</dt><dd>{selectedCase.location_name || selectedCase.location_id || "—"}</dd></div>
        <div><dt>{t("assuranceVersion")}</dt><dd>v{selectedCase.version}</dd></div>
      </dl>

      {isAssignedManager || canStandardsReview ? (
        <>
          <label className="audit-assurance-reason">
            <span>{t("assuranceReason")}</span>
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder={t("assuranceReasonPlaceholder")}
              maxLength={4000}
              disabled={saving}
            />
          </label>
          {error ? <div className="audit-assurance-error" role="alert">{error}</div> : null}

          {isAssignedManager ? (
            <div className="audit-assurance-decision__actions">
              <button type="button" disabled={!reason.trim() || saving} onClick={() => submit("AI_CONFIRMED")}>
                <Bot size={16} /> {t("assuranceConfirmAi")}
              </button>
              <button type="button" disabled={!reason.trim() || saving} onClick={() => submit("AUDITOR_CONFIRMED")}>
                <UserRoundCheck size={16} /> {t("assuranceConfirmAuditor")}
              </button>
            </div>
          ) : null}

          {canStandardsReview ? (
            <div className="audit-assurance-standards-actions">
              {[
                ["AI_CONFIRMED", "assuranceConfirmAi"],
                ["AUDITOR_CONFIRMED", "assuranceConfirmAuditor"],
                ["STANDARD_CHANGED", "assuranceStandardChanged"],
                ["MODEL_REVIEW_REQUIRED", "assuranceModelReview"],
                ["NO_CHANGE", "assuranceNoChange"],
              ].map(([value, key]) => (
                <button key={value} type="button" disabled={!reason.trim() || saving} onClick={() => submit(value)}>
                  {t(key)}
                </button>
              ))}
            </div>
          ) : null}
        </>
      ) : (
        <div className="audit-assurance-readonly">
          <ShieldCheck size={17} /> {t("assuranceReadOnly")}
        </div>
      )}
    </div>
  );
}

export default function AuditAssuranceWorkspace({ locale, t }) {
  const [state, setState] = useState("loading");
  const [cases, setCases] = useState([]);
  const [auditors, setAuditors] = useState([]);
  const [selectedId, setSelectedId] = useState(null);

  const refresh = useCallback(async () => {
    setState("loading");
    try {
      const [casePayload, auditorPayload] = await Promise.all([
        apiGet("/v1/audit/assurance/cases?limit=200"),
        apiGet("/v1/audit/assurance/auditors"),
      ]);
      if (!Array.isArray(casePayload) || !Array.isArray(auditorPayload)) {
        throw new Error("Invalid assurance payload");
      }
      setCases(casePayload);
      setAuditors(auditorPayload);
      setSelectedId((current) => {
        if (current && casePayload.some((item) => String(item.id) === String(current))) return current;
        return casePayload.find((item) => item.state !== "RESOLVED")?.id || casePayload[0]?.id || null;
      });
      setState(casePayload.length || auditorPayload.length ? "connected" : "connected-empty");
    } catch {
      setCases([]);
      setAuditors([]);
      setSelectedId(null);
      setState("error");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const selectedCase = useMemo(
    () => cases.find((item) => String(item.id) === String(selectedId)) || null,
    [cases, selectedId],
  );
  const metrics = useMemo(() => ({
    manager: cases.filter((item) => MANAGER_STATES.has(item.state)).length,
    standards: cases.filter((item) => STANDARDS_STATES.has(item.state)).length,
    unassigned: cases.filter((item) => String(item.state || "").includes("UNASSIGNED")).length,
    resolved: cases.filter((item) => item.state === "RESOLVED").length,
  }), [cases]);

  return (
    <section className="audit-assurance-workspace" id="audit-assurance" data-assurance-state={state}>
      <header className="audit-assurance-workspace__head">
        <div>
          <span className="audit-kicker">{t("assuranceKicker")}</span>
          <h2>{t("assuranceTitle")}</h2>
          <p>{t("assuranceSubtitle")}</p>
        </div>
        <button type="button" className="audit-assurance-refresh" onClick={refresh} disabled={state === "loading"}>
          <RefreshCw size={16} className={state === "loading" ? "is-spinning" : ""} /> {t("assuranceRefresh")}
        </button>
      </header>

      {state === "error" ? (
        <div className="audit-assurance-state" role="alert">
          <ShieldAlert size={22} />
          <div><strong>{t("assuranceLoadError")}</strong><span>{t("assuranceLoadErrorBody")}</span></div>
        </div>
      ) : null}

      {state !== "error" ? (
        <>
          <div className="audit-assurance-metrics" aria-label={t("assuranceTitle")}>
            {[
              [Scale, "assuranceManagerQueue", metrics.manager],
              [ShieldCheck, "assuranceStandardsQueue", metrics.standards],
              [ShieldAlert, "assuranceUnassignedQueue", metrics.unassigned],
              [CheckCircle2, "assuranceResolved", metrics.resolved],
            ].map(([Icon, key, value]) => (
              <article key={key}>
                <Icon size={18} />
                <span>{t(key)}</span>
                <strong>{state === "loading" ? "—" : value}</strong>
              </article>
            ))}
          </div>

          <div className="audit-assurance-workspace__grid">
            <div className="audit-assurance-cases">
              <div className="audit-assurance-section-head">
                <div><span>{t("assuranceCases")}</span><strong>{state === "loading" ? "—" : cases.length}</strong></div>
              </div>
              {state === "loading" ? <div className="audit-assurance-empty">{t("assuranceLoading")}</div> : null}
              {state !== "loading" && !cases.length ? <div className="audit-assurance-empty">{t("assuranceNoCases")}</div> : null}
              {cases.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`audit-assurance-case ${String(item.id) === String(selectedId) ? "is-selected" : ""}`}
                  onClick={() => setSelectedId(item.id)}
                >
                  <div className="audit-assurance-case__top">
                    <strong>{item.location_name || item.location_id || "—"}</strong>
                    <AssuranceStatePill state={item.state} />
                  </div>
                  <span className="audit-assurance-case__item">{item.item_key}</span>
                  <div className="audit-assurance-case__decisions">
                    {/* i18n-data-literal: canonical decision-source identifier emitted by the Audit API. */}
                    <span>AI <strong>{item.ai_decision || "—"}</strong></span>
                    <span>{t("assuranceAuditor")} <strong>{item.auditor_decision || "—"}</strong></span>
                  </div>
                  <time dateTime={item.updated_at || undefined}>
                    {item.updated_at ? new Date(item.updated_at).toLocaleString(locale) : "—"}
                  </time>
                </button>
              ))}
            </div>

            <DecisionComposer selectedCase={selectedCase} onSaved={refresh} t={t} />
          </div>

          <div className="audit-assurance-calibration">
            <div className="audit-assurance-section-head">
              <div>
                <span>{t("assuranceCalibration")}</span>
                <small>{t("assuranceCalibrationBody")}</small>
              </div>
            </div>
            <AuditorCalibrationTable rows={auditors} t={t} />
          </div>
        </>
      ) : null}
    </section>
  );
}
