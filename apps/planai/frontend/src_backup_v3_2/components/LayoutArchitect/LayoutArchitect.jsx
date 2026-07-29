
import React, { useCallback, useMemo, useRef, useState } from "react";

const catalog = [
  { type: "wall", label: "Duvar Paneli", w: 8, d: 0.35 },
  { type: "round_column", label: "Yuvarlak Kolon", w: 0.8, d: 0.8 },
  { type: "column", label: "Dikdörtgen Kolon", w: 0.6, d: 1.0 },
  { type: "electric", label: "Elektrik Panosu", w: 1.6, d: 0.6 },
  { type: "exit", label: "Acil Çıkış", w: 3, d: 1.2 },
  { type: "dispatch", label: "Dispatch", w: 10, d: 5 },
  { type: "chilled", label: "Soğuk Oda +4", w: 12, d: 8 },
  { type: "frozen", label: "Donuk Oda -18", w: 12, d: 8 },
  { type: "algida", label: "Algida Dolap", w: 3, d: 2 },
  { type: "fridge", label: "Yatay Dolap", w: 5, d: 1.4 },
];

const scale = 12;
const world = { xMin: -38, zMin: -26, width: 76, depth: 52 };
const clamp = (v, min, max) => Math.min(max, Math.max(min, v));
function pctX(x) { return ((x - world.xMin) / world.width) * 100; }
function pctZ(z) { return ((z - world.zMin) / world.depth) * 100; }
function worldFromPoint(rect, clientX, clientY) {
  const px = (clientX - rect.left) / rect.width;
  const py = (clientY - rect.top) / rect.height;
  return { x: world.xMin + px * world.width, z: world.zMin + py * world.depth };
}

export default function LayoutArchitect({ plan, setPlan }) {
  const boardRef = useRef(null);
  const [selected, setSelected] = useState(null);
  const [snap, setSnap] = useState(true);
  const [drag, setDrag] = useState(null);

  const objects = useMemo(() => {
    const aisles = plan.aisles.map((a) => ({ ...a, id: `aisle-${a.aisle_id}`, label: a.aisle_id, type: "aisle", w: a.width, d: a.depth }));
    const zones = plan.zones.map((z) => ({ ...z, id: `zone-${z.id}`, w: z.w, d: z.d }));
    return [...aisles, ...zones];
  }, [plan]);

  const updateObject = useCallback((id, patch) => {
    setPlan((old) => ({
      ...old,
      aisles: old.aisles.map((a) => id === `aisle-${a.aisle_id}` ? { ...a, x: patch.x ?? a.x, z: patch.z ?? a.z, width: patch.w ?? a.width, depth: patch.d ?? a.depth, rotation: patch.rotation ?? a.rotation } : a),
      zones: old.zones.map((z) => id === `zone-${z.id}` ? { ...z, x: patch.x ?? z.x, z: patch.z ?? z.z, w: patch.w ?? z.w, d: patch.d ?? z.d } : z),
    }));
  }, [setPlan]);

  const addObject = (item) => {
    const n = Date.now().toString(36);
    setPlan((old) => ({ ...old, zones: [...old.zones, { id: `${item.type}-${n}`, label: item.label, type: item.type, x: 0, z: 0, w: item.w, d: item.d }] }));
  };

  const onPointerMove = (e) => {
    if (!drag || !boardRef.current) return;
    const p = worldFromPoint(boardRef.current.getBoundingClientRect(), e.clientX, e.clientY);
    const next = { x: p.x - drag.dx, z: p.z - drag.dz };
    if (snap) { next.x = Math.round(next.x); next.z = Math.round(next.z); }
    updateObject(drag.id, next);
  };

  const onPointerUp = () => setDrag(null);
  const selectedObj = objects.find((o) => o.id === selected);

  return (
    <div className="architectPage">
      <section className="sectionTitle"><small>ARCHITECT MODE</small><h1>Mimari düzenleyici<span>.</span></h1><p>Mouse ile seç, taşı, ölçülendir, döndür; snap/free mod ile layout'u gerçek planograma yaz.</p></section>
      <div className="architectToolbar"><button className="primary">AI en optimal yerleşimi uygula</button><button onClick={() => setSnap(true)} className={snap ? "on" : ""}>Snap</button><button onClick={() => setSnap(false)} className={!snap ? "on" : ""}>Free</button><button>Undo</button><button>Redo</button><button>Layout kaydet</button></div>
      <div className="architectGrid">
        <aside className="objectCatalog"><h3>Obje Kataloğu</h3>{catalog.map((item) => <button key={item.type} onClick={() => addObject(item)}><span>{item.label}</span><small>{item.w}m / {item.d}m</small></button>)}</aside>
        <div ref={boardRef} className="blueprintBoard" onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerLeave={onPointerUp}>
          <div className="axis x">{Array.from({ length: 15 }, (_, i) => <span key={i}>{i * 10}</span>)}</div>
          <div className="axis y">{"ABCDEFGHIJ".split("").map((x) => <span key={x}>{x}</span>)}</div>
          {objects.map((o) => (
            <button
              key={o.id}
              className={`layoutObj ${o.type} ${selected === o.id ? "selected" : ""}`}
              style={{ left: `${pctX(o.x)}%`, top: `${pctZ(o.z)}%`, width: `${Math.max(3, o.w * scale)}px`, height: `${Math.max(24, o.d * scale)}px`, transform: `translate(-50%,-50%) rotate(${o.rotation || 0}deg)` }}
              onPointerDown={(e) => { e.stopPropagation(); const rect = boardRef.current.getBoundingClientRect(); const p = worldFromPoint(rect, e.clientX, e.clientY); setSelected(o.id); setDrag({ id: o.id, dx: p.x - o.x, dz: p.z - o.z }); }}
            ><b>{o.label}</b><small>{o.w || o.width}m × {o.d || o.depth}m</small></button>
          ))}
        </div>
        <aside className="propertiesPanel"><h3>Özellikler</h3>{selectedObj ? <>
          <b>{selectedObj.label}</b><small>{selectedObj.type}</small>
          <label>X (m)<input type="number" value={Number(selectedObj.x).toFixed(1)} onChange={(e) => updateObject(selectedObj.id, { x: Number(e.target.value) })} /></label>
          <label>Z (m)<input type="number" value={Number(selectedObj.z).toFixed(1)} onChange={(e) => updateObject(selectedObj.id, { z: Number(e.target.value) })} /></label>
          <label>Genişlik (m)<input type="number" value={Number(selectedObj.w || selectedObj.width).toFixed(1)} onChange={(e) => updateObject(selectedObj.id, { w: Number(e.target.value) })} /></label>
          <label>Derinlik (m)<input type="number" value={Number(selectedObj.d || selectedObj.depth).toFixed(1)} onChange={(e) => updateObject(selectedObj.id, { d: Number(e.target.value) })} /></label>
          <label>Rotasyon<input type="range" min="0" max="360" value={selectedObj.rotation || 0} onChange={(e) => updateObject(selectedObj.id, { rotation: Number(e.target.value) })} /></label>
          <button className="primary">AI önerisini uygula</button>
        </> : <p>Bir modül, kolon veya zone seç.</p>}</aside>
      </div>
    </div>
  );
}
