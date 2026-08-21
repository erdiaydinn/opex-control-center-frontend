import React, { useMemo, useState } from "react";
import { GraduationCap, Layers3, Plus, Save } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translateAcademyAuthoring } from "../../platform/i18n/academyAuthoringMessages.js";
import AcademyQuizAuthoring from "./AcademyQuizAuthoring.jsx";
import "./academy-path-authoring.css";

function localized(value, locale) {
  if (!value || typeof value !== "object") return "";
  return String(value[locale] || value.en || value.tr || Object.values(value).find(Boolean) || "");
}

function emptyForm() {
  return {
    key: "",
    title: "",
    description: "",
    status: "draft",
    certificateEnabled: true,
  };
}

function normalizePathKey(value) {
  return value.trimStart().toLowerCase().replace(/\s+/g, "-");
}

export default function AcademyPathAuthoring({
  workspace,
  locale,
  t,
  canAction,
  refresh,
}) {
  const at = useMemo(() => (key) => translateAcademyAuthoring(locale, key), [locale]);
  const versions = workspace?.authoring?.published_versions || [];
  const roles = workspace?.authoring?.roles || [];
  const paths = workspace?.paths || [];
  const canManage = canAction("academy", "managePaths");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [selectedVersions, setSelectedVersions] = useState({});
  const [selectedRoles, setSelectedRoles] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function reset() {
    setForm(emptyForm());
    setSelectedVersions({});
    setSelectedRoles({});
    setError("");
  }

  function closeBuilder() {
    reset();
    setCreating(false);
  }

  function toggleVersion(contentVersionId) {
    setSelectedVersions((current) => {
      const next = { ...current };
      if (next[contentVersionId]) delete next[contentVersionId];
      else next[contentVersionId] = { required: true };
      return next;
    });
  }

  function toggleVersionRequired(contentVersionId) {
    setSelectedVersions((current) => ({
      ...current,
      [contentVersionId]: {
        ...current[contentVersionId],
        required: !current[contentVersionId]?.required,
      },
    }));
  }

  function toggleRole(roleKey) {
    setSelectedRoles((current) => {
      const next = { ...current };
      if (next[roleKey]) delete next[roleKey];
      else next[roleKey] = { required: true, dueDays: "" };
      return next;
    });
  }

  function updateRole(roleKey, field, value) {
    setSelectedRoles((current) => ({
      ...current,
      [roleKey]: { ...current[roleKey], [field]: value },
    }));
  }

  async function createPath(event) {
    event.preventDefault();
    const chosenVersions = versions.filter((item) => selectedVersions[item.content_version_id]);
    if (!chosenVersions.length) {
      setError(at("selectContentError"));
      return;
    }

    setSaving(true);
    setError("");
    try {
      await apiPost("/v1/academy/admin/paths", {
        key: form.key.trim(),
        title_i18n: { [locale]: form.title.trim() },
        description_i18n: form.description.trim() ? { [locale]: form.description.trim() } : {},
        certificate_enabled: form.certificateEnabled,
        completion_policy: {
          required_progress_percent: 90,
          required_quizzes: true,
        },
        items: chosenVersions.map((item) => ({
          content_version_id: item.content_version_id,
          required: selectedVersions[item.content_version_id]?.required !== false,
          completion_policy: {},
        })),
        role_assignments: roles
          .filter((role) => selectedRoles[role.key])
          .map((role) => ({
            role_key: role.key,
            required: selectedRoles[role.key]?.required !== false,
            due_days: selectedRoles[role.key]?.dueDays === ""
              ? null
              : Number(selectedRoles[role.key]?.dueDays),
          })),
        status: form.status,
      });
      closeBuilder();
      await refresh();
    } catch {
      setError(at("createError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <section className="eay-academy-path-authoring">
        <header className="eay-academy-section-head">
          <div>
            <span>{t("academyAdmin")}</span>
            <h2>{t("learningPaths")}</h2>
          </div>
          {canManage ? (
            <button
              type="button"
              className="eay-academy-primary"
              onClick={() => setCreating((value) => !value)}
              disabled={!versions.length}
            >
              <Plus size={16} aria-hidden="true" />
              {at("createPath")}
            </button>
          ) : null}
        </header>

        {canManage && !versions.length ? (
          <p className="eay-academy-path-notice" role="status">{at("noPublishedContent")}</p>
        ) : null}

        {creating && canManage ? (
          <form className="eay-academy-create-form eay-academy-path-builder" onSubmit={createPath}>
            <label>
              <span>{at("pathKey")}</span>
              <input
                value={form.key}
                onChange={(event) => setForm((value) => ({
                  ...value,
                  key: normalizePathKey(event.target.value),
                }))}
                pattern="[a-z0-9][a-z0-9._-]+"
                minLength={2}
                required
              />
            </label>
            <label>
              <span>{t("academyTitle")}</span>
              <input
                value={form.title}
                onChange={(event) => setForm((value) => ({ ...value, title: event.target.value }))}
                required
              />
            </label>
            <label>
              <span>{t("status")}</span>
              <select
                value={form.status}
                onChange={(event) => setForm((value) => ({ ...value, status: event.target.value }))}
              >
                <option value="draft">{t("draft")}</option>
                <option value="published">{t("published")}</option>
              </select>
            </label>
            <label className="wide">
              <span>{t("academyDescription")}</span>
              <textarea
                value={form.description}
                onChange={(event) => setForm((value) => ({ ...value, description: event.target.value }))}
                rows={3}
              />
            </label>
            <label className="wide eay-academy-path-toggle">
              <input
                type="checkbox"
                checked={form.certificateEnabled}
                onChange={(event) => setForm((value) => ({
                  ...value,
                  certificateEnabled: event.target.checked,
                }))}
              />
              <span>{at("certificateEnabled")}</span>
            </label>

            <fieldset className="wide eay-academy-path-fieldset">
              <legend>{at("publishedContent")}</legend>
              <div className="eay-academy-path-options">
                {versions.map((item) => {
                  const selected = Boolean(selectedVersions[item.content_version_id]);
                  return (
                    <article key={item.content_version_id} className={selected ? "is-selected" : ""}>
                      <label className="eay-academy-path-main-option">
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={() => toggleVersion(item.content_version_id)}
                        />
                        <span>
                          <strong>{localized(item.title_i18n, locale) || item.slug}</strong>
                          <small>{item.version_label} · {item.locale}</small>
                        </span>
                      </label>
                      <label className="eay-academy-path-required">
                        <input
                          type="checkbox"
                          checked={selectedVersions[item.content_version_id]?.required !== false}
                          disabled={!selected}
                          onChange={() => toggleVersionRequired(item.content_version_id)}
                        />
                        <span>{t("academyRequired")}</span>
                      </label>
                    </article>
                  );
                })}
              </div>
            </fieldset>

            <fieldset className="wide eay-academy-path-fieldset">
              <legend>{at("audienceRoles")}</legend>
              <p>{at("audienceOptional")}</p>
              {roles.length ? (
                <div className="eay-academy-path-options">
                  {roles.map((role) => {
                    const selected = Boolean(selectedRoles[role.key]);
                    return (
                      <article key={role.key} className={selected ? "is-selected" : ""}>
                        <label className="eay-academy-path-main-option">
                          <input
                            type="checkbox"
                            checked={selected}
                            onChange={() => toggleRole(role.key)}
                          />
                          <span>
                            <strong>{role.name || role.key}</strong>
                            <small>{role.key}</small>
                          </span>
                        </label>
                        <label className="eay-academy-path-required">
                          <input
                            type="checkbox"
                            checked={selectedRoles[role.key]?.required !== false}
                            disabled={!selected}
                            onChange={() => updateRole(
                              role.key,
                              "required",
                              selectedRoles[role.key]?.required === false,
                            )}
                          />
                          <span>{t("academyRequired")}</span>
                        </label>
                        <label className="eay-academy-path-days">
                          <span>{at("dueDays")}</span>
                          <input
                            type="number"
                            min="0"
                            max="3650"
                            value={selectedRoles[role.key]?.dueDays || ""}
                            disabled={!selected}
                            onChange={(event) => updateRole(role.key, "dueDays", event.target.value)}
                          />
                        </label>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <p className="eay-academy-path-notice">{at("noAudienceRoles")}</p>
              )}
              {!Object.keys(selectedRoles).length ? (
                <small className="eay-academy-path-manual"><GraduationCap size={15} />{at("manualOnly")}</small>
              ) : null}
            </fieldset>

            {error ? <p className="wide eay-academy-inline-error" role="alert">{error}</p> : null}
            <div className="wide eay-academy-form-actions">
              <button type="button" onClick={closeBuilder}>{t("cancel")}</button>
              <button className="eay-academy-primary" type="submit" disabled={saving}>
                <Save size={16} aria-hidden="true" />
                {saving ? t("loading") : at("savePath")}
              </button>
            </div>
          </form>
        ) : null}

        {paths.length ? (
          <section className="eay-academy-path-grid">
            {paths.map((item) => (
              <article key={item.id}>
                <div>
                  <Layers3 size={19} aria-hidden="true" />
                  <span className={`eay-academy-status is-${item.status}`}>
                    {item.status === "published" ? t("published") : t("draft")}
                  </span>
                </div>
                <h3>{localized(item.title_i18n, locale) || item.key}</h3>
                <p>{localized(item.description_i18n, locale)}</p>
                <footer>
                  <span>{t("academyContent")}: {item.item_count}</span>
                  <span>{t("academyEnrollments")}: {item.enrollment_count}</span>
                  <span>{t("completed")}: {item.completed_count}</span>
                </footer>
              </article>
            ))}
          </section>
        ) : (
          <p className="eay-academy-path-notice">{t("emptyTitle")}</p>
        )}
      </section>
      <AcademyQuizAuthoring
        workspace={workspace}
        locale={locale}
        t={t}
        canAction={canAction}
        refresh={refresh}
      />
    </>
  );
}
