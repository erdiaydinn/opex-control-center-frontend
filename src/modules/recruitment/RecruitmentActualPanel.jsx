import React, { useRef, useState } from "react";
import { AlertTriangle, BadgeCheck, FileSpreadsheet, RefreshCw, ShieldCheck, Upload, Users } from "lucide-react";

import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import { recruitmentMessage } from "../../platform/i18n/recruitmentMessages.js";
import { recruitmentProjectionMessage } from "../../platform/i18n/recruitmentProjectionMessages.js";
import { importRecruitmentHrActual } from "./recruitmentApi.js";
import { parseRecruitmentHrActualFile } from "./recruitmentImporters.js";
import "./recruitmentLifecycle.css";


function today() { return new Date().toISOString().slice(0, 10); }
function valueOrDash(value) { return value == null ? "—" : value; }
function QualityStatus({ row, snapshot, m, pm }) {
  if (row.hrActualUnmatched) return <span className="rec-status warning">{row.hrActualUnmatched} {m("actualUnmatched")}</span>;
  if (snapshot?.freshness === "STALE") return <span className="rec-status warning">{snapshot.ageDays == null ? pm("stale") : pm("daysOld", { days: snapshot.ageDays })}</span>;
  if (snapshot) return <span className="rec-status success">{pm("fresh")} · {m("reconciled")}</span>;
  return <span className="rec-status neutral">{m("snapshotWaiting")}</span>;
}

export default function RecruitmentActualPanel({ data, refresh, flash, setError, canManage = false }) {
  const { locale } = usePlatformPreferences();
  const m = (key, params) => recruitmentMessage(locale, key, params);
  const pm = (key, params) => recruitmentProjectionMessage(locale, key, params);
  const fileRef = useRef(null);
  const [asOf, setAsOf] = useState(data?.actualSnapshot?.asOf || today());
  const [busy, setBusy] = useState(false);
  const snapshot = data?.actualSnapshot;
  const rows = data?.dashboard?.warehouseRows || [];

  async function upload(file) {
    if (!file || !canManage) return;
    setBusy(true);
    try {
      const parsed = await parseRecruitmentHrActualFile(file);
      if (!parsed.rows.length) throw new Error(m("actualUnmatchedDetail"));
      const result = await importRecruitmentHrActual(parsed.rows, file.name, asOf);
      flash(m("actualLoaded", { active: result.activeRows, match: result.matchRate }));
      await refresh();
    } catch (error) {
      setError(error.message || m("officialSnapshotWaiting"));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return <section className="rec-content rec-actual-stack">
    <div className="rec-panel rec-actual-hero">
      <div>
        <span className="rec-kicker">{m("headcountAuthority")}</span>
        <h2>{m("actualTitle")}</h2>
        <p>{m("actualDesc")}</p>
      </div>
      {canManage ? <div className="rec-actual-upload">
        <label>{m("dataDate")}<input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} /></label>
        <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" hidden onChange={(event) => upload(event.target.files?.[0])} />
        <button className="rec-primary" disabled={busy} onClick={() => fileRef.current?.click()}><Upload size={17} />{busy ? m("processing") : m("uploadActual")}</button>
      </div> : null}
    </div>

    <div className="rec-metrics">
      <article className="rec-metric tone-pink"><span><Users size={19} /></span><div><small>{m("hrActual")}</small><strong>{valueOrDash(snapshot?.activeRows)}</strong><p>{snapshot ? `${snapshot.activeFte} ${m("fte")} · ${snapshot.asOf}` : m("officialSnapshotWaiting")}</p></div></article>
      <article className="rec-metric tone-green"><span><BadgeCheck size={19} /></span><div><small>{m("emMatch")}</small><strong>{snapshot ? `%${snapshot.matchRate}` : "—"}</strong><p>{snapshot ? `${snapshot.matchedRows}/${snapshot.sourceRows}` : m("snapshotWaiting")}</p></div></article>
      <article className="rec-metric tone-amber"><span><AlertTriangle size={19} /></span><div><small>{m("actualUnmatched")}</small><strong>{valueOrDash(snapshot?.unmatchedRows)}</strong><p>{m("actualUnmatchedDetail")}</p></div></article>
      <article className="rec-metric tone-purple"><span><FileSpreadsheet size={19} /></span><div><small>{m("sourceProof")}</small><strong>{snapshot?.sourceSha256 ? snapshot.sourceSha256.slice(0, 8) : "—"}</strong><p>{snapshot?.sourceName || m("officialSnapshotWaiting")}</p></div></article>
    </div>

    <div className="rec-panel">
      <div className="rec-panel-head"><div><span className="rec-kicker">{m("staffingReconciliation")}</span><h2>{m("staffingReconciliationHeading")}</h2></div><button className="rec-secondary" onClick={refresh}><RefreshCw size={16} /> {m("refresh")}</button></div>
      <div className="rec-table-wrap"><table className="rec-actual-table"><thead><tr><th>{m("depot")}</th><th>{m("capacity")}</th><th>{m("hrActual")}</th><th>{m("emActual")}</th><th>{pm("committed")}</th><th>{m("openReq")}</th><th>{pm("uncovered")}</th><th>{pm("forecast")}</th><th>{m("dataQuality")}</th></tr></thead><tbody>
        {rows.map((row) => <tr key={row.warehouseName}>
          <td><strong>{row.warehouseName}</strong><small>{row.normRecord?.regionalExecutive || m("byPending")}</small></td>
          <td><strong>{row.capacity}</strong><small>{row.normStatus === "TEMPORARY_ACTIVE" ? m("temporaryNorm") : m("capacityLabel")}</small></td>
          <td><strong>{valueOrDash(row.hrActual)}</strong><small>{valueOrDash(row.hrActualFte)} {m("fte")} · {row.hrActualAsOf || m("snapshotWaiting")}</small></td>
          <td><strong>{row.active}</strong><small>{row.hrActualDelta == null ? m("opActual") : `${m("hrEmDelta")} ${row.hrActualDelta}`}</small></td>
          <td><strong>{valueOrDash(row.committedHeadcount)}</strong><small>+{row.incomingCommitted || 0} {pm("incoming")} · -{row.confirmedExits || 0} {pm("exits")}</small></td>
          <td>{row.openPositions}</td>
          <td><strong>{valueOrDash(row.uncoveredGap)}</strong></td>
          <td><span className="rec-projection-cell"><b>30</b> {row.forecast30?.uncoveredGap ?? "—"}<b>60</b> {row.forecast60?.uncoveredGap ?? "—"}<b>90</b> {row.forecast90?.uncoveredGap ?? "—"}</span></td>
          <td><QualityStatus row={row} snapshot={snapshot} m={m} pm={pm} /></td>
        </tr>)}
      </tbody></table>{!rows.length && <div className="rec-empty">{m("noStaffingRows")}</div>}</div>
      <p className="rec-config-note"><ShieldCheck size={15} />{m("authorityNote")}</p>
    </div>
  </section>;
}