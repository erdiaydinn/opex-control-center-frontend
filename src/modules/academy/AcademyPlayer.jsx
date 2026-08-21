import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, CheckCircle2, Circle, LoaderCircle, LockKeyhole, Play, RefreshCw, ShieldCheck } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import { apiFetch, apiGet, apiPost } from "../../api/client.js";
import { translateAcademyPlayer } from "../../platform/i18n/academyPlayerMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import "./academy-player.css";

function localized(value, locale) {
  if (!value || typeof value !== "object") return "";
  return String(value[locale] || value.en || value.tr || Object.values(value).find(Boolean) || "");
}

function progressLabel(status, t) {
  if (status === "completed") return t("completed");
  if (status === "in_progress") return t("inProgress");
  return t("notStarted");
}

function percent(value) {
  return Math.max(0, Math.min(100, Number(value || 0)));
}

export default function AcademyPlayer() {
  const { enrollmentId } = useParams();
  const navigate = useNavigate();
  const { locale } = usePlatformPreferences();
  const t = useMemo(() => (key) => translateAcademyPlayer(locale, key), [locale]);
  const [workspace, setWorkspace] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [media, setMedia] = useState(null);
  const [mediaBusy, setMediaBusy] = useState(false);
  const [activeQuiz, setActiveQuiz] = useState(null);
  const [answers, setAnswers] = useState({});
  const [quizResult, setQuizResult] = useState(null);
  const [certificate, setCertificate] = useState(null);
  const [saving, setSaving] = useState(false);
  const videoRef = useRef(null);
  const lastWallClockRef = useRef(null);
  const pendingWatchedMsRef = useRef(0);
  const saveBusyRef = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const value = await apiGet(`/v1/academy/enrollments/${enrollmentId}`);
      setWorkspace(value);
      setSelectedId((current) => current || value.items?.find((item) => item.progress_status !== "completed")?.content_version_id || value.items?.[0]?.content_version_id || null);
    } catch {
      setError(t("loadError"));
    } finally {
      setLoading(false);
    }
  }, [enrollmentId, t]);

  useEffect(() => { load(); }, [load]);

  const selected = useMemo(
    () => workspace?.items?.find((item) => item.content_version_id === selectedId) || null,
    [selectedId, workspace]
  );

  useEffect(() => {
    setMedia(null);
    setActiveQuiz(null);
    setAnswers({});
    setQuizResult(null);
    pendingWatchedMsRef.current = 0;
    lastWallClockRef.current = null;
  }, [selectedId]);

  const hlsNative = useMemo(() => {
    if (typeof document === "undefined") return false;
    const element = document.createElement("video");
    return Boolean(element.canPlayType("application/vnd.apple.mpegurl"));
  }, []);

  const updateSelected = useCallback((result) => {
    setWorkspace((current) => current ? {
      ...current,
      items: current.items.map((item) => item.content_version_id === selectedId ? {
        ...item,
        progress_status: result.status,
        progress_percent: result.progress_percent,
        last_position_ms: result.last_position_ms,
        watched_ms: result.watched_ms,
        progress_revision: result.revision,
      } : item),
    } : current);
  }, [selectedId]);

  const saveProgress = useCallback(async (completeRequested = false) => {
    const item = workspace?.items?.find((entry) => entry.content_version_id === selectedId);
    if (!item || saveBusyRef.current) return;
    const video = videoRef.current;
    const positionMs = video ? Math.max(0, Math.round(video.currentTime * 1000)) : Number(item.last_position_ms || 0);
    const watchedDeltaMs = Math.min(300000, Math.max(0, Math.round(pendingWatchedMsRef.current)));
    if (!completeRequested && watchedDeltaMs < 1000) return;
    saveBusyRef.current = true;
    setSaving(true);
    try {
      const result = await apiFetch(`/v1/academy/enrollments/${enrollmentId}/progress`, {
        method: "PATCH",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({
          content_version_id: item.content_version_id,
          last_position_ms: positionMs,
          watched_delta_ms: watchedDeltaMs,
          complete_requested: completeRequested,
          expected_revision: Number(item.progress_revision || 0),
        }),
      });
      pendingWatchedMsRef.current = 0;
      updateSelected(result);
      if (result.status === "completed") await load();
    } catch {
      await load();
    } finally {
      saveBusyRef.current = false;
      setSaving(false);
    }
  }, [enrollmentId, load, selectedId, updateSelected, workspace]);

  async function authorizeMedia() {
    if (!selected?.media_id || mediaBusy) return;
    setMediaBusy(true);
    setError("");
    try {
      setMedia(await apiPost(`/v1/academy/media/${selected.media_id}/playback-authorization`));
    } catch {
      setError(t("mediaUnavailable"));
    } finally {
      setMediaBusy(false);
    }
  }

  async function openQuiz(quiz) {
    if (!quiz || quiz.passed || activeQuiz?.id === quiz.id) return;
    try {
      const definition = await apiGet(`/v1/academy/enrollments/${enrollmentId}/quizzes/${quiz.id}`);
      setActiveQuiz(definition);
      setAnswers({});
      setQuizResult(null);
      videoRef.current?.pause();
    } catch {
      setError(t("loadError"));
    }
  }

  function onPlaying() {
    lastWallClockRef.current = performance.now();
  }

  function onTimeUpdate() {
    const video = videoRef.current;
    if (!video || video.paused || video.seeking) return;
    const now = performance.now();
    if (lastWallClockRef.current != null) {
      pendingWatchedMsRef.current += Math.min(3000, Math.max(0, now - lastWallClockRef.current));
    }
    lastWallClockRef.current = now;
    const currentMs = Math.round(video.currentTime * 1000);
    const checkpoint = selected?.quizzes?.find((quiz) => quiz.required && !quiz.passed && quiz.checkpoint_at_ms != null && Number(quiz.checkpoint_at_ms) <= currentMs + 250);
    if (checkpoint) void openQuiz(checkpoint);
    if (pendingWatchedMsRef.current >= 15000) void saveProgress(false);
  }

  function onPause() {
    lastWallClockRef.current = null;
    void saveProgress(false);
  }

  async function submitQuiz(event) {
    event.preventDefault();
    if (!activeQuiz) return;
    const quizAnswers = (activeQuiz.questions || []).map((question) => ({
      question_id: question.id,
      selected_option_ids: answers[question.id] || [],
    }));
    if (quizAnswers.some((answer) => !answer.selected_option_ids.length)) {
      setQuizResult({ passed: false, message: t("selectAnswer") });
      return;
    }
    try {
      const result = await apiFetch(`/v1/academy/quizzes/${activeQuiz.id}/attempts`, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ enrollment_id: enrollmentId, answers: quizAnswers }),
      });
      setQuizResult({ passed: Boolean(result.passed), message: result.passed ? t("quizPassed") : t("quizFailed") });
      if (result.passed) {
        await load();
        setTimeout(() => setActiveQuiz(null), 700);
      }
    } catch {
      setQuizResult({ passed: false, message: t("loadError") });
    }
  }

  async function completePath() {
    try {
      const result = await apiPost(`/v1/academy/enrollments/${enrollmentId}/complete`);
      setCertificate(result);
      await load();
    } catch {
      setError(t("completionBlocked"));
    }
  }

  const requiredComplete = useMemo(() => {
    if (!workspace?.items?.length) return false;
    return workspace.items.every((item) => !item.required || (item.progress_status === "completed" && (item.quizzes || []).every((quiz) => !quiz.required || quiz.passed)));
  }, [workspace]);

  if (loading) return <main className="academy-player-page"><div className="academy-player-state" role="status"><LoaderCircle className="spin" />{t("loadingEnrollment")}</div></main>;
  if (error && !workspace) return <main className="academy-player-page"><div className="academy-player-state" role="alert"><strong>{error}</strong><button onClick={load}><RefreshCw size={16} />{t("retry")}</button></div></main>;

  return (
    <main className="academy-player-page">
      <header className="academy-player-header">
        <button type="button" onClick={() => navigate("/academy")}><ArrowLeft size={18} />{t("backToAcademy")}</button>
        <div><span>{t("playerTitle")}</span><h1>{localized(workspace?.enrollment?.title_i18n, locale) || workspace?.enrollment?.path_key}</h1><p>{localized(workspace?.enrollment?.description_i18n, locale)}</p></div>
        <span className="academy-player-protected"><ShieldCheck size={16} />{t("playbackProtected")}</span>
      </header>

      {error ? <div className="academy-player-inline-error" role="alert">{error}</div> : null}

      <div className="academy-player-layout">
        <aside className="academy-player-outline" aria-label={t("pathContent")}>
          <h2>{t("pathContent")}</h2>
          {(workspace?.items || []).map((item) => (
            <button key={item.content_version_id} className={selectedId === item.content_version_id ? "active" : ""} type="button" onClick={() => setSelectedId(item.content_version_id)}>
              {item.progress_status === "completed" ? <CheckCircle2 size={18} /> : <Circle size={18} />}
              <span><strong>{localized(item.title_i18n, locale) || item.slug}</strong><small>{item.required ? t("required") : t("optional")} · {progressLabel(item.progress_status, t)}</small></span>
            </button>
          ))}
        </aside>

        <section className="academy-player-content">
          {selected ? (
            <>
              <div className="academy-player-content-head"><div><span>{selected.content_type}</span><h2>{localized(selected.title_i18n, locale) || selected.slug}</h2><p>{localized(selected.description_i18n, locale)}</p></div><strong>{Math.round(percent(selected.progress_percent))}%</strong></div>
              <div className="academy-player-progress" aria-label={t("progress")}><span style={{ width: `${percent(selected.progress_percent)}%` }} /></div>

              {selected.media_id ? (
                <section className="academy-player-media">
                  {!media ? <button className="academy-player-primary" type="button" onClick={authorizeMedia} disabled={mediaBusy}>{mediaBusy ? <LoaderCircle className="spin" size={17} /> : <Play size={17} />}{t("authorizeMedia")}</button> : null}
                  {media && selected.delivery_mode === "hls" && hlsNative ? <video ref={videoRef} src={media.playback_url} controls preload="metadata" onPlay={onPlaying} onPlaying={onPlaying} onTimeUpdate={onTimeUpdate} onPause={onPause} onSeeking={() => { lastWallClockRef.current = null; }} onSeeked={() => { if (!videoRef.current?.paused) lastWallClockRef.current = performance.now(); }} onEnded={() => void saveProgress(true)} /> : null}
                  {media && selected.delivery_mode === "hls" && !hlsNative ? <div className="academy-player-unsupported" role="status"><LockKeyhole size={24} /><strong>{t("hlsUnsupported")}</strong><p>{t("hlsUnsupportedDetail")}</p><span>{t("browserSupport")}: {t("unsupported")}</span></div> : null}
                  {media && selected.delivery_mode === "document" ? <a className="academy-player-primary" href={media.playback_url} target="_blank" rel="noopener noreferrer">{t("openContent")}</a> : null}
                </section>
              ) : <div className="academy-player-unsupported"><strong>{t("mediaUnavailable")}</strong></div>}

              {(selected.quizzes || []).filter((quiz) => quiz.required && !quiz.passed).map((quiz) => <button className="academy-player-checkpoint" type="button" key={quiz.id} onClick={() => openQuiz(quiz)}><LockKeyhole size={17} /><span><strong>{quiz.kind === "checkpoint" ? t("checkpoint") : t("quiz")}</strong><small>{t("checkpointRequired")}</small></span></button>)}

              {selected.content_type !== "video" && selected.content_type !== "live" && selected.progress_status !== "completed" ? <button className="academy-player-primary" type="button" disabled={saving} onClick={() => saveProgress(true)}>{t("markReviewed")}</button> : null}
            </>
          ) : null}

          <footer className="academy-player-completion">
            <button type="button" className="academy-player-primary" disabled={!requiredComplete} onClick={completePath}>{t("completePath")}</button>
            {!requiredComplete ? <p>{t("completionBlocked")}</p> : null}
            {certificate?.certificate_code ? <div className="academy-player-certificate" role="status"><CheckCircle2 size={20} /><div><strong>{t("certificateIssued")}</strong><span>{certificate.certificate_code}</span></div></div> : null}
          </footer>
        </section>
      </div>

      {activeQuiz ? <div className="academy-player-modal-backdrop"><section className="academy-player-quiz" role="dialog" aria-modal="true" aria-labelledby="academy-quiz-title"><h2 id="academy-quiz-title">{t("quiz")}</h2><form onSubmit={submitQuiz}>{(activeQuiz.questions || []).map((question) => <fieldset key={question.id}><legend>{localized(question.prompt_i18n, locale)}</legend>{(question.options || []).map((option) => { const multiple = question.question_type === "multiple_choice"; const selectedValues = answers[question.id] || []; const checked = selectedValues.includes(option.id); return <label key={option.id}><input type={multiple ? "checkbox" : "radio"} name={`question-${question.id}`} checked={checked} onChange={(event) => setAnswers((current) => ({ ...current, [question.id]: multiple ? (event.target.checked ? [...selectedValues, option.id] : selectedValues.filter((value) => value !== option.id)) : [option.id] }))} /><span>{localized(option.label_i18n, locale)}</span></label>; })}</fieldset>)}{quizResult ? <p className={quizResult.passed ? "is-pass" : "is-fail"} role="status">{quizResult.message}</p> : null}<div className="academy-player-quiz-actions"><button type="button" onClick={() => setActiveQuiz(null)}>×</button><button className="academy-player-primary" type="submit">{t("submitQuiz")}</button></div></form></section></div> : null}
    </main>
  );
}
