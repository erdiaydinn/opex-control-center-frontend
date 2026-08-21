import React, { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarClock, CheckCircle2, Clock3, RefreshCw, ShieldCheck, Sparkles, Users } from "lucide-react";

import { useAuth } from "../../auth/AuthContext.jsx";
import { workforceFlexibilityMessage } from "../../platform/i18n/workforceFlexibilityMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import WorkforceShiftTradePanel from "./WorkforceShiftTradePanel.jsx";
import {
  claimWorkforceOpenShift,
  loadWorkforceFlexibility,
  saveWorkforceAvailability,
} from "./workforceFlexibilityApi.js";
import "./workforceFlexibility.css";


function nextDay() {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  return date.toLocaleDateString("sv-SE", { timeZone: "Europe/Istanbul" });
}

function formatDate(value, locale) {
  if (!value) return "—";
  return new Date(`${value}T12:00:00`).toLocaleDateString(locale, {
    day: "2-digit", month: "short", weekday: "short",
  });
}

function fatigueLabelKey(value) {
  const band = String(value || "LOW").toUpperCase();
  return {
    LOW: "fatigueLow",
    MODERATE: "fatigueModerate",
    HIGH: "fatigueHigh",
    CRITICAL: "fatigueCritical",
  }[band] || "fatigueLow";
}

