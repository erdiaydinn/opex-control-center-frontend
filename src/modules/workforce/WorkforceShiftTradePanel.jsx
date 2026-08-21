import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, CheckCircle2, Clock3, RefreshCw, ShieldCheck, UserRoundCheck, XCircle } from "lucide-react";

import {
  workforceShiftTradeMessage,
  workforceShiftTradeStatusMessage,
} from "../../platform/i18n/workforceShiftTradeMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import {
  acceptWorkforceShiftTrade,
  cancelWorkforceShiftTrade,
  createWorkforceShiftTrade,
  loadWorkforceOwnShifts,
  loadWorkforceShiftTrades,
  loadWorkforceSwapCandidates,
} from "./workforceFlexibilityApi.js";
import "./workforceShiftTrade.css";


function todayIstanbul() {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Istanbul" });
}

function formatDate(value, locale) {
  if (!value) return "—";
  return new Date(`${value}T12:00:00`).toLocaleDateString(locale, {
    day: "2-digit", month: "short", weekday: "short",
  });
}

function shiftLabel(shift, locale, m) {
  return m("dateTime", {
    date: formatDate(shift?.date, locale),
    start: shift?.start || "—",
    end: shift?.end || "—",
  });
}

export default function WorkforceShiftTradePanel({ personId }) {
  const { locale } = usePlatformPreferences();
  const m = useCallback((key, params) => workforceShiftTradeMessage(locale, key, params), [locale]);
  const [shifts, setShifts] = useState([]);
  const [trades, setTrades] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [mode, setMode] = useState("TRANSFER");
  const [shiftId, setShiftId] = useState("");
  const [targetShiftId, setTargetShiftId] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const activeShiftIds = useMemo(() => new Set(
    trades
      .filter((row) => !["APPROVED", "REJECTED", "CANCELLED"].includes(row.status))
      .flatMap((row) => [row.shiftId, row.targetShiftId].filter(Boolean).map(String)),
  ), [trades]);

  const tradeableShifts = useMemo(() => shifts.filter((shift) => (
    String(shift.status) === "Atandı"
    && String(shift.date || "") >= todayIstanbul()
    && !activeShiftIds.has(String(shift.id))
  )), [activeShiftIds, shifts]);

  const selectedShift = useMemo(
    () => tradeableShifts.find((shift) => String(shift.id) === String(shiftId)),
    [shiftId, tradeableShifts],
  );

  const refresh = useCallback(async () => {
    if (!personId) return;
    setBusy((current) => current || "load");
    setError("");
    try {
      const [shiftRows, tradeRows] = await Promise.all([
        loadWorkforceOwnShifts(personId),
        loadWorkforceShiftTrades(personId),
      ]);
      setShifts(shiftRows);
      setTrades(tradeRows);
    } catch (requestError) {
      setError(requestError.message || m("loadError"));
    } finally {
      setBusy((current) => current === "load" ? "" : current);
    }
  }, [m, personId]);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    if (!tradeableShifts.length) {
      setShiftId("");
      return;
    }
    if (!tradeableShifts.some((shift) => String(shift.id) === String(shiftId))) {
      setShiftId(String(tradeableShifts[0].id));
    }
  }, [shiftId, tradeableShifts]);

  useEffect(() => {
    let active = true;
    setTargetShiftId("");
    setCandidates([]);
    if (mode !== "SWAP" || !shiftId || !personId) return () => { active = false; };
    setBusy("candidates");
    loadWorkforceSwapCandidates(personId, shiftId)
      .then((rows) => {
        if (!active) return;
        setCandidates(rows);
        setTargetShiftId(rows[0]?.shiftId ? String(rows[0].shiftId) : "");
      })
      .catch((requestError) => { if (active) setError(requestError.message || m("loadError")); })
      .finally(() => { if (active) setBusy((current) => current === "candidates" ? "" : current); });
    return () => { active = false; };
  }, [m, mode, personId, shiftId]);

  async function submit(event) {
    event.preventDefault();
    if (!shiftId || (mode === "SWAP" && !targetShiftId)) return;
    setBusy("submit"); setMessage(""); setError("");
    try {
      await createWorkforceShiftTrade({ personId, shiftId, mode, targetShiftId, note });
      setMessage(m("requested"));
      setNote("");
      setTargetShiftId("");
      await refresh();
    } catch (requestError) {
      setError(requestError.message || m("actionError"));
    } finally { setBusy(""); }
  }

  async function accept(tradeId) {
    setBusy(`accept-${tradeId}`); setMessage(""); setError("");
    try {
      await acceptWorkforceShiftTrade(tradeId, personId);
      setMessage(m("accepted"));
      await refresh();
    } catch (requestError) {
      setError(requestError.message || m("actionError"));
    } finally { setBusy(""); }
  }

  async function cancel(tradeId) {
    setBusy(`cancel-${tradeId}`); setMessage(""); setError("");
    try {
      await cancelWorkforceShiftTrade(tradeId, personId);
      setMessage(m("cancelled"));
      await refresh();
    } catch (requestError) {
      setError(requestError.message || m("actionError"));
    } finally { setBusy(""); }
  }

  return <section className="wfx-shift-trade" aria-labelledby="wfx-shift-trade-title">
    <header className="wfx-shift-trade-head">
      <div><small>{m("eyebrow")}</small><h3 id="wfx-shift-trade-title">{m("title")}</h3><p>{m("detail")}</p></div>
      <button type="button" className="wfx-shift-trade-refresh" onClick={refresh} disabled={busy === "load"}><RefreshCw size={16} />{m("refresh")}</button>
    </header>

    <div className="wfx-shift-trade-policy"><ShieldCheck size={18} /><div><strong>{m("policy")}</strong><span>{m("policyDetail")}</span></div></div>
    {error ? <div className="wfx-shift-trade-message error">{error}</div> : null}
    {message ? <div className="wfx-shift-trade-message success"><CheckCircle2 size={16} />{message}</div> : null}

    <form className="wfx-shift-trade-form" onSubmit={submit}>
      <label>{m("sourceShift")}
        <select value={shiftId} onChange={(event) => setShiftId(event.target.value)} disabled={!tradeableShifts.length}>
          {!tradeableShifts.length ? <option value="">{m("noShift")}</option> : null}
          {tradeableShifts.map((shift) => <option key={shift.id} value={shift.id}>{shiftLabel(shift, locale, m)} · {shift.warehouse || shift.warehouseName || "—"}</option>)}
        </select>
      </label>

      <div className="wfx-shift-trade-mode" role="group">
        <button type="button" className={mode === "TRANSFER" ? "active" : ""} onClick={() => setMode("TRANSFER")}><UserRoundCheck size={17} /><span><strong>{m("transfer")}</strong><small>{m("transferDetail")}</small></span></button>
        <button type="button" className={mode === "SWAP" ? "active" : ""} onClick={() => setMode("SWAP")}><ArrowLeftRight size={17} /><span><strong>{m("swap")}</strong><small>{m("swapDetail")}</small></span></button>
      </div>

      {mode === "SWAP" ? <label>{m("swapCandidate")}
        <select value={targetShiftId} onChange={(event) => setTargetShiftId(event.target.value)} disabled={busy === "candidates" || !candidates.length}>
          {!candidates.length ? <option value="">{m("noCandidate")}</option> : null}
          {candidates.map((candidate) => <option key={candidate.shiftId} value={candidate.shiftId}>{candidate.counterpartDisplayName} · {shiftLabel(candidate, locale, m)}</option>)}
        </select>
      </label> : null}

      {mode === "SWAP" && candidates.length ? <div className="wfx-shift-trade-candidates">
        {candidates.map((candidate) => <button type="button" key={candidate.shiftId} className={String(candidate.shiftId) === String(targetShiftId) ? "selected" : ""} onClick={() => setTargetShiftId(String(candidate.shiftId))}>
          <span><strong>{candidate.counterpartDisplayName}</strong><small><Clock3 size={13} />{shiftLabel(candidate, locale, m)}</small></span>
          {candidate.requesterPreferenceMatch ? <em><CheckCircle2 size={13} />{m("preferenceMatch")}</em> : null}
        </button>)}
      </div> : null}

      <label>{m("note")}<input value={note} maxLength={500} placeholder={m("notePlaceholder")} onChange={(event) => setNote(event.target.value)} /></label>
      <button className="wfx-shift-trade-submit" disabled={!selectedShift || busy === "submit" || (mode === "SWAP" && !targetShiftId)}><ArrowLeftRight size={17} />{busy === "submit" ? m("submitting") : m("submit")}</button>
    </form>

    <div className="wfx-shift-trade-requests">
      <header><strong>{m("activeRequests")}</strong><span>{trades.length}</span></header>
      {!trades.length ? <div className="wfx-shift-trade-empty">{m("noRequests")}</div> : trades.map((trade) => {
        const requester = String(trade.requesterPersonId) === String(personId);
        const canAccept = !requester && ["OPEN_FOR_ACCEPTANCE", "PENDING_EMPLOYEE_ACCEPTANCE"].includes(trade.status);
        const canCancel = requester && !["APPROVED", "REJECTED", "CANCELLED"].includes(trade.status);
        return <article key={trade.id}>
          <div className="wfx-shift-trade-request-main">
            <span className={`status ${String(trade.status || "").toLowerCase()}`}>{workforceShiftTradeStatusMessage(locale, trade.status)}</span>
            <strong>{trade.mode === "SWAP" ? m("modeSwap") : m("modeTransfer")}</strong>
            <small>{formatDate(trade.date, locale)}</small>
          </div>
          <div className="wfx-shift-trade-request-actions">
            {canAccept ? <button type="button" onClick={() => accept(trade.id)} disabled={busy === `accept-${trade.id}`}><CheckCircle2 size={15} />{busy === `accept-${trade.id}` ? m("accepting") : m("accept")}</button> : null}
            {canCancel ? <button type="button" className="secondary" onClick={() => cancel(trade.id)} disabled={busy === `cancel-${trade.id}`}><XCircle size={15} />{busy === `cancel-${trade.id}` ? m("cancelling") : m("cancel")}</button> : null}
          </div>
        </article>;
      })}
    </div>
  </section>;
}
