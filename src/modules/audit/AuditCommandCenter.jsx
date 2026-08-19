import React from "react";
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
  ScanEye,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  Video,
} from "lucide-react";

import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import { auditCopy } from "./auditMessages.js";
import "./AuditCommandCenter.css";

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
      <div className="audit-stat__note">Live truth required</div>
    </article>
  );
}

function AuditCommandCenter() {
  const { locale } = usePlatformPreferences();
  const t = (key) => auditCopy(locale, key);

  return (
    <main className="audit-shell" data-eay-product-state="ready" data-audit-truth-state="unbound">
      <header className="audit-hero">
        <div>
          <div className="audit-eyebrow"><Sparkles size={15} /> {t("eyebrow")}</div>
          <h1>{t("title")}</h1>
          <p>{t("subtitle")}</p>
          <div className="audit-preview"><ShieldCheck size={15} /> {t("preview")}</div>
        </div>
        <div className="audit-hero__actions">
          <button className="audit-btn audit-btn--secondary" type="button"><CalendarDays size={17} /> {t("schedule")}</button>
          <button className="audit-btn audit-btn--primary" type="button"><Play size={17} /> {t("start")}</button>
        </div>
      </header>

      <nav className="audit-subnav" aria-label="Audit workspace navigation">
        {["audits", "actions", "standards", "locations", "intelligence"].map((key, index) => (
          <button key={key} className={index === 0 ? "is-active" : ""} type="button">{t(key)}</button>
        ))}
      </nav>

      <section className="audit-kpis" aria-label="Audit key indicators">
        {KPI.map((item) => <StatCard key={item.key} item={item} t={t} />)}
      </section>

      <section className="audit-grid audit-grid--top">
        <article className="audit-panel audit-panel--truth">
          <div className="audit-panel__heading">
            <div>
              <span className="audit-kicker">LIVE AUDIT TRUTH</span>
              <h2>{t("noLiveData")}</h2>
            </div>
            <span className="audit-status"><span /> UNBOUND</span>
          </div>
          <p>{t("noLiveDataBody")}</p>
          <div className="audit-truth-map" aria-hidden="true">
            <div className="audit-pulse audit-pulse--one" />
            <div className="audit-pulse audit-pulse--two" />
            <div className="audit-pulse audit-pulse--three" />
            <div className="audit-truth-map__line" />
            <MapPinned size={32} />
          </div>
          <button className="audit-link" type="button">{t("connect")} <ArrowRight size={16} /></button>
        </article>

        <aside className="audit-panel audit-panel--jarvis">
          <div className="audit-jarvis__icon"><Bot size={24} /></div>
          <div>
            <span className="audit-kicker">JARVIS / AUDIT INTELLIGENCE</span>
            <h2>{t("jarvisTitle")}</h2>
            <p>{t("jarvisBody")}</p>
          </div>
          <div className="audit-jarvis__prompts">
            <button type="button">“En riskli lokasyonlar?”</button>
            <button type="button">“AI–denetçi ayrışmaları?”</button>
            <button type="button">“Tekrar eden bulgular?”</button>
          </div>
          <button className="audit-btn audit-btn--dark" type="button"><Sparkles size={16} /> {t("askJarvis")}</button>
        </aside>
      </section>

      <section className="audit-section">
        <div className="audit-section__heading">
          <div>
            <span className="audit-kicker">AUDIT OPERATING SYSTEM</span>
            <h2>{t("attention")}</h2>
          </div>
          <button className="audit-text-action" type="button">Intelligence View <ChevronRight size={16} /></button>
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
            <div><Bot size={20} /><span>AI</span></div>
            <span className="audit-assurance__connector">↔</span>
            <div><ClipboardCheck size={20} /><span>Auditor</span></div>
            <span className="audit-assurance__connector">→</span>
            <div><ShieldCheck size={20} /><span>Manager</span></div>
          </div>
          <span className="audit-kicker">ASSURANCE</span>
          <h2>{t("disagreement")}</h2>
          <p>{t("disagreementBody")}</p>
        </article>
        <article className="audit-panel audit-panel--capture">
          <div className="audit-capture__media">
            <Camera size={24} />
            <div className="audit-capture__timeline">
              <span className="is-done">Giriş</span>
              <span className="is-warning">Kahve</span>
              <span>Fırın</span>
              <span>Raf</span>
              <span>Soğuk</span>
            </div>
          </div>
          <span className="audit-kicker">MOBILE-FIRST CAPTURE</span>
          <h2>{t("videoAudit")}</h2>
          <p>{t("videoAuditBody")}</p>
          <div className="audit-capture__foot"><ShieldCheck size={15} /> Privacy redaction before inference</div>
        </article>
      </section>
    </main>
  );
}

export default AuditCommandCenter;
