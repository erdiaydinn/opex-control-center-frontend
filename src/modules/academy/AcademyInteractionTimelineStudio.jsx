import React, { useMemo, useState } from "react";
import { Clock3, LoaderCircle, Plus, Save, Sparkles, Trash2 } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translateAcademyExpansion } from "../../platform/i18n/academyExpansionMessages.js";
import { translateAcademyInteraction } from "../../platform/i18n/academyInteractionMessages.js";
import "./academy-expansion.css";

const NODE_TYPES = [
  "checkpoint",
  "hotspot",
  "single_choice",
  "multiple_choice",
  "drag_drop",
  "overlay",
  "reflection",
  "branch",
  "cta",
];

async function sha256(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (item) => item.toString(16).padStart(2, "0")).join("");
}

function makeNode(index) {
  return {
    node_key: `interaction-${index}`,
    node_type: "checkpoint",
    at_ms: Math.max(0, (index - 1) * 30000),
    blocking: true,
    required: true,
    score_weight: 0,
    prompt: "",
    payloadText: "{}",
  };
}

export default function AcademyInteractionTimelineStudio({ workspace, locale, t, refresh }) {
  const tx = (key) => translateAcademyExpansion(locale, key);
  const ix = (key) => translateAcademyInteraction(locale, key);
  const versions = useMemo(
    () => (workspace?.authoring?.published_versions || []).filter((item) => ["video", "interactive", "live"].includes(item.content_type)),
    [workspace],
  );
  const [contentVersionId, setContentVersionId] = useState(versions[0]?.content_version_id || "");
  const [versionNumber, setVersionNumber] = useState(1);
  const [status, setStatus] = useState("draft");
  const [nodes, setNodes] = useState([makeNode(1)]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const orderedNodes = useMemo(
    () => [...nodes].sort((left, right) => Number(left.at_ms) - Number(right.at_ms) || left.node_key.localeCompare(right.node_key)),
    [nodes],
  );

  function updateNode(index, patch) {
    setNodes((items) => items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  function addNode() {
    setNodes((items) => [...items, makeNode(items.length + 1)]);
  }

  function removeNode(index) {
    setNodes((items) => items.filter((_, itemIndex) => itemIndex !== index));
  }

  async function saveTimeline(event) {
    event.preventDefault();
    if (!contentVersionId || !nodes.length) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const normalizedNodes = nodes.map((node) => {
        let extraPayload = {};
        try {
          extraPayload = node.payloadText.trim() ? JSON.parse(node.payloadText) : {};
        } catch {
          throw new Error(`${ix("payload")}: JSON`);
        }
        return {
          node_key: node.node_key.trim().toLowerCase().replace(/\s+/g, "-"),
          node_type: node.node_type,
          at_ms: Number(node.at_ms),
          blocking: Boolean(node.blocking),
          required: Boolean(node.required),
          score_weight: Number(node.score_weight),
          payload: {
            ...extraPayload,
            ...(node.prompt.trim() ? { prompt_i18n: { [locale]: node.prompt.trim() } } : {}),
          },
        };
      });
      const fingerprint = await sha256(JSON.stringify({
        contentVersionId,
        versionNumber: Number(versionNumber),
        status,
        nodes: normalizedNodes,
      }));
      await apiPost("/v1/academy/admin/interaction-sets", {
        content_version_id: contentVersionId,
        version_number: Number(versionNumber),
        title_i18n: { [locale]: ix("timeline") },
        source_fingerprint: fingerprint,
        nodes: normalizedNodes,
        status,
      });
      setMessage(ix("saved"));
      if (refresh) await refresh();
    } catch (reason) {
      setError(reason instanceof Error && reason.message ? reason.message : ix("error"));
    } finally {
      setSaving(false);
    }
  }

  if (!versions.length) {
    return (
      <section className="eay-academy-expansion-card" data-eay-product-state="empty" role="status">
        <Clock3 size={24} aria-hidden="true" />
        <strong>{tx("interactionStudio")}</strong>
        <p>{tx("noPublishedVersions")}</p>
      </section>
    );
  }

  return (
    <section className="eay-academy-expansion-card" data-eay-product-state="ready">
      <header className="eay-academy-expansion-head">
        <div><span><Sparkles size={16} aria-hidden="true" /> EAY Academy</span><h2>{tx("interactionStudio")}</h2><p>{ix("hint")}</p></div>
      </header>
      <form className="eay-academy-expansion-form" onSubmit={saveTimeline}>
        <label><span>{tx("contentVersion")}</span><select value={contentVersionId} onChange={(event) => setContentVersionId(event.target.value)}>{versions.map((item) => <option value={item.content_version_id} key={item.content_version_id}>{item.slug} · {item.version_label} · {item.locale}</option>)}</select></label>
        <label><span>{tx("versionNumber")}</span><input type="number" min="1" value={versionNumber} onChange={(event) => setVersionNumber(event.target.value)} /></label>
        <label><span>{ix("status")}</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="draft">{t("draft")}</option><option value="published">{t("published")}</option></select></label>

        <div className="wide eay-academy-expansion-set" aria-label={ix("timeline")}>
          <div className="eay-academy-timeline-preview">
            {orderedNodes.map((node) => <div key={node.node_key} className="eay-academy-timeline-point"><span>{Math.round(Number(node.at_ms) / 1000)}s</span><strong>{node.node_key}</strong><small>{node.node_type}</small></div>)}
          </div>
        </div>

        <fieldset className="wide eay-academy-expansion-set"><legend>{tx("nodes")}</legend>
          {nodes.map((node, index) => (
            <div className="eay-academy-expansion-row" key={`${index}-${node.node_key}`}>
              <label><span>{tx("nodeKey")}</span><input required value={node.node_key} onChange={(event) => updateNode(index, { node_key: event.target.value })} /></label>
              <label><span>{tx("nodeType")}</span><select value={node.node_type} onChange={(event) => updateNode(index, { node_type: event.target.value })}>{NODE_TYPES.map((kind) => <option key={kind} value={kind}>{kind.replaceAll("_", " ")}</option>)}</select></label>
              <label><span>{ix("timeMs")}</span><input type="number" min="0" value={node.at_ms} onChange={(event) => updateNode(index, { at_ms: event.target.value })} /></label>
              <label><span>{ix("scoreWeight")}</span><input type="number" min="0" max="1000" value={node.score_weight} onChange={(event) => updateNode(index, { score_weight: event.target.value })} /></label>
              <label className="grow"><span>{ix("prompt")}</span><input value={node.prompt} onChange={(event) => updateNode(index, { prompt: event.target.value })} /></label>
              <label className="grow"><span>{ix("payload")}</span><input value={node.payloadText} onChange={(event) => updateNode(index, { payloadText: event.target.value })} spellCheck="false" /></label>
              <label className="check"><input type="checkbox" checked={node.blocking} onChange={(event) => updateNode(index, { blocking: event.target.checked })} /><span>{ix("blocking")}</span></label>
              <label className="check"><input type="checkbox" checked={node.required} onChange={(event) => updateNode(index, { required: event.target.checked })} /><span>{tx("required")}</span></label>
              {nodes.length > 1 ? <button type="button" className="eay-academy-secondary" onClick={() => removeNode(index)} aria-label={`${ix("timeline")} ${index + 1}`}><Trash2 size={15} aria-hidden="true" /></button> : null}
            </div>
          ))}
          <button type="button" className="eay-academy-secondary" onClick={addNode}><Plus size={15} aria-hidden="true" />{ix("addInteraction")}</button>
        </fieldset>

        {message ? <p className="wide eay-academy-expansion-success" role="status">{message}</p> : null}
        {error ? <p className="wide eay-academy-inline-error" role="alert">{error}</p> : null}
        <div className="wide eay-academy-form-actions"><button className="eay-academy-primary" type="submit" disabled={saving}>{saving ? <LoaderCircle className="spin" size={16} aria-hidden="true" /> : <Save size={16} aria-hidden="true" />}{saving ? t("loading") : ix("save")}</button></div>
      </form>
    </section>
  );
}
