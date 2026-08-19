import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Bot,
  CalendarDays,
  Camera,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  FileCheck2,
  MapPinned,
  Play,
  RefreshCw,
  ScanEye,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  Video,
} from "lucide-react";

import { apiGet } from "../../api/client.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import { auditCopy } from "./auditMessages.js";
import "./AuditCommandCenter.css";
import "./AuditLiveTruth.css";

const KPI = [
  { key: "critical", icon: TriangleAlert, tone: "danger" },
  { key: "overdue", icon: CalendarDays, tone: "warning" },
  { key: "repeat", icon: ClipboardCheck, tone: "violet" },
  { key: "coverage", icon: FileCheck2, tone: "success" },
];

const FLOW = [
  { icon: ShieldCheck, titleKey: "redaction", bodyKey: "redactionBody", badge: "FAIL-CLOSED" },
  { icon: Video, titleKey: "videoAudit", bodyKey: "videoAuditBody", badge: "LOCAL-FIRST" },
  { icon: ScanEye, titleKey: "truthBoundary", bodyKey: "truthBoundaryBody", badge: "EVIDENCE" },
  { icon: CheckCircle2, titleKey: "verification", bodyKey: "verificationBody", badge: "VERIFIED" },
];

function StatCard({ item, t }) {
  const Icon = item.icon;
  return (
    <article className={`audit-stat audit-stat--${item.tone}`}>
      <div className="audit-stat__top">
        <span className="audit-stat__icon"><Icon size={18} /></span>
        <span className="audit-stat__label">{t(item.key)}</span>
      </div>
      <div className="audit-stat__value">—</div>
      <div className="audit-stat__note">{t("noLiveData")}</div>
    </article>
  );
}

function localizedProgramName(program, locale) {
  const names = program?.name_i18n;
  if (!names || typeof names !== "object") return program?.program_key || "—";
  const rawLocale = String(locale || "tr");
  const baseLocale = rawLocale.split("-")[0];
  return names[rawLocale] || names[baseLocale] || names.en || names.tr || program?.program_key || "—";
}

function AuditLiveTruth({ live, locale, t, onRefresh }) {
  const activePrograms = useMemo(
    () => live.programs.filter((program) => program?.status === "active"),
    [live.programs],
  );
  const visibleRuns = live.runs.slice(0, 4);
  const connected = live.state === "connected" || live.state === "connected-empty";

  return (
    <article className="audit-panel audit-panel--truth" data-audit-live-state={live.state}>
      <div className="audit-panel__heading">
        <div>
          <span className="audit-kicker">{t("truthBoundary")}</span>
          <h2>{connected ? t("audits") : t("noLiveData")}</h2>
        </div>
        <span className={`audit-status audit-status--${live.state}`} aria-live="polite">
          <span aria-hidden="true" /> {live.state.toUpperCase()}
        </span>
      </div>

      {connected ? (
        <>
          <p>{t("truthBoundaryBody")}</p>
          <div className="audit-live-grid">
            <section className="audit-live-column" aria-label={t("audits")}>
              <div className="audit-live-column__heading">{t("audits")}</div>
              {visibleRuns.length > 0 ? visibleRuns.map((run) => (
                <div className="audit-live-row" key={String(run.id)}>
                  <div>
                    <strong>{run.location_name || run.location_id || "—"}</strong>
                    <span>{run.program_key || "—"} · v{run.program_version ?? "—"}</span>
                  </div>
                  <div className="audit-live-row__meta">
                    <span>{String(run.status || "—").replaceAll("_", " ")}</span>
                    <time dateTime={run.started_at || undefined}>
                      {run.started_at ? new Date(run.started_at).toLocaleString(locale) : "—"}
                    </time>
                  </div>
                </div>
              )) : <div className="audit-live-empty">{t("noLiveData")}</div>}
            </section>

            <section className="audit-live-column" aria-label={t("standards")}>
              <div className="audit-live-column__heading">{t("standards")}</div>
              {activePrograms.length > 0 ? activePrograms.slice(0, 4).map((program) => (
                <div className="audit-live-row" key={`${program.program_key}:${program.version}`}>
                  <div>
                    <strong>{localizedProgramName(program, locale)}</strong>
                    <span>{program.program_key} · v{program.version}</span>
                  </div>
                  <div className="audit-live-row__meta">
                    <span>{program.status}</span>
                    <time dateTime={program.effective_from || undefined}>
                      {program.effective_from ? new Date(program.effective_from).toLocaleDateString(locale) : "—"}
                    </time>
                  </div>
                </div>
              )) : <div className="audit-live-empty">{t("noLiveData")}</div>}
            </section>
          </div>
        </>
      ) : (
        <>
          <p>{t("noLiveDataBody")}</p>
          <div className="audit-truth-map" aria-hidden="true">
            <div className="audit-pulse audit-pulse--one" />
            <div className="audit-pulse audit-pulse--two" />
            <div className="audit-pulse audit-pulse--three" />
            <div className="audit-truth-map__line" />
            <MapPinned size={32} />
          </div>
        </>
      )}

      <button className="audit-link" type="button" onClick={onRefresh} disabled={live.state === "loading"}>
        <RefreshCw size={15} className={live.state === "loading" ? "is-spinning" : ""} />
        {t("connect")} <ArrowRight size={16} />
      </button>
    </article>
  );
}

