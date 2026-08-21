import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Bot, LockKeyhole, RefreshCw, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { apiGet } from "../../api/client.js";
import { translateIntelligence } from "../../platform/i18n/intelligenceMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import "./intelligence.css";

export default function JarvisWorkspace() {
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
      setData(await apiGet("/v1/jarvis/workspace"));
    } catch {
      setError(i("workspaceLoadError"));
    } finally {
      setLoading(false);
    }
  }, [i]);

  useEffect(() => {
    load();
  }, [load]);

  const features = data?.features || [];
  const tools = data?.tools || [];

  return (
    <main className="eay-intelligence-shell">
      <header className="eay-intelligence-head">
        <div>
          <div className="eay-intelligence-status"><Bot size={22} aria-hidden="true" /><span>{i("tenantBound")}</span></div>
          <h1>{i("jarvisTitle")}</h1>
          <p>{i("jarvisSubtitle")}</p>
        </div>
        <button className="eay-intelligence-back" type="button" onClick={() => navigate("/")}>
          <ArrowLeft size={18} aria-hidden="true" /> {t("back")}
        </button>
      </header>

      {loading ? <section className="eay-intelligence-state" role="status" aria-live="polite" aria-atomic="true" aria-busy="true" data-eay-product-state="loading"><RefreshCw size={20} aria-hidden="true" />{i("workspaceLoading")}</section> : null}
      {error ? <section className="eay-intelligence-state" role="alert" aria-live="assertive" aria-atomic="true" data-eay-product-state="error"><span>{error}</span><button className="eay-intelligence-retry" type="button" onClick={load}>{t("retry")}</button></section> : null}

      {data && !loading && !error ? (
        <>
          <section className="eay-intelligence-section">
            <h2>{i("capabilities")}</h2>
            <div className="eay-intelligence-capabilities">
              {features.map((item) => <span className="eay-intelligence-pill" key={item}>{item}</span>)}
              {!features.length ? <p role="status" aria-live="polite" aria-atomic="true" data-eay-product-state="empty">{i("noCapabilities")}</p> : null}
            </div>
          </section>

          <section className="eay-intelligence-section">
            <h2>{i("governedTools")}</h2>
            {!tools.length ? <p className="eay-intelligence-state" role="status" aria-live="polite" aria-atomic="true" data-eay-product-state="empty">{t("emptyTitle")}</p> : null}
            {tools.length ? <div className="eay-intelligence-grid">
              {tools.map((tool) => (
                <article className="eay-intelligence-card" key={tool.tool}>
                  <div className="eay-intelligence-card-head">
                    <strong>{tool.tool}</strong>
                    <span className={`eay-intelligence-pill ${tool.runtime_ready ? "is-ready" : ""}`}>
                      {tool.runtime_ready ? <ShieldCheck size={15} aria-hidden="true" /> : <LockKeyhole size={15} aria-hidden="true" />}
                      {tool.runtime_ready ? i("productionReady") : i("blocked")}
                    </span>
                  </div>
                  <dl>
                    <dt>{i("queryContract")}</dt><dd>{tool.query_contract_id}</dd>
                    <dt>{t("status")}</dt><dd>{tool.grant_eligible ? i("available") : i("unavailable")}</dd>
                  </dl>
                  {(tool.blockers || []).length ? <><strong>{i("blockers")}</strong><ul className="eay-intelligence-blockers">{tool.blockers.map((item) => <li key={item}>{item}</li>)}</ul></> : null}
                </article>
              ))}
            </div> : null}
          </section>

          <section className="eay-intelligence-section eay-intelligence-note">
            <h2>{i("askUnavailable")}</h2>
            <p>{i("askUnavailableDetail")}</p>
            <textarea disabled aria-label={i("askUnavailable")} />
          </section>
        </>
      ) : null}
    </main>
  );
}
