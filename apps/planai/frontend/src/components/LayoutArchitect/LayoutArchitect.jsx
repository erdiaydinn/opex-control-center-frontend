import React, { useMemo, useState } from "react";
import FixtureInventoryPanel from "./FixtureInventoryPanel";
import ObjectInspector from "./ObjectInspector";

export default function LayoutArchitect({ planogram, onCommit }) {
  const [inventory, setInventory] = useState(planogram?.fixture_inventory || {});
  const [objects, setObjects] = useState(planogram?.layout_objects || []);
  const [selectedId, setSelectedId] = useState(null);
  const selected = useMemo(() => objects.find((o) => o.id === selectedId), [objects, selectedId]);
  function updateObject(next) { setObjects((prev) => prev.map((x) => (x.id === next.id ? next : x))); }
  function addObject(type) { const id = `${type}-${Date.now()}`; setObjects((prev) => [...prev, { id, type, label: type.toUpperCase(), x: 0, y: 0, w: 1, h: 1, rotation: 0 }]); setSelectedId(id); }
  function commit() { onCommit?.({ ...planogram, fixture_inventory: inventory, layout_objects: objects }); }
  return <div className="layout-architect-v18">
    <FixtureInventoryPanel inventory={inventory} onChange={setInventory} />
    <section className="layout-canvas-lite"><div className="layout-toolbar"><button onClick={() => addObject("column")}>Kolon</button><button onClick={() => addObject("wall")}>Duvar</button><button onClick={() => addObject("dispatch")}>Dispatch</button><button onClick={() => addObject("receiving")}>Mal Kabul</button><button onClick={commit}>Kaydet</button></div><div className="layout-object-map">{objects.map((o) => <button key={o.id} className={`layout-object-chip ${selectedId === o.id ? "selected" : ""}`} style={{ left: `${50 + (o.x || 0) * 12}px`, top: `${50 + (o.y || 0) * 12}px` }} onClick={() => setSelectedId(o.id)}>{o.label || o.type}</button>)}</div></section>
    <ObjectInspector object={selected} onChange={updateObject} onDelete={(id) => { setObjects((prev) => prev.filter((x) => x.id !== id)); setSelectedId(null); }} />
  </div>;
}
