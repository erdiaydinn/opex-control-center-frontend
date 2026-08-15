import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, BarChart3, RefreshCw, ShieldCheck, TriangleAlert } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { apiGet } from "../../api/client.js";
import { translateIntelligence } from "../../platform/i18n/intelligenceMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import "./intelligence.css";

export default function InsightWorkspace() {
  const navigate = useNavigate();
  const { locale, t } = usePlatformPreferences();
  const i = useMemo(() => (key) => translateIntelligence(locale, key), [locale]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await apiGet("/v1/insight/metrics"));
    } catch {
      setError(i("workspaceLoadError"));
    } finally {
      setLoading(false);
    }
  }, [i]);

  useEffect(() => {
    load();
  }, [load]);

  const metrics = data?.metrics || [];

  return (
    <main className="eay-intelligence-shell">
      <header className="eay-intelligence-head">
        <div>
          <div className="eay-intelligence-status"><BarChart3 size={22} aria-hidden="true" /><span>{i("canonicalMetrics")}</span></div>
          <h1>{i("insightTitle")}</h1>
          <p>{i("insightSubtitle")}</p>
        </div>
        <button className="eay-intelligence-back" type="button" onClick={() => navigate("/")}>
          <ArrowLeft size={18} aria-hidden="true" /> {t("back")}
        </button>
      </header>

      {loading ? <section className="eay-intelligence-state" role="status" aria-live="polite" aria-atomic="true" aria-busy="true" data-eay-product-state="loading"><RefreshCw size={20} aria-hidden="true" />{i("workspaceLoading")}</section> : null}
      {error ? <section className="eay-intelligence-state" role="alert" aria-live="assertive" aria-atomic="true" data-eay-product-state="error"><span>{error}</span><button className="eay-intelligence-retry" type="button" onClick={load}>{t("retry")}</button></section> : null}
      {data && !loading && !error && metrics.length === 0 ? <section className="eay-intelligence-state" role="status" aria-live="polite" aria-atomic="true" data-eay-product-state="empty">{t("emptyTitle")}</section> : null}

      {data && !loading && !error && metrics.length > 0 ? (
        <section className="eay-intelligence-grid" aria-label={i("canonicalMetrics")}>
          {metrics.map((metric) => (
            <article className="eay-intelligence-card" key={metric.metric_id}>
              <div className="eay-intelligence-card-head">
                <strong>{metric.metric_id}</strong>
                <span className={`eay-intelligence-pill ${metric.production_ready ? "is-ready" : ""}`}>
                  {metric.production_ready ? <ShieldCheck size={15} aria-hidden="true" /> : <TriangleAlert size={15} aria-hidden="true" />}
                  {metric.production_ready ? i("productionReady") : i("candidate")}
                </span>
              </div>
              <dl>
                <dt>{i("source")}</dt><dd>{metric.source}</dd>
                <dt>{i("tenantDiscriminator")}</dt><dd>{metric.tenant_discriminator?.expression || "—"} · {i("candidateUnverified")}</dd>
                <dt>{t("status")}</dt><dd>{metric.activation_state}</dd>
              </dl>
              {(metric.blockers || []).length ? <><strong>{i("externalEvidenceRequired")}</strong><ul className="eay-intelligence-blockers">{metric.blockers.map((item) => <li key={item}>{item}</li>)}</ul></> : null}
            </article>
          ))}
        </section>
      ) : null}
    </main>
  );
}
