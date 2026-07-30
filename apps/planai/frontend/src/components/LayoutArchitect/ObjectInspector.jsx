import React from "react";

export default function ObjectInspector({ object, onChange, onDelete }) {
  if (!object) return <aside className="object-inspector empty">Nesne seç.</aside>;
  function patch(key, value) { onChange?.({ ...object, [key]: value }); }
  return <aside className="object-inspector">
    <h3>{object.label || object.type || "Nesne"}</h3>
    <label>X <input type="number" value={object.x || 0} onChange={(e) => patch("x", Number(e.target.value))} /></label>
    <label>Y <input type="number" value={object.y || 0} onChange={(e) => patch("y", Number(e.target.value))} /></label>
    <label>Genişlik <input type="number" value={object.w || object.width || 1} onChange={(e) => patch("w", Number(e.target.value))} /></label>
    <label>Derinlik <input type="number" value={object.h || object.depth || 1} onChange={(e) => patch("h", Number(e.target.value))} /></label>
    <label>Yön <input type="number" value={object.rotation || 0} onChange={(e) => patch("rotation", Number(e.target.value))} /></label>
    <button onClick={() => onDelete?.(object.id)}>Sil</button>
  </aside>;
}
