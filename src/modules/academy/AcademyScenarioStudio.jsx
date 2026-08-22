import React, { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, GitBranch, LoaderCircle, Plus, Save, Sparkles, Trash2 } from "lucide-react";

import { apiPost } from "../../api/client.js";
import { translateAcademyExpansion } from "../../platform/i18n/academyExpansionMessages.js";
import { translateAcademyGraph } from "../../platform/i18n/academyGraphMessages.js";
import { translateAcademyStudioTerm } from "../../platform/i18n/academyStudioTermMessages.js";
import AcademyScenarioGraphCanvas from "./AcademyScenarioGraphCanvas.jsx";
import "./academy-expansion.css";

function initialNodes(locale) {
  return [
    {
      node_key: "start",
      node_type: "scene",
      prompt_i18n: { [locale]: "" },
      payload: { authoring_position: { x: 34, y: 42 } },
      terminal: false,
      terminal_outcome: null,
    },
    {
      node_key: "complete",
      node_type: "outcome",
      prompt_i18n: { [locale]: "" },
      payload: { authoring_position: { x: 254, y: 42 } },
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
  const gx = (key) => translateAcademyGraph(locale, key);
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
  const [entryNodeKey, setEntryNodeKey] = useState("start");
  const [selectedNodeKey, setSelectedNodeKey] = useState("start");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const nodeKeys = useMemo(() => nodes.map((item) => item.node_key).filter(Boolean), [nodes]);

  function updateNode(index, patch) {
    setNodes((items) => items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  function updateNodeKey(index, rawValue) {
    const oldKey = nodes[index]?.node_key || "";
    const newKey = rawValue.trim().toLowerCase().replace(/\s+/g, "-");
    updateNode(index, { node_key: newKey });
    if (!oldKey || oldKey === newKey) return;
    setEdges((items) => items.map((edge) => ({
      ...edge,
      from_node_key: edge.from_node_key === oldKey ? newKey : edge.from_node_key,
      to_node_key: edge.to_node_key === oldKey ? newKey : edge.to_node_key,
    })));
    if (entryNodeKey === oldKey) setEntryNodeKey(newKey);
    if (selectedNodeKey === oldKey) setSelectedNodeKey(newKey);
  }

  function updateNodePrompt(index, value) {
    updateNode(index, { prompt_i18n: value.trim() ? { [locale]: value } : {} });
  }

  function updateNodePosition(nodeKey, position) {
    setNodes((items) => items.map((item) => (
      item.node_key === nodeKey
        ? { ...item, payload: { ...(item.payload || {}), authoring_position: position } }
        : item
    )));
  }

  function updateEdge(index, patch) {
    setEdges((items) => items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  function updateEdgeLabel(index, value) {
    updateEdge(index, { label_i18n: { [locale]: value } });
  }

  function addNode() {
    const next = nodes.length + 1;
    const nodeKey = `node-${next}`;
    setNodes((items) => [
      ...items,
      {
        node_key: nodeKey,
        node_type: "decision",
        prompt_i18n: {},
        payload: { authoring_position: { x: 34 + ((next - 1) % 4) * 220, y: 42 + Math.floor((next - 1) / 4) * 150 } },
        terminal: false,
        terminal_outcome: null,
      },
    ]);
    setSelectedNodeKey(nodeKey);
  }

  function removeNode(index) {
    const node = nodes[index];
    if (!node) return;
    if (node.terminal && nodes.filter((item) => item.terminal).length <= 1) {
      setError(gx("cannotRemoveTerminal"));
      return;
    }
    const remaining = nodes.filter((_, itemIndex) => itemIndex !== index);
    setError("");
    setNodes(remaining);
    setEdges((items) => items.filter((edge) => edge.from_node_key !== node.node_key && edge.to_node_key !== node.node_key));
    if (entryNodeKey === node.node_key) setEntryNodeKey(remaining[0]?.node_key || "");
    if (selectedNodeKey === node.node_key) setSelectedNodeKey(remaining[0]?.node_key || "");
  }

  function moveNodeOrder(index, direction) {
    const target = index + direction;
    if (target < 0 || target >= nodes.length) return;
    setNodes((items) => {
      const next = [...items];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  function addEdge() {
    const fallbackEntry = entryNodeKey || nodeKeys[0] || "";
    setEdges((items) => [
      ...items,
      {
        from_node_key: fallbackEntry,
        choice_key: `choice-${items.length + 1}`,
        to_node_key: nodeKeys.at(-1) || fallbackEntry,
        label_i18n: { [locale]: "" },
        score_delta: 0,
        correct: false,
        feedback_i18n: {},
      },
    ]);
  }

  function removeEdge(index) {
    setEdges((items) => items.filter((_, itemIndex) => itemIndex !== index));
  }

  async function saveScenario(event) {
    event.preventDefault();
    if (!contentVersionId || !scenarioKey.trim() || !title.trim() || !entryNodeKey) return;
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
        entryNodeKey,
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
        <label><span>{gx("entryNode")}</span><select value={entryNodeKey} onChange={(event) => setEntryNodeKey(event.target.value)}>{nodeKeys.map((key) => <option value={key} key={key}>{key}</option>)}</select></label>

        <div className="wide">
          <AcademyScenarioGraphCanvas nodes={nodes} edges={edges} locale={locale} selectedKey={selectedNodeKey} onSelect={setSelectedNodeKey} onMove={updateNodePosition} />
        </div>

        <fieldset className="wide eay-academy-expansion-set"><legend>{tx("nodes")}</legend>{nodes.map((node, index) => <div className={`eay-academy-expansion-row ${selectedNodeKey === node.node_key ? "is-selected" : ""}`} key={`${index}-${node.node_key}`}><label><span>{tx("nodeKey")}</span><input value={node.node_key} onFocus={() => setSelectedNodeKey(node.node_key)} onChange={(event) => updateNodeKey(index, event.target.value)} /></label><label><span>{tx("nodeType")}</span><select value={node.node_type} onFocus={() => setSelectedNodeKey(node.node_key)} onChange={(event) => updateNode(index, { node_type: event.target.value })}>{["scene", "decision", "task", "evidence", "outcome"].map((kind) => <option value={kind} key={kind}>{st(kind)}</option>)}</select></label><label className="grow"><span>{tx("prompt")}</span><input value={node.prompt_i18n?.[locale] || ""} onFocus={() => setSelectedNodeKey(node.node_key)} onChange={(event) => updateNodePrompt(index, event.target.value)} /></label><label className="check"><input type="checkbox" checked={node.terminal} onChange={(event) => updateNode(index, { terminal: event.target.checked, terminal_outcome: event.target.checked ? (node.terminal_outcome || "completed") : null })} /><span>{tx("terminal")}</span></label>{node.terminal ? <label><span>{tx("terminalOutcome")}</span><select value={node.terminal_outcome || "completed"} onChange={(event) => updateNode(index, { terminal_outcome: event.target.value })}>{["completed", "failed", "remediation"].map((outcome) => <option value={outcome} key={outcome}>{st(outcome)}</option>)}</select></label> : null}<div className="eay-academy-row-actions"><button type="button" className="eay-academy-icon-action" aria-label={gx("moveNodeUp")} disabled={index === 0} onClick={() => moveNodeOrder(index, -1)}><ArrowUp size={15} aria-hidden="true" /></button><button type="button" className="eay-academy-icon-action" aria-label={gx("moveNodeDown")} disabled={index === nodes.length - 1} onClick={() => moveNodeOrder(index, 1)}><ArrowDown size={15} aria-hidden="true" /></button><button type="button" className="eay-academy-icon-action is-danger" aria-label={gx("removeNode")} onClick={() => removeNode(index)}><Trash2 size={15} aria-hidden="true" /></button></div></div>)}<button type="button" className="eay-academy-secondary" onClick={addNode}><Plus size={15} aria-hidden="true" />{tx("addNode")}</button></fieldset>

        <fieldset className="wide eay-academy-expansion-set"><legend>{tx("edges")}</legend>{edges.map((edge, index) => <div className="eay-academy-expansion-row" key={`${index}-${edge.choice_key}`}><label><span>{tx("fromNode")}</span><select value={edge.from_node_key} onChange={(event) => updateEdge(index, { from_node_key: event.target.value })}>{nodeKeys.map((key) => <option value={key} key={key}>{key}</option>)}</select></label><label><span>{tx("choiceKey")}</span><input value={edge.choice_key} onChange={(event) => updateEdge(index, { choice_key: event.target.value.trim().toLowerCase().replace(/\s+/g, "-") })} /></label><label><span>{tx("toNode")}</span><select value={edge.to_node_key} onChange={(event) => updateEdge(index, { to_node_key: event.target.value })}>{nodeKeys.map((key) => <option value={key} key={key}>{key}</option>)}</select></label><label className="grow"><span>{tx("choiceLabel")}</span><input value={edge.label_i18n?.[locale] || ""} onChange={(event) => updateEdgeLabel(index, event.target.value)} required /></label><label><span>{tx("scoreDelta")}</span><input type="number" min="-1000" max="1000" value={edge.score_delta} onChange={(event) => updateEdge(index, { score_delta: Number(event.target.value) })} /></label><label className="check"><input type="checkbox" checked={edge.correct} onChange={(event) => updateEdge(index, { correct: event.target.checked })} /><span>{tx("correctChoice")}</span></label><div className="eay-academy-row-actions"><button type="button" className="eay-academy-icon-action is-danger" aria-label={gx("removeEdge")} onClick={() => removeEdge(index)}><Trash2 size={15} aria-hidden="true" /></button></div></div>)}<button type="button" className="eay-academy-secondary" onClick={addEdge}><Plus size={15} aria-hidden="true" />{tx("addEdge")}</button></fieldset>

        {message ? <p className="wide eay-academy-expansion-success" role="status">{message}</p> : null}
        {error ? <p className="wide eay-academy-inline-error" role="alert">{error}</p> : null}
        <div className="wide eay-academy-form-actions"><button className="eay-academy-primary" type="submit" disabled={saving}>{saving ? <LoaderCircle className="spin" size={16} aria-hidden="true" /> : <Save size={16} aria-hidden="true" />}{saving ? t("loading") : tx("saveScenario")}</button></div>
      </form>
    </section>
  );
}