export default function WorkforceFlexibilityCenter() {
  const { user } = useAuth();
  const { locale } = usePlatformPreferences();
  const m = useCallback((key, params) => workforceFlexibilityMessage(locale, key, params), [locale]);
  const personId = user?.employeeId || (import.meta.env.DEV ? window.localStorage.getItem("opex_picker_person_id") || "100184" : "");
  const [data, setData] = useState({ availability: [], openShifts: [] });
  const [form, setForm] = useState({
    date: nextDay(), available: true,
    earliestStart: "08:00", latestEnd: "20:00",
    preferredStart: "09:00", preferredEnd: "18:00", note: "",
  });
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const selectedAvailability = useMemo(
    () => data.availability.find((row) => row.date === form.date),
    [data.availability, form.date],
  );

  const refresh = useCallback(async () => {
    if (!personId) {
      setError(m("identityMissing"));
      return;
    }
    setBusy((current) => current || "load");
    setError("");
    try {
      const next = await loadWorkforceFlexibility(personId);
      setData(next);
    } catch (requestError) {
      setError(requestError.message || m("loadError"));
    } finally {
      setBusy((current) => current === "load" ? "" : current);
    }
  }, [m, personId]);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    if (!selectedAvailability) return;
    setForm((current) => ({
      ...current,
      available: selectedAvailability.available !== false,
      earliestStart: selectedAvailability.earliestStart || "08:00",
      latestEnd: selectedAvailability.latestEnd || "20:00",
      preferredStart: selectedAvailability.preferredStart || "09:00",
      preferredEnd: selectedAvailability.preferredEnd || "18:00",
      note: selectedAvailability.note || "",
    }));
  }, [selectedAvailability]);

  async function save(event) {
    event.preventDefault();
    setBusy("save"); setMessage(""); setError("");
    try {
      await saveWorkforceAvailability(personId, form);
      setMessage(m("saved"));
      await refresh();
    } catch (requestError) {
      setError(requestError.message || m("loadError"));
    } finally { setBusy(""); }
  }

  async function claim(openShiftId) {
    setBusy(`claim-${openShiftId}`); setMessage(""); setError("");
    try {
      await claimWorkforceOpenShift(openShiftId, personId);
      setMessage(m("claimed"));
      await refresh();
    } catch (requestError) {
      setError(requestError.message || m("loadError"));
    } finally { setBusy(""); }
  }

  return <div className="wfx-service-detail wfx-flexibility-center">
    <div className="wfx-service-title"><CalendarClock size={24} /><div><span>{m("center")}</span><h2>{m("heading")}</h2></div></div>
    <p className="wfx-flexibility-intro">{m("intro")}</p>
    <section className="wfx-experience-trust"><ShieldCheck size={18} /><div><strong>{m("trust")}</strong><small>{m("trustDetail")}</small></div></section>

    {error ? <div className="wfx-flex-message error">{error}</div> : null}
    {message ? <div className="wfx-flex-message success"><CheckCircle2 size={16} />{message}</div> : null}

    <form className="wfx-flex-form" onSubmit={save}>
      <header><div><small>{m("availability")}</small><strong>{selectedAvailability ? m("saved") : m("detail")}</strong></div><button type="button" onClick={refresh} disabled={busy === "load"}><RefreshCw size={16} />{m("refresh")}</button></header>
      <div className="wfx-flex-form-grid">
        <label>{m("date")}<input type="date" value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} /></label>
        <label className="wfx-flex-toggle"><span>{form.available ? m("available") : m("unavailable")}</span><input type="checkbox" checked={form.available} onChange={(event) => setForm({ ...form, available: event.target.checked })} /></label>
        {form.available ? <>
          <label>{m("earliest")}<input type="time" value={form.earliestStart} onChange={(event) => setForm({ ...form, earliestStart: event.target.value })} /></label>
          <label>{m("latest")}<input type="time" value={form.latestEnd} onChange={(event) => setForm({ ...form, latestEnd: event.target.value })} /></label>
          <label>{m("preferredStart")}<input type="time" value={form.preferredStart} onChange={(event) => setForm({ ...form, preferredStart: event.target.value })} /></label>
          <label>{m("preferredEnd")}<input type="time" value={form.preferredEnd} onChange={(event) => setForm({ ...form, preferredEnd: event.target.value })} /></label>
        </> : null}
        <label className="wide">{m("note")}<input value={form.note} maxLength={500} onChange={(event) => setForm({ ...form, note: event.target.value })} /></label>
      </div>
      <button className="wfx-flex-primary" disabled={busy === "save" || !personId}><CheckCircle2 size={17} />{busy === "save" ? m("saving") : m("save")}</button>
    </form>

    <section className="wfx-flex-open-shifts">
      <header><div><small>{m("openShifts")}</small><strong>{data.openShifts.length}</strong></div><Sparkles size={19} /></header>
      <p className="wfx-flex-ranking-note"><ShieldCheck size={15} /><span>{m("rankingNotice")}</span></p>
      <div className="wfx-flex-shift-list">
        {data.openShifts.map((shift) => {
          const ranking = shift.eligibility?.assignmentRanking;
          return <article key={shift.id}>
            <div className="wfx-flex-shift-time"><strong>{formatDate(shift.date, locale)}</strong><span><Clock3 size={15} />{shift.start}–{shift.end}</span></div>
            <div className="wfx-flex-shift-main">
              <strong>{shift.warehouse}</strong>
              <small>{shift.role}</small>
              {shift.activities?.length ? <div className="wfx-flex-activity-chips">{shift.activities.map((activity) => <span key={`${shift.id}-${activity.activityKey}`}>{activity.displayName}</span>)}</div> : null}
              <span><Users size={14} /> {m("capacity", { count: shift.remainingCapacity })}</span>
              {ranking ? <div className="wfx-flex-ranking-components">
                <span>{m("preferenceComponent", { score: ranking.preferenceScore ?? "—" })}</span>
                <span>{m("workloadComponent", { score: ranking.workloadBalanceScore ?? "—" })}</span>
                <span>{m("restComponent", { score: ranking.restBufferScore ?? "—" })}</span>
                <span>{m("recoveryComponent", { score: ranking.recoveryScore ?? "—" })}</span>
              </div> : null}
              {ranking?.softOnly ? <small className="wfx-flex-ranking-boundary"><ShieldCheck size={12} />{m("rankingSoftOnly")}</small> : null}
            </div>
            <div className="wfx-flex-shift-fit">
              {ranking ? <>
                <b>{m("fairnessScore", { score: ranking.fairnessScore ?? "—" })}</b>
                <small className="wfx-flex-fatigue" data-risk={String(ranking.fatigueRiskBand || "LOW").toUpperCase()}>{m("fatigueRisk", { band: m(fatigueLabelKey(ranking.fatigueRiskBand)), score: ranking.fatigueRiskScore ?? "—" })}</small>
              </> : <b>{m("score", { score: shift.eligibility?.score ?? "—" })}</b>}
              {shift.eligibility?.preferenceMatch ? <small><CheckCircle2 size={13} />{m("preferenceMatch")}</small> : null}
            </div>
            <button type="button" disabled={busy === `claim-${shift.id}`} onClick={() => claim(shift.id)}>{busy === `claim-${shift.id}` ? m("claiming") : m("claim")}</button>
          </article>;
        })}
        {!data.openShifts.length ? <div className="wfx-flex-empty">{m("noOpen")}</div> : null}
      </div>
    </section>

    {personId ? <WorkforceShiftTradePanel personId={personId} /> : null}
  </div>;
}
