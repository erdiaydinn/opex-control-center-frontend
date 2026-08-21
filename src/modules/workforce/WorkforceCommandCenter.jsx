import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BadgeCheck,
  Clock3,
  Gauge,
  RefreshCw,
  ShieldCheck,
  UsersRound,
  Zap,
} from "lucide-react";

import { workforceCommandCenterMessage } from "../../platform/i18n/workforceCommandCenterMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import {
  loadWorkforceCommandCenter,
  loadWorkforceCommandCenterLocations,
} from "./workforceCommandCenterApi.js";
import "./workforceCommandCenter.css";


function number(value, locale, digits = 1) {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "—";
  return new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(parsed);
}

function timeLabel(value, locale) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(locale, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function codeLabel(value) {
  return String(value || "—").replaceAll("_", " ").replaceAll("-", " ");
}

function Metric({ icon: Icon, label, value, note, tone = "neutral" }) {
  return <article className={`wfx-command-metric ${tone}`}>
    <div><Icon size={18} /></div>
    <span>{label}</span>
    <strong>{value}</strong>
    <small>{note}</small>
  </article>;
}

export default function WorkforceCommandCenter({ onLocationChange }) {
  const { locale } = usePlatformPreferences();
  const m = useCallback((key, params) => workforceCommandCenterMessage(locale, key, params), [locale]);
  const [locations, setLocations] = useState([]);
  const [locationId, setLocationId] = useState("");
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");

  const refresh = useCallback(async (requestedLocation = locationId) => {
    if (!requestedLocation) return;
    setStatus("loading");
    setError("");
    try {
      const result = await loadWorkforceCommandCenter(requestedLocation);
      setData(result);
      setStatus("ready");
    } catch (requestError) {
      setData(null);
      setError(requestError.message || m("error"));
      setStatus("error");
    }
  }, [locationId, m]);

  useEffect(() => {
    let active = true;
    loadWorkforceCommandCenterLocations().then((rows) => {
      if (!active) return;
      setLocations(rows);
      const first = rows[0]?.id || "";
      setLocationId(first);
      if (first) {
        onLocationChange?.(first);
        refresh(first);
      } else setStatus("empty");
    }).catch((requestError) => {
      if (!active) return;
      setError(requestError.message || m("error"));
      setStatus("error");
    });
    return () => { active = false; };
  }, []);

  const selectedLocation = useMemo(
    () => locations.find((row) => String(row.id) === String(locationId)),
    [locationId, locations],
  );

  const relationLabel = data?.interval?.relation === "CURRENT"
    ? m("current")
    : data?.interval?.relation === "FUTURE"
      ? m("future")
      : m("past");

  const isCurrent = data?.interval?.relation === "CURRENT";
  const actions = data?.actionQueue || [];
  const demand = data?.demand || {};
  const capacity = data?.capacity || {};
  const pressure = data?.pressure || {};
  const operations = data?.operations || {};
  const replan = data?.replan;

  return <section className="wfx-command-shell" aria-labelledby="wfx-command-title">
    <header className="wfx-command-header">
      <div className="wfx-command-heading">
        <span>{m("eyebrow")}</span>
        <h2 id="wfx-command-title">{m("title")}</h2>
        <p>{m("detail")}</p>
      </div>
      <div className="wfx-command-controls">
        <label>{m("worksite")}
          <select
            value={locationId}
            onChange={(event) => {
              const next = event.target.value;
              setLocationId(next);
              onLocationChange?.(next);
              refresh(next);
            }}
          >
            {locations.map((row) => <option key={row.id} value={row.id}>{row.name || row.code || row.id}</option>)}
          </select>
        </label>
        <button type="button" onClick={() => refresh()} disabled={!locationId || status === "loading"}>
          <RefreshCw size={16} />{m("refresh")}
        </button>
      </div>
    </header>

    {status === "loading" ? <div className="wfx-command-state" role="status" aria-live="polite" aria-busy="true"><RefreshCw size={18} />{m("loading")}</div> : null}
    {status === "empty" ? <div className="wfx-command-state"><AlertTriangle size={18} />{m("noLocations")}</div> : null}
    {status === "error" ? <div className="wfx-command-state error" role="alert"><AlertTriangle size={18} />{error || m("error")}</div> : null}

    {data ? <>
      <div className={`wfx-command-truth ${isCurrent ? "current" : "stale"}`}>
        {isCurrent ? <BadgeCheck size={18} /> : <AlertTriangle size={18} />}
        <div><strong>{isCurrent ? m("liveTruth") : m("staleTruth")}</strong><small>{relationLabel} · {m("intervalWidth", { minutes: data.interval.minutes })} · {m("observedAt", { time: timeLabel(data.interval.observedAt, locale) })}</small></div>
        <span>{selectedLocation?.name || selectedLocation?.code || locationId}</span>
      </div>

      <div className="wfx-command-metrics">
        <Metric icon={Activity} label={m("demand")} value={`${number(demand.requiredManHours, locale)} ${m("manHours")}`} note={`${number(demand.requiredPeople, locale)} ${m("people")}`} tone="demand" />
        <Metric icon={UsersRound} label={m("scheduled")} value={`${number(capacity.authorityScheduledManHours, locale)} ${m("manHours")}`} note={`${number(operations.scheduledPeople, locale, 0)} ${m("people")}`} tone="scheduled" />
        <Metric icon={Zap} label={m("effective")} value={`${number(capacity.effectiveManHours, locale)} ${m("manHours")}`} note={`${m("skillDeficit")}: ${number(capacity.skillDeficitManHours, locale)} ${m("manHours")}`} tone="capacity" />
        <Metric icon={Gauge} label={m("gap")} value={`${number(pressure.capacityGapManHours, locale)} ${m("manHours")}`} note={`${m("dpi")}: ${number(pressure.demandPressureIndex, locale, 2)}`} tone={pressure.manpowerShortage ? "risk" : "capacity"} />
      </div>

      <div className="wfx-command-grid">
        <section className="wfx-command-card">
          <header><div><span>{m("operations")}</span><strong>{relationLabel}</strong></div><Clock3 size={20} /></header>
          <dl className="wfx-command-operation-list">
            <div><dt>{m("scheduledPeople")}</dt><dd>{number(operations.scheduledPeople, locale, 0)}</dd></div>
            <div><dt>{isCurrent ? m("present") : m("attendanceStarted")}</dt><dd>{number(isCurrent ? operations.actualPresentPeople : operations.attendanceStartedPeople, locale, 0)}</dd></div>
            <div className={operations.noShowCount ? "danger" : ""}><dt>{m("noShow")}</dt><dd>{number(operations.noShowCount, locale, 0)}</dd></div>
            <div><dt>{m("breaks")}</dt><dd>{number(operations.activeBreakCount, locale, 0)}</dd></div>
            <div className={operations.dailyLimitBreachCount ? "danger" : ""}><dt>{m("DAILY_LIMIT_BREACH_TITLE")}</dt><dd>{number(operations.dailyLimitBreachCount, locale, 0)}</dd></div>
            <div className={operations.restRuleBreachCount ? "danger" : ""}><dt>{m("REST_RULE_BREACH_TITLE")}</dt><dd>{number(operations.restRuleBreachCount, locale, 0)}</dd></div>
          </dl>
        </section>

        <section className="wfx-command-card">
          <header><div><span>{m("kpiPressure")}</span><strong>{codeLabel(pressure.rootCause)}</strong></div><Gauge size={20} /></header>
          <div className="wfx-command-kpi-list">
            {(pressure.kpiObservations || []).map((row, index) => <article key={`${row.key || "kpi"}-${index}`}><span>{codeLabel(row.key)}</span><strong>{number(row.actual, locale, 2)}</strong><small>{row.target !== undefined ? number(row.target, locale, 2) : "—"}</small></article>)}
            {!(pressure.kpiObservations || []).length ? <p>{m("noActions")}</p> : null}
          </div>
          <div className="wfx-command-skill-list">
            {Object.entries(capacity.skillDeficits || {}).map(([key, value]) => <span key={key}>{codeLabel(key)} <b>{number(value, locale)} {m("manHours")}</b></span>)}
          </div>
        </section>

        <section className="wfx-command-card wfx-command-actions">
          <header><div><span>{m("actions")}</span><strong>{actions.length}</strong></div><AlertTriangle size={20} /></header>
          <div>
            {actions.map((action) => <article className={action.severity} key={action.code}>
              <i />
              <span><strong>{m(action.titleCode, { count: action.count ?? 0 })}</strong><small>{m(action.detailCode, { count: action.count ?? 0 })}</small></span>
              {action.requiresHumanApproval ? <b><ShieldCheck size={13} />{m("humanApproval")}</b> : null}
            </article>)}
            {!actions.length ? <p className="wfx-command-empty"><BadgeCheck size={18} />{m("noActions")}</p> : null}
          </div>
        </section>

        <section className="wfx-command-card wfx-command-replan">
          <header><div><span>{m("replan")}</span><strong>{m("automaticOff")}</strong></div><ShieldCheck size={20} /></header>
          {replan ? <div>
            <p><span>{m("recommendation")}</span><strong>{codeLabel(replan.recommendation)}</strong></p>
            <p><span>{m("gap")}</span><strong>{number(replan.scenarioGapManHours, locale)} {m("manHours")}</strong></p>
            <p><span>{m("costDelta")}</span><strong>{number(replan.costDeltaMinorUnits, locale, 0)}</strong></p>
            {replan.humanApprovalRequired ? <b><ShieldCheck size={14} />{m("humanApproval")}</b> : null}
          </div> : <p className="wfx-command-empty">{m("replanNone")}</p>}
        </section>
      </div>

      <details className="wfx-command-authority">
        <summary><BadgeCheck size={16} />{m("authority")}</summary>
        <div><span>{m("dpi")}</span><code>{data.authority.dpiFingerprint}</code></div>
        <div><span>{m("demand")}</span><code>{data.authority.demandFingerprint}</code></div>
        <div><span>{m("effective")}</span><code>{data.authority.capacityFingerprint}</code></div>
        <small>{m("truthBoundary")}</small>
      </details>
    </> : null}
  </section>;
}
