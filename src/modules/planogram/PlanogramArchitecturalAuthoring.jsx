import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  BoxSelect,
  Grid3X3,
  LockKeyhole,
  MousePointer2,
  Redo2,
  Ruler,
  ScanLine,
  Trash2,
  Undo2,
  UnlockKeyhole,
} from "lucide-react";

import { translatePlanogramAuthoring } from "../../platform/i18n/planogramAuthoringMessages.js";
import { rotatedRectSvgPoints, svgPointString } from "./planogramEngineering2D.js";
import {
  createPlanogramAuthoringElement,
  createStoreSceneNode,
  PLANOGRAM_AUTHORING_ELEMENT_TYPES,
  projectStoreScene2D,
  snapPlanogramAuthoringValue,
} from "./planogramAuthoringModel.js";
import {
  createPlanogramCadSession,
  executePlanogramCadSessionCommand,
  redoPlanogramCadSession,
  undoPlanogramCadSession,
} from "./planogramCadSession.js";
import "./planogram-authoring.css";

const SVG_WIDTH = 1040;
const SVG_HEIGHT = 640;
const PADDING = 44;
const PRIMARY_TOOLS = ["wall", "door", "window", "column", "no_go", "technical"];
const AUTHORING_TYPES = new Set(PLANOGRAM_AUTHORING_ELEMENT_TYPES);

function projectionFor(document) {
  if (!document) return null;
  const scale = Math.min(
    (SVG_WIDTH - PADDING * 2) / document.floor.widthM,
    (SVG_HEIGHT - PADDING * 2) / document.floor.depthM
  );
  return {
    offsetX: (SVG_WIDTH - document.floor.widthM * scale) / 2,
    offsetY: (SVG_HEIGHT - document.floor.depthM * scale) / 2,
    floorDepthM: document.floor.depthM,
    scale,
  };
}

function modelPoint(event, svg, projection, document) {
  if (!svg || !projection || !document) return null;
  const rect = svg.getBoundingClientRect();
  const svgX = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * SVG_WIDTH;
  const svgY = ((event.clientY - rect.top) / Math.max(rect.height, 1)) * SVG_HEIGHT;
  const x = (svgX - projection.offsetX) / projection.scale;
  const y = document.floor.depthM - (svgY - projection.offsetY) / projection.scale;
  if (x < 0 || y < 0 || x > document.floor.widthM || y > document.floor.depthM) return null;
  return [
    snapPlanogramAuthoringValue(x, document.gridM),
    snapPlanogramAuthoringValue(y, document.gridM),
  ];
}

