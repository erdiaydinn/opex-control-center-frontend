import React, { useEffect, useMemo, useState } from "react";

import { translateAuditLog } from "../../platform/i18n/auditLogMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import "./audit-log.css";
import { fetchAuditEvents } from "./auditLogApi";

function decisionLabel(decision, a) {
  const labels = { allowed: a("allowed"), denied: a("denied"), error: a("error") };
  return labels[decision] || decision;
}

export default function AuditLog() {
  const { locale, t, formatDate } = usePlatformPreferences();
  const a = (key) => translateAuditLog(locale, key);
  const [items, setItems] = useState([]);
  const [actor, setActor] = useState("");
  const [decision, setDecision] = useState("");
  const [action, setAction] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadEvents(filters = { actor, decision, action }) {
    setLoading(true);
    setError("");
    try {
      const result = await fetchAuditEvents({ limit: 100, ...filters });
      setItems(Array.isArray(result?.items) ? result.items : []);
    } catch {
      setError(a("loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadEvents({ actor: "", decision: "", action: "" });
    // Initial authoritative load only; filters are explicitly submitted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const summary = useMemo(() => items.reduce((acc, item) => {
    acc.total += 1;
    acc[item.decision] = (acc[item.decision] || 0) + 1;
    return acc;
  }, { total: 0, allowed: 0, denied: 0, error: 0 }), [items]);

  function handleSubmit(event) {
    event.preventDefault();
    loadEvents();
  }

  function handleReset() {
    const cleared = { actor: "", decision: "", action: "" };
    setActor(cleared.actor);
    setDecision(cleared.decision);
    setAction(cleared.action);
    loadEvents(cleared);
  }

  const productState = loading ? "loading" : error ? "error" : items.length ? "ready" : "empty";

  return (
    <section className="audit-log" data-eay-product-state={productState} aria-busy={loading ? "true" : "false"}>
      <header className="audit-log__header">
        <div>
          <span className="audit-log__eyebrow">{a("eyebrow")}</span>
          <h1>{a("title")}</h1>
          <p>{a("subtitle")}</p>
        </div>
        <button className="audit-log__refresh" type="button" onClick={() => loadEvents()} disabled={loading}>
          {loading ? t("loading") : t("refresh")}
        </button>
      </header>

      {!loading && !error ? (
        <div className="audit-log__summary">
          <article><span>{a("total")}</span><strong>{summary.total}</strong></article>
          <article><span>{a("allowed")}</span><strong>{summary.allowed}</strong></article>
          <article><span>{a("denied")}</span><strong>{summary.denied}</strong></article>
          <article><span>{a("error")}</span><strong>{summary.error}</strong></article>
        </div>
      ) : null}

      <form className="audit-log__filters" onSubmit={handleSubmit}>
        <label>{a("actor")}<input value={actor} onChange={(event) => setActor(event.target.value)} placeholder={a("actorPlaceholder")} /></label>
        <label>{a("decision")}<select value={decision} onChange={(event) => setDecision(event.target.value)}><option value="">{a("all")}</option><option value="allowed">{a("allowed")}</option><option value="denied">{a("denied")}</option><option value="error">{a("error")}</option></select></label>
        <label>{a("action")}<input value={action} onChange={(event) => setAction(event.target.value)} placeholder={a("actionPlaceholder")} /></label>
        <div className="audit-log__filter-actions"><button type="submit" disabled={loading}>{a("filter")}</button><button type="button" onClick={handleReset} disabled={loading}>{a("clear")}</button></div>
      </form>

      {loading ? <div role="status" aria-live="polite" aria-atomic="true">{t("loading")}</div> : null}
      {!loading && error ? <div className="audit-log__error" role="alert" aria-atomic="true">{error} <button type="button" onClick={() => loadEvents()}>{t("retry")}</button></div> : null}
      {!loading && !error ? <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{a("total")}: {summary.total}</p> : null}

      {!loading && !error ? (
        <div className="audit-log__table-wrap">
          <table className="audit-log__table">
            <caption className="sr-only">{a("title")}</caption>
            <thead><tr><th scope="col">{a("time")}</th><th scope="col">{a("actor")}</th><th scope="col">{a("action")}</th><th scope="col">{a("decision")}</th><th scope="col">{a("status")}</th><th scope="col">{a("requestId")}</th></tr></thead>
            <tbody>
              {items.length === 0 ? <tr><td colSpan="6" className="audit-log__empty"><span role="status" aria-live="polite">{a("empty")}</span></td></tr> : null}
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.created_at ? formatDate(item.created_at, { dateStyle: "short", timeStyle: "medium" }) : "—"}</td>
                  <td>{item.actor}</td><td><code>{item.action}</code></td>
                  <td><span className={`audit-log__decision audit-log__decision--${item.decision}`}>{decisionLabel(item.decision, a)}</span></td>
                  <td>{item.data?.status_code ?? "—"}</td>
                  <td><code title={item.request_id}>{item.request_id ? `${item.request_id.slice(0, 12)}…` : "—"}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
