import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowUpRight, CheckCircle2, ClipboardList, RefreshCw, ShieldCheck } from "lucide-react";

import { apiGet, apiPatch } from "../../api/client.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import "./AuditActionsWorkspace.css";

function localized(value, locale) {
  if (!value || typeof value !== "object") return "";
  const raw = String(locale || "tr");
  return value[raw] || value[raw.split("-")[0]] || value.en || value.tr || "";
}

function originLabel(action, locale) {
  const field = action?.origin_field || {};
  return localized(field.question_i18n, locale)
    || localized(field.label_i18n, locale)
    || localized(field.name_i18n, locale)
    || localized(field.title_i18n, locale)
    || field.question || field.label || field.title || action?.item_key || "—";
}

function nextTransition(action, canAction) {
  if (!action) return null;
  if (action.status === "open" && canAction("audit", "updateAction")) return { status: "in_progress", messageKey: "actionStart" };
  if (action.status === "in_progress" && canAction("audit", "updateAction")) return { status: "submitted_for_verification", messageKey: "actionSubmit", evidence: true };
  if (action.status === "submitted_for_verification" && canAction("audit", "verifyAction")) return { status: "human_verified", messageKey: "actionVerify", evidence: true, receipt: true };
  if (action.status === "human_verified" && canAction("audit", "verifyAction")) return { status: "closed", messageKey: "actionClose", evidence: true, receipt: true };
  return null;
}

export default function AuditActionsWorkspace({ locale, t, refreshKey = 0 }) {
  const { canAction } = useAuth();
  const [state, setState] = useState({ loading: true, error: "", actions: [] });
  const [selectedId, setSelectedId] = useState(null);
  const [form, setForm] = useState({ closureEvidenceRef: "", verificationReceiptRef: "" });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const actions = await apiGet("/v1/audit/actions?limit=200");
      if (!Array.isArray(actions)) throw new Error("Invalid Audit actions payload");
      setState({ loading: false, error: "", actions });
      setSelectedId((current) => current && actions.some((action) => action.id === current) ? current : actions[0]?.id || null);
    } catch (error) {
      setState({ loading: false, error: error?.message || t("actionSaveError"), actions: [] });
    }
  }, [t]);

  useEffect(() => { load(); }, [load, refreshKey]);
  const selected = useMemo(() => state.actions.find((action) => action.id === selectedId) || null, [selectedId, state.actions]);
  useEffect(() => {
    setForm({ closureEvidenceRef: selected?.closure_evidence_ref || "", verificationReceiptRef: selected?.verification_receipt_ref || "" });
  }, [selected]);
  const transition = nextTransition(selected, canAction);

  async function advance() {
    if (!transition || saving) return;
    setSaving(true);
    try {
      await apiPatch(`/v1/audit/actions/${selected.id}`, {
        expected_version: selected.version,
        status: transition.status,
        closure_evidence_ref: form.closureEvidenceRef.trim() || null,
        verification_receipt_ref: form.verificationReceiptRef.trim() || null,
      });
      await load();
    } catch (error) {
      setState((current) => ({ ...current, error: error?.message || t("actionSaveError") }));
    } finally { setSaving(false); }
  }

  function goToOrigin() {
    document.getElementById(`audit-run-${selected?.audit_run_id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  return (
    <section className="audit-actions" id="audit-actions">
      <div className="audit-section__heading">
        <div><span className="audit-kicker">{t("actions")}</span><h2>{t("actionsTitle")}</h2><p>{t("actionsSubtitle")}</p></div>
        <button className="audit-text-action" type="button" onClick={load} disabled={state.loading}><RefreshCw size={15} /> {t("assuranceRefresh")}</button>
      </div>
      {state.error ? <div className="audit-modal__error" role="alert">{state.error}</div> : null}
      <div className="audit-actions__layout">
        <div className="audit-actions__list">
          {state.loading ? <div className="audit-actions__empty">{t("assuranceLoading")}</div> : null}
          {!state.loading && !state.actions.length ? <div className="audit-actions__empty">{t("actionNoCases")}</div> : null}
          {state.actions.map((action) => (
            <button type="button" key={action.id} className={action.id === selectedId ? "is-active" : ""} onClick={() => setSelectedId(action.id)}>
              <span className={`audit-actions__priority audit-actions__priority--${action.priority}`} />
              <span><strong>{action.title}</strong><small>{action.location_name || action.location_id} · {action.item_key}</small></span>
              <em>{String(action.status).replaceAll("_", " ")}</em>
            </button>
          ))}
        </div>
        {selected ? (
          <article className="audit-actions__detail">
            <div className="audit-actions__detail-head"><ClipboardList size={22} /><div><h3>{selected.title}</h3><span>{selected.program_key} · v{selected.program_version}</span></div></div>
            <p>{selected.description}</p>
            <dl><div><dt>{t("status")}</dt><dd>{String(selected.status).replaceAll("_", " ")}</dd></div><div><dt>{t("priority")}</dt><dd>{selected.priority}</dd></div><div><dt>{t("assignee")}</dt><dd>{selected.assignee_subject || "—"}</dd></div><div><dt>{t("dueDate")}</dt><dd>{new Date(selected.due_at).toLocaleString(locale)}</dd></div></dl>
            <div className="audit-actions__origin"><span>{t("originalQuestion")}</span><strong>{originLabel(selected, locale)}</strong><button type="button" onClick={goToOrigin}>{t("actionOrigin")} <ArrowUpRight size={14} /></button></div>
            {transition?.evidence ? <label>{t("actionClosureEvidence")}<input value={form.closureEvidenceRef} onChange={(event) => setForm((current) => ({ ...current, closureEvidenceRef: event.target.value }))} maxLength={500} required /></label> : null}
            {transition?.receipt ? <label>{t("actionVerificationReceipt")}<input value={form.verificationReceiptRef} onChange={(event) => setForm((current) => ({ ...current, verificationReceiptRef: event.target.value }))} maxLength={500} required /></label> : null}
            {transition ? <button className="audit-btn audit-btn--primary" type="button" onClick={advance} disabled={saving || (transition.evidence && !form.closureEvidenceRef.trim()) || (transition.receipt && !form.verificationReceiptRef.trim())}>{transition.status === "closed" ? <CheckCircle2 size={16} /> : <ShieldCheck size={16} />}{t(transition.messageKey)}</button> : <div className="audit-actions__readonly">{t("actionReadOnly")}</div>}
          </article>
        ) : <div className="audit-actions__empty">{t("actionSelect")}</div>}
      </div>
    </section>
  );
}
