import React, { useMemo, useRef, useState } from "react";

import { translateAcademyGraph } from "../../platform/i18n/academyGraphMessages.js";
import { translateAcademyStudioTerm } from "../../platform/i18n/academyStudioTermMessages.js";
import "./academy-expansion.css";

const NODE_WIDTH = 156;
const NODE_HEIGHT = 78;
const CANVAS_WIDTH = 960;
const CANVAS_HEIGHT = 560;

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
  const canvasRef = useRef(null);
  const dragRef = useRef(null);
  const [draggingKey, setDraggingKey] = useState("");

  const positions = useMemo(
    () => Object.fromEntries(nodes.map((node, index) => [node.node_key, nodePosition(node, index)])),
    [nodes],
  );

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
      drag.startX + event.clientX - drag.startClientX,
      drag.startY + event.clientY - drag.startClientY,
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

  return (
    <section className="eay-academy-graph-shell" aria-label={gx("graphCanvas")}>
      <header>
        <div><strong>{gx("graphCanvas")}</strong><p>{gx("graphHint")}</p></div>
        {selectedKey ? <span>{gx("selectedNode")}: {selectedKey}</span> : null}
      </header>
      <div className="eay-academy-graph-scroll">
        <div className="eay-academy-graph-canvas" ref={canvasRef} style={{ width: CANVAS_WIDTH, height: CANVAS_HEIGHT }}>
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
    </section>
  );
}
