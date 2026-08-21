import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Award,
  BarChart3,
  BookOpen,
  Bot,
  CheckCircle2,
  ChevronRight,
  FileText,
  GraduationCap,
  Layers3,
  Library,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Users,
  Video,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { apiGet, apiPost } from "../../api/client.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { translateAcademyContent } from "../../platform/i18n/academyContentMessages.js";
import { translateAcademyExpansion } from "../../platform/i18n/academyExpansionMessages.js";
import { translateAcademySkillGap } from "../../platform/i18n/academySkillGapMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import AcademyPathAuthoring from "./AcademyPathAuthoring.jsx";
import "./academy.css";

const CONTENT_TYPES = [
  "video",
  "document",
  "sop",
  "interactive",
  "live",
  "announcement",
  "poster",
  "survey",
];

function localized(value, locale) {
  if (!value || typeof value !== "object") return "";
  return String(value[locale] || value.en || value.tr || Object.values(value).find(Boolean) || "");
}

function contentIcon(type) {
  if (type === "video" || type === "live") return Video;
  if (type === "document" || type === "sop") return FileText;
  return Layers3;
}

function statusLabel(status, t, locale) {
  const map = {
    completed: t("completed"),
    in_progress: t("inProgress"),
    assigned: t("assigned"),
    draft: t("draft"),
    published: t("published"),
    revoked: translateAcademyContent(locale, "revoked"),
  };
  return map[status] || "—";
}

function EmptyState({ icon: Icon = Library, title, detail }) {
  return (
    <section
      className="eay-academy-empty"
      data-eay-product-state="empty"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <Icon size={28} aria-hidden="true" />
      <strong>{title}</strong>
      {detail ? <p>{detail}</p> : null}
    </section>
  );
}

function LoadingState({ label }) {
  return (
    <section
      className="eay-academy-loading"
      data-eay-product-state="loading"
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-busy="true"
    >
      <LoaderCircle className="spin" size={22} aria-hidden="true" />
      <span>{label}</span>
    </section>
  );
}

function ErrorState({ label, retry, retryLabel }) {
  return (
    <section
      className="eay-academy-error"
      data-eay-product-state="error"
      role="alert"
      aria-atomic="true"
    >
      <strong>{label}</strong>
      <button type="button" onClick={retry}>
        <RefreshCw size={16} aria-hidden="true" />
        {retryLabel}
      </button>
    </section>
  );
}

function Metric({ label, value }) {
  return (
    <article className="eay-academy-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function MyLearning({ data, locale, t, formatDate, onOpen }) {
  const items = data?.enrollments || [];
  if (!items.length) return <EmptyState title={t("academyEmpty")} />;

  return (
    <section className="eay-academy-list" aria-label={t("myLearning")}>
      {items.map((item) => (
        <article className="eay-academy-learning-card" key={item.id}>
          <div className="eay-academy-card-icon"><GraduationCap size={20} aria-hidden="true" /></div>
          <div className="eay-academy-card-copy">
            <div className="eay-academy-card-topline">
              <span className={`eay-academy-status is-${item.status}`}>{statusLabel(item.status, t, locale)}</span>
              {item.due_at ? <small>{t("due")}: {formatDate(item.due_at, { dateStyle: "medium" })}</small> : null}
            </div>
            <h3>{localized(item.title_i18n, locale) || item.key}</h3>
            <p>{item.source === "role" ? t("academyRequired") : t("academyOptional")}</p>
          </div>
          <button className="eay-academy-primary" type="button" onClick={() => onOpen(item.id)}>
            {item.status === "assigned" ? t("start") : t("academyResume")}
            <ChevronRight size={16} aria-hidden="true" />
          </button>
        </article>
      ))}
    </section>
  );
}

function Catalog({ data, locale, t, query, setQuery }) {
  const normalized = query.trim().toLocaleLowerCase(locale);
  const items = (data?.content || []).filter((item) => {
    if (!normalized) return true;
    return [
      localized(item.title_i18n, locale),
      localized(item.description_i18n, locale),
      item.slug,
      item.content_type,
    ]
      .join(" ")
      .toLocaleLowerCase(locale)
      .includes(normalized);
  });

  return (
    <>
      <label className="eay-academy-search">
        <Search size={18} aria-hidden="true" />
        <span className="sr-only">{t("search")}</span>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("search")} />
      </label>
      {items.length ? (
        <section className="eay-academy-catalog-grid">
          {items.map((item) => {
            const Icon = contentIcon(item.content_type);
            return (
              <article key={item.id} className="eay-academy-content-card">
                <div className="eay-academy-content-kind">
                  <Icon size={19} aria-hidden="true" />
                  <span>{translateAcademyContent(locale, item.content_type)}</span>
                </div>
                <h3>{localized(item.title_i18n, locale) || item.slug}</h3>
                <p>{localized(item.description_i18n, locale)}</p>
              </article>
            );
          })}
        </section>
      ) : <EmptyState title={t("emptyTitle")} />}
    </>
  );
}

