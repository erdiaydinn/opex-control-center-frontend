import React, { useEffect, useMemo, useRef, useState } from "react";

import { translateAuditLog } from "../../platform/i18n/auditLogMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import "./audit-log.css";
import { fetchAuditEvents } from "./auditLogApi";

const EMPTY_FILTERS = Object.freeze({ actor: "", decision: "", action: "" });
const AUDIT_DECISIONS = new Set(["allowed", "denied", "error"]);

function safeAuditText(value) {
  return typeof value === "string" || typeof value === "number" ? String(value) : "—";
}

function safeDecision(decision) {
  return AUDIT_DECISIONS.has(decision) ? decision : "unknown";
}

function decisionLabel(decision, a) {
  const labels = { allowed: a("allowed"), denied: a("denied"), error: a("error") };
  return labels[safeDecision(decision)] || "—";
}

function safeAuditDate(value, formatDate) {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) return "—";
  try {
    return formatDate(value, { dateStyle: "short", timeStyle: "medium" });
  } catch {
    return "—";
  }
}

function safeRequestId(value) {
  if (typeof value !== "string" || !value.trim()) return { full: "", short: "—" };
  return { full: value, short: value.length > 12 ? `${value.slice(0, 12)}…` : value };
}

export default function AuditLog() {
  const { locale, t, formatDate } = usePlatformPreferences();
  const a = (key) => translateAuditLog(locale, key);
  const [items, setItems] = useState([]);
  const [actor, setActor] = useState("");
  const [decision, setDecision] = useState("");
  const [action, setAction] = useState("");
  const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestSequence = useRef(0);

  async function loadEvents(filters) {
    const requestId = requestSequence.current + 1;
    requestSequence.current = requestId;
    setLoading(true);
    setError("");
    try {
      const result = await fetchAuditEvents({ limit: 100, ...filters });
      if (requestId !== requestSequence.current) return;
      setItems(Array.isArray(result?.items) ? result.items : []);
    } catch {
      if (requestId !== requestSequence.current) return;
      setError(a("loadError"));
    } finally {
      if (requestId === requestSequence.current) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    loadEvents(EMPTY_FILTERS);
    // Initial authoritative load only; filters are explicitly submitted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    return () => {
      requestSequence.current += 1;
    };
  }, []);

  const summary = useMemo(() => items.reduce((acc, item) => {
    acc.total += 1;
    const normalizedDecision = safeDecision(item?.decision);
    if (normalizedDecision !== "unknown") {
      acc[normalizedDecision] += 1;
    }
    return acc;
  }, { total: 0, allowed: 0, denied: 0, error: 0 }), [items]);

  function handleSubmit(event) {
    event.preventDefault();
    const nextFilters = { actor, decision, action };
    setAppliedFilters(nextFilters);
    loadEvents(nextFilters);
  }

  function handleReset() {
    setActor(EMPTY_FILTERS.actor);
    setDecision(EMPTY_FILTERS.decision);
    setAction(EMPTY_FILTERS.action);
    setAppliedFilters(EMPTY_FILTERS);
    loadEvents(EMPTY_FILTERS);
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
        <button className="audit-log__refresh" type="button" onClick={() => loadEvents(appliedFilters)} disabled={loading}>
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
      {!loading && error ? <div className="audit-log__error" role="alert" aria-atomic="true">{error} <button type="button" onClick={() => loadEvents(appliedFilters)}>{t("retry")}</button></div> : null}
      {!loading && !error ? <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">{a("total")}: {summary.total}</p> : null}

      {!loading && !error ? (
        <div className="audit-log__table-wrap">
          <table className="audit-log__table">
            <caption className="sr-only">{a("title")}</caption>
            <thead><tr><th scope="col">{a("time")}</th><th scope="col">{a("actor")}</th><th scope="col">{a("action")}</th><th scope="col">{a("decision")}</th><th scope="col">{a("status")}</th><th scope="col">{a("requestId")}</th></tr></thead>
            <tbody>
              {items.length === 0 ? <tr><td colSpan="6" className="audit-log__empty"><span role="status" aria-live="polite">{a("empty")}</span></td></tr> : null}
              {items.map((item, index) => {
                const normalizedDecision = safeDecision(item?.decision);
                const requestId = safeRequestId(item?.request_id);
                const rowKey = typeof item?.id === "string" || typeof item?.id === "number"
                  ? item.id
                  : `${requestId.full || "audit"}-${index}`;
                return (
                  <tr key={rowKey}>
                    <td>{safeAuditDate(item?.created_at, formatDate)}</td>
                    <td>{safeAuditText(item?.actor)}</td><td><code>{safeAuditText(item?.action)}</code></td>
                    <td><span className={`audit-log__decision audit-log__decision--${normalizedDecision}`}>{decisionLabel(item?.decision, a)}</span></td>
                    <td>{safeAuditText(item?.data?.status_code)}</td>
                    <td><code title={requestId.full || undefined}>{requestId.short}</code></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