function numericValue(value, fallback) {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

function architectureSignature(candidate) {
  const architecture = candidate?.store_dna?.architecture;
  if (!architecture) return "none";
  const rows = (architecture.elements || []).map((row) => [
    row.element_id,
    row.element_type,
    row.center_x_m,
    row.center_y_m,
    row.x_m,
    row.y_m,
    row.width_m,
    row.depth_m,
    row.rotation_deg,
    row.clearance_m,
    Boolean(row.locked),
    row.scan_source_element_id,
  ]);
  return JSON.stringify([
    candidate?.store_code || candidate?.store_dna?.store_code || null,
    architecture.source_ref || null,
    architecture.source_review_fingerprint || null,
    architecture.floor_width_m,
    architecture.floor_depth_m,
    rows,
  ]);
}

function elementFromProjection(node, baseElement = null) {
  return {
    ...(baseElement || {}),
    element_id: node.nodeId,
    element_type: node.nodeType,
    center_x_m: node.geometry.centerXM,
    center_y_m: node.geometry.centerYM,
    width_m: node.geometry.widthM,
    depth_m: node.geometry.depthM,
    height_m: node.geometry.heightM,
    rotation_deg: node.geometry.rotationDeg,
    clearance_m: node.metadata?.clearanceM || 0,
    locked: Boolean(node.locked),
    provenance: node.provenance || {},
  };
}

export default function PlanogramArchitecturalAuthoring({ candidate, locale, canEdit, onCandidateChange }) {
  const t = useMemo(() => (key) => translatePlanogramAuthoring(locale, key), [locale]);
  const formatMetric = useMemo(() => {
    const formatter = new Intl.NumberFormat(locale || "en", { maximumFractionDigits: 2 });
    return (value) => formatter.format(Number(value || 0));
  }, [locale]);
  const svgRef = useRef(null);
  const dragRef = useRef(null);
  const sequenceRef = useRef(1);
  const commandSequenceRef = useRef(1);
  const pulseTimerRef = useRef(null);
  const emittedSignatureRef = useRef(null);
  const [session, setSession] = useState(() => createPlanogramCadSession({ candidate }));
  const [tool, setTool] = useState("select");
  const [selectedId, setSelectedId] = useState(null);
  const [dragPreview, setDragPreview] = useState(null);
  const [appliedPulse, setAppliedPulse] = useState(false);
  const [commandError, setCommandError] = useState("");
  const externalSignature = useMemo(() => architectureSignature(candidate), [candidate]);

  useEffect(() => {
    if (emittedSignatureRef.current === externalSignature) {
      emittedSignatureRef.current = null;
      return;
    }
    setSession(createPlanogramCadSession({ candidate }));
    setSelectedId(null);
    setDragPreview(null);
    setTool("select");
    setCommandError("");
  }, [externalSignature]);

  useEffect(() => () => window.clearTimeout(pulseTimerRef.current), []);

  const document = session?.document || null;
  const projection = useMemo(() => projectionFor(document), [document]);
  const scene2D = useMemo(() => (session?.scene ? projectStoreScene2D(session.scene) : null), [session?.scene]);
  const baseElements = useMemo(() => new Map((document?.architecture?.elements || []).map((row) => [row.element_id, row])), [document]);
  const renderedElements = useMemo(() => (scene2D?.nodes || []).filter((node) => AUTHORING_TYPES.has(node.nodeType)).map((node) => elementFromProjection(node, baseElements.get(node.nodeId))), [baseElements, scene2D]);
  const displayElements = useMemo(() => renderedElements.map((element) => (dragPreview?.id === element.element_id ? { ...element, center_x_m: dragPreview.centerXM, center_y_m: dragPreview.centerYM } : element)), [dragPreview, renderedElements]);
  const selected = useMemo(() => renderedElements.find((row) => row.element_id === selectedId) || null, [renderedElements, selectedId]);
  const scanDerived = Boolean(document?.architecture?.source_review_fingerprint || document?.architecture?.scan_fingerprint || String(document?.architecture?.source || "").includes("scan"));

  const diagnosticState = useMemo(() => {
    const collisions = new Set();
    const aisle = new Set();
    const boundary = new Set();
    for (const row of session?.diagnostics?.collisions || []) { collisions.add(row.leftNodeId); collisions.add(row.rightNodeId); }
    for (const row of session?.diagnostics?.aisleViolations || []) { aisle.add(row.leftNodeId); aisle.add(row.rightNodeId); }
    for (const row of session?.diagnostics?.boundaryViolations || []) boundary.add(row.nodeId);
    return { collisions, aisle, boundary };
  }, [session?.diagnostics]);

  const applySession = useCallback((nextSession) => {
    if (!nextSession) return;
    setSession(nextSession);
    setCommandError("");
    setAppliedPulse(true);
    window.clearTimeout(pulseTimerRef.current);
    pulseTimerRef.current = window.setTimeout(() => setAppliedPulse(false), 1100);
    if (selectedId && !nextSession.scene.nodes.some((node) => node.nodeId === selectedId)) setSelectedId(null);
    if (typeof onCandidateChange === "function" && nextSession.candidate) {
      emittedSignatureRef.current = architectureSignature(nextSession.candidate);
      onCandidateChange(nextSession.candidate);
    }
  }, [onCandidateChange, selectedId]);

  const executeCommand = useCallback((rawCommand) => {
    if (!session || !canEdit) return null;
    const command = { commandId: rawCommand.commandId || `CAD-UI-${commandSequenceRef.current++}`, expectedRevision: session.scene.revision, ...rawCommand };
    try {
      const next = executePlanogramCadSessionCommand(session, command);
      applySession(next);
      return next;
    } catch {
      setCommandError(t("commandRejected"));
      return null;
    }
  }, [applySession, canEdit, session, t]);

  const undoSession = useCallback(() => { if (session?.history?.past?.length && canEdit) applySession(undoPlanogramCadSession(session)); }, [applySession, canEdit, session]);
  const redoSession = useCallback(() => { if (session?.history?.future?.length && canEdit) applySession(redoPlanogramCadSession(session)); }, [applySession, canEdit, session]);

  const handleFloorPointerDown = useCallback((event) => {
    if (!canEdit || !document || !projection || tool === "select") return;
    const point = modelPoint(event, svgRef.current, projection, document);
    if (!point) return;
    const created = createPlanogramAuthoringElement({ type: tool, centerXM: point[0], centerYM: point[1], floor: document.floor, sequence: sequenceRef.current, gridM: document.gridM });
    sequenceRef.current += 1;
    const node = createStoreSceneNode({ ...created, provenance: { source: "human", sourceRef: "cad-session-ui" }, metadata: { clearanceM: created.clearance_m || 0 } });
    const next = executeCommand({ type: "CREATE_NODE", node });
    if (next) { setSelectedId(node.nodeId); setTool("select"); }
  }, [canEdit, document, executeCommand, projection, tool]);

  const beginDrag = useCallback((event, element) => {
    event.stopPropagation();
    setSelectedId(element.element_id);
    if (!canEdit || element.locked || tool !== "select" || !document || !projection) return;
    const point = modelPoint(event, svgRef.current, projection, document);
    if (!point) return;
    dragRef.current = { id: element.element_id, dx: point[0] - element.center_x_m, dy: point[1] - element.center_y_m, latest: { centerXM: element.center_x_m, centerYM: element.center_y_m } };
    svgRef.current?.setPointerCapture?.(event.pointerId);
  }, [canEdit, document, projection, tool]);

  const moveDrag = useCallback((event) => {
    const drag = dragRef.current;
    if (!drag || !document || !projection || !canEdit) return;
    const point = modelPoint(event, svgRef.current, projection, document);
    if (!point) return;
    const latest = { centerXM: snapPlanogramAuthoringValue(point[0] - drag.dx, document.gridM), centerYM: snapPlanogramAuthoringValue(point[1] - drag.dy, document.gridM) };
    drag.latest = latest;
    setDragPreview({ id: drag.id, ...latest });
  }, [canEdit, document, projection]);

  const endDrag = useCallback((event) => {
    const drag = dragRef.current;
    dragRef.current = null;
    setDragPreview(null);
    if (svgRef.current?.hasPointerCapture?.(event.pointerId)) svgRef.current.releasePointerCapture(event.pointerId);
    if (drag?.latest) executeCommand({ type: "UPDATE_NODE", nodeId: drag.id, patch: { geometry: { centerXM: drag.latest.centerXM, centerYM: drag.latest.centerYM } } });
  }, [executeCommand]);

  const updateSelectedField = useCallback((field, value) => {
    if (!selected || selected.locked || !document || !canEdit) return;
    const geometry = {};
    const metadata = {};
    if (field === "centerXM") geometry.centerXM = snapPlanogramAuthoringValue(value, document.gridM);
    if (field === "centerYM") geometry.centerYM = snapPlanogramAuthoringValue(value, document.gridM);
    if (field === "widthM") geometry.widthM = snapPlanogramAuthoringValue(Math.max(0.05, value), document.gridM);
    if (field === "depthM") geometry.depthM = snapPlanogramAuthoringValue(Math.max(0.05, value), document.gridM);
    if (field === "rotationDeg") geometry.rotationDeg = value;
    if (field === "clearanceM") metadata.clearanceM = Math.max(0, value);
    executeCommand({ type: "UPDATE_NODE", nodeId: selected.element_id, patch: { ...(Object.keys(geometry).length ? { geometry } : {}), ...(Object.keys(metadata).length ? { metadata } : {}) } });
  }, [canEdit, document, executeCommand, selected]);

  const deleteSelected = useCallback(() => { if (selected && !selected.locked && canEdit && executeCommand({ type: "DELETE_NODE", nodeId: selected.element_id })) setSelectedId(null); }, [canEdit, executeCommand, selected]);
  const toggleSelectedLock = useCallback(() => { if (selected && canEdit) executeCommand({ type: "SET_LOCK", nodeId: selected.element_id, locked: !selected.locked }); }, [canEdit, executeCommand, selected]);
  const resizeFloor = useCallback((widthM, depthM) => { if (document && canEdit) executeCommand({ type: "RESIZE_FLOOR", widthM: snapPlanogramAuthoringValue(Math.max(1, widthM), document.gridM), depthM: snapPlanogramAuthoringValue(Math.max(1, depthM), document.gridM) }); }, [canEdit, document, executeCommand]);

  const handleKeyboardShortcut = useCallback((event) => {
    const modifier = event.ctrlKey || event.metaKey;
    const key = event.key.toLowerCase();
    if (modifier && key === "z") { event.preventDefault(); if (event.shiftKey) redoSession(); else undoSession(); return; }
    if (modifier && key === "y") { event.preventDefault(); redoSession(); return; }
    const tagName = String(event.target?.tagName || "").toUpperCase();
    if (!["INPUT", "TEXTAREA", "SELECT"].includes(tagName) && event.key === "Delete") { event.preventDefault(); deleteSelected(); }
  }, [deleteSelected, redoSession, undoSession]);

  if (!session || !document || !projection) return <section className="eay-authoring eay-authoring--empty"><header><div><Ruler size={21} aria-hidden="true" /><div><h2>{t("title")}</h2><p>{t("subtitle")}</p></div></div></header><p>{t("noArchitecture")}</p></section>;

  const diagnostics = session.diagnostics;
  const hasDiagnostics = diagnostics.collisionCount + diagnostics.aisleViolationCount + diagnostics.boundaryViolationCount > 0;
  const gridStepPx = Math.max(8, document.gridM * projection.scale * 10);
  return (
    <section className="eay-authoring" data-preview-only={session.previewOnly ? "true" : "false"} data-cad-session-contract={session.contract} data-store-scene-revision={session.scene.revision} onKeyDown={handleKeyboardShortcut}>
      <header className="eay-authoring-head"><div><Ruler size={21} aria-hidden="true" /><div><h2>{t("title")}</h2><p>{t("subtitle")}</p></div></div><div className="eay-authoring-badges">{scanDerived ? <span><ScanLine size={14} aria-hidden="true" />{t("scanDraft")}</span> : null}<span>{session.previewOnly ? t("previewOnly") : t("measured")}</span><span>{t("canonicalTruth")}</span></div></header>
      <div className="eay-authoring-status"><span><Grid3X3 size={15} aria-hidden="true" />{t("grid")}: {document.gridM} m</span><span><BoxSelect size={15} aria-hidden="true" />{t("elements")}: {renderedElements.length}</span><span>{t("revision")}: {session.scene.revision}</span><span>{t("history")}: {session.historyDepth} / {session.redoDepth}</span><span>{t("source")}: {document.architecture.source || document.sourceContract}</span>{appliedPulse ? <strong role="status">{t("applied")}</strong> : null}</div>
      <div className="eay-authoring-history-controls" aria-label={t("history")}><button type="button" disabled={!canEdit || !session.history.past.length} onClick={undoSession}><Undo2 size={16} aria-hidden="true" />{t("undo")}</button><button type="button" disabled={!canEdit || !session.history.future.length} onClick={redoSession}><Redo2 size={16} aria-hidden="true" />{t("redo")}</button><span>{t("keyboardHint")}</span></div>
      {commandError ? <p className="eay-authoring-command-error" role="alert">{commandError}</p> : null}
      <div className="eay-authoring-workspace">
        <aside className="eay-authoring-toolbar" aria-label={t("title")}><button type="button" className={tool === "select" ? "active" : ""} aria-pressed={tool === "select"} onClick={() => setTool("select")}><MousePointer2 size={17} aria-hidden="true" />{t("select")}</button>{PRIMARY_TOOLS.map((item) => <button key={item} type="button" className={tool === item ? "active" : ""} aria-pressed={tool === item} disabled={!canEdit} onClick={() => setTool(item)}>{t(item)}</button>)}<div className="eay-authoring-tool-divider" />{PLANOGRAM_AUTHORING_ELEMENT_TYPES.filter((item) => !PRIMARY_TOOLS.includes(item)).map((item) => <button key={item} type="button" className={tool === item ? "active" : ""} aria-pressed={tool === item} disabled={!canEdit} onClick={() => setTool(item)}>{t(item)}</button>)}</aside>
        <div className="eay-authoring-canvas-wrap"><p className="eay-authoring-hint">{tool === "select" ? t("selectHint") : t("addHint")}</p><svg ref={svgRef} className={`eay-authoring-canvas eay-authoring-canvas--${tool}`} viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`} role="application" tabIndex={0} aria-label={t("title")} onPointerDown={handleFloorPointerDown} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag}><defs><pattern id="eay-authoring-grid" width={gridStepPx} height={gridStepPx} patternUnits="userSpaceOnUse"><path d={`M ${gridStepPx} 0 L 0 0 0 ${gridStepPx}`} className="eay-authoring-grid-line" /></pattern></defs><rect x={projection.offsetX} y={projection.offsetY} width={document.floor.widthM * projection.scale} height={document.floor.depthM * projection.scale} className="eay-authoring-floor" /><rect x={projection.offsetX} y={projection.offsetY} width={document.floor.widthM * projection.scale} height={document.floor.depthM * projection.scale} fill="url(#eay-authoring-grid)" className="eay-authoring-grid" />{displayElements.map((element) => { const classes = ["eay-authoring-element", `eay-authoring-element--${element.element_type}`, selectedId === element.element_id ? "is-selected" : "", element.locked ? "is-locked" : "", dragPreview?.id === element.element_id ? "is-drag-preview" : "", diagnosticState.collisions.has(element.element_id) ? "has-collision" : "", diagnosticState.aisle.has(element.element_id) ? "has-aisle-violation" : "", diagnosticState.boundary.has(element.element_id) ? "has-boundary-violation" : ""].filter(Boolean).join(" "); return <polygon key={element.element_id} points={svgPointString(rotatedRectSvgPoints({ centerXM: element.center_x_m, centerYM: element.center_y_m, widthM: element.width_m, depthM: element.depth_m, rotationDeg: element.rotation_deg }, projection))} className={classes} data-element-id={element.element_id} data-rotation-deg={element.rotation_deg} data-locked={element.locked ? "true" : "false"} onPointerDown={(event) => beginDrag(event, element)}><title>{`${t(element.element_type)} · ${element.element_id}`}</title></polygon>; })}</svg></div>
        <aside className="eay-authoring-inspector"><h3>{t("architectureInspector")}</h3><fieldset><legend>{t("floor")}</legend><label><span>{t("width")}</span><input type="number" min="1" step="0.05" value={document.floor.widthM} disabled={!canEdit} onChange={(event) => resizeFloor(numericValue(event.target.value, document.floor.widthM), document.floor.depthM)} /></label><label><span>{t("depth")}</span><input type="number" min="1" step="0.05" value={document.floor.depthM} disabled={!canEdit} onChange={(event) => resizeFloor(document.floor.widthM, numericValue(event.target.value, document.floor.depthM))} /></label></fieldset>
          {selected ? <fieldset><legend>{t("exactDimensions")}</legend><code>{selected.element_id}</code><div className="eay-authoring-lock-state" data-locked={selected.locked ? "true" : "false"}>{selected.locked ? <LockKeyhole size={15} aria-hidden="true" /> : <UnlockKeyhole size={15} aria-hidden="true" />}<strong>{selected.locked ? t("locked") : t("unlocked")}</strong></div><label><span>{t("x")}</span><input type="number" step="0.05" value={selected.center_x_m} disabled={!canEdit || selected.locked} onChange={(event) => updateSelectedField("centerXM", numericValue(event.target.value, selected.center_x_m))} /></label><label><span>{t("y")}</span><input type="number" step="0.05" value={selected.center_y_m} disabled={!canEdit || selected.locked} onChange={(event) => updateSelectedField("centerYM", numericValue(event.target.value, selected.center_y_m))} /></label><label><span>{t("width")}</span><input type="number" min="0.05" step="0.05" value={selected.width_m} disabled={!canEdit || selected.locked} onChange={(event) => updateSelectedField("widthM", numericValue(event.target.value, selected.width_m))} /></label><label><span>{t("depth")}</span><input type="number" min="0.05" step="0.05" value={selected.depth_m} disabled={!canEdit || selected.locked} onChange={(event) => updateSelectedField("depthM", numericValue(event.target.value, selected.depth_m))} /></label><label><span>{t("rotation")}</span><input type="number" step="1" value={selected.rotation_deg} disabled={!canEdit || selected.locked} onChange={(event) => updateSelectedField("rotationDeg", numericValue(event.target.value, selected.rotation_deg))} /></label><label><span>{t("clearance")}</span><input type="number" min="0" step="0.05" value={selected.clearance_m || 0} disabled={!canEdit || selected.locked} onChange={(event) => updateSelectedField("clearanceM", numericValue(event.target.value, selected.clearance_m || 0))} /></label><button type="button" className="eay-authoring-lock" disabled={!canEdit} onClick={toggleSelectedLock}>{selected.locked ? <UnlockKeyhole size={16} aria-hidden="true" /> : <LockKeyhole size={16} aria-hidden="true" />}{selected.locked ? t("unlockElement") : t("lockElement")}</button><button type="button" className="eay-authoring-delete" disabled={!canEdit || selected.locked} onClick={deleteSelected}><Trash2 size={16} aria-hidden="true" />{t("delete")}</button></fieldset> : <p>{t("selectHint")}</p>}
          <fieldset className={`eay-authoring-diagnostics${hasDiagnostics ? " has-issues" : ""}`}><legend>{t("diagnostics")}</legend><div className="eay-authoring-diagnostic-counts"><span>{t("collisionCount")}<strong>{diagnostics.collisionCount}</strong></span><span>{t("aisleViolationCount")}<strong>{diagnostics.aisleViolationCount}</strong></span><span>{t("boundaryViolationCount")}<strong>{diagnostics.boundaryViolationCount}</strong></span></div>{!hasDiagnostics ? <p>{t("noDiagnostics")}</p> : null}{diagnostics.collisions.slice(0, 4).map((row) => <p key={`collision-${row.leftNodeId}-${row.rightNodeId}`}><AlertTriangle size={14} aria-hidden="true" /><span>{t("collision")}</span><code>{row.leftNodeId} ↔ {row.rightNodeId}</code></p>)}{diagnostics.aisleViolations.slice(0, 4).map((row) => <p key={`aisle-${row.leftNodeId}-${row.rightNodeId}`}><AlertTriangle size={14} aria-hidden="true" /><span>{t("aisleViolation")}</span><code>{row.leftNodeId} ↔ {row.rightNodeId} · {formatMetric(row.clearanceM)} m</code></p>)}{diagnostics.boundaryViolations.slice(0, 4).map((row) => <p key={`boundary-${row.nodeId}`}><AlertTriangle size={14} aria-hidden="true" /><span>{t("boundaryViolation")}</span><code>{row.nodeId} · {formatMetric(row.outsideM)} m</code></p>)}</fieldset>
          {selected ? <fieldset className="eay-authoring-provenance-panel"><legend>{t("sourceProvenance")}</legend><label><span>{t("source")}</span><code>{selected.provenance?.source || document.architecture.source || document.sourceContract}</code></label><label><span>{t("sourceReference")}</span><code>{selected.provenance?.sourceRef || document.architecture.source_ref || "—"}</code></label><label><span>{t("reviewFingerprint")}</span><code>{selected.provenance?.reviewFingerprint || session.reviewFingerprint || "—"}</code></label></fieldset> : null}{scanDerived ? <p className="eay-authoring-provenance">{t("provenancePreserved")}</p> : null}</aside>
      </div>
    </section>
  );
}
