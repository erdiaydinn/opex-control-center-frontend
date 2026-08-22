import React, { useMemo, useRef, useState } from "react";
import { Maximize2, Minus, Plus, RotateCcw } from "lucide-react";

import { translateAcademyGraph } from "../../platform/i18n/academyGraphMessages.js";
import { translateAcademyStudioTerm } from "../../platform/i18n/academyStudioTermMessages.js";
import "./academy-expansion.css";

const NODE_WIDTH = 156;
const NODE_HEIGHT = 78;
const CANVAS_WIDTH = 960;
const CANVAS_HEIGHT = 560;
const MIN_ZOOM = 0.6;
const MAX_ZOOM = 1.6;
const ZOOM_STEP = 0.1;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function autoPosition(index) {
  const column = index % 4;
  const row = Math.floor(index / 4);
  return { x: 34 + column * 220, y: 42 + row * 150 };
}

function nodePosition(node, index) {
  const position = node?.payload?.authoring_position;
  if (position && Number.isFinite(Number(position.x)) && Number.isFinite(Number(position.y))) {
    return {
      x: clamp(Number(position.x), 0, CANVAS_WIDTH - NODE_WIDTH),
      y: clamp(Number(position.y), 0, CANVAS_HEIGHT - NODE_HEIGHT),
    };
  }
  return autoPosition(index);
}

