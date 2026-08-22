import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, AlignCenterHorizontal, AlignCenterVertical, BoxSelect, Grid3X3, LockKeyhole, MousePointer2, Redo2, Ruler, ScanLine, Trash2, Undo2, UnlockKeyhole, X } from "lucide-react";

import { translatePlanogramAuthoring } from "../../platform/i18n/planogramAuthoringMessages.js";
import {
  buildPlanogramCadDistributeUpdates,
  buildPlanogramCadSelectionMetrics,
  createPlanogramCadFixtureNode,
  createPlanogramCadMeasurementNode,
  snapPlanogramCadSelectionDelta,
} from "./planogramCadAdvanced.js";
import { rotatedRectSvgPoints, svgPointString } from "./planogramEngineering2D.js";
import { createPlanogramAuthoringElement, createStoreSceneNode, PLANOGRAM_AUTHORING_ELEMENT_TYPES, projectStoreScene2D, snapPlanogramAuthoringValue } from "./planogramAuthoringModel.js";
import { createPlanogramCadSession, executePlanogramCadSessionCommand, redoPlanogramCadSession, undoPlanogramCadSession } from "./planogramCadSession.js";
import "./planogram-authoring.css";
import "./planogram-cad-advanced.css";

const SVG_WIDTH = 1040;
const SVG_HEIGHT = 640;
const PADDING = 44;
const PRIMARY_TOOLS = ["wall", "door", "window", "column", "no_go", "technical"];
const AUTHORING_TYPES = new Set([...PLANOGRAM_AUTHORING_ELEMENT_TYPES, "fixture"]);
const EPSILON = 1e-9;

function projectionFor(document) {
  if (!document) return null;
  const scale = Math.min((SVG_WIDTH - PADDING * 2) / document.floor.widthM, (SVG_HEIGHT - PADDING * 2) / document.floor.depthM);
  return { offsetX: (SVG_WIDTH - document.floor.widthM * scale) / 2, offsetY: (SVG_HEIGHT - document.floor.depthM * scale) / 2, floorDepthM: document.floor.depthM, scale };
}

function modelPoint(event, svg, projection, document) {
  if (!svg || !projection || !document) return null;
  const rect = svg.getBoundingClientRect();
  const svgX = ((event.clientX - rect.left) / Math.max(rect.width, 1)) * SVG_WIDTH;
  const svgY = ((event.clientY - rect.top) / Math.max(rect.height, 1)) * SVG_HEIGHT;
  const x = (svgX - projection.offsetX) / projection.scale;
  const y = document.floor.depthM - (svgY - projection.offsetY) / projection.scale;
  if (x < 0 || y < 0 || x > document.floor.widthM || y > document.floor.depthM) return null;
  return [snapPlanogramAuthoringValue(x, document.gridM), snapPlanogramAuthoringValue(y, document.gridM)];
}

function svgPoint(xM, yM, projection, document) {
  return [projection.offsetX + xM * projection.scale, projection.offsetY + (document.floor.depthM - yM) * projection.scale];
}

