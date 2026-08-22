import React, { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  BookOpenCheck,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Target,
  Workflow,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { apiGet } from "../../api/client.js";
import { translateAcademyOperationalReadiness } from "../../platform/i18n/academyOperationalReadinessMessages.js";
import { translateAcademySkillGap } from "../../platform/i18n/academySkillGapMessages.js";
import "./academy-expansion.css";

function localized(value, locale) {
  if (!value || typeof value !== "object") return "";
  return value[locale]
    || value.en
    || value.tr
    || Object.values(value).find((item) => typeof item === "string")
    || "";
}

function formatMetric(value, locale) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return new Intl.NumberFormat(locale || "en", { maximumFractionDigits: 6 }).format(numeric);
}

export default function AcademySkillGap({ locale, t, formatDate }) {
  const navigate = useNavigate();
  const sx = (key) => translateAcademySkillGap(locale, key);
  const ox = (key) => translateAcademyOperationalReadiness(locale, key);
  const [snapshot, setSnapshot] = useState(null);
  const [readiness, setReadiness] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [readinessError, setReadinessError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    setReadinessError("");
    const [skillGapResult, readinessResult] = await Promise.allSettled([
      apiGet("/v1/academy/credentials/me/skill-gaps"),
      apiGet("/v1/academy/operational-readiness/me"),
    ]);

    if (skillGapResult.status === "fulfilled") {
      setSnapshot(skillGapResult.value);
    } else {
      setSnapshot(null);
      const reason = skillGapResult.reason;
      setError(reason instanceof Error && reason.message ? reason.message : sx("loadError"));
    }

    if (readinessResult.status === "fulfilled") {
      setReadiness(readinessResult.value);
    } else {
      setReadiness(null);
      const reason = readinessResult.reason;
      setReadinessError(
        reason instanceof Error && reason.message ? reason.message : ox("loadError"),
      );
    }
    setLoading(false);
  }, [locale]);

  useEffect(() => {
    load();
  }, [load]);

  function openRecommendedPath(path) {
    if (path?.enrollment_id) {
      navigate(`/academy/enrollments/${encodeURIComponent(String(path.enrollment_id))}`);
      return;
    }
    navigate("/academy");
  }

  const gaps = snapshot?.gaps || [];
  const recommendations = snapshot?.recommended_paths || [];
  const readinessItems = readiness?.items || [];

  return (
    <section className="eay-academy-expansion-card" aria-busy={loading ? "true" : "false"}>
      <header className="eay-academy-expansion-head">
        <div>
          <span><Target size={16} aria-hidden="true" /> EAY Academy</span>
          <h2>{sx("skillGap")}</h2>
          <p>{sx("skillGapHint")}</p>
        </div>
        <button
          type="button"
          className="eay-academy-secondary"
          onClick={load}
          disabled={loading}
        >
          <RefreshCw className={loading ? "spin" : ""} size={15} aria-hidden="true" />
          {sx("refresh")}
        </button>
      </header>

      {loading ? (
        <p role="status" data-eay-product-state="loading">
          <LoaderCircle className="spin" size={18} aria-hidden="true" /> {t("loading")}
        </p>
      ) : null}
      {!loading && error ? (
        <p className="eay-academy-inline-error" role="alert" data-eay-product-state="error">
          {error}
        </p>
      ) : null}
      {!loading && !error && !gaps.length ? (
        <div
          className="eay-academy-governance-row"
          role="status"
          data-eay-product-state="empty"
        >
          <ShieldCheck size={20} aria-hidden="true" />
          <strong>{sx("noGaps")}</strong>
          <small>
            {sx("policy")}: {snapshot?.recommendation_policy || "deterministic_role_skill_gap_v1"}
          </small>
        </div>
      ) : null}

      {!loading && !error && gaps.length ? (
        <div data-eay-product-state="ready">
          <div className="eay-academy-governance-list">
            {gaps.map((item) => (
              <article className="eay-academy-governance-row" key={item.skill_key}>
                <header>
                  <strong>{localized(item.title_i18n, locale) || item.skill_key}</strong>
                  <span className="eay-academy-status is-draft">
                    {sx("gap")}: {item.gap}
                  </span>
                </header>
                {localized(item.description_i18n, locale) ? (
                  <p>{localized(item.description_i18n, locale)}</p>
                ) : null}
                <small>
                  {sx("currentLevel")}: {item.current_level}/5 · {sx("requiredLevel")}: {item.required_level}/5
                </small>
                <small>
                  {sx("requiredBy")}: {(item.required_by_roles || []).join(", ") || "—"}
                </small>
                {item.latest_evidence ? (
                  <small>
                    {sx("latestEvidence")}: {item.latest_evidence.evidence_type} · {item.latest_evidence.evidence_ref}
                    {item.latest_evidence.observed_at
                      ? ` · ${formatDate(item.latest_evidence.observed_at)}`
                      : ""}
                  </small>
                ) : null}
              </article>
            ))}
          </div>

          <section className="eay-academy-expansion-set" aria-label={sx("recommendedPaths")}>
            <h3><BookOpenCheck size={17} aria-hidden="true" /> {sx("recommendedPaths")}</h3>
            {recommendations.length ? (
              <div className="eay-academy-governance-list">
                {recommendations.map((path) => (
                  <article className="eay-academy-governance-row" key={path.path_key}>
                    <strong>{localized(path.title_i18n, locale) || path.path_key}</strong>
                    <small>
                      {(path.outcomes || [])
                        .map((outcome) => `${outcome.skill_key} → ${outcome.target_level}/5`)
                        .join(" · ")}
                    </small>
                    <button
                      type="button"
                      className="eay-academy-secondary"
                      onClick={() => openRecommendedPath(path)}
                    >
                      {path.enrollment_id ? sx("openLearning") : sx("openAcademy")}
                      <ArrowRight size={15} aria-hidden="true" />
                    </button>
                  </article>
                ))}
              </div>
            ) : (
              <p role="status">{sx("noRecommendation")}</p>
            )}
          </section>

          <small>
            {sx("policy")}: {snapshot?.recommendation_policy || "deterministic_role_skill_gap_v1"}
          </small>
        </div>
      ) : null}

      <section
        className="eay-academy-expansion-set"
        aria-label={ox("title")}
        data-eay-operational-readiness="self-scoped"
      >
        <h3><Workflow size={17} aria-hidden="true" /> {ox("title")}</h3>
        <p>{ox("hint")}</p>

        {!loading && readinessError ? (
          <p className="eay-academy-inline-error" role="alert">
            {readinessError}
          </p>
        ) : null}
        {!loading && !readinessError && !readinessItems.length ? (
          <div className="eay-academy-governance-row" role="status">
            <ShieldCheck size={20} aria-hidden="true" />
            <strong>{ox("noItems")}</strong>
          </div>
        ) : null}
        {!loading && !readinessError && readinessItems.length ? (
          <div className="eay-academy-governance-list">
            {readinessItems.map((item) => (
              <article className="eay-academy-governance-row" key={item.remediation_id}>
                <header>
                  <strong>{localized(item.skill_title_i18n, locale) || item.skill_key}</strong>
                  <span className="eay-academy-status is-draft">
                    {sx("gap")}: {item.gap}
                  </span>
                </header>
                <small>
                  {sx("currentLevel")}: {item.current_level}/5 · {sx("requiredLevel")}: {item.required_level}/5
                </small>
                <small>
                  {ox("source")}: {item.source_domain} · {ox("signal")}: {item.signal_type} · {ox("severity")}: {item.severity}/5
                </small>
                <small>
                  {ox("provenance")}: {item.source_ref} · {item.source_version}
                  {item.source_fingerprint ? ` · ${item.source_fingerprint.slice(0, 12)}…` : ""}
                  {item.occurred_at ? ` · ${formatDate(item.occurred_at)}` : ""}
                </small>
                <small>
                  {ox("recommendedPath")}: {localized(item.recommended_path_title_i18n, locale) || item.recommended_path_key}
                </small>
                <small>
                  {ox("enrollmentStatus")}: {item.enrollment_status || "—"}
                </small>

                {item.latest_observation_id ? (
                  <div data-eay-causal-attribution="false">
                    <strong>{ox("observation")}</strong>
                    <small>
                      {item.metric_key} · {item.metric_direction} · {ox("baseline")}: {formatMetric(item.baseline_value, locale)} · {ox("observed")}: {formatMetric(item.observed_value, locale)} · {ox("delta")}: {formatMetric(item.observed_delta, locale)}
                    </small>
                    <small>
                      {ox("window")}: {item.window_start ? formatDate(item.window_start) : "—"} → {item.window_end ? formatDate(item.window_end) : "—"}
                    </small>
                    <small><ShieldCheck size={14} aria-hidden="true" /> {ox("associationOnly")}</small>
                  </div>
                ) : null}

                <button
                  type="button"
                  className="eay-academy-secondary"
                  onClick={() => openRecommendedPath(item)}
                >
                  {item.enrollment_id ? ox("openLearning") : ox("openAcademy")}
                  <ArrowRight size={15} aria-hidden="true" />
                </button>
              </article>
            ))}
          </div>
        ) : null}
        <small>
          {ox("policy")}: {readiness?.policy || "operational_gap_v1"} · causal_attribution=false
        </small>
      </section>
    </section>
  );
}
