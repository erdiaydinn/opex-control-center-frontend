import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BoxSelect, Grid3X3, MousePointer2, Ruler, ScanLine, Trash2 } from "lucide-react";

import { translatePlanogramAuthoring } from "../../platform/i18n/planogramAuthoringMessages.js";
import { rotatedRectSvgPoints, svgPointString } from "./planogramEngineering2D.js";
import {
  buildPlanogramAuthoringDocument,
  candidateWithPlanogramAuthoringDocument,
  createPlanogramAuthoringElement,
  PLANOGRAM_AUTHORING_ELEMENT_TYPES,
  removePlanogramAuthoringElement,
  resizePlanogramAuthoringFloor,
  snapPlanogramAuthoringValue,
  updatePlanogramAuthoringElement,
} from "./planogramAuthoringModel.js";
import "./planogram-authoring.css";

const SVG_WIDTH = 1040;
const SVG_HEIGHT = 640;
const PADDING = 44;
const PRIMARY_TOOLS = ["wall", "door", "window", "column", "no_go", "technical"];

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

export default function PlanogramArchitecturalAuthoring({
  candidate,
  locale,
  canEdit,
  onCandidateChange,
}) {
  const t = useMemo(() => (key) => translatePlanogramAuthoring(locale, key), [locale]);
  const svgRef = useRef(null);
  const dragRef = useRef(null);
  const sequenceRef = useRef(1);
  const [document, setDocument] = useState(() => buildPlanogramAuthoringDocument(candidate));
  const [tool, setTool] = useState("select");
  const [selectedId, setSelectedId] = useState(null);
  const [appliedPulse, setAppliedPulse] = useState(false);

  const architectureKey = useMemo(() => {
    const architecture = candidate?.store_dna?.architecture;
    if (!architecture) return "none";
    return [
      architecture.source_ref,
      architecture.source_review_fingerprint,
      architecture.floor_width_m,
      architecture.floor_depth_m,
      architecture.elements?.length || 0,
    ].join("|");
  }, [candidate]);

  useEffect(() => {
    setDocument(buildPlanogramAuthoringDocument(candidate));
    setSelectedId(null);
    setTool("select");
  }, [architectureKey]);

  const projection = useMemo(() => projectionFor(document), [document]);
  const selected = useMemo(
    () => document?.architecture?.elements?.find((row) => row.element_id === selectedId) || null,
    [document, selectedId]
  );
  const scanDerived = Boolean(
    document?.architecture?.source_review_fingerprint ||
    document?.architecture?.scan_fingerprint ||
    String(document?.architecture?.source || "").includes("scan")
  );

  const commit = useCallback((nextDocument) => {
    if (!nextDocument) return;
    setDocument(nextDocument);
    setAppliedPulse(true);
    window.clearTimeout(commit._pulseTimer);
    commit._pulseTimer = window.setTimeout(() => setAppliedPulse(false), 1100);
    if (typeof onCandidateChange === "function") {
      onCandidateChange(candidateWithPlanogramAuthoringDocument(candidate, nextDocument));
    }
  }, [candidate, onCandidateChange]);

  useEffect(() => () => window.clearTimeout(commit._pulseTimer), [commit]);

  const handleFloorPointerDown = useCallback((event) => {
    if (!canEdit || !document || !projection || tool === "select") return;
    const point = modelPoint(event, svgRef.current, projection, document);
    if (!point) return;
    const next = createPlanogramAuthoringElement({
      type: tool,
      centerXM: point[0],
      centerYM: point[1],
      floor: document.floor,
      sequence: sequenceRef.current,
      gridM: document.gridM,
    });
    sequenceRef.current += 1;
    const nextDocument = {
      ...document,
      architecture: {
        ...document.architecture,
        elements: [...document.architecture.elements, next],
      },
    };
    setSelectedId(next.element_id);
    setTool("select");
    commit(nextDocument);
  }, [canEdit, commit, document, projection, tool]);

  const beginDrag = useCallback((event, element) => {
    event.stopPropagation();
    setSelectedId(element.element_id);
    if (!canEdit || tool !== "select" || !document || !projection) return;
    const point = modelPoint(event, svgRef.current, projection, document);
    if (!point) return;
    dragRef.current = {
      id: element.element_id,
      dx: point[0] - element.center_x_m,
      dy: point[1] - element.center_y_m,
    };
    svgRef.current?.setPointerCapture?.(event.pointerId);
  }, [canEdit, document, projection, tool]);

  const moveDrag = useCallback((event) => {
    const drag = dragRef.current;
    if (!drag || !document || !projection || !canEdit) return;
    const point = modelPoint(event, svgRef.current, projection, document);
    if (!point) return;
    const next = updatePlanogramAuthoringElement(document, drag.id, {
      center_x_m: point[0] - drag.dx,
      center_y_m: point[1] - drag.dy,
    });
    commit(next);
  }, [canEdit, commit, document, projection]);

  const endDrag = useCallback((event) => {
    dragRef.current = null;
    if (svgRef.current?.hasPointerCapture?.(event.pointerId)) {
      svgRef.current.releasePointerCapture(event.pointerId);
    }
  }, []);

  const updateSelected = useCallback((patch) => {
    if (!document || !selectedId || !canEdit) return;
    commit(updatePlanogramAuthoringElement(document, selectedId, patch));
  }, [canEdit, commit, document, selectedId]);

  const deleteSelected = useCallback(() => {
    if (!document || !selectedId || !canEdit) return;
    commit(removePlanogramAuthoringElement(document, selectedId));
    setSelectedId(null);
  }, [canEdit, commit, document, selectedId]);

  if (!document || !projection) {
    return (
      <section className="eay-authoring eay-authoring--empty">
        <header><div><Ruler size={21} aria-hidden="true" /><div><h2>{t("title")}</h2><p>{t("subtitle")}</p></div></div></header>
        <p>{t("noArchitecture")}</p>
      </section>
    );
  }

  const gridStepPx = Math.max(8, document.gridM * projection.scale * 10);
  return (
    <section className="eay-authoring" data-preview-only={document.previewOnly ? "true" : "false"}>
      <header className="eay-authoring-head">
        <div><Ruler size={21} aria-hidden="true" /><div><h2>{t("title")}</h2><p>{t("subtitle")}</p></div></div>
        <div className="eay-authoring-badges">
          {scanDerived ? <span><ScanLine size={14} aria-hidden="true" />{t("scanDraft")}</span> : null}
          <span>{document.previewOnly ? t("previewOnly") : t("measured")}</span>
          <span>{t("canonicalTruth")}</span>
        </div>
      </header>

      <div className="eay-authoring-status">
        <span><Grid3X3 size={15} aria-hidden="true" />{t("grid")}: {document.gridM} m</span>
        <span><BoxSelect size={15} aria-hidden="true" />{t("elements")}: {document.architecture.elements.length}</span>
        <span>{t("source")}: {document.architecture.source || document.sourceContract}</span>
        {appliedPulse ? <strong role="status">{t("applied")}</strong> : null}
      </div>

      <div className="eay-authoring-workspace">
        <aside className="eay-authoring-toolbar" aria-label={t("title")}>
          <button type="button" className={tool === "select" ? "active" : ""} aria-pressed={tool === "select"} onClick={() => setTool("select")}>
            <MousePointer2 size={17} aria-hidden="true" />{t("select")}
          </button>
          {PRIMARY_TOOLS.map((item) => (
            <button key={item} type="button" className={tool === item ? "active" : ""} aria-pressed={tool === item} disabled={!canEdit} onClick={() => setTool(item)}>{t(item)}</button>
          ))}
          <div className="eay-authoring-tool-divider" />
          {PLANOGRAM_AUTHORING_ELEMENT_TYPES.filter((item) => !PRIMARY_TOOLS.includes(item)).map((item) => (
            <button key={item} type="button" className={tool === item ? "active" : ""} aria-pressed={tool === item} disabled={!canEdit} onClick={() => setTool(item)}>{t(item)}</button>
          ))}
        </aside>

        <div className="eay-authoring-canvas-wrap">
          <p className="eay-authoring-hint">{tool === "select" ? t("selectHint") : t("addHint")}</p>
          <svg
            ref={svgRef}
            className={`eay-authoring-canvas eay-authoring-canvas--${tool}`}
            viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
            role="application"
            aria-label={t("title")}
            onPointerDown={handleFloorPointerDown}
            onPointerMove={moveDrag}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
          >
            <defs>
              <pattern id="eay-authoring-grid" width={gridStepPx} height={gridStepPx} patternUnits="userSpaceOnUse">
                <path d={`M ${gridStepPx} 0 L 0 0 0 ${gridStepPx}`} className="eay-authoring-grid-line" />
              </pattern>
            </defs>
            <rect x={projection.offsetX} y={projection.offsetY} width={document.floor.widthM * projection.scale} height={document.floor.depthM * projection.scale} className="eay-authoring-floor" />
            <rect x={projection.offsetX} y={projection.offsetY} width={document.floor.widthM * projection.scale} height={document.floor.depthM * projection.scale} fill="url(#eay-authoring-grid)" className="eay-authoring-grid" />
            {document.architecture.elements.map((element) => (
              <polygon
                key={element.element_id}
                points={svgPointString(rotatedRectSvgPoints({
                  centerXM: element.center_x_m,
                  centerYM: element.center_y_m,
                  widthM: element.width_m,
                  depthM: element.depth_m,
                  rotationDeg: element.rotation_deg,
                }, projection))}
                className={`eay-authoring-element eay-authoring-element--${element.element_type}${selectedId === element.element_id ? " is-selected" : ""}`}
                data-element-id={element.element_id}
                data-rotation-deg={element.rotation_deg}
                onPointerDown={(event) => beginDrag(event, element)}
              >
                <title>{`${t(element.element_type)} · ${element.element_id}`}</title>
              </polygon>
            ))}
          </svg>
        </div>

        <aside className="eay-authoring-inspector">
          <h3>{t("architectureInspector")}</h3>
          <fieldset>
            <legend>{t("floor")}</legend>
            <label><span>{t("width")}</span><input type="number" min="1" step="0.05" value={document.floor.widthM} disabled={!canEdit} onChange={(event) => commit(resizePlanogramAuthoringFloor(document, numericValue(event.target.value, document.floor.widthM), document.floor.depthM))} /></label>
            <label><span>{t("depth")}</span><input type="number" min="1" step="0.05" value={document.floor.depthM} disabled={!canEdit} onChange={(event) => commit(resizePlanogramAuthoringFloor(document, document.floor.widthM, numericValue(event.target.value, document.floor.depthM)))} /></label>
          </fieldset>
          {selected ? (
            <fieldset>
              <legend>{t("exactDimensions")}</legend>
              <code>{selected.element_id}</code>
              <label><span>{t("x")}</span><input type="number" step="0.05" value={selected.center_x_m} disabled={!canEdit} onChange={(event) => updateSelected({ center_x_m: numericValue(event.target.value, selected.center_x_m) })} /></label>
              <label><span>{t("y")}</span><input type="number" step="0.05" value={selected.center_y_m} disabled={!canEdit} onChange={(event) => updateSelected({ center_y_m: numericValue(event.target.value, selected.center_y_m) })} /></label>
              <label><span>{t("width")}</span><input type="number" min="0.05" step="0.05" value={selected.width_m} disabled={!canEdit} onChange={(event) => updateSelected({ width_m: numericValue(event.target.value, selected.width_m) })} /></label>
              <label><span>{t("depth")}</span><input type="number" min="0.05" step="0.05" value={selected.depth_m} disabled={!canEdit} onChange={(event) => updateSelected({ depth_m: numericValue(event.target.value, selected.depth_m) })} /></label>
              <label><span>{t("rotation")}</span><input type="number" step="1" value={selected.rotation_deg} disabled={!canEdit} onChange={(event) => updateSelected({ rotation_deg: numericValue(event.target.value, selected.rotation_deg) })} /></label>
              <label><span>{t("clearance")}</span><input type="number" min="0" step="0.05" value={selected.clearance_m || 0} disabled={!canEdit} onChange={(event) => updateSelected({ clearance_m: numericValue(event.target.value, selected.clearance_m || 0) })} /></label>
              <button type="button" className="eay-authoring-delete" disabled={!canEdit} onClick={deleteSelected}><Trash2 size={16} aria-hidden="true" />{t("delete")}</button>
            </fieldset>
          ) : <p>{t("selectHint")}</p>}
          {scanDerived ? <p className="eay-authoring-provenance">{t("provenancePreserved")}</p> : null}
        </aside>
      </div>
    </section>
  );
}
