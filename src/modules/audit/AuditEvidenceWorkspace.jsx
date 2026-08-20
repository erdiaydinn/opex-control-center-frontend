import React, { useEffect, useMemo, useState } from "react";
import { Camera, CheckCircle2, FileLock2, ShieldAlert, Upload, Video } from "lucide-react";

import { apiFetch, apiGet, apiPatch, apiPost } from "../../api/client.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import "./AuditEvidenceWorkspace.css";

async function sha256Hex(file) {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export default function AuditEvidenceWorkspace({ runs, locale, t, onActionsChanged }) {
  const { canAction } = useAuth();
  const eligibleRuns = useMemo(() => runs.filter((run) => run.status !== "cancelled"), [runs]);
  const [actions, setActions] = useState([]);
  const [form, setForm] = useState({ runId: "", itemKey: "", sourceFingerprint: "", privacyPolicy: "audit-privacy-v1", detectorModel: "device-redaction:unverified", canonicalFrames: 1, processedFrames: 1, faceBlurConfirmed: false, actionId: "" });
  const [file, setFile] = useState(null);
  const [state, setState] = useState({ saving: false, error: "", storage: null, binding: null });

  useEffect(() => {
    setForm((current) => current.runId || !eligibleRuns[0] ? current : { ...current, runId: String(eligibleRuns[0].id) });
  }, [eligibleRuns]);
  useEffect(() => {
    if (!canAction("audit", "updateAction")) return;
    apiGet("/v1/audit/actions?limit=200").then(setActions).catch(() => setActions([]));
  }, [canAction]);

  const selectedRun = eligibleRuns.find((run) => String(run.id) === form.runId);
  const isVideo = Boolean(file?.type?.startsWith("video/"));
  const framesComplete = Number(form.canonicalFrames) > 0 && Number(form.canonicalFrames) === Number(form.processedFrames);
  const canUpload = canAction("audit", "submitEvidence") && selectedRun && file && file.type === "image/jpeg" && Number(form.canonicalFrames) === 1 && form.itemKey.trim() && /^[0-9a-f]{64}$/.test(form.sourceFingerprint) && form.faceBlurConfirmed && framesComplete;

  async function submit(event) {
    event.preventDefault();
    if (!canUpload || state.saving) return;
    setState({ saving: true, error: "", storage: null, binding: null });
    try {
      const contentSha = await sha256Hex(file);
      const submissionId = crypto.randomUUID();
      const storage = await apiFetch(`/v1/audit/runs/${selectedRun.id}/evidence-objects/${encodeURIComponent(form.itemKey.trim())}?client_submission_id=${submissionId}`, {
        method: "POST",
        headers: { "Content-Type": "image/jpeg", "X-EAY-Content-SHA256": contentSha },
        body: file,
      });
      const binding = await apiPost(`/v1/audit/runs/${selectedRun.id}/redaction-receipts`, {
        field_evidence_receipt_id: storage.receipt_id,
        source_fingerprint: form.sourceFingerprint,
        privacy_policy_version: form.privacyPolicy.trim(),
        detector_model_ref: form.detectorModel.trim(),
      });
      if (form.actionId) {
        const action = actions.find((candidate) => String(candidate.id) === form.actionId);
        if (action) {
          await apiPatch(`/v1/audit/actions/${action.id}`, {
            expected_version: action.version,
            status: action.status,
            closure_evidence_ref: binding.redacted_evidence_ref,
            verification_receipt_ref: action.verification_receipt_ref || null,
          });
          onActionsChanged?.();
        }
      }
      setState({ saving: false, error: "", storage, binding });
    } catch (error) {
      setState({ saving: false, error: error?.message || t("evidenceError"), storage: null, binding: null });
    }
  }

  return (
    <section className="audit-evidence" id="audit-evidence">
      <div className="audit-section__heading"><div><span className="audit-kicker">{t("evidence")}</span><h2>{t("evidenceTitle")}</h2><p>{t("evidenceSubtitle")}</p></div><FileLock2 size={25} /></div>
      <form className="audit-evidence__form" onSubmit={submit}>
        <label>{t("auditRun")}<select value={form.runId} onChange={(e) => setForm((current) => ({ ...current, runId: e.target.value }))} required><option value="">{t("noRuns")}</option>{eligibleRuns.map((run) => <option key={run.id} value={run.id}>{run.location_name || run.location_id} · {run.program_key} · {new Date(run.started_at).toLocaleString(locale)}</option>)}</select></label>
        <label>{t("auditItemKey")}<input value={form.itemKey} onChange={(e) => setForm((current) => ({ ...current, itemKey: e.target.value }))} maxLength={180} required /></label>
        <label className="audit-evidence__file">{t("sanitizedFile")}<input type="file" accept="image/jpeg,video/*" onChange={(e) => { setFile(e.target.files?.[0] || null); setState({ saving: false, error: "", storage: null, binding: null }); }} required /><span>{isVideo ? <Video size={18} /> : <Camera size={18} />}{file?.name || "JPEG / video"}</span></label>
        <label>{t("sourceFingerprint")}<input value={form.sourceFingerprint} onChange={(e) => setForm((current) => ({ ...current, sourceFingerprint: e.target.value.toLowerCase().trim() }))} pattern="[0-9a-f]{64}" maxLength={64} required /></label>
        <label>{t("privacyPolicy")}<input value={form.privacyPolicy} onChange={(e) => setForm((current) => ({ ...current, privacyPolicy: e.target.value }))} required /></label>
        <label>{t("detectorModel")}<input value={form.detectorModel} onChange={(e) => setForm((current) => ({ ...current, detectorModel: e.target.value }))} required /></label>
        <label>{t("canonicalFrames")}<input type="number" min="1" value={form.canonicalFrames} onChange={(e) => setForm((current) => ({ ...current, canonicalFrames: e.target.value }))} /></label>
        <label>{t("processedFrames")}<input type="number" min="1" value={form.processedFrames} onChange={(e) => setForm((current) => ({ ...current, processedFrames: e.target.value }))} /></label>
        <label>{t("attachAction")}<select value={form.actionId} onChange={(e) => setForm((current) => ({ ...current, actionId: e.target.value }))}><option value="">—</option>{actions.filter((action) => String(action.audit_run_id) === form.runId && action.item_key === form.itemKey.trim()).map((action) => <option key={action.id} value={action.id}>{action.title}</option>)}</select></label>
        <label className="audit-evidence__confirm"><input type="checkbox" checked={form.faceBlurConfirmed} onChange={(e) => setForm((current) => ({ ...current, faceBlurConfirmed: e.target.checked }))} />{t("faceBlurConfirm")}</label>
        {!framesComplete ? <div className="audit-evidence__blocked"><ShieldAlert size={17} />{t("frameMismatch")}</div> : null}
        {isVideo ? <div className="audit-evidence__blocked"><Video size={17} /><div><strong>{t("videoHold")}</strong><span>{t("videoHoldBody")}</span></div></div> : null}
        <button className="audit-btn audit-btn--primary" type="submit" disabled={!canUpload || state.saving}><Upload size={16} />{state.saving ? t("evidenceUploading") : t("evidenceUpload")}</button>
      </form>
      {state.error ? <div className="audit-modal__error" role="alert">{state.error}</div> : null}
      {state.storage ? <div className="audit-evidence__receipt"><CheckCircle2 size={17} /><span>{t("storageReceipt")}</span><code>{state.storage.receipt_id}</code></div> : null}
      {state.binding ? <><div className="audit-evidence__receipt"><CheckCircle2 size={17} /><span>{t("redactionBound")}</span><code>{state.binding.id}</code></div><div className="audit-evidence__hold"><ShieldAlert size={19} /><div><strong>{t("privacyHold")}</strong><span>{t("privacyHoldBody")}</span></div></div></> : null}
    </section>
  );
}
