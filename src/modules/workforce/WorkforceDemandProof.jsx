import React, { useEffect, useMemo, useState } from "react";
import { Calculator, Fingerprint, ShieldCheck } from "lucide-react";

import { useAuth } from "../../auth/AuthContext.jsx";
import { workforceActivityStudioMessage } from "../../platform/i18n/workforceActivityStudioMessages.js";
import { workforceCapacityMessage } from "../../platform/i18n/workforceCapacityMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import {
  previewWorkforceActivityCapacity,
  previewWorkforceActivityDemand,
} from "./workforceFlexibilityApi.js";
import "./workforceDemandProof.css";


function nextHourIstanbul() {
  const date = new Date(Date.now() + 60 * 60 * 1000);
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Istanbul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}T${value.hour}:${value.minute}`;
}

function istanbulIso(value) {
  return value ? `${value}:00+03:00` : "";
}

function rootCauseKey(value) {
  if (value === "skill_mix_constraint") return "skillMix";
  if (value === "manpower_capacity_shortage") return "manpowerShortage";
  return "noPressure";
}

export default function WorkforceDemandProof({ activities = [], locations = [], standards = [] }) {
  const { canAction } = useAuth();
  const { locale } = usePlatformPreferences();
  const m = (key, params) => workforceActivityStudioMessage(locale, key, params);
  const c = (key) => workforceCapacityMessage(locale, key);
  const allowed = canAction("workforce", "manageStaffingNorms");
  const [worksiteId, setWorksiteId] = useState("");
  const [activityKey, setActivityKey] = useState("");
  const [intervalStart, setIntervalStart] = useState(nextHourIstanbul());
  const [intervalMinutes, setIntervalMinutes] = useState("60");
  const [quantity, setQuantity] = useState("");
  const [sourceRef, setSourceRef] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setWorksiteId((current) => current || locations[0]?.id || "");
  }, [locations]);
  useEffect(() => {
    setActivityKey((current) => current || activities[0]?.activityKey || "");
  }, [activities]);

  const activity = useMemo(
    () => activities.find((row) => row.activityKey === activityKey),
    [activities, activityKey],
  );
  const standard = useMemo(
    () => standards.find((row) => row.activityKey === activityKey),
    [standards, activityKey],
  );
  const ready = Boolean(
    allowed
      && worksiteId
      && activity
      && standard
      && intervalStart
      && Number(quantity) > 0
      && sourceRef.trim(),
  );

  async function calculate(event) {
    event.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const values = {
        worksiteId,
        intervalStart: istanbulIso(intervalStart),
        intervalMinutes,
        modelVersion: "generic-work-activity-v1",
        signals: [{
          driverKey: `studio:${activity.activityKey}`,
          activityKey: activity.activityKey,
          demandMode: activity.demandMode,
          quantity,
          sourceRef: sourceRef.trim(),
        }],
      };
      const [demand, capacity] = await Promise.all([
        previewWorkforceActivityDemand(values),
        previewWorkforceActivityCapacity(values),
      ]);
      setResult({ demand, capacity });
    } catch (requestError) {
      setError(requestError.message || m("loadError"));
    } finally {
      setBusy(false);
    }
  }

  return <section className="wfx-demand-proof">
    <header>
      <div><small>{m("demandTitle")}</small><strong>{m("demandDetail")}</strong></div>
      <Calculator size={20} />
    </header>
    {!allowed ? <p className="wfx-demand-proof-note"><ShieldCheck size={15} />{m("demandPermission")}</p> : <>
      <form onSubmit={calculate}>
        <label>{m("worksite")}<select value={worksiteId} onChange={(event) => setWorksiteId(event.target.value)}>{locations.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
        <label>{m("selectActivity")}<select value={activityKey} onChange={(event) => { setActivityKey(event.target.value); setResult(null); }}>{activities.map((row) => <option key={row.activityKey} value={row.activityKey}>{row.displayName}</option>)}</select></label>
        <label>{m("intervalStart")}<input type="datetime-local" value={intervalStart} onChange={(event) => setIntervalStart(event.target.value)} /></label>
        <label>{m("interval")}<select value={intervalMinutes} onChange={(event) => setIntervalMinutes(event.target.value)}>{[15, 30, 60].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label>{m("quantity")}<input type="number" min="0.001" step="0.001" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label>
        <label className="wide">{m("demandSource")}<input maxLength={300} value={sourceRef} onChange={(event) => setSourceRef(event.target.value)} placeholder={m("demandSource")} /></label>
        <button disabled={!ready || busy}><Calculator size={16} />{busy ? m("calculating") : m("runDemand")}</button>
      </form>
      {!standard && activity ? <p className="wfx-demand-proof-note"><ShieldCheck size={15} />{m("standardMissing")}</p> : null}
      {error ? <div className="wfx-demand-proof-error">{error}</div> : null}
      {result ? <div className="wfx-demand-proof-result">
        <article><small>{m("requiredHours")}</small><strong>{result.demand.requiredManHours}</strong></article>
        <article><small>{m("requiredPeople")}</small><strong>{result.demand.requiredPeople}</strong></article>
        <article><small>{c("scheduledCapacity")}</small><strong>{result.capacity.availableManHours}</strong></article>
        <article><small>{c("allocatedCapacity")}</small><strong>{result.capacity.allocatedManHours}</strong></article>
        <article><small>{c("deficit")}</small><strong>{result.capacity.deficitManHours}</strong></article>
        <article><small>{c("recommendedPeople")}</small><strong>{result.capacity.recommendedPeople}</strong></article>
        <article className="wide"><small>{c("rootCause")}</small><strong>{c(rootCauseKey(result.capacity.rootCause))}</strong></article>
        <article className="wide"><small>{m("fingerprint")}</small><span><Fingerprint size={14} />{result.demand.snapshotFingerprint}</span></article>
      </div> : null}
    </>}
  </section>;
}
