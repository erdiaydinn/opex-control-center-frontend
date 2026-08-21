import React, { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Award, Clock3, GitBranch, Languages, LoaderCircle, RefreshCw, Target } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { apiGet } from "../../api/client.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import { translateAcademyExpansion } from "../../platform/i18n/academyExpansionMessages.js";
import { translateAcademyInteraction } from "../../platform/i18n/academyInteractionMessages.js";
import { translateAcademySkillGap } from "../../platform/i18n/academySkillGapMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import AcademyAchievements from "./AcademyAchievements.jsx";
import AcademyInteractionTimelineStudio from "./AcademyInteractionTimelineStudio.jsx";
import AcademyLocalizationGovernance from "./AcademyLocalizationGovernance.jsx";
import AcademyScenarioStudio from "./AcademyScenarioStudio.jsx";
import AcademySkillGap from "./AcademySkillGap.jsx";
import "./academy.css";
import "./academy-expansion.css";

export default function AcademyExpansionHub() {
  const navigate = useNavigate();
  const { canFeature } = useAuth();
  const { locale, t, formatDate } = usePlatformPreferences();
  const tx = (key) => translateAcademyExpansion(locale, key);
  const ix = (key) => translateAcademyInteraction(locale, key);
  const sx = (key) => translateAcademySkillGap(locale, key);
  const canStudio = canFeature("academy", "contentStudio");
  const [workspace, setWorkspace] = useState(null);
  const [loading, setLoading] = useState(canStudio);
  const [error, setError] = useState("");
  const [tab, setTab] = useState(canStudio ? "scenario" : "skill-gap");

  const load = useCallback(async () => {
    if (!canStudio) {
      setWorkspace(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      setWorkspace(await apiGet("/v1/academy/admin/workspace"));
    } catch (reason) {
      setWorkspace(null);
      setError(reason instanceof Error && reason.message ? reason.message : t("academyLoadError"));
    } finally {
      setLoading(false);
    }
  }, [canStudio, t]);

  useEffect(() => { load(); }, [load]);

  const tabs = useMemo(() => {
    const items = [
      ["skill-gap", sx("skillGap"), Target],
      ["achievements", tx("achievements"), Award],
    ];
    if (canStudio) {
      items.unshift(["scenario", tx("scenarioStudio"), GitBranch]);
      items.splice(1, 0, ["interaction", tx("interactionStudio"), Clock3]);
      items.push(["localization", tx("localizationGovernance"), Languages]);
    }
    return items;
  }, [canStudio, locale]);

  const hint = tab === "scenario"
    ? tx("scenarioHint")
    : tab === "interaction"
      ? ix("hint")
      : tab === "localization"
        ? tx("localizationHint")
        : tab === "skill-gap"
          ? sx("skillGapHint")
          : tx("achievementsHint");

  return (
    <main className="eay-academy-page">
      <aside className="eay-academy-nav" aria-label={t("academy")}>
        <button type="button" className="eay-academy-back" onClick={() => navigate("/academy")} aria-label={tx("backToAcademy")}><ArrowLeft size={18} aria-hidden="true" /></button>
        <div className="eay-academy-brand"><div><GitBranch size={21} aria-hidden="true" /></div><span><strong>EAY</strong><small>{t("academy")}</small></span></div>
        <nav>{tabs.map(([key, label, Icon]) => <button type="button" key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}><Icon size={18} aria-hidden="true" /><span>{label}</span></button>)}</nav>
      </aside>
      <section className="eay-academy-main" aria-busy={loading ? "true" : "false"}>
        <header className="eay-academy-header"><div><span>EAY · {t("academy")}</span><h1>{tabs.find(([key]) => key === tab)?.[1] || t("academy")}</h1><p>{hint}</p></div>{canStudio ? <button type="button" className="eay-academy-refresh" onClick={load} disabled={loading}><RefreshCw className={loading ? "spin" : ""} size={17} aria-hidden="true" /><span>{tx("refresh")}</span></button> : null}</header>
        {loading ? <div role="status" aria-live="polite" data-eay-product-state="loading"><LoaderCircle className="spin" size={20} aria-hidden="true" /> {t("loading")}</div> : null}
        {!loading && error ? <p className="eay-academy-inline-error" role="alert">{error}</p> : null}
        {!loading && !error ? <div className="eay-academy-view" data-eay-product-state="ready">{tab === "scenario" && canStudio ? <AcademyScenarioStudio workspace={workspace} locale={locale} t={t} refresh={load} /> : null}{tab === "interaction" && canStudio ? <AcademyInteractionTimelineStudio workspace={workspace} locale={locale} t={t} refresh={load} /> : null}{tab === "localization" && canStudio ? <AcademyLocalizationGovernance workspace={workspace} locale={locale} t={t} /> : null}{tab === "skill-gap" ? <AcademySkillGap locale={locale} t={t} formatDate={formatDate} /> : null}{tab === "achievements" ? <AcademyAchievements locale={locale} t={t} formatDate={formatDate} /> : null}</div> : null}
      </section>
    </main>
  );
}