function Certificates({ data, locale, t, formatDate }) {
  const items = data?.certificates || [];
  if (!items.length) return <EmptyState icon={Award} title={t("emptyTitle")} />;
  return (
    <section className="eay-academy-certificate-grid">
      {items.map((item) => (
        <article key={item.id} className={`eay-academy-certificate ${item.revoked_at ? "is-revoked" : ""}`}>
          <Award size={28} aria-hidden="true" />
          <span>{item.revoked_at ? statusLabel("revoked", t, locale) : t("completed")}</span>
          <h3>{localized(item.title_i18n, locale) || item.path_key}</h3>
          <p>{item.certificate_code}</p>
          <small>{formatDate(item.issued_at, { dateStyle: "long" })}</small>
        </article>
      ))}
    </section>
  );
}

function JarvisTutor({ locale, t }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function ask(event) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError("");
    try {
      setAnswer(await apiPost("/v1/academy/knowledge/answer", { question: trimmed, locale, top_k: 5 }));
    } catch {
      setError(t("academyLoadError"));
      setAnswer(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="eay-academy-tutor">
      <div className="eay-academy-tutor-intro">
        <div><Bot size={24} aria-hidden="true" /></div>
        <div><span>Jarvis</span><h2>{t("jarvisTutor")}</h2><p>{t("academySubtitle")}</p></div>
      </div>
      <form onSubmit={ask} className="eay-academy-question">
        <label>
          <span className="sr-only">{t("academyAskJarvis")}</span>
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={t("academyQuestionPlaceholder")} rows={3} />
        </label>
        <button type="submit" disabled={busy || !question.trim()}>
          {busy ? <LoaderCircle className="spin" size={17} aria-hidden="true" /> : <Sparkles size={17} aria-hidden="true" />}
          {t("academyAskJarvis")}
        </button>
      </form>
      {error ? <p className="eay-academy-inline-error" role="alert">{error}</p> : null}
      {answer ? (
        <article className="eay-academy-answer">
          <div className="eay-academy-answer-head">
            <strong>{t("academySourceAnswer")}</strong>
            <span>
              {answer.supported
                ? <><CheckCircle2 size={15} aria-hidden="true" /> {t("academySourceAnswer")}</>
                : t("academyNoAnswer")}
            </span>
          </div>
          <p>{answer.answer || (answer.supported ? "" : t("academyNoAnswer"))}</p>
          {(answer.sources || []).length ? (
            <div className="eay-academy-sources">
              <strong>{t("academySources")}</strong>
              {(answer.sources || []).map((source, index) => (
                <article key={`${source.content_version_id}-${source.chunk_ordinal || index}`}>
                  <span>{source.title || source.heading || `${t("academyContentVersion")} ${source.content_version_id}`}</span>
                  <small>{source.source_page ? `#${source.source_page}` : source.source_anchor || source.content_version_id}</small>
                </article>
              ))}
            </div>
          ) : null}
        </article>
      ) : null}
    </section>
  );
}

function ContentStudio({ workspace, locale, t, canAction, refresh }) {
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ title: "", slug: "", description: "", contentType: "video" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function createContent(event) {
    event.preventDefault();
    if (!form.title.trim() || !form.slug.trim()) return;
    setSaving(true);
    setError("");
    try {
      await apiPost("/v1/academy/admin/content", {
        content_type: form.contentType,
        slug: form.slug.trim().toLowerCase().replace(/\s+/g, "-"),
        title_i18n: { [locale]: form.title.trim() },
        description_i18n: form.description.trim() ? { [locale]: form.description.trim() } : {},
        version_label: "v1",
        locale,
        accessibility_metadata: {
          captions_required: form.contentType === "video" || form.contentType === "live",
          transcript_required: form.contentType === "video" || form.contentType === "live",
          keyboard_operable: true,
        },
        status: "draft",
      });
      setForm({ title: "", slug: "", description: "", contentType: "video" });
      setCreating(false);
      await refresh();
    } catch {
      setError(t("errorTitle"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="eay-academy-studio">
      <header className="eay-academy-section-head">
        <div><span>{t("academyAdmin")}</span><h2>{t("contentStudio")}</h2></div>
        {canAction("academy", "manageContent") ? (
          <button type="button" className="eay-academy-primary" onClick={() => setCreating((value) => !value)}>
            <Plus size={16} aria-hidden="true" />{t("academyCreateContent")}
          </button>
        ) : null}
      </header>
      {creating ? (
        <form className="eay-academy-create-form" onSubmit={createContent}>
          <label><span>{t("academyTitle")}</span><input value={form.title} onChange={(event) => setForm((value) => ({ ...value, title: event.target.value }))} required /></label>
          <label><span>{t("academySlug")}</span><input value={form.slug} onChange={(event) => setForm((value) => ({ ...value, slug: event.target.value }))} required /></label>
          <label>
            <span>{t("academyContentType")}</span>
            <select value={form.contentType} onChange={(event) => setForm((value) => ({ ...value, contentType: event.target.value }))}>
              {CONTENT_TYPES.map((item) => (
                <option key={item} value={item}>{translateAcademyContent(locale, item)}</option>
              ))}
            </select>
          </label>
          <label className="wide"><span>{t("academyDescription")}</span><textarea value={form.description} onChange={(event) => setForm((value) => ({ ...value, description: event.target.value }))} rows={3} /></label>
          {error ? <p role="alert">{error}</p> : null}
          <div className="wide eay-academy-form-actions"><button type="button" onClick={() => setCreating(false)}>{t("cancel")}</button><button className="eay-academy-primary" disabled={saving}>{saving ? t("loading") : t("create")}</button></div>
        </form>
      ) : null}
      {(workspace?.content || []).length ? (
        <div className="eay-academy-table-wrap"><table><thead><tr><th>{t("academyTitle")}</th><th>{t("academyContentType")}</th><th>{t("academyContentVersion")}</th><th>{t("status")}</th></tr></thead><tbody>{workspace.content.map((item) => <tr key={item.id}><td><strong>{localized(item.title_i18n, locale) || item.slug}</strong><small>{item.slug}</small></td><td>{translateAcademyContent(locale, item.content_type)}</td><td>{item.version_label || "—"} · {item.locale || "—"}</td><td><span className={`eay-academy-status is-${item.status}`}>{statusLabel(item.status, t, locale)}</span></td></tr>)}</tbody></table></div>
      ) : <EmptyState title={t("emptyTitle")} />}
    </section>
  );
}

function Analytics({ workspace, t, formatNumber }) {
  const summary = workspace?.summary || {};
  const completed = Number(summary.completed_count || 0);
  const enrollments = Number(summary.enrollment_count || 0);
  const completionRate = enrollments ? completed / enrollments : 0;
  return (
    <section className="eay-academy-analytics">
      <div className="eay-academy-metrics">
        <Metric label={t("academyContent")} value={formatNumber(summary.content_count)} />
        <Metric label={t("published")} value={formatNumber(summary.published_content_count)} />
        <Metric label={t("learningPaths")} value={formatNumber(summary.path_count)} />
        <Metric label={t("academyEnrollments")} value={formatNumber(summary.enrollment_count)} />
      </div>
      <article className="eay-academy-analytics-card">
        <div><BarChart3 size={22} aria-hidden="true" /><span>{t("analytics")}</span></div>
        <strong>{Math.round(completionRate * 100)}%</strong>
        <p>{t("completed")} / {t("academyEnrollments")}</p>
      </article>
    </section>
  );
}

export default function AcademyWorkspace() {
  const navigate = useNavigate();
  const { canAction, canFeature } = useAuth();
  const { locale, t, formatDate, formatNumber } = usePlatformPreferences();
  const [data, setData] = useState(null);
  const [workspace, setWorkspace] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("learning");
  const [query, setQuery] = useState("");

  const canStudio = canFeature("academy", "contentStudio");
  const canAnalytics = canFeature("academy", "analytics");
  const experienceLabel = canStudio
    ? translateAcademyExpansion(locale, "scenarioStudio")
    : translateAcademySkillGap(locale, "skillGap");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [home, admin] = await Promise.all([
        apiGet("/v1/academy/me"),
        canStudio ? apiGet("/v1/academy/admin/workspace") : Promise.resolve(null),
      ]);
      setData(home);
      setWorkspace(admin);
    } catch {
      setError(t("academyLoadError"));
      setData(null);
      setWorkspace(null);
    } finally {
      setLoading(false);
    }
  }, [canStudio, t]);

  useEffect(() => { load(); }, [load]);

  const tabs = useMemo(() => {
    const items = [
      ["learning", t("myLearning"), BookOpen],
      ["catalog", t("catalog"), Library],
      ["certificates", t("certificates"), Award],
      ["tutor", t("jarvisTutor"), Bot],
    ];
    if (canStudio) {
      items.push(["studio", t("contentStudio"), Layers3]);
      items.push(["paths", t("learningPaths"), GraduationCap]);
    }
    if (canAnalytics) items.push(["analytics", t("analytics"), BarChart3]);
    return items;
  }, [canAnalytics, canStudio, t]);

  return (
    <main className="eay-academy-page">
      <aside className="eay-academy-nav" aria-label={t("academy")}>
        <button type="button" className="eay-academy-back" onClick={() => navigate("/")} aria-label={t("back")}><ArrowLeft size={18} aria-hidden="true" /></button>
        <div className="eay-academy-brand"><div><GraduationCap size={21} aria-hidden="true" /></div><span><strong>EAY</strong><small>{t("academy")}</small></span></div>
        <nav>{tabs.map(([key, label, Icon]) => <button type="button" key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}><Icon size={18} aria-hidden="true" /><span>{label}</span></button>)}</nav>
        <button type="button" className="eay-academy-back" onClick={() => navigate("/academy/experience")} aria-label={experienceLabel}><Sparkles size={18} aria-hidden="true" /><span className="sr-only">{experienceLabel}</span></button>
        <div className="eay-academy-nav-foot"><Users size={17} aria-hidden="true" /><span>{data?.subject || "—"}</span></div>
      </aside>

      <section className="eay-academy-main" aria-busy={loading ? "true" : "false"}>
        <header className="eay-academy-header">
          <div><span>EAY · {t("academy")}</span><h1>{tabs.find(([key]) => key === tab)?.[1] || t("academy")}</h1><p>{t("academySubtitle")}</p></div>
          <button type="button" className="eay-academy-refresh" onClick={load} disabled={loading}><RefreshCw className={loading ? "spin" : ""} size={17} aria-hidden="true" /><span>{t("refresh")}</span></button>
        </header>

        {loading ? <LoadingState label={t("academyLoading")} /> : null}
        {!loading && error ? <ErrorState label={error} retry={load} retryLabel={t("retry")} /> : null}
        {!loading && !error ? (
          <div className="eay-academy-view" data-eay-product-state="ready">
            {tab === "learning" ? <MyLearning data={data} locale={locale} t={t} formatDate={formatDate} onOpen={(id) => navigate(`/academy/enrollments/${id}`)} /> : null}
            {tab === "catalog" ? <Catalog data={data} locale={locale} t={t} query={query} setQuery={setQuery} /> : null}
            {tab === "certificates" ? <Certificates data={data} locale={locale} t={t} formatDate={formatDate} /> : null}
            {tab === "tutor" ? <JarvisTutor locale={locale} t={t} /> : null}
            {tab === "studio" && canStudio ? <ContentStudio workspace={workspace} locale={locale} t={t} canAction={canAction} refresh={load} /> : null}
            {tab === "paths" && canStudio ? <AcademyPathAuthoring workspace={workspace} locale={locale} t={t} canAction={canAction} refresh={load} /> : null}
            {tab === "analytics" && canAnalytics ? <Analytics workspace={workspace} t={t} formatNumber={formatNumber} /> : null}
          </div>
        ) : null}
      </section>
    </main>
  );
}
