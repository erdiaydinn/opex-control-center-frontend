import React, { useMemo, useState } from "react";
import { CheckCircle2, Plus, Save, Trash2 } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translateAcademyQuizAuthoring } from "../../platform/i18n/academyQuizAuthoringMessages.js";
import "./academy-quiz-authoring.css";

function localized(value, locale) {
  if (!value || typeof value !== "object") return "";
  return String(value[locale] || value.en || value.tr || Object.values(value).find(Boolean) || "");
}

function option(value = "", correct = false) {
  return { value, correct };
}

function question() {
  return {
    type: "single_choice",
    prompt: "",
    points: "1",
    required: true,
    options: [option(), option()],
  };
}

function initialForm() {
  return {
    contentVersionId: "",
    kind: "completion",
    checkpointSeconds: "",
    passScore: "80",
    maxAttempts: "",
    required: true,
    status: "draft",
    questions: [question()],
  };
}

function quizStatus(status, t) {
  if (status === "published") return t("published");
  if (status === "draft") return t("draft");
  return "—";
}

export default function AcademyQuizAuthoring({ workspace, locale, t, canAction, refresh }) {
  const qt = useMemo(() => (key) => translateAcademyQuizAuthoring(locale, key), [locale]);
  const versions = workspace?.authoring?.published_versions || [];
  const existing = workspace?.authoring?.quizzes || [];
  const canManage = canAction("academy", "manageQuizzes");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(initialForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const selectedVersion = versions.find((item) => item.content_version_id === form.contentVersionId);
  const checkpointAvailable = Boolean(selectedVersion && ["video", "live"].includes(selectedVersion.content_type));
  const checkpointMaxSeconds = selectedVersion?.duration_ms == null
    ? undefined
    : Number(selectedVersion.duration_ms) / 1000;

  function reset() {
    setForm(initialForm());
    setError("");
  }

  function close() {
    reset();
    setOpen(false);
  }

  function selectContentVersion(contentVersionId) {
    const selected = versions.find((item) => item.content_version_id === contentVersionId);
    const supportsCheckpoint = Boolean(selected && ["video", "live"].includes(selected.content_type));
    setForm((current) => ({
      ...current,
      contentVersionId,
      kind: supportsCheckpoint ? current.kind : "completion",
      checkpointSeconds: supportsCheckpoint ? current.checkpointSeconds : "",
    }));
  }

  function updateQuestion(index, patch) {
    setForm((current) => ({
      ...current,
      questions: current.questions.map((item, itemIndex) => (
        itemIndex === index ? { ...item, ...patch } : item
      )),
    }));
  }

  function changeType(index, type) {
    setForm((current) => ({
      ...current,
      questions: current.questions.map((item, itemIndex) => {
        if (itemIndex !== index) return item;
        if (type === "true_false") {
          return {
            ...item,
            type,
            options: [option(qt("trueLabel"), false), option(qt("falseLabel"), false)],
          };
        }
        return { ...item, type, options: item.options.length >= 2 ? item.options : [option(), option()] };
      }),
    }));
  }

  function updateOption(questionIndex, optionIndex, patch) {
    setForm((current) => ({
      ...current,
      questions: current.questions.map((item, itemIndex) => {
        if (itemIndex !== questionIndex) return item;
        return {
          ...item,
          options: item.options.map((choice, choiceIndex) => (
            choiceIndex === optionIndex ? { ...choice, ...patch } : choice
          )),
        };
      }),
    }));
  }

  function setCorrect(questionIndex, optionIndex, checked) {
    setForm((current) => ({
      ...current,
      questions: current.questions.map((item, itemIndex) => {
        if (itemIndex !== questionIndex) return item;
        return {
          ...item,
          options: item.options.map((choice, choiceIndex) => ({
            ...choice,
            correct: item.type === "multiple_choice"
              ? (choiceIndex === optionIndex ? checked : choice.correct)
              : choiceIndex === optionIndex && checked,
          })),
        };
      }),
    }));
  }

  function addOption(questionIndex) {
    setForm((current) => ({
      ...current,
      questions: current.questions.map((item, itemIndex) => (
        itemIndex === questionIndex && item.type !== "true_false" && item.options.length < 20
          ? { ...item, options: [...item.options, option()] }
          : item
      )),
    }));
  }

  function removeOption(questionIndex, optionIndex) {
    setForm((current) => ({
      ...current,
      questions: current.questions.map((item, itemIndex) => (
        itemIndex === questionIndex && item.type !== "true_false" && item.options.length > 2
          ? { ...item, options: item.options.filter((_, choiceIndex) => choiceIndex !== optionIndex) }
          : item
      )),
    }));
  }

  function addQuestion() {
    setForm((current) => ({
      ...current,
      questions: current.questions.length < 200 ? [...current.questions, question()] : current.questions,
    }));
  }

  function removeQuestion(index) {
    setForm((current) => ({
      ...current,
      questions: current.questions.length > 1
        ? current.questions.filter((_, itemIndex) => itemIndex !== index)
        : current.questions,
    }));
  }

  function validate() {
    if (!form.contentVersionId) return qt("validationContent");
    if (form.kind === "checkpoint") {
      if (!checkpointAvailable || form.checkpointSeconds === "" || Number(form.checkpointSeconds) < 0) {
        return qt("validationCheckpoint");
      }
      if (checkpointMaxSeconds != null && Number(form.checkpointSeconds) > checkpointMaxSeconds) {
        return qt("validationCheckpoint");
      }
    }
    for (const item of form.questions) {
      if (!item.prompt.trim()) return qt("validationQuestion");
      if (item.options.length < 2 || item.options.some((choice) => !choice.value.trim())) return qt("validationOptions");
      const correctCount = item.options.filter((choice) => choice.correct).length;
      if (item.type === "multiple_choice" && correctCount < 1) return qt("validationCorrectMultiple");
      if (item.type !== "multiple_choice" && correctCount !== 1) return qt("validationCorrectSingle");
    }
    return "";
  }

  async function save(event) {
    event.preventDefault();
    const validation = validate();
    if (validation) {
      setError(validation);
      return;
    }
    setSaving(true);
    setError("");
    try {
      await apiPost("/v1/academy/admin/quizzes", {
        content_version_id: form.contentVersionId,
        kind: form.kind,
        checkpoint_at_ms: form.kind === "checkpoint" ? Math.round(Number(form.checkpointSeconds) * 1000) : null,
        pass_score: Number(form.passScore),
        max_attempts: form.maxAttempts === "" ? null : Number(form.maxAttempts),
        required: form.required,
        status: form.status,
        questions: form.questions.map((item) => ({
          question_type: item.type,
          prompt_i18n: { [locale]: item.prompt.trim() },
          points: Number(item.points),
          required: item.required,
          options: item.options.map((choice) => ({
            label_i18n: { [locale]: choice.value.trim() },
            is_correct: choice.correct,
          })),
        })),
      });
      close();
      await refresh();
    } catch {
      setError(qt("createError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="eay-academy-quiz-authoring">
      <header className="eay-academy-section-head">
        <div><span>{t("academyAdmin")}</span><h2>{qt("quizAuthoring")}</h2></div>
        {canManage ? (
          <button className="eay-academy-primary" type="button" onClick={() => setOpen((value) => !value)} disabled={!versions.length}>
            <Plus size={16} aria-hidden="true" />{qt("createQuiz")}
          </button>
        ) : null}
      </header>

      {canManage && !versions.length ? <p className="eay-academy-quiz-notice">{qt("noPublishedContent")}</p> : null}

      {open && canManage ? (
        <form className="eay-academy-quiz-builder" onSubmit={save}>
          <div className="eay-academy-quiz-basics">
            <label><span>{qt("contentVersion")}</span><select value={form.contentVersionId} onChange={(event) => selectContentVersion(event.target.value)} required><option value="">—</option>{versions.map((item) => <option key={item.content_version_id} value={item.content_version_id}>{localized(item.title_i18n, locale) || item.slug} · {item.version_label} · {item.locale}</option>)}</select></label>
            <label><span>{qt("quizKind")}</span><select value={form.kind} onChange={(event) => setForm((value) => ({ ...value, kind: event.target.value, checkpointSeconds: event.target.value === "completion" ? "" : value.checkpointSeconds }))}><option value="completion">{qt("completionQuiz")}</option><option value="checkpoint" disabled={!checkpointAvailable}>{qt("checkpointQuiz")}</option></select></label>
            {form.kind === "checkpoint" ? <label><span>{qt("checkpointSecond")}</span><input type="number" min="0" max={checkpointMaxSeconds} step="0.1" value={form.checkpointSeconds} onChange={(event) => setForm((value) => ({ ...value, checkpointSeconds: event.target.value }))} required /></label> : null}
            <label><span>{qt("passScore")}</span><input type="number" min="0" max="100" step="0.01" value={form.passScore} onChange={(event) => setForm((value) => ({ ...value, passScore: event.target.value }))} required /></label>
            <label><span>{qt("maxAttempts")}</span><input type="number" min="1" max="100" placeholder={qt("unlimited")} value={form.maxAttempts} onChange={(event) => setForm((value) => ({ ...value, maxAttempts: event.target.value }))} /></label>
            <label><span>{t("status")}</span><select value={form.status} onChange={(event) => setForm((value) => ({ ...value, status: event.target.value }))}><option value="draft">{t("draft")}</option><option value="published">{t("published")}</option></select></label>
            <label className="eay-academy-quiz-toggle"><input type="checkbox" checked={form.required} onChange={(event) => setForm((value) => ({ ...value, required: event.target.checked }))} /><span>{qt("requiredQuiz")}</span></label>
          </div>

          <div className="eay-academy-quiz-question-head"><h3>{qt("questions")}</h3><button type="button" onClick={addQuestion}><Plus size={16} aria-hidden="true" />{qt("addQuestion")}</button></div>
          <div className="eay-academy-quiz-questions">
            {form.questions.map((item, questionIndex) => (
              <fieldset key={`question-${questionIndex}`} className="eay-academy-quiz-question">
                <legend>{qt("questions")} {questionIndex + 1}</legend>
                <div className="eay-academy-quiz-question-grid">
                  <label><span>{qt("questionType")}</span><select value={item.type} onChange={(event) => changeType(questionIndex, event.target.value)}><option value="single_choice">{qt("singleChoice")}</option><option value="multiple_choice">{qt("multipleChoice")}</option><option value="true_false">{qt("trueFalse")}</option></select></label>
                  <label><span>{qt("points")}</span><input type="number" min="0.01" max="1000" step="0.01" value={item.points} onChange={(event) => updateQuestion(questionIndex, { points: event.target.value })} /></label>
                  <label className="eay-academy-quiz-prompt"><span>{qt("questionPrompt")}</span><textarea rows={2} value={item.prompt} onChange={(event) => updateQuestion(questionIndex, { prompt: event.target.value })} required /></label>
                </div>
                <div className="eay-academy-quiz-options-head"><strong>{qt("options")}</strong>{item.type !== "true_false" ? <button type="button" onClick={() => addOption(questionIndex)} disabled={item.options.length >= 20}><Plus size={15} aria-hidden="true" />{qt("addOption")}</button> : null}</div>
                <div className="eay-academy-quiz-options">
                  {item.options.map((choice, optionIndex) => (
                    <div key={`option-${questionIndex}-${optionIndex}`} className="eay-academy-quiz-option">
                      <label className="eay-academy-quiz-correct"><input type={item.type === "multiple_choice" ? "checkbox" : "radio"} name={`correct-${questionIndex}`} checked={choice.correct} onChange={(event) => setCorrect(questionIndex, optionIndex, event.target.checked)} /><span className="sr-only">{qt("correctAnswer")}</span><CheckCircle2 size={18} aria-hidden="true" /></label>
                      <input value={choice.value} onChange={(event) => updateOption(questionIndex, optionIndex, { value: event.target.value })} required />
                      {item.type !== "true_false" ? <button type="button" className="eay-academy-quiz-icon" onClick={() => removeOption(questionIndex, optionIndex)} disabled={item.options.length <= 2} aria-label={qt("removeOption")}><Trash2 size={16} aria-hidden="true" /></button> : null}
                    </div>
                  ))}
                </div>
                <button type="button" className="eay-academy-quiz-remove-question" onClick={() => removeQuestion(questionIndex)} disabled={form.questions.length <= 1}><Trash2 size={16} aria-hidden="true" />{qt("removeQuestion")}</button>
              </fieldset>
            ))}
          </div>
          {error ? <p className="eay-academy-inline-error" role="alert">{error}</p> : null}
          <div className="eay-academy-form-actions"><button type="button" onClick={close}>{t("cancel")}</button><button className="eay-academy-primary" type="submit" disabled={saving}><Save size={16} aria-hidden="true" />{saving ? t("loading") : qt("saveQuiz")}</button></div>
        </form>
      ) : null}

      <div className="eay-academy-quiz-existing">
        <h3>{qt("existingQuizzes")}</h3>
        {existing.length ? <div className="eay-academy-table-wrap"><table><thead><tr><th>{qt("contentVersion")}</th><th>{qt("quizKind")}</th><th>{qt("questionCount")}</th><th>{qt("attemptLimit")}</th><th>{t("status")}</th></tr></thead><tbody>{existing.map((item) => <tr key={item.id}><td><strong>{localized(item.title_i18n, locale) || item.slug}</strong><small>{item.version_label} · {item.locale} · {qt("quizVersion")} {item.version_number}</small></td><td>{item.kind === "checkpoint" ? qt("checkpointQuiz") : qt("completionQuiz")}</td><td>{item.question_count}</td><td>{item.max_attempts ?? qt("unlimited")}</td><td><span className={`eay-academy-status is-${item.status}`}>{quizStatus(item.status, t)}</span></td></tr>)}</tbody></table></div> : <p className="eay-academy-quiz-notice">—</p>}
      </div>
    </section>
  );
}
