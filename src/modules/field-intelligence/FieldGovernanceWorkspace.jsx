import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Download, RefreshCw, Repeat2, ShieldCheck, Target, UserX } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { apiGet, apiPost } from "../../api/client.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import { translateFieldGovernance } from "./fieldGovernanceMessages.js";
import "./field-governance.css";

function localized(value, locale) {
  if (!value || typeof value !== "object") return "";
  return value[locale] || value.en || value.tr || Object.values(value).find(Boolean) || "";
}

export default function FieldGovernanceWorkspace() {
  const navigate = useNavigate();
  const { locale } = usePlatformPreferences();
  const { canAction } = useAuth();
  const g = useMemo(() => (key) => translateFieldGovernance(locale, key), [locale]);
  const [bootstrap, setBootstrap] = useState(null);
  const [promotions, setPromotions] = useState([]);
  const [missionId, setMissionId] = useState("");
  const [criterion, setCriterion] = useState("field.overdue");
  const [targetPreview, setTargetPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [recurrence, setRecurrence] = useState({
    cadence: "weekly",
    interval_count: 1,
    timezone: "Europe/Istanbul",
    window_minutes: 120,
    effective_from: "",
    effective_until: "",
  });
  const [exemption, setExemption] = useState({
    location_id: "",
    reason_code: "operational_exception",
    reason: "",
    evidence_ref: "",
  });
  const [exportFormat, setExportFormat] = useState("xlsx");

  const canRecurrence = canAction("field_intelligence", "manageRecurrence");
  const canExempt = canAction("field_intelligence", "exemptTarget");
  const canExport = canAction("field_intelligence", "exportResults");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [fieldBootstrap, promotionResult] = await Promise.all([
        apiGet("/v1/field/bootstrap"),
        apiGet("/v1/field/promotions?limit=100").catch(() => ({ items: [] })),
      ]);
      setBootstrap(fieldBootstrap);
      setPromotions(promotionResult?.items || []);
    } catch {
      setError(g("error"));
    } finally {
      setLoading(false);
    }
  }, [g]);

  useEffect(() => {
    load();
  }, [load]);

  const missions = bootstrap?.missions || [];
  const selectedMission = missions.find((item) => item.id === missionId) || null;
  const targets = selectedMission?.targets || [];

  const run = async (operation, successMessage = g("saved")) => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await operation();
      setMessage(successMessage);
      await load();
      return result;
    } catch {
      setError(g("error"));
      return null;
    } finally {
      setBusy(false);
    }
  };

  async function previewTargets() {
    setBusy(true);
    setError("");
    try {
      setTargetPreview(await apiGet(`/v1/field/governance/targeting/${encodeURIComponent(criterion)}`));
    } catch {
      setError(g("error"));
    } finally {
      setBusy(false);
    }
  }

  async function saveRecurrence(event) {
    event.preventDefault();
    if (!missionId) return;
    await run(() => apiPost(`/v1/field/governance/missions/${encodeURIComponent(missionId)}/recurrence`, {
      cadence: recurrence.cadence,
      interval_count: Number(recurrence.interval_count),
      timezone: recurrence.timezone,
      window_minutes: Number(recurrence.window_minutes),
      effective_from: new Date(recurrence.effective_from).toISOString(),
      effective_until: recurrence.effective_until ? new Date(recurrence.effective_until).toISOString() : null,
    }));
  }

  async function exemptTarget(event) {
    event.preventDefault();
    if (!missionId || !exemption.location_id) return;
    const result = await run(() => apiPost(
      `/v1/field/governance/missions/${encodeURIComponent(missionId)}/targets/${encodeURIComponent(exemption.location_id)}/exempt`,
      {
        reason_code: exemption.reason_code,
        reason: exemption.reason,
        evidence_ref: exemption.evidence_ref || null,
      },
    ));
    if (result) setExemption((current) => ({ ...current, reason: "", evidence_ref: "" }));
  }

  async function requestExport(event) {
    event.preventDefault();
    await run(
      () => apiPost("/v1/field/governance/exports", {
        format: exportFormat,
        mission_id: missionId || null,
      }),
      g("pendingApproval"),
    );
  }

  return (
    <main className="eay-field-governance-shell">
      <header className="eay-field-governance-header">
        <div>
          <span className="eay-field-governance-eyebrow"><ShieldCheck aria-hidden="true" size={18} />{g("title")}</span>
          <h1>{g("title")}</h1>
          <p>{g("subtitle")}</p>
        </div>
        <div className="eay-field-governance-header-actions">
          <button type="button" onClick={load} disabled={busy}><RefreshCw aria-hidden="true" size={18} />{g("refresh")}</button>
          <button type="button" onClick={() => navigate("/field-intelligence")}><ArrowLeft aria-hidden="true" size={18} />{g("back")}</button>
        </div>
      </header>

      {loading ? <section role="status" aria-busy="true" data-eay-product-state="loading">{g("loading")}</section> : null}
      {error ? <section role="alert" data-eay-product-state="error">{error}</section> : null}
      {message ? <section role="status" className="eay-field-governance-success">{message}</section> : null}

      {!loading ? (
        <>
          <section className="eay-field-governance-card">
            <label>
              <span>{g("mission")}</span>
              <select value={missionId} onChange={(event) => { setMissionId(event.target.value); setExemption((current) => ({ ...current, location_id: "" })); }}>
                <option value="">—</option>
                {missions.map((mission) => (
                  <option key={mission.id} value={mission.id}>{localized(mission.title_i18n, locale) || mission.template_id}</option>
                ))}
              </select>
            </label>
            {missions.length === 0 ? <p data-eay-product-state="empty">{g("noMission")}</p> : null}
          </section>

          <section className="eay-field-governance-grid">
            <article className="eay-field-governance-card">
              <h2><Target aria-hidden="true" size={20} />{g("targeting")}</h2>
              <label><span>{g("criterion")}</span>
                <select value={criterion} onChange={(event) => setCriterion(event.target.value)}>
                  <option value="field.overdue">{g("overdue")}</option>
                  <option value="field.rework">{g("rework")}</option>
                  <option value="field.unseen">{g("unseen")}</option>
                </select>
              </label>
              <button type="button" onClick={previewTargets} disabled={busy}>{g("preview")}</button>
              {targetPreview ? <output>{g("targetCount")}: {targetPreview.target_count}</output> : null}
            </article>

            <article className="eay-field-governance-card">
              <h2><Repeat2 aria-hidden="true" size={20} />{g("recurrence")}</h2>
              <form onSubmit={saveRecurrence}>
                <label><span>{g("cadence")}</span><select value={recurrence.cadence} onChange={(event) => setRecurrence((current) => ({ ...current, cadence: event.target.value }))}><option value="daily">{g("daily")}</option><option value="weekly">{g("weekly")}</option><option value="monthly">{g("monthly")}</option></select></label>
                <label><span>{g("interval")}</span><input type="number" min="1" max="52" value={recurrence.interval_count} onChange={(event) => setRecurrence((current) => ({ ...current, interval_count: event.target.value }))} /></label>
                <label><span>{g("timezone")}</span><input value={recurrence.timezone} onChange={(event) => setRecurrence((current) => ({ ...current, timezone: event.target.value }))} /></label>
                <label><span>{g("window")}</span><input type="number" min="5" max="10080" value={recurrence.window_minutes} onChange={(event) => setRecurrence((current) => ({ ...current, window_minutes: event.target.value }))} /></label>
                <label><span>{g("effectiveFrom")}</span><input type="datetime-local" required value={recurrence.effective_from} onChange={(event) => setRecurrence((current) => ({ ...current, effective_from: event.target.value }))} /></label>
                <label><span>{g("effectiveUntil")}</span><input type="datetime-local" value={recurrence.effective_until} onChange={(event) => setRecurrence((current) => ({ ...current, effective_until: event.target.value }))} /></label>
                <button type="submit" disabled={!missionId || !canRecurrence || busy}>{g("saveRecurrence")}</button>
              </form>
            </article>

            <article className="eay-field-governance-card">
              <h2><UserX aria-hidden="true" size={20} />{g("exemption")}</h2>
              <form onSubmit={exemptTarget}>
                <label><span>{g("location")}</span><select required value={exemption.location_id} onChange={(event) => setExemption((current) => ({ ...current, location_id: event.target.value }))}><option value="">—</option>{targets.map((target) => <option key={target.location_id} value={target.location_id}>{target.location_name || target.location_id}</option>)}</select></label>
                <label><span>{g("reasonCode")}</span><input required value={exemption.reason_code} onChange={(event) => setExemption((current) => ({ ...current, reason_code: event.target.value }))} /></label>
                <label><span>{g("reason")}</span><textarea required rows="3" value={exemption.reason} onChange={(event) => setExemption((current) => ({ ...current, reason: event.target.value }))} /></label>
                <label><span>{g("evidenceRef")}</span><input value={exemption.evidence_ref} onChange={(event) => setExemption((current) => ({ ...current, evidence_ref: event.target.value }))} /></label>
                <button type="submit" disabled={!missionId || !canExempt || busy}>{g("exempt")}</button>
              </form>
            </article>

            <article className="eay-field-governance-card">
              <h2><Download aria-hidden="true" size={20} />{g("export")}</h2>
              <form onSubmit={requestExport}>
                <label><span>{g("format")}</span><select value={exportFormat} onChange={(event) => setExportFormat(event.target.value)}><option value="xlsx">XLSX</option><option value="csv">CSV</option><option value="json">JSON</option></select></label>
                <button type="submit" disabled={!canExport || busy}>{g("requestExport")}</button>
              </form>
            </article>
          </section>

          <section className="eay-field-governance-card">
            <h2>{g("promotions")}</h2>
            <p className="eay-field-governance-boundary">{g("truthBoundary")}</p>
            {promotions.length === 0 ? <p data-eay-product-state="empty">{g("noPromotions")}</p> : (
              <div className="eay-field-governance-promotions">
                {promotions.map((item) => (
                  <article key={item.id}>
                    <strong>{item.consumer_module}</strong>
                    <span>{item.adapter_key}</span>
                    <span>{item.state}</span>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      ) : null}
    </main>
  );
}