function numericValue(value, fallback) {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

function architectureSignature(candidate) {
  const architecture = candidate?.store_dna?.architecture;
  if (!architecture) return "none";
  const architectureRows = (architecture.elements || []).map((row) => [row.element_id, row.element_type, row.center_x_m, row.center_y_m, row.x_m, row.y_m, row.width_m, row.depth_m, row.rotation_deg, row.clearance_m, Boolean(row.locked), row.scan_source_element_id]);
  const overlay = candidate?.store_dna?.cad_overlay;
  const overlayRows = (overlay?.nodes || []).map((row) => [row.nodeId, row.nodeType, row.geometry?.centerXM, row.geometry?.centerYM, row.geometry?.widthM, row.geometry?.depthM, row.geometry?.rotationDeg, Boolean(row.locked), row.metadata?.fixtureType, row.metadata?.measuredDistanceM]);
  return JSON.stringify([candidate?.store_code || candidate?.store_dna?.store_code || null, architecture.source_ref || null, architecture.source_review_fingerprint || null, architecture.floor_width_m, architecture.floor_depth_m, architectureRows, overlay?.contract || null, overlayRows]);
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
    metadata: node.metadata || {},
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
  const [selectedIds, setSelectedIds] = useState([]);
  const [dragPreview, setDragPreview] = useState({});
  const [snapGuides, setSnapGuides] = useState([]);
  const [appliedPulse, setAppliedPulse] = useState(false);
  const [commandError, setCommandError] = useState("");
  const externalSignature = useMemo(() => architectureSignature(candidate), [candidate]);

  useEffect(() => {
    if (emittedSignatureRef.current === externalSignature) { emittedSignatureRef.current = null; return; }
    setSession(createPlanogramCadSession({ candidate }));
    setSelectedIds([]);
    setDragPreview({});
    setSnapGuides([]);
    setTool("select");
    setCommandError("");
  }, [externalSignature]);
  useEffect(() => () => window.clearTimeout(pulseTimerRef.current), []);

  const document = session?.document || null;
  const projection = useMemo(() => projectionFor(document), [document]);
  const scene2D = useMemo(() => (session?.scene ? projectStoreScene2D(session.scene) : null), [session?.scene]);
  const baseElements = useMemo(() => new Map((document?.architecture?.elements || []).map((row) => [row.element_id, row])), [document]);
  const renderedElements = useMemo(() => (scene2D?.nodes || []).filter((node) => AUTHORING_TYPES.has(node.nodeType)).map((node) => elementFromProjection(node, baseElements.get(node.nodeId))), [baseElements, scene2D]);
  const renderedById = useMemo(() => new Map(renderedElements.map((row) => [row.element_id, row])), [renderedElements]);
  const sceneNodesById = useMemo(() => new Map((scene2D?.nodes || []).map((row) => [row.nodeId, row])), [scene2D]);
  const measurementRows = useMemo(() => (scene2D?.nodes || []).filter((node) => node.nodeType === "measurement" && Array.isArray(node.metadata?.sourceNodeIds) && node.metadata.sourceNodeIds.length === 2), [scene2D]);
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const primarySelected = useMemo(() => renderedById.get(selectedIds[selectedIds.length - 1]) || null, [renderedById, selectedIds]);
  const selectionMetrics = useMemo(() => (session?.scene ? buildPlanogramCadSelectionMetrics(session.scene, selectedIds) : null), [selectedIds, session?.scene]);
  const displayElements = useMemo(() => renderedElements.map((element) => dragPreview[element.element_id] ? { ...element, center_x_m: dragPreview[element.element_id].centerXM, center_y_m: dragPreview[element.element_id].centerYM } : element), [dragPreview, renderedElements]);
  const scanDerived = Boolean(document?.architecture?.source_review_fingerprint || document?.architecture?.scan_fingerprint || String(document?.architecture?.source || "").includes("scan"));

  const diagnosticState = useMemo(() => {
    const collisions = new Set(); const aisle = new Set(); const boundary = new Set();
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
    setSelectedIds((current) => current.filter((id) => nextSession.scene.nodes.some((node) => node.nodeId === id)));
    if (typeof onCandidateChange === "function" && nextSession.candidate) {
      emittedSignatureRef.current = architectureSignature(nextSession.candidate);
      onCandidateChange(nextSession.candidate);
    }
  }, [onCandidateChange]);

  const executeCommand = useCallback((rawCommand) => {
    if (!session || !canEdit) return null;
    const command = { commandId: rawCommand.commandId || `CAD-UI-${commandSequenceRef.current++}`, expectedRevision: session.scene.revision, ...rawCommand };
    try {
      const next = executePlanogramCadSessionCommand(session, command);
      if (next !== session) applySession(next);
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
    let node;
    if (tool === "fixture") {
      node = createPlanogramCadFixtureNode({ nodeId: `CAD-FIXTURE-${sequenceRef.current}`, centerXM: point[0], centerYM: point[1], fixtureType: "REGULAR_SHELF" });
    } else {
      const created = createPlanogramAuthoringElement({ type: tool, centerXM: point[0], centerYM: point[1], floor: document.floor, sequence: sequenceRef.current, gridM: document.gridM });
      node = createStoreSceneNode({ ...created, provenance: { source: "human", sourceRef: "cad-session-ui" }, metadata: { clearanceM: created.clearance_m || 0 } });
    }
    sequenceRef.current += 1;
    const next = executeCommand({ type: "CREATE_NODE", node });
    if (next) { setSelectedIds([node.nodeId]); setTool("select"); }
  }, [canEdit, document, executeCommand, projection, tool]);

  const beginDrag = useCallback((event, element) => {
    event.stopPropagation();
    const modifier = event.shiftKey || event.ctrlKey || event.metaKey;
    if (modifier) {
      setSelectedIds((current) => current.includes(element.element_id) ? current.filter((id) => id !== element.element_id) : [...current, element.element_id]);
      return;
    }
    const activeIds = selectedSet.has(element.element_id) ? selectedIds : [element.element_id];
    if (!selectedSet.has(element.element_id)) setSelectedIds(activeIds);
    if (!canEdit || tool !== "select" || !document || !projection) return;
    const activeRows = activeIds.map((id) => renderedById.get(id)).filter(Boolean);
    if (activeRows.some((row) => row.locked)) { setCommandError(t("groupLocked")); return; }
    const point = modelPoint(event, svgRef.current, projection, document);
    if (!point) return;
    dragRef.current = { startPoint: point, rows: activeRows.map((row) => ({ id: row.element_id, centerXM: row.center_x_m, centerYM: row.center_y_m })), deltaX: 0, deltaY: 0 };
    svgRef.current?.setPointerCapture?.(event.pointerId);
  }, [canEdit, document, projection, renderedById, selectedIds, selectedSet, t, tool]);

  const moveDrag = useCallback((event) => {
    const drag = dragRef.current;
    if (!drag || !document || !projection || !canEdit || !session?.scene) return;
    const point = modelPoint(event, svgRef.current, projection, document);
    if (!point) return;
    const rawDeltaX = point[0] - drag.startPoint[0];
    const rawDeltaY = point[1] - drag.startPoint[1];
    const snapped = snapPlanogramCadSelectionDelta(session.scene, drag.rows.map((row) => row.id), rawDeltaX, rawDeltaY, { gridM: document.gridM, thresholdM: Math.max(0.08, document.gridM) });
    drag.deltaX = snapped.deltaX;
    drag.deltaY = snapped.deltaY;
    setSnapGuides(snapped.guides);
    const preview = {};
    for (const row of drag.rows) preview[row.id] = { centerXM: row.centerXM + drag.deltaX, centerYM: row.centerYM + drag.deltaY };
    setDragPreview(preview);
  }, [canEdit, document, projection, session?.scene]);

  const endDrag = useCallback((event) => {
    const drag = dragRef.current;
    dragRef.current = null;
    setDragPreview({});
    setSnapGuides([]);
    if (svgRef.current?.hasPointerCapture?.(event.pointerId)) svgRef.current.releasePointerCapture(event.pointerId);
    if (!drag || (Math.abs(drag.deltaX) <= EPSILON && Math.abs(drag.deltaY) <= EPSILON)) return;
    executeCommand({ type: "UPDATE_NODES", updates: drag.rows.map((row) => ({ nodeId: row.id, patch: { geometry: { centerXM: row.centerXM + drag.deltaX, centerYM: row.centerYM + drag.deltaY } } })) });
  }, [executeCommand]);

  const updateSelectedField = useCallback((field, value) => {
    if (!primarySelected || primarySelected.locked || !document || !canEdit) return;
    const geometry = {}; const metadata = {};
    if (field === "centerXM") geometry.centerXM = snapPlanogramAuthoringValue(value, document.gridM);
    if (field === "centerYM") geometry.centerYM = snapPlanogramAuthoringValue(value, document.gridM);
    if (field === "widthM") geometry.widthM = snapPlanogramAuthoringValue(Math.max(0.05, value), document.gridM);
    if (field === "depthM") geometry.depthM = snapPlanogramAuthoringValue(Math.max(0.05, value), document.gridM);
    if (field === "rotationDeg") geometry.rotationDeg = value;
    if (field === "clearanceM") metadata.clearanceM = Math.max(0, value);
    executeCommand({ type: "UPDATE_NODE", nodeId: primarySelected.element_id, patch: { ...(Object.keys(geometry).length ? { geometry } : {}), ...(Object.keys(metadata).length ? { metadata } : {}) } });
  }, [canEdit, document, executeCommand, primarySelected]);

  const deletePrimary = useCallback(() => {
    if (primarySelected && !primarySelected.locked && canEdit && executeCommand({ type: "DELETE_NODE", nodeId: primarySelected.element_id })) setSelectedIds((current) => current.filter((id) => id !== primarySelected.element_id));
  }, [canEdit, executeCommand, primarySelected]);
  const togglePrimaryLock = useCallback(() => { if (primarySelected && canEdit) executeCommand({ type: "SET_LOCK", nodeId: primarySelected.element_id, locked: !primarySelected.locked }); }, [canEdit, executeCommand, primarySelected]);
  const resizeFloor = useCallback((widthM, depthM) => { if (document && canEdit) executeCommand({ type: "RESIZE_FLOOR", widthM: snapPlanogramAuthoringValue(Math.max(1, widthM), document.gridM), depthM: snapPlanogramAuthoringValue(Math.max(1, depthM), document.gridM) }); }, [canEdit, document, executeCommand]);

  const selectionRows = useCallback(() => selectedIds.map((id) => renderedById.get(id)).filter(Boolean), [renderedById, selectedIds]);
  const ensureGroupEditable = useCallback(() => {
    const rows = selectionRows();
    if (rows.some((row) => row.locked)) { setCommandError(t("groupLocked")); return null; }
    return rows;
  }, [selectionRows, t]);
  const alignSelection = useCallback((axis) => {
    const rows = ensureGroupEditable();
    if (!rows || rows.length < 2 || !primarySelected) return;
    const field = axis === "x" ? "centerXM" : "centerYM";
    const target = axis === "x" ? primarySelected.center_x_m : primarySelected.center_y_m;
    executeCommand({ type: "UPDATE_NODES", updates: rows.map((row) => ({ nodeId: row.element_id, patch: { geometry: { [field]: target } } })) });
  }, [ensureGroupEditable, executeCommand, primarySelected]);
  const distributeSelection = useCallback((axis) => {
    const rows = ensureGroupEditable();
    if (!rows || rows.length < 3 || !session?.scene) return;
    try {
      const updates = buildPlanogramCadDistributeUpdates(session.scene, rows.map((row) => row.element_id), axis);
      if (updates.length) executeCommand({ type: "UPDATE_NODES", updates });
    } catch { setCommandError(t("commandRejected")); }
  }, [ensureGroupEditable, executeCommand, session?.scene, t]);
  const nudgeSelection = useCallback((deltaX, deltaY) => {
    const rows = ensureGroupEditable();
    if (!rows?.length) return;
    executeCommand({ type: "UPDATE_NODES", updates: rows.map((row) => ({ nodeId: row.element_id, patch: { geometry: { centerXM: row.center_x_m + deltaX, centerYM: row.center_y_m + deltaY } } })) });
  }, [ensureGroupEditable, executeCommand]);
  const createMeasurement = useCallback(() => {
    if (!canEdit || selectedIds.length !== 2 || !session?.scene) return;
    try {
      const node = createPlanogramCadMeasurementNode({ scene: session.scene, nodeId: `CAD-MEASURE-${commandSequenceRef.current++}`, sourceNodeIds: selectedIds });
      executeCommand({ type: "CREATE_NODE", node });
    } catch { setCommandError(t("commandRejected")); }
  }, [canEdit, executeCommand, selectedIds, session?.scene, t]);

  const handleKeyboardShortcut = useCallback((event) => {
    const modifier = event.ctrlKey || event.metaKey;
    const key = event.key.toLowerCase();
    if (modifier && key === "z") { event.preventDefault(); if (event.shiftKey) redoSession(); else undoSession(); return; }
    if (modifier && key === "y") { event.preventDefault(); redoSession(); return; }
    const tagName = String(event.target?.tagName || "").toUpperCase();
    if (["INPUT", "TEXTAREA", "SELECT"].includes(tagName)) return;
    if (event.key === "Delete") { event.preventDefault(); deletePrimary(); return; }
    if (event.key === "Escape") { event.preventDefault(); setSelectedIds([]); return; }
    if (!document || !selectedIds.length) return;
    const step = document.gridM * (event.shiftKey ? 5 : 1);
    if (event.key === "ArrowLeft") { event.preventDefault(); nudgeSelection(-step, 0); }
    else if (event.key === "ArrowRight") { event.preventDefault(); nudgeSelection(step, 0); }
    else if (event.key === "ArrowUp") { event.preventDefault(); nudgeSelection(0, step); }
    else if (event.key === "ArrowDown") { event.preventDefault(); nudgeSelection(0, -step); }
  }, [deletePrimary, document, nudgeSelection, redoSession, selectedIds.length, undoSession]);

  if (!session || !document || !projection) return <section className="eay-authoring eay-authoring--empty"><header><div><Ruler size={21} aria-hidden="true" /><div><h2>{t("title")}</h2><p>{t("subtitle")}</p></div></div></header><p>{t("noArchitecture")}</p></section>;
  const diagnostics = session.diagnostics;
  const hasDiagnostics = diagnostics.collisionCount + diagnostics.aisleViolationCount + diagnostics.boundaryViolationCount > 0;
  const gridStepPx = Math.max(8, document.gridM * projection.scale * 10);
  return (
    <section className="eay-authoring" data-preview-only={session.previewOnly ? "true" : "false"} data-cad-session-contract={session.contract} data-store-scene-revision={session.scene.revision} data-selection-count={selectedIds.length} onKeyDown={handleKeyboardShortcut}>
      <header className="eay-authoring-head"><div><Ruler size={21} aria-hidden="true" /><div><h2>{t("title")}</h2><p>{t("subtitle")}</p></div></div><div className="eay-authoring-badges">{scanDerived ? <span><ScanLine size={14} aria-hidden="true" />{t("scanDraft")}</span> : null}<span>{session.previewOnly ? t("previewOnly") : t("measured")}</span><span>{t("canonicalTruth")}</span></div></header>
      <div className="eay-authoring-status"><span><Grid3X3 size={15} aria-hidden="true" />{t("grid")}: {document.gridM} {t("metersShort")}</span><span><BoxSelect size={15} aria-hidden="true" />{t("elements")}: {renderedElements.length}</span><span>{t("revision")}: {session.scene.revision}</span><span>{t("history")}: {session.historyDepth} / {session.redoDepth}</span><span>{t("selectedCount")}: {selectedIds.length}</span><span>{t("source")}: {document.architecture.source || document.sourceContract}</span>{appliedPulse ? <strong role="status">{t("applied")}</strong> : null}</div>
      <div className="eay-authoring-history-controls" aria-label={t("history")}><button type="button" disabled={!canEdit || !session.history.past.length} onClick={undoSession}><Undo2 size={16} aria-hidden="true" />{t("undo")}</button><button type="button" disabled={!canEdit || !session.history.future.length} onClick={redoSession}><Redo2 size={16} aria-hidden="true" />{t("redo")}</button><span>{t("keyboardHint")}</span></div>
      {selectedIds.length > 1 ? <div className="eay-authoring-selection-controls" aria-label={t("selection")}><strong>{t("selection")}: {selectedIds.length}</strong><span>{t("selectionSpan")}: {formatMetric(selectionMetrics?.widthM)} × {formatMetric(selectionMetrics?.depthM)} {t("metersShort")}</span><button type="button" disabled={!canEdit} onClick={() => alignSelection("x")}><AlignCenterVertical size={16} aria-hidden="true" />{t("alignX")}</button><button type="button" disabled={!canEdit} onClick={() => alignSelection("y")}><AlignCenterHorizontal size={16} aria-hidden="true" />{t("alignY")}</button><button type="button" disabled={!canEdit || selectedIds.length < 3} onClick={() => distributeSelection("x")}>{t("distributeX")}</button><button type="button" disabled={!canEdit || selectedIds.length < 3} onClick={() => distributeSelection("y")}>{t("distributeY")}</button><button type="button" disabled={!canEdit || selectedIds.length !== 2} onClick={createMeasurement}><Ruler size={16} aria-hidden="true" />{t("measureSelection")}</button><button type="button" onClick={() => setSelectedIds([])}><X size={16} aria-hidden="true" />{t("clearSelection")}</button></div> : null}
      {commandError ? <p className="eay-authoring-command-error" role="alert">{commandError}</p> : null}
      <div className="eay-authoring-workspace">
        <aside className="eay-authoring-toolbar" aria-label={t("title")}><button type="button" className={tool === "select" ? "active" : ""} aria-pressed={tool === "select"} onClick={() => setTool("select")}><MousePointer2 size={17} aria-hidden="true" />{t("select")}</button>{PRIMARY_TOOLS.map((item) => <button key={item} type="button" className={tool === item ? "active" : ""} aria-pressed={tool === item} disabled={!canEdit} onClick={() => setTool(item)}>{t(item)}</button>)}<div className="eay-authoring-tool-divider" /><button type="button" className={tool === "fixture" ? "active" : ""} aria-pressed={tool === "fixture"} disabled={!canEdit} onClick={() => setTool("fixture")}>{t("fixture")}</button>{PLANOGRAM_AUTHORING_ELEMENT_TYPES.filter((item) => !PRIMARY_TOOLS.includes(item)).map((item) => <button key={item} type="button" className={tool === item ? "active" : ""} aria-pressed={tool === item} disabled={!canEdit} onClick={() => setTool(item)}>{t(item)}</button>)}</aside>
        <div className="eay-authoring-canvas-wrap"><p className="eay-authoring-hint">{tool === "select" ? (selectedIds.length ? t("multiSelectHint") : t("selectHint")) : (tool === "fixture" ? t("fixtureHint") : t("addHint"))}</p><svg ref={svgRef} className={`eay-authoring-canvas eay-authoring-canvas--${tool}`} viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`} role="application" tabIndex={0} aria-label={t("title")} onPointerDown={handleFloorPointerDown} onPointerMove={moveDrag} onPointerUp={endDrag} onPointerCancel={endDrag}><defs><pattern id="eay-authoring-grid" width={gridStepPx} height={gridStepPx} patternUnits="userSpaceOnUse"><path d={`M ${gridStepPx} 0 L 0 0 0 ${gridStepPx}`} className="eay-authoring-grid-line" /></pattern></defs><rect x={projection.offsetX} y={projection.offsetY} width={document.floor.widthM * projection.scale} height={document.floor.depthM * projection.scale} className="eay-authoring-floor" /><rect x={projection.offsetX} y={projection.offsetY} width={document.floor.widthM * projection.scale} height={document.floor.depthM * projection.scale} fill="url(#eay-authoring-grid)" className="eay-authoring-grid" />{snapGuides.map((guide, index) => guide.axis === "x" ? <line key={`snap-${index}`} x1={svgPoint(guide.value, 0, projection, document)[0]} x2={svgPoint(guide.value, 0, projection, document)[0]} y1={projection.offsetY} y2={projection.offsetY + document.floor.depthM * projection.scale} className="eay-authoring-snap-guide" data-snap-axis="x" /> : <line key={`snap-${index}`} x1={projection.offsetX} x2={projection.offsetX + document.floor.widthM * projection.scale} y1={svgPoint(0, guide.value, projection, document)[1]} y2={svgPoint(0, guide.value, projection, document)[1]} className="eay-authoring-snap-guide" data-snap-axis="y" />)}{measurementRows.map((measurement) => { const left = sceneNodesById.get(measurement.metadata.sourceNodeIds[0]); const right = sceneNodesById.get(measurement.metadata.sourceNodeIds[1]); if (!left || !right) return null; const a = svgPoint(left.geometry.centerXM, left.geometry.centerYM, projection, document); const b = svgPoint(right.geometry.centerXM, right.geometry.centerYM, projection, document); const mx = (a[0] + b[0]) / 2; const my = (a[1] + b[1]) / 2; return <g key={measurement.nodeId} className="eay-authoring-measurement" data-measurement-id={measurement.nodeId}><line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} /><text x={mx} y={my - 6}>{formatMetric(measurement.metadata.measuredDistanceM)} {t("metersShort")}</text></g>; })}{displayElements.map((element) => { const classes = ["eay-authoring-element", `eay-authoring-element--${element.element_type}`, selectedSet.has(element.element_id) ? "is-selected" : "", primarySelected?.element_id === element.element_id ? "is-primary" : "", element.locked ? "is-locked" : "", dragPreview[element.element_id] ? "is-drag-preview" : "", diagnosticState.collisions.has(element.element_id) ? "has-collision" : "", diagnosticState.aisle.has(element.element_id) ? "has-aisle-violation" : "", diagnosticState.boundary.has(element.element_id) ? "has-boundary-violation" : ""].filter(Boolean).join(" "); return <polygon key={element.element_id} points={svgPointString(rotatedRectSvgPoints({ centerXM: element.center_x_m, centerYM: element.center_y_m, widthM: element.width_m, depthM: element.depth_m, rotationDeg: element.rotation_deg }, projection))} className={classes} data-element-id={element.element_id} data-rotation-deg={element.rotation_deg} data-locked={element.locked ? "true" : "false"} data-selected={selectedSet.has(element.element_id) ? "true" : "false"} onPointerDown={(event) => beginDrag(event, element)}><title>{`${t(element.element_type)} · ${element.element_id}`}</title></polygon>; })}</svg></div>
        <aside className="eay-authoring-inspector"><h3>{t("architectureInspector")}</h3><fieldset><legend>{t("floor")}</legend><label><span>{t("width")}</span><input type="number" min="1" step="0.05" value={document.floor.widthM} disabled={!canEdit} onChange={(event) => resizeFloor(numericValue(event.target.value, document.floor.widthM), document.floor.depthM)} /></label><label><span>{t("depth")}</span><input type="number" min="1" step="0.05" value={document.floor.depthM} disabled={!canEdit} onChange={(event) => resizeFloor(document.floor.widthM, numericValue(event.target.value, document.floor.depthM))} /></label></fieldset>
          {primarySelected ? <fieldset><legend>{t("exactDimensions")}</legend><code>{primarySelected.element_id}</code>{primarySelected.element_type === "fixture" ? <p className="eay-authoring-fixture-meta"><strong>{t("fixtureType")}</strong>: {primarySelected.metadata?.fixtureType || t("fixturePreview")}</p> : null}<div className="eay-authoring-lock-state" data-locked={primarySelected.locked ? "true" : "false"}>{primarySelected.locked ? <LockKeyhole size={15} aria-hidden="true" /> : <UnlockKeyhole size={15} aria-hidden="true" />}<strong>{primarySelected.locked ? t("locked") : t("unlocked")}</strong></div><label><span>{t("x")}</span><input type="number" step="0.05" value={primarySelected.center_x_m} disabled={!canEdit || primarySelected.locked} onChange={(event) => updateSelectedField("centerXM", numericValue(event.target.value, primarySelected.center_x_m))} /></label><label><span>{t("y")}</span><input type="number" step="0.05" value={primarySelected.center_y_m} disabled={!canEdit || primarySelected.locked} onChange={(event) => updateSelectedField("centerYM", numericValue(event.target.value, primarySelected.center_y_m))} /></label><label><span>{t("width")}</span><input type="number" min="0.05" step="0.05" value={primarySelected.width_m} disabled={!canEdit || primarySelected.locked} onChange={(event) => updateSelectedField("widthM", numericValue(event.target.value, primarySelected.width_m))} /></label><label><span>{t("depth")}</span><input type="number" min="0.05" step="0.05" value={primarySelected.depth_m} disabled={!canEdit || primarySelected.locked} onChange={(event) => updateSelectedField("depthM", numericValue(event.target.value, primarySelected.depth_m))} /></label><label><span>{t("rotation")}</span><input type="number" step="1" value={primarySelected.rotation_deg} disabled={!canEdit || primarySelected.locked} onChange={(event) => updateSelectedField("rotationDeg", numericValue(event.target.value, primarySelected.rotation_deg))} /></label><label><span>{t("clearance")}</span><input type="number" min="0" step="0.05" value={primarySelected.clearance_m || 0} disabled={!canEdit || primarySelected.locked || primarySelected.element_type === "fixture"} onChange={(event) => updateSelectedField("clearanceM", numericValue(event.target.value, primarySelected.clearance_m || 0))} /></label><button type="button" className="eay-authoring-lock" disabled={!canEdit} onClick={togglePrimaryLock}>{primarySelected.locked ? <UnlockKeyhole size={16} aria-hidden="true" /> : <LockKeyhole size={16} aria-hidden="true" />}{primarySelected.locked ? t("unlockElement") : t("lockElement")}</button><button type="button" className="eay-authoring-delete" disabled={!canEdit || primarySelected.locked} onClick={deletePrimary}><Trash2 size={16} aria-hidden="true" />{t("delete")}</button></fieldset> : <p>{t("selectHint")}</p>}
          <fieldset className={`eay-authoring-diagnostics${hasDiagnostics ? " has-issues" : ""}`}><legend>{t("diagnostics")}</legend><div className="eay-authoring-diagnostic-counts"><span>{t("collisionCount")}<strong>{diagnostics.collisionCount}</strong></span><span>{t("aisleViolationCount")}<strong>{diagnostics.aisleViolationCount}</strong></span><span>{t("boundaryViolationCount")}<strong>{diagnostics.boundaryViolationCount}</strong></span></div>{!hasDiagnostics ? <p>{t("noDiagnostics")}</p> : null}{diagnostics.collisions.slice(0, 4).map((row) => <p key={`collision-${row.leftNodeId}-${row.rightNodeId}`}><AlertTriangle size={14} aria-hidden="true" /><span>{t("collision")}</span><code>{row.leftNodeId} ↔ {row.rightNodeId}</code></p>)}{diagnostics.aisleViolations.slice(0, 4).map((row) => <p key={`aisle-${row.leftNodeId}-${row.rightNodeId}`}><AlertTriangle size={14} aria-hidden="true" /><span>{t("aisleViolation")}</span><code>{row.leftNodeId} ↔ {row.rightNodeId} · {formatMetric(row.clearanceM)} {t("metersShort")}</code></p>)}{diagnostics.boundaryViolations.slice(0, 4).map((row) => <p key={`boundary-${row.nodeId}`}><AlertTriangle size={14} aria-hidden="true" /><span>{t("boundaryViolation")}</span><code>{row.nodeId} · {formatMetric(row.outsideM)} {t("metersShort")}</code></p>)}</fieldset>
          {primarySelected ? <fieldset className="eay-authoring-provenance-panel"><legend>{t("sourceProvenance")}</legend><label><span>{t("source")}</span><code>{primarySelected.provenance?.source || document.architecture.source || document.sourceContract}</code></label><label><span>{t("sourceReference")}</span><code>{primarySelected.provenance?.sourceRef || document.architecture.source_ref || "—"}</code></label><label><span>{t("reviewFingerprint")}</span><code>{primarySelected.provenance?.reviewFingerprint || session.reviewFingerprint || "—"}</code></label></fieldset> : null}{scanDerived ? <p className="eay-authoring-provenance">{t("provenancePreserved")}</p> : null}</aside>
      </div>
    </section>
  );
}
