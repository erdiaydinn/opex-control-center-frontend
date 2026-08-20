import React, { useCallback, useEffect, useState } from "react";
import { ArrowLeftRight, CheckCircle2, Clock3, RefreshCw, ShieldCheck, XCircle } from "lucide-react";

import {
  workforceShiftTradeMessage,
  workforceShiftTradeStatusMessage,
} from "../../platform/i18n/workforceShiftTradeMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import {
  approveWorkforceShiftTrade,
  loadWorkforceShiftTradesAdmin,
  rejectWorkforceShiftTrade,
} from "./workforceFlexibilityApi.js";
import "./workforceShiftTrade.css";


function formatDate(value, locale) {
  if (!value) return "—";
  return new Date(`${value}T12:00:00`).toLocaleDateString(locale, {
    day: "2-digit", month: "short", weekday: "short",
  });
}

function shiftSummary(shift, locale, m) {
  if (!shift) return "—";
  return m("dateTime", {
    date: formatDate(shift.date, locale),
    start: shift.start || "—",
    end: shift.end || "—",
  });
}

export default function WorkforceShiftTradeAdminPanel({ warehouseId }) {
  const { locale } = usePlatformPreferences();
  const m = useCallback((key, params) => workforceShiftTradeMessage(locale, key, params), [locale]);
  const [rows, setRows] = useState([]);
  const [notes, setNotes] = useState({});
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!warehouseId) {
      setRows([]);
      return;
    }
    setBusy((current) => current || "load");
    setError("");
    try {
      setRows(await loadWorkforceShiftTradesAdmin(warehouseId, true));
    } catch (requestError) {
      setError(requestError.message || m("managerLoadError"));
    } finally {
      setBusy((current) => current === "load" ? "" : current);
    }
  }, [m, warehouseId]);

  useEffect(() => { refresh(); }, [refresh]);

  async function decide(tradeId, decision) {
    setBusy(`${decision}-${tradeId}`); setMessage(""); setError("");
    try {
      const note = notes[tradeId] || "";
      if (decision === "approve") {
        await approveWorkforceShiftTrade(tradeId, note);
        setMessage(m("approved"));
      } else {
        await rejectWorkforceShiftTrade(tradeId, note);
        setMessage(m("rejected"));
      }
      setNotes((current) => ({ ...current, [tradeId]: "" }));
      await refresh();
    } catch (requestError) {
      setError(requestError.message || m("actionError"));
    } finally { setBusy(""); }
  }

  return <section className="wfx-shift-trade wfx-shift-trade-admin" aria-labelledby="wfx-shift-trade-admin-title">
    <header className="wfx-shift-trade-head">
      <div><small>{m("managerEyebrow")}</small><h3 id="wfx-shift-trade-admin-title">{m("managerTitle")}</h3><p>{m("managerDetail")}</p></div>
      <button type="button" className="wfx-shift-trade-refresh" onClick={refresh} disabled={busy === "load" || !warehouseId}><RefreshCw size={16} />{m("refresh")}</button>
    </header>
    <div className="wfx-shift-trade-policy"><ShieldCheck size={18} /><div><strong>{m("policy")}</strong><span>{m("policyDetail")}</span></div></div>
    {error ? <div className="wfx-shift-trade-message error">{error}</div> : null}
    {message ? <div className="wfx-shift-trade-message success"><CheckCircle2 size={16} />{message}</div> : null}

    <div className="wfx-shift-trade-admin-list">
      {!rows.length ? <div className="wfx-shift-trade-empty">{m("noManagerRows")}</div> : rows.map((trade) => {
        const pendingManager = trade.status === "PENDING_MANAGER_APPROVAL";
        return <article key={trade.id}>
          <header>
            <div><span className={`status ${String(trade.status || "").toLowerCase()}`}>{workforceShiftTradeStatusMessage(locale, trade.status)}</span><strong><ArrowLeftRight size={15} />{trade.mode === "SWAP" ? m("modeSwap") : m("modeTransfer")}</strong></div>
            <small><Clock3 size={13} />{formatDate(trade.date, locale)}</small>
          </header>
          <div className="wfx-shift-trade-admin-grid">
            <div><small>{m("requester")}</small><strong>{trade.requesterDisplayName}</strong><span>{m("source")}: {shiftSummary(trade.sourceShift, locale, m)}</span></div>
            <div><small>{m("target")}</small><strong>{trade.targetDisplayName}</strong><span>{m("targetShift")}: {shiftSummary(trade.targetShift, locale, m)}</span></div>
          </div>
          {pendingManager ? <div className="wfx-shift-trade-decision">
            <label>{m("decisionNote")}<input maxLength={500} value={notes[trade.id] || ""} onChange={(event) => setNotes((current) => ({ ...current, [trade.id]: event.target.value }))} /></label>
            <div>
              <button type="button" onClick={() => decide(trade.id, "approve")} disabled={busy === `approve-${trade.id}`}><CheckCircle2 size={15} />{busy === `approve-${trade.id}` ? m("approving") : m("approve")}</button>
              <button type="button" className="danger" onClick={() => decide(trade.id, "reject")} disabled={busy === `reject-${trade.id}`}><XCircle size={15} />{busy === `reject-${trade.id}` ? m("rejecting") : m("reject")}</button>
            </div>
          </div> : null}
        </article>;
      })}
    </div>
  </section>;
}
