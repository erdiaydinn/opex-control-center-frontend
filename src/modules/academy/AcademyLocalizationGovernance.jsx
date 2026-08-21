import React, { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Languages, LoaderCircle, RefreshCw, Send, ShieldCheck, XCircle } from "lucide-react";

import { apiGet, apiPost, apiPut } from "../../api/client.js";
import { translateAcademyExpansion } from "../../platform/i18n/academyExpansionMessages.js";
import { translateAcademyStudioTerm } from "../../platform/i18n/academyStudioTermMessages.js";
import "./academy-expansion.css";

function LocalePolicyRow({ item, locale, onSaved }) {
  const tx = (key) => translateAcademyExpansion(locale, key);
  const st = (key) => translateAcademyStudioTerm(locale, key);
  const [draft, setDraft] = useState(item);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    setSaving(true);
    setError("");
    try {
      await apiPut(`/v1/academy/localization/settings/${encodeURIComponent(item.locale)}`, {
        enabled: Boolean(draft.enabled),
        required: Boolean(draft.required),
        is_default: Boolean(draft.is_default),
        allow_machine_draft: Boolean(draft.allow_machine_draft),
      });
      await onSaved();
    } catch (reason) {
      setError(reason instanceof Error && reason.message ? reason.message : tx("governanceError"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="eay-academy-governance-row">
      <header><strong>{item.locale}</strong>{draft.is_default ? <span className="eay-academy-status is-published">{st("defaultLabel")}</span> : null}</header>
      <label className="check"><input type="checkbox" checked={Boolean(draft.enabled)} onChange={(event) => setDraft((value) => ({ ...value, enabled: event.target.checked }))} /><span>{tx("enabled")}</span></label>
      <label className="check"><input type="checkbox" checked={Boolean(draft.required)} onChange={(event) => setDraft((value) => ({ ...value, required: event.target.checked, enabled: event.target.checked ? true : value.enabled }))} /><span>{tx("required")}</span></label>
      <label className="check"><input type="checkbox" checked={Boolean(draft.allow_machine_draft)} onChange={(event) => setDraft((value) => ({ ...value, allow_machine_draft: event.target.checked }))} /><span>{tx("machineDraft")}</span></label>
      <label className="check"><input type="checkbox" checked={Boolean(draft.is_default)} onChange={(event) => setDraft((value) => ({ ...value, is_default: event.target.checked, enabled: event.target.checked ? true : value.enabled }))} /><span>{st("defaultLabel")}</span></label>
      {error ? <p className="eay-academy-inline-error" role="alert">{error}</p> : null}
      <button type="button" className="eay-academy-secondary" disabled={saving} onClick={save}>{saving ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <ShieldCheck size={15} aria-hidden="true" />}{tx("savePolicy")}</button>
    </article>
  );
}

export default function AcademyLocalizationGovernance({ workspace, locale, t }) {
  const tx = (key) => translateAcademyExpansion(locale, key);
  const st = (key) => translateAcademyStudioTerm(locale, key);
  const [settings, setSettings] = useState([]);
  const [translations, setTranslations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newLocale, setNewLocale] = useState("");
  const [sourceVersionId, setSourceVersionId] = useState("");
  const [targetVersionId, setTargetVersionId] = useState("");
  const [method, setMethod] = useState("human");
  const [rejectReasons, setRejectReasons] = useState({});
  const [busyAction, setBusyAction] = useState("");

  const sourceOptions = workspace?.authoring?.published_versions || [];
  const contentVersions = workspace?.authoring?.content_versions || [];
  const selectedSource = sourceOptions.find((item) => item.content_version_id === sourceVersionId) || sourceOptions[0] || null;
  const targetOptions = useMemo(() => {
    if (!selectedSource) return [];
    return contentVersions.filter((item) => (
      item.content_id === selectedSource.content_id
      && item.content_version_id !== selectedSource.content_version_id
      && item.locale !== selectedSource.locale
      && ["draft", "published"].includes(item.version_status)
      && ["draft", "published"].includes(item.content_status)
    ));
  }, [contentVersions, selectedSource]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [settingsPayload, translationPayload] = await Promise.all([
        apiGet("/v1/academy/localization/settings"),
        apiGet("/v1/academy/localization/translations"),
      ]);
      setSettings(settingsPayload?.items || []);
      setTranslations(translationPayload?.items || []);
    } catch (reason) {
      setError(reason instanceof Error && reason.message ? reason.message : tx("governanceError"));
    } finally {
      setLoading(false);
    }
  }, [locale]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!sourceVersionId && sourceOptions[0]?.content_version_id) setSourceVersionId(sourceOptions[0].content_version_id);
  }, [sourceOptions, sourceVersionId]);
  useEffect(() => {
    if (!targetOptions.some((item) => item.content_version_id === targetVersionId)) setTargetVersionId(targetOptions[0]?.content_version_id || "");
  }, [targetOptions, targetVersionId]);

  async function addLocale(event) {
    event.preventDefault();
    if (!newLocale.trim()) return;
    setBusyAction("locale");
    setError("");
    try {
      await apiPut(`/v1/academy/localization/settings/${encodeURIComponent(newLocale.trim())}`, { enabled: true, required: false, is_default: false, allow_machine_draft: false });
      setNewLocale("");
      await load();
    } catch (reason) {
      setError(reason instanceof Error && reason.message ? reason.message : tx("governanceError"));
    } finally {
      setBusyAction("");
    }
  }

  async function createLineage(event) {
    event.preventDefault();
    if (!sourceVersionId || !targetVersionId) return;
    setBusyAction("lineage");
    setError("");
    try {
      await apiPost("/v1/academy/localization/translations", { source_version_id: sourceVersionId, target_version_id: targetVersionId, translation_method: method });
      await load();
    } catch (reason) {
      setError(reason instanceof Error && reason.message ? reason.message : tx("governanceError"));
    } finally {
      setBusyAction("");
    }
  }

  async function act(translationId, action, payload = {}) {
    setBusyAction(`${translationId}:${action}`);
    setError("");
    try {
      if (action === "submit") await apiPost(`/v1/academy/localization/translations/${translationId}/submit`, {});
      else await apiPost(`/v1/academy/localization/translations/${translationId}/review`, payload);
      await load();
    } catch (reason) {
      setError(reason instanceof Error && reason.message ? reason.message : tx("governanceError"));
    } finally {
      setBusyAction("");
    }
  }

  return (
    <section className="eay-academy-expansion-card" aria-busy={loading ? "true" : "false"}>
      <header className="eay-academy-expansion-head"><div><span><Languages size={16} aria-hidden="true" /> EAY Academy</span><h2>{tx("localizationGovernance")}</h2><p>{tx("localizationHint")}</p></div><button type="button" className="eay-academy-secondary" onClick={load} disabled={loading}><RefreshCw className={loading ? "spin" : ""} size={15} aria-hidden="true" />{tx("refresh")}</button></header>
      {loading ? <p role="status"><LoaderCircle className="spin" size={18} aria-hidden="true" /> {t("loading")}</p> : null}
      {error ? <p className="eay-academy-inline-error" role="alert">{error}</p> : null}
      {!loading ? (
        <div className="eay-academy-governance-grid" data-eay-product-state="ready">
          <section>
            <h3>{tx("localePolicy")}</h3>
            <form className="eay-academy-expansion-form" onSubmit={addLocale}><label className="wide"><span>{tx("locale")}</span><input value={newLocale} onChange={(event) => setNewLocale(event.target.value)} placeholder="fa-IR" /></label><button type="submit" className="eay-academy-secondary" disabled={busyAction === "locale"}>{tx("savePolicy")}</button></form>
            <div className="eay-academy-governance-list">{settings.map((item) => <LocalePolicyRow key={item.locale} item={item} locale={locale} onSaved={load} />)}</div>
          </section>
          <section>
            <h3>{tx("translations")}</h3>
            <form className="eay-academy-expansion-form" onSubmit={createLineage}>
              <label><span>{tx("sourceVersion")}</span><select value={sourceVersionId} onChange={(event) => setSourceVersionId(event.target.value)}>{sourceOptions.map((item) => <option value={item.content_version_id} key={item.content_version_id}>{item.slug} · {item.version_label} · {item.locale}</option>)}</select></label>
              <label><span>{tx("targetVersion")}</span><select value={targetVersionId} onChange={(event) => setTargetVersionId(event.target.value)}>{targetOptions.map((item) => <option value={item.content_version_id} key={item.content_version_id}>{item.slug} · {item.version_label} · {item.locale} · {item.version_status}</option>)}</select></label>
              <label><span>{tx("translationMethod")}</span><select value={method} onChange={(event) => setMethod(event.target.value)}>{["human", "machine_assisted", "machine_draft"].map((item) => <option value={item} key={item}>{st(item)}</option>)}</select></label>
              <button type="submit" className="eay-academy-secondary" disabled={!sourceVersionId || !targetVersionId || busyAction === "lineage"}><Send size={15} aria-hidden="true" />{tx("translations")}</button>
            </form>
            {!translations.length ? <p role="status">{tx("noTranslations")}</p> : <div className="eay-academy-governance-list">{translations.map((item) => <article className="eay-academy-governance-row" key={item.translation_id}><header><strong>{item.source_locale} → {item.target_locale}</strong><span className={`eay-academy-status ${item.authoritative ? "is-published" : item.stale ? "is-revoked" : "is-draft"}`}>{item.authoritative ? tx("authoritative") : item.stale ? tx("stale") : item.workflow_status}</span></header><small>{tx("sourceVersion")}: {item.source_version_id}</small><small>{tx("targetVersion")}: {item.target_version_id}</small><small>{tx("translationMethod")}: {st(item.translation_method)}</small>{item.workflow_status === "draft" ? <button type="button" className="eay-academy-secondary" onClick={() => act(item.translation_id, "submit")} disabled={busyAction.startsWith(String(item.translation_id))}><Send size={14} aria-hidden="true" />{tx("submitReview")}</button> : null}{item.workflow_status === "submitted" ? <><label><span className="sr-only">{tx("reject")}</span><input value={rejectReasons[item.translation_id] || ""} onChange={(event) => setRejectReasons((value) => ({ ...value, [item.translation_id]: event.target.value }))} /></label><div className="eay-academy-governance-actions"><button type="button" className="eay-academy-secondary" onClick={() => act(item.translation_id, "review", { decision: "approved", reason: null })}><CheckCircle2 size={14} aria-hidden="true" />{tx("approve")}</button><button type="button" className="eay-academy-secondary" disabled={!String(rejectReasons[item.translation_id] || "").trim()} onClick={() => act(item.translation_id, "review", { decision: "rejected", reason: rejectReasons[item.translation_id] })}><XCircle size={14} aria-hidden="true" />{tx("reject")}</button></div></> : null}</article>)}</div>}
          </section>
        </div>
      ) : null}
    </section>
  );
}