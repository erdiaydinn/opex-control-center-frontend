import React, { useMemo, useState } from "react";
import { GitBranch, LoaderCircle, Plus, Save, Sparkles } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translateAcademyExpansion } from "../../platform/i18n/academyExpansionMessages.js";
import { translateAcademyStudioTerm } from "../../platform/i18n/academyStudioTermMessages.js";
import "./academy-expansion.css";

function initialNodes(locale) {
  return [
    {
      node_key: "start",
      node_type: "scene",
      prompt_i18n: { [locale]: "" },
      payload: {},
      terminal: false,
      terminal_outcome: null,
    },
    {
      node_key: "complete",
      node_type: "outcome",
      prompt_i18n: { [locale]: "" },
      payload: {},
      terminal: true,
      terminal_outcome: "completed",
    },
  ];
}

function initialEdges(locale) {
  return [
    {
      from_node_key: "start",
      choice_key: "continue",
      to_node_key: "complete",
      label_i18n: { [locale]: "" },
      score_delta: 0,
      correct: true,
      feedback_i18n: {},
    },
  ];
}

async function sha256(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (item) => item.toString(16).padStart(2, "0")).join("");
}

export default function AcademyScenarioStudio({ workspace, locale, t, refresh }) {
  const tx = (key) => translateAcademyExpansion(locale, key);
  const st = (key) => translateAcademyStudioTerm(locale, key);
  const versions = workspace?.authoring?.published_versions || [];
  const [contentVersionId, setContentVersionId] = useState(versions[0]?.content_version_id || "");
  const [scenarioKey, setScenarioKey] = useState("");
  const [versionNumber, setVersionNumber] = useState(1);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [passingScore, setPassingScore] = useState(80);
  const [status, setStatus] = useState("draft");
  const [nodes, setNodes] = useState(() => initialNodes(locale));
  const [edges, setEdges] = useState(() => initialEdges(locale));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const nodeKeys = useMemo(() => nodes.map((item) => item.node_key).filter(Boolean), [nodes]);
  const entryNodeKey = nodeKeys[0] || "start";

  function updateNode(index, patch) {
    setNodes((items) => items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  function updateNodePrompt(index, value) {
    updateNode(index, { prompt_i18n: value.trim() ? { [locale]: value } : {} });
  }

  function updateEdge(index, patch) {
    setEdges((items) => items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  function updateEdgeLabel(index, value) {
    updateEdge(index, { label_i18n: { [locale]: value } });
  }

  function addNode() {
    const next = nodes.length + 1;
    setNodes((items) => [
      ...items,
      {
        node_key: `node-${next}`,
        node_type: "decision",
        prompt_i18n: {},
        payload: {},
        terminal: false,
        terminal_outcome: null,
      },
    ]);
  }

  function addEdge() {
    setEdges((items) => [
      ...items,
      {
        from_node_key: entryNodeKey,
        choice_key: `choice-${items.length + 1}`,
        to_node_key: nodeKeys.at(-1) || entryNodeKey,
        label_i18n: { [locale]: "" },
        score_delta: 0,
        correct: false,
        feedback_i18n: {},
      },
    ]);
  }

  async function saveScenario(event) {
    event.preventDefault();
    if (!contentVersionId || !scenarioKey.trim() || !title.trim()) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const normalizedNodes = nodes.map((node) => ({
        ...node,
        prompt_i18n: Object.fromEntries(Object.entries(node.prompt_i18n || {}).filter(([, value]) => String(value).trim())),
      }));
      const normalizedEdges = edges.map((edge) => ({
        ...edge,
        label_i18n: Object.fromEntries(Object.entries(edge.label_i18n || {}).filter(([, value]) => String(value).trim())),
      }));
      const fingerprint = await sha256(JSON.stringify({
        contentVersionId,
        scenarioKey: scenarioKey.trim(),
        versionNumber,
        title: title.trim(),
        description: description.trim(),
        passingScore,
        normalizedNodes,
        normalizedEdges,
      }));
      await apiPost("/v1/academy/admin/scenarios", {
        content_version_id: contentVersionId,
        scenario_key: scenarioKey.trim().toLowerCase().replace(/\s+/g, "-"),
        version_number: Number(versionNumber),
        title_i18n: { [locale]: title.trim() },
        description_i18n: description.trim() ? { [locale]: description.trim() } : {},
        entry_node_key: entryNodeKey,
        passing_score: Number(passingScore),
        source_fingerprint: fingerprint,
        nodes: normalizedNodes,
        edges: normalizedEdges,
        status,
      });
      setMessage(tx("scenarioSaved"));
      if (refresh) await refresh();
    } catch (reason) {
      setError(reason instanceof Error && reason.message ? reason.message : tx("studioError"));
    } finally {
      setSaving(false);
    }
  }

  if (!versions.length) {
    return (
      <section className="eay-academy-expansion-card" data-eay-product-state="empty" role="status">
        <GitBranch size={24} aria-hidden="true" />
        <strong>{tx("scenarioStudio")}</strong>
        <p>{tx("noPublishedVersions")}</p>
      </section>
    );
  }

  return (
    <section className="eay-academy-expansion-card" data-eay-product-state="ready">
      <header className="eay-academy-expansion-head">
        <div><span><Sparkles size={16} aria-hidden="true" /> EAY Academy</span><h2>{tx("scenarioStudio")}</h2><p>{tx("scenarioHint")}</p></div>
      </header>
      <form className="eay-academy-expansion-form" onSubmit={saveScenario}>
        <label><span>{tx("contentVersion")}</span><select value={contentVersionId} onChange={(event) => setContentVersionId(event.target.value)}>{versions.map((item) => <option value={item.content_version_id} key={item.content_version_id}>{item.slug} · {item.version_label} · {item.locale}</option>)}</select></label>
        <label><span>{tx("scenarioKey")}</span><input required value={scenarioKey} onChange={(event) => setScenarioKey(event.target.value)} pattern="[a-zA-Z0-9._ -]+" /></label>
        <label><span>{tx("versionNumber")}</span><input type="number" min="1" value={versionNumber} onChange={(event) => setVersionNumber(event.target.value)} /></label>
        <label><span>{tx("passingScore")}</span><input type="number" min="0" max="100" value={passingScore} onChange={(event) => setPassingScore(event.target.value)} /></label>
        <label className="wide"><span>{t("academyTitle")}</span><input required value={title} onChange={(event) => setTitle(event.target.value)} /></label>
        <label className="wide"><span>{t("academyDescription")}</span><textarea rows="2" value={description} onChange={(event) => setDescription(event.target.value)} /></label>
        <label><span>{t("status")}</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="draft">{t("draft")}</option><option value="published">{t("published")}</option></select></label>

        <fieldset className="wide eay-academy-expansion-set"><legend>{tx("nodes")}</legend>{nodes.map((node, index) => <div className="eay-academy-expansion-row" key={`${index}-${node.node_key}`}><label><span>{tx("nodeKey")}</span><input value={node.node_key} onChange={(event) => updateNode(index, { node_key: event.target.value.trim().toLowerCase().replace(/\s+/g, "-") })} /></label><label><span>{tx("nodeType")}</span><select value={node.node_type} onChange={(event) => updateNode(index, { node_type: event.target.value })}>{["scene", "decision", "task", "evidence", "outcome"].map((kind) => <option value={kind} key={kind}>{st(kind)}</option>)}</select></label><label className="grow"><span>{tx("prompt")}</span><input value={node.prompt_i18n?.[locale] || ""} onChange={(event) => updateNodePrompt(index, event.target.value)} /></label><label className="check"><input type="checkbox" checked={node.terminal} onChange={(event) => updateNode(index, { terminal: event.target.checked, terminal_outcome: event.target.checked ? (node.terminal_outcome || "completed") : null })} /><span>{tx("terminal")}</span></label>{node.terminal ? <label><span>{tx("terminalOutcome")}</span><select value={node.terminal_outcome || "completed"} onChange={(event) => updateNode(index, { terminal_outcome: event.target.value })}>{["completed", "failed", "remediation"].map((outcome) => <option value={outcome} key={outcome}>{st(outcome)}</option>)}</select></label> : null}</div>)}<button type="button" className="eay-academy-secondary" onClick={addNode}><Plus size={15} aria-hidden="true" />{tx("addNode")}</button></fieldset>

        <fieldset className="wide eay-academy-expansion-set"><legend>{tx("edges")}</legend>{edges.map((edge, index) => <div className="eay-academy-expansion-row" key={`${index}-${edge.choice_key}`}><label><span>{tx("fromNode")}</span><select value={edge.from_node_key} onChange={(event) => updateEdge(index, { from_node_key: event.target.value })}>{nodeKeys.map((key) => <option value={key} key={key}>{key}</option>)}</select></label><label><span>{tx("choiceKey")}</span><input value={edge.choice_key} onChange={(event) => updateEdge(index, { choice_key: event.target.value.trim().toLowerCase().replace(/\s+/g, "-") })} /></label><label><span>{tx("toNode")}</span><select value={edge.to_node_key} onChange={(event) => updateEdge(index, { to_node_key: event.target.value })}>{nodeKeys.map((key) => <option value={key} key={key}>{key}</option>)}</select></label><label className="grow"><span>{tx("choiceLabel")}</span><input value={edge.label_i18n?.[locale] || ""} onChange={(event) => updateEdgeLabel(index, event.target.value)} required /></label><label><span>{tx("scoreDelta")}</span><input type="number" min="-1000" max="1000" value={edge.score_delta} onChange={(event) => updateEdge(index, { score_delta: Number(event.target.value) })} /></label><label className="check"><input type="checkbox" checked={edge.correct} onChange={(event) => updateEdge(index, { correct: event.target.checked })} /><span>{tx("correctChoice")}</span></label></div>)}<button type="button" className="eay-academy-secondary" onClick={addEdge}><Plus size={15} aria-hidden="true" />{tx("addEdge")}</button></fieldset>

        {message ? <p className="wide eay-academy-expansion-success" role="status">{message}</p> : null}
        {error ? <p className="wide eay-academy-inline-error" role="alert">{error}</p> : null}
        <div className="wide eay-academy-form-actions"><button className="eay-academy-primary" type="submit" disabled={saving}>{saving ? <LoaderCircle className="spin" size={16} aria-hidden="true" /> : <Save size={16} aria-hidden="true" />}{saving ? t("loading") : tx("saveScenario")}</button></div>
      </form>
    </section>
  );
}