export default function AcademyScenarioGraphCanvas({ nodes, edges, locale, selectedKey, onSelect, onMove }) {
  const gx = (key) => translateAcademyGraph(locale, key);
  const st = (key) => translateAcademyStudioTerm(locale, key);
  const scrollRef = useRef(null);
  const dragRef = useRef(null);
  const [draggingKey, setDraggingKey] = useState("");
  const [zoom, setZoom] = useState(1);

  const positions = useMemo(
    () => Object.fromEntries(nodes.map((node, index) => [node.node_key, nodePosition(node, index)])),
    [nodes],
  );

  const diagnostics = useMemo(() => {
    const issues = [];
    const nodeKeys = nodes.map((node) => String(node.node_key || "").trim());
    const knownKeys = new Set(nodeKeys.filter(Boolean));
    const seenNodeKeys = new Set();

    if (nodeKeys.some((key) => !key)) issues.push(gx("missingNodeKey"));
    for (const key of nodeKeys) {
      if (!key) continue;
      if (seenNodeKeys.has(key)) issues.push(gx("duplicateNodeKey"));
      seenNodeKeys.add(key);
    }
    if (!nodes.some((node) => node.terminal)) issues.push(gx("missingTerminal"));

    const seenChoices = new Set();
    for (const edge of edges) {
      if (!knownKeys.has(edge.from_node_key) || !knownKeys.has(edge.to_node_key)) {
        issues.push(gx("brokenEdgeReference"));
      }
      const choiceIdentity = `${edge.from_node_key || ""}::${edge.choice_key || ""}`;
      if (seenChoices.has(choiceIdentity)) issues.push(gx("duplicateChoice"));
      seenChoices.add(choiceIdentity);
      const localizedLabel = edge?.label_i18n?.[locale] || edge?.label_i18n?.en || edge?.label_i18n?.tr || "";
      if (!String(localizedLabel).trim()) issues.push(gx("blankEdgeLabel"));
    }

    return [...new Set(issues)];
  }, [edges, locale, nodes]);

  function move(nodeKey, x, y) {
    onMove(nodeKey, {
      x: Math.round(clamp(x, 0, CANVAS_WIDTH - NODE_WIDTH)),
      y: Math.round(clamp(y, 0, CANVAS_HEIGHT - NODE_HEIGHT)),
    });
  }

  function pointerDown(event, nodeKey) {
    if (event.button !== 0) return;
    const position = positions[nodeKey];
    if (!position) return;
    dragRef.current = {
      nodeKey,
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startX: position.x,
      startY: position.y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDraggingKey(nodeKey);
    onSelect(nodeKey);
  }

  function pointerMove(event) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    move(
      drag.nodeKey,
      drag.startX + (event.clientX - drag.startClientX) / zoom,
      drag.startY + (event.clientY - drag.startClientY) / zoom,
    );
  }

  function pointerUp(event) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    dragRef.current = null;
    setDraggingKey("");
  }

  function keyDown(event, nodeKey) {
    const delta = event.shiftKey ? 25 : 10;
    const position = positions[nodeKey];
    if (!position) return;
    const offsets = {
      ArrowLeft: [-delta, 0],
      ArrowRight: [delta, 0],
      ArrowUp: [0, -delta],
      ArrowDown: [0, delta],
    };
    const offset = offsets[event.key];
    if (!offset) return;
    event.preventDefault();
    onSelect(nodeKey);
    move(nodeKey, position.x + offset[0], position.y + offset[1]);
  }

  function changeZoom(delta) {
    setZoom((value) => Number(clamp(value + delta, MIN_ZOOM, MAX_ZOOM).toFixed(2)));
  }

  function fitView() {
    const availableWidth = Math.max(320, Number(scrollRef.current?.clientWidth || CANVAS_WIDTH) - 24);
    const nextZoom = clamp(Math.min(1, availableWidth / CANVAS_WIDTH), MIN_ZOOM, MAX_ZOOM);
    setZoom(Number(nextZoom.toFixed(2)));
    requestAnimationFrame(() => scrollRef.current?.scrollTo({ left: 0, top: 0, behavior: "smooth" }));
  }

  function resetView() {
    setZoom(1);
    requestAnimationFrame(() => scrollRef.current?.scrollTo({ left: 0, top: 0, behavior: "smooth" }));
  }

  return (
    <section className="eay-academy-graph-shell" aria-label={gx("graphCanvas")}>
      <header>
        <div><strong>{gx("graphCanvas")}</strong><p>{gx("graphHint")}</p></div>
        <div className="eay-academy-graph-toolbar" role="group" aria-label={`${gx("graphCanvas")} · ${gx("zoomLevel")}`}>
          <button type="button" className="eay-academy-icon-action" aria-label={gx("zoomOut")} title={gx("zoomOut")} disabled={zoom <= MIN_ZOOM} onClick={() => changeZoom(-ZOOM_STEP)}><Minus size={15} aria-hidden="true" /></button>
          <span aria-live="polite">{gx("zoomLevel")}: {Math.round(zoom * 100)}%</span>
          <button type="button" className="eay-academy-icon-action" aria-label={gx("zoomIn")} title={gx("zoomIn")} disabled={zoom >= MAX_ZOOM} onClick={() => changeZoom(ZOOM_STEP)}><Plus size={15} aria-hidden="true" /></button>
          <button type="button" className="eay-academy-icon-action" aria-label={gx("fitView")} title={gx("fitView")} onClick={fitView}><Maximize2 size={15} aria-hidden="true" /></button>
          <button type="button" className="eay-academy-icon-action" aria-label={gx("resetView")} title={gx("resetView")} onClick={resetView}><RotateCcw size={15} aria-hidden="true" /></button>
        </div>
        {selectedKey ? <span>{gx("selectedNode")}: {selectedKey}</span> : null}
      </header>

      <div className={`eay-academy-graph-preflight ${diagnostics.length ? "has-issues" : "is-ready"}`} role="status" aria-live="polite">
        <strong>{gx("preflight")}</strong>
        {diagnostics.length ? <ul>{diagnostics.map((issue) => <li key={issue}>{issue}</li>)}</ul> : <span>{gx("preflightReady")}</span>}
      </div>

      <div className="eay-academy-graph-scroll" ref={scrollRef}>
        <div className="eay-academy-graph-viewport" style={{ width: CANVAS_WIDTH * zoom, height: CANVAS_HEIGHT * zoom }}>
          <div className="eay-academy-graph-canvas" style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT, transform: `scale(${zoom})` }}>
            <svg className="eay-academy-graph-edges" viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`} aria-hidden="true">
              <defs>
                <marker id="academy-scenario-arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" /></marker>
              </defs>
              {edges.map((edge, index) => {
                const from = positions[edge.from_node_key];
                const to = positions[edge.to_node_key];
                if (!from || !to) return null;
                const x1 = from.x + NODE_WIDTH;
                const y1 = from.y + NODE_HEIGHT / 2;
                const x2 = to.x;
                const y2 = to.y + NODE_HEIGHT / 2;
                const bend = Math.max(60, Math.abs(x2 - x1) * 0.45);
                return <path key={`${edge.from_node_key}-${edge.choice_key}-${index}`} d={`M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`} markerEnd="url(#academy-scenario-arrow)" />;
              })}
            </svg>
            {nodes.map((node, index) => {
              const position = positions[node.node_key] || autoPosition(index);
              return (
                <button
                  type="button"
                  key={`${node.node_key}-${index}`}
                  className={`eay-academy-graph-node ${selectedKey === node.node_key ? "is-selected" : ""} ${node.terminal ? "is-terminal" : ""} ${draggingKey === node.node_key ? "is-dragging" : ""}`}
                  style={{ left: position.x, top: position.y }}
                  onClick={() => onSelect(node.node_key)}
                  onPointerDown={(event) => pointerDown(event, node.node_key)}
                  onPointerMove={pointerMove}
                  onPointerUp={pointerUp}
                  onPointerCancel={pointerUp}
                  onKeyDown={(event) => keyDown(event, node.node_key)}
                  aria-label={`${node.node_key}. ${st(node.node_type)}. ${gx("keyboardMove")}`}
                >
                  <strong>{node.node_key}</strong>
                  <span>{st(node.node_type)}</span>
                  {node.terminal ? <small>{st(node.terminal_outcome || "completed")}</small> : null}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
