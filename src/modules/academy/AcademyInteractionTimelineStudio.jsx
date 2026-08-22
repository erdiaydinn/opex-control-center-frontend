import React, { useMemo, useRef, useState } from "react";
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

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function formatTime(value) {
  const totalSeconds = Math.max(0, Math.round(Number(value || 0) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

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
  const [selectedNodeKey, setSelectedNodeKey] = useState("interaction-1");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const timelineRef = useRef(null);
  const dragRef = useRef(null);

  const selectedVersion = useMemo(
    () => versions.find((item) => item.content_version_id === contentVersionId) || versions[0] || null,
    [contentVersionId, versions],
  );

  const timelineDurationMs = useMemo(() => {
    const governedDuration = Number(selectedVersion?.duration_ms);
    if (Number.isFinite(governedDuration) && governedDuration > 0) return governedDuration;
    const latestNodeMs = nodes.reduce((maximum, node) => Math.max(maximum, Number(node.at_ms) || 0), 0);
    return Math.max(60000, latestNodeMs + 30000);
  }, [nodes, selectedVersion]);

  const orderedNodes = useMemo(
    () => [...nodes].sort((left, right) => Number(left.at_ms) - Number(right.at_ms) || left.node_key.localeCompare(right.node_key)),
    [nodes],
  );

  function updateNode(index, patch) {
    setNodes((items) => items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  function updateNodeByKey(nodeKey, patch) {
    setNodes((items) => items.map((item) => (item.node_key === nodeKey ? { ...item, ...patch } : item)));
  }

  function renameNode(index, value) {
    const oldKey = nodes[index]?.node_key || "";
    const nextKey = value.trim().toLowerCase().replace(/\s+/g, "-");
    updateNode(index, { node_key: nextKey });
    if (selectedNodeKey === oldKey) setSelectedNodeKey(nextKey);
  }

  function addNode() {
    let next = nodes.length + 1;
    while (nodes.some((node) => node.node_key === `interaction-${next}`)) next += 1;
    const node = makeNode(next);
    setNodes((items) => [...items, node]);
    setSelectedNodeKey(node.node_key);
  }

  function removeNode(index) {
    const node = nodes[index];
    setNodes((items) => items.filter((_, itemIndex) => itemIndex !== index));
    if (node && selectedNodeKey === node.node_key) {
      setSelectedNodeKey(nodes[index - 1]?.node_key || nodes[index + 1]?.node_key || "");
    }
  }

  function timeFromClientX(clientX) {
    const rect = timelineRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) return 0;
    const ratio = clamp((clientX - rect.left) / rect.width, 0, 1);
    return Math.round(ratio * timelineDurationMs);
  }

  function markerPointerDown(event, nodeKey) {
    if (event.button !== 0) return;
    dragRef.current = { nodeKey, pointerId: event.pointerId };
    event.currentTarget.setPointerCapture(event.pointerId);
    setSelectedNodeKey(nodeKey);
    updateNodeByKey(nodeKey, { at_ms: timeFromClientX(event.clientX) });
  }

  function markerPointerMove(event) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    updateNodeByKey(drag.nodeKey, { at_ms: timeFromClientX(event.clientX) });
  }

  function markerPointerUp(event) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragRef.current = null;
  }

  function markerKeyDown(event, nodeKey) {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const current = Number(nodes.find((node) => node.node_key === nodeKey)?.at_ms) || 0;
    const step = event.shiftKey ? 5000 : 1000;
    const direction = event.key === 'ArrowLeft' ? -1 : 1;
    setSelectedNodeKey(nodeKey);
    updateNodeByKey(nodeKey, { at_ms: clamp(current + direction * step, 0, timelineDurationMs) });
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
          <div className="eay-academy-timeline-ruler" aria-hidden="true">
            {[0, 0.25, 0.5, 0.75, 1].map((ratio) => <span key={ratio}>{formatTime(timelineDurationMs * ratio)}</span>)}
          </div>
          <div className="eay-academy-timeline-track" ref={timelineRef}>
            {orderedNodes.map((node) => {
              const percent = clamp((Number(node.at_ms) || 0) / timelineDurationMs, 0, 1) * 100;
              return (
                <button
                  type="button"
                  key={node.node_key}
                  className={`eay-academy-timeline-marker ${selectedNodeKey === node.node_key ? "is-selected" : ""}`}
                  style={{ left: `${percent}%` }}
                  onFocus={() => setSelectedNodeKey(node.node_key)}
                  onPointerDown={(event) => markerPointerDown(event, node.node_key)}
                  onPointerMove={markerPointerMove}
                  onPointerUp={markerPointerUp}
                  onPointerCancel={markerPointerUp}
                  onKeyDown={(event) => markerKeyDown(event, node.node_key)}
                  aria-label={`${node.node_key}. ${ix("timeMs")}: ${Math.round(Number(node.at_ms) || 0)}`}
                >
                  <strong>{formatTime(node.at_ms)}</strong>
                  <span>{node.node_key}</span>
                  <small>{node.node_type.replaceAll("_", " ")}</small>
                </button>
              );
            })}
          </div>
        </div>

        <fieldset className="wide eay-academy-expansion-set"><legend>{tx("nodes")}</legend>
          {nodes.map((node, index) => (
            <div className={`eay-academy-expansion-row ${selectedNodeKey === node.node_key ? "is-selected" : ""}`} key={`${index}-${node.node_key}`}>
              <label><span>{tx("nodeKey")}</span><input required value={node.node_key} onFocus={() => setSelectedNodeKey(node.node_key)} onChange={(event) => renameNode(index, event.target.value)} /></label>
              <label><span>{tx("nodeType")}</span><select value={node.node_type} onFocus={() => setSelectedNodeKey(node.node_key)} onChange={(event) => updateNode(index, { node_type: event.target.value })}>{NODE_TYPES.map((kind) => <option key={kind} value={kind}>{kind.replaceAll("_", " ")}</option>)}</select></label>
              <label><span>{ix("timeMs")}</span><input type="number" min="0" value={node.at_ms} onFocus={() => setSelectedNodeKey(node.node_key)} onChange={(event) => updateNode(index, { at_ms: event.target.value })} /></label>
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