function AuditCommandCenter() {
  const { locale } = usePlatformPreferences();
  const t = (key) => auditCopy(locale, key);
  const [live, setLive] = useState({
    state: "loading",
    programs: [],
    runs: [],
  });

  const refreshLiveTruth = useCallback(async () => {
    setLive((current) => ({ ...current, state: "loading" }));
    try {
      const [programsPayload, runsPayload] = await Promise.all([
        apiGet("/v1/audit/programs"),
        apiGet("/v1/audit/runs?limit=100"),
      ]);
      if (!Array.isArray(programsPayload) || !Array.isArray(runsPayload)) {
        throw new Error("Audit API returned an invalid truth payload.");
      }
      setLive({
        state: programsPayload.length > 0 || runsPayload.length > 0 ? "connected" : "connected-empty",
        programs: programsPayload,
        runs: runsPayload,
      });
    } catch {
      setLive({ state: "error", programs: [], runs: [] });
    }
  }, []);

  useEffect(() => {
    refreshLiveTruth();
  }, [refreshLiveTruth]);

  return (
    <main
      className="audit-shell"
      data-eay-product-state="ready"
      data-audit-truth-state={live.state}
    >
      <header className="audit-hero">
        <div>
          <div className="audit-eyebrow"><Sparkles size={15} /> {t("eyebrow")}</div>
          <h1>{t("title")}</h1>
          <p>{t("subtitle")}</p>
          <div className="audit-preview"><ShieldCheck size={15} /> {t("preview")}</div>
        </div>
        <div className="audit-hero__actions">
          <button className="audit-btn audit-btn--secondary" type="button" disabled><CalendarDays size={17} /> {t("schedule")}</button>
          <button className="audit-btn audit-btn--primary" type="button" disabled><Play size={17} /> {t("start")}</button>
        </div>
      </header>

      <nav className="audit-subnav" aria-label={t("title")}>
        {["audits", "actions", "standards", "locations", "intelligence"].map((key, index) => (
          <button key={key} className={index === 0 ? "is-active" : ""} type="button">{t(key)}</button>
        ))}
      </nav>

      <section className="audit-kpis" aria-label={t("eyebrow")}>
        {KPI.map((item) => <StatCard key={item.key} item={item} t={t} />)}
      </section>

      <section className="audit-grid audit-grid--top">
        <AuditLiveTruth live={live} locale={locale} t={t} onRefresh={refreshLiveTruth} />

        <aside className="audit-panel audit-panel--jarvis">
          <div className="audit-jarvis__icon"><Bot size={24} /></div>
          <div>
            <span className="audit-kicker">{t("moduleMeta")}</span>
            <h2>{t("jarvisTitle")}</h2>
            <p>{t("jarvisBody")}</p>
          </div>
          <div className="audit-jarvis__prompts">
            <button type="button">{t("critical")}</button>
            <button type="button">{t("disagreement")}</button>
            <button type="button">{t("repeat")}</button>
          </div>
          <button className="audit-btn audit-btn--dark" type="button"><Sparkles size={16} /> {t("askJarvis")}</button>
        </aside>
      </section>

      <section className="audit-section">
        <div className="audit-section__heading">
          <div>
            <span className="audit-kicker">{t("eyebrow")}</span>
            <h2>{t("attention")}</h2>
          </div>
          <button className="audit-text-action" type="button">{t("actionView")} <ChevronRight size={16} /></button>
        </div>
        <div className="audit-flow">
          {FLOW.map(({ icon: Icon, titleKey, bodyKey, badge }) => (
            <article className="audit-flow__item" key={titleKey}>
              <div className="audit-flow__icon"><Icon size={21} /></div>
              <div className="audit-flow__content">
                <div className="audit-flow__title"><h3>{t(titleKey)}</h3><span>{badge}</span></div>
                <p>{t(bodyKey)}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="audit-grid audit-grid--bottom">
        <article className="audit-panel audit-panel--assurance">
          <div className="audit-assurance__visual" aria-hidden="true">
            <div><Bot size={20} /></div>
            <span className="audit-assurance__connector">↔</span>
            <div><ClipboardCheck size={20} /></div>
            <span className="audit-assurance__connector">→</span>
            <div><ShieldCheck size={20} /></div>
          </div>
          <span className="audit-kicker">{t("disagreement")}</span>
          <h2>{t("disagreement")}</h2>
          <p>{t("disagreementBody")}</p>
        </article>
        <article className="audit-panel audit-panel--capture">
          <div className="audit-capture__media" aria-hidden="true">
            <Camera size={24} />
            <div className="audit-capture__timeline">
              <span className="is-done" />
              <span className="is-warning" />
              <span />
              <span />
              <span />
            </div>
          </div>
          <span className="audit-kicker">{t("videoAudit")}</span>
          <h2>{t("videoAudit")}</h2>
          <p>{t("videoAuditBody")}</p>
          <div className="audit-capture__foot"><ShieldCheck size={15} /> {t("redaction")}</div>
        </article>
      </section>
    </main>
  );
}

export default AuditCommandCenter;
