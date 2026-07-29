import React, { useEffect, useMemo, useState } from "react";
import "./LayoutEditor.css";
import "./LayoutEditor.world.css";

const GRID = 42;
const CELL = 18;

function uid(type) { return `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`; }
function clamp(v, min, max) { return Math.max(min, Math.min(max, Number(v) || 0)); }

function objectDefaults(type) {
  const base = { id: uid(type), type, x: 2, y: 2, w: 3, h: 2, rotation: 0, label: type.toUpperCase() };
  if (type === "wall") return { ...base, w: 14, h: 0.35, label: "DUVAR" };
  if (type === "column_round") return { ...base, w: 1.1, h: 1.1, label: "KOLON" };
  if (type === "column_rect") return { ...base, w: 1.6, h: 1, label: "KOLON" };
  if (type === "dispatch") return { ...base, w: 5, h: 2, label: "DISPATCH" };
  if (type === "electrical_panel") return { ...base, w: 1.3, h: .7, label: "PANO" };
  if (type === "fire_exit") return { ...base, w: 2, h: .6, label: "ACİL" };
  if (type === "horizontal_freezer") return { ...base, w: 5, h: 1.4, label: "YATAY" };
  if (type === "algida_freezer") return { ...base, w: 5, h: 1.4, label: "ALGIDA" };
  return base;
}

function moduleDefaults(aisle, module, idx, baseX, baseY) {
  const lp = module?.layout_position || {};
  const side = module?.side || (idx % 2 === 0 ? "L" : "R");
  const localIndex = Math.floor(idx / 2);
  const orientation = module?.layout_orientation || ((lp.rotation || module?.layout_rotation) === 90 ? "horizontal" : "vertical");
  return {
    id: `${aisle.aisle_id}__${module.module_id}`,
    kind: "module",
    aisle_id: aisle.aisle_id,
    module_id: module.module_id,
    short: `${side}${module.module_id}`,
    label: `${aisle.aisle_id}-${side}${module.module_id}`,
    side,
    fixture_type: module.fixture_type || module.module_type || "regular_shelf",
    x: Number(lp.x ?? lp.grid_x ?? (baseX + localIndex * 1.35)),
    y: Number(lp.y ?? lp.grid_y ?? (baseY + (side === "R" ? 2.55 : 0))),
    w: Number(lp.w ?? (orientation === "horizontal" ? 1.6 : 1.0)),
    h: Number(lp.h ?? (orientation === "horizontal" ? .65 : 1.55)),
    rotation: Number(lp.rotation ?? module.layout_rotation ?? (orientation === "horizontal" ? 90 : 0)),
    orientation,
  };
}

function normalizeAisle(a, i) {
  const count = a.modules?.length || 0;
  const baseX = Number(a.layout_position?.grid_x ?? a.layout_position?.x ?? ((i % 2) * 9 + 2));
  const baseY = Number(a.layout_position?.grid_y ?? a.layout_position?.y ?? (Math.floor(i / 2) * 4 + 2));
  const walkwayM = Number(a.walkway_m ?? a.walkway_width_m ?? 1.2);
  return {
    aisle_id: a.aisle_id,
    label: a.aisle_id,
    grid_x: baseX,
    grid_y: baseY,
    rotation: Number(a.layout_position?.rotation ?? 0),
    walkway_m: Number.isFinite(walkwayM) ? walkwayM : 1.2,
    type: a.zone_type === "COLD_ZONE" ? "cold" : a.zone_type === "FROZEN_ZONE" ? "frozen" : "ambient",
    modules: (a.modules || []).map((m, idx) => moduleDefaults(a, m, idx, baseX, baseY)),
  };
}

function rect(n) { return { x1: n.x, y1: n.y, x2: n.x + n.w, y2: n.y + n.h }; }
function overlap(a,b){ const A=rect(a),B=rect(b); return A.x1<B.x2&&A.x2>B.x1&&A.y1<B.y2&&A.y2>B.y1; }

export default function LayoutEditor({ plan, open, onClose, onSave }) {
  const [selectedAisle, setSelectedAisle] = useState("ALL");
  const [selectedId, setSelectedId] = useState(null);
  const [aisles, setAisles] = useState([]);
  const [objects, setObjects] = useState([]);
  const [drag, setDrag] = useState(null);
  const [moveMode, setMoveMode] = useState("snap");

  useEffect(() => {
    if (!open) return;
    setAisles((plan?.aisles || []).map(normalizeAisle));
    setObjects(plan?.layout_objects || []);
    setSelectedAisle("ALL");
    setSelectedId(null);
  }, [open, plan]);

  useEffect(() => {
    if (!open) return;
    document.body.classList.add("layout-architect-open");
    return () => document.body.classList.remove("layout-architect-open");
  }, [open]);

  const modules = useMemo(() => aisles.flatMap(a => a.modules || []), [aisles]);
  const visibleModules = selectedAisle === "ALL" ? modules : modules.filter(m => String(m.aisle_id) === String(selectedAisle));
  const visibleAisles = selectedAisle === "ALL" ? aisles : aisles.filter(a => String(a.aisle_id) === String(selectedAisle));
  const selected = [...modules, ...objects].find(x => x.id === selectedId);
  const warnings = useMemo(() => {
    const out=[]; for(const m of modules){for(const o of objects){if(overlap(m,o)) out.push(`${m.label} ile ${o.label || o.type} çakışıyor.`)}} return out.slice(0,10);
  }, [modules, objects]);

  if (!open) return null;

  function addObject(type){ const o=objectDefaults(type); setObjects(p=>[...p,o]); setSelectedId(o.id); }
  function patchSelected(patch){
    if(!selected) return;
    if(selected.kind==="module") setAisles(prev=>prev.map(a=>({...a,modules:(a.modules||[]).map(m=>m.id===selected.id?{...m,...patch}:m)})));
    else setObjects(prev=>prev.map(o=>o.id===selected.id?{...o,...patch}:o));
  }
  function startDrag(kind,id,e){ e.stopPropagation(); setSelectedId(id); setDrag({kind,id}); }
  function onMove(e){
    if(!drag) return;
    const r=e.currentTarget.getBoundingClientRect();
    const rawX=(e.clientX-r.left)/CELL, rawY=(e.clientY-r.top)/CELL;
    const x=moveMode==="free"?Math.round(rawX*10)/10:Math.round(rawX);
    const y=moveMode==="free"?Math.round(rawY*10)/10:Math.round(rawY);
    const patch={x:clamp(x,0,GRID-1),y:clamp(y,0,GRID-1)};
    if(drag.kind==="module") setAisles(prev=>prev.map(a=>({...a,modules:(a.modules||[]).map(m=>m.id===drag.id?{...m,...patch}:m)})));
    else if(drag.kind==="object") setObjects(prev=>prev.map(o=>o.id===drag.id?{...o,...patch}:o));
  }
  function rotateSelected(id=selectedId){
    if(!id) return;
    const target=[...modules,...objects].find(x=>x.id===id); if(!target) return;
    const rot=((Number(target.rotation)||0)+90)%360;
    if(target.kind==="module"){
      const orientation=rot%180===90?"horizontal":"vertical";
      setAisles(prev=>prev.map(a=>({...a,modules:(a.modules||[]).map(m=>m.id===id?{...m,rotation:rot,orientation,w:orientation==="horizontal"?1.6:1,h:orientation==="horizontal"?.65:1.55}:m)})));
    } else setObjects(prev=>prev.map(o=>o.id===id?{...o,rotation:rot}:o));
  }
  function deleteSelected(id=selectedId){
    if(!id) return;
    setObjects(prev=>prev.filter(o=>o.id!==id));
    setAisles(prev=>prev.map(a=>({...a,modules:(a.modules||[]).filter(m=>m.id!==id)})));
    setSelectedId(null);
  }
  function applyAiBestPlacement(){
    const sorted = [...aisles].sort((a,b)=>{
      const rank = (x)=> x.type==="ambient"?0:x.type==="cold"?1:x.type==="frozen"?2:3;
      return rank(a)-rank(b) || String(a.aisle_id).localeCompare(String(b.aisle_id));
    });
    const placed = sorted.map((a, idx)=>{
      const col = idx % 2;
      const row = Math.floor(idx / 2);
      const baseX = 2 + col * 14;
      const baseY = 2 + row * 4;
      const mods = (a.modules||[]).map((m,i)=>{
        const side = i % 2 === 0 ? "L" : "R";
        const local = Math.floor(i/2);
        return {
          ...m,
          side,
          short: `${side}${m.module_id}`,
          x: baseX + local*1.35,
          y: baseY + (side==="R"?2.55:0),
          rotation: 0,
          orientation: "vertical",
          w: 1,
          h: 1.55,
        };
      });
      return {...a,grid_x:baseX,grid_y:baseY,walkway_m:1.2,modules:mods};
    });
    const essentialObjects = objects.map(o => ({...o}));
    setAisles(placed);
    setObjects(essentialObjects);
    setSelectedId(null);
  }
  function save(){
    const payloadAisles=aisles.map(a=>({
      aisle_id:a.aisle_id, grid_x:a.grid_x, grid_y:a.grid_y, rotation:a.rotation||0,
      module_count:a.modules.length, walkway_m:a.walkway_m,
      module_orientations:(a.modules||[]).map(m=>m.orientation||"vertical"),
      module_layouts:(a.modules||[]).map((m,idx)=>({
        module_id:idx+1, side:m.side||"L", x:m.x, y:m.y, w:m.w, h:m.h,
        rotation:m.rotation||0, orientation:m.orientation||"vertical", fixture_type:m.fixture_type||"regular_shelf",
      })),
    }));
    onSave?.({aisles:payloadAisles,objects}); onClose?.();
  }

  return (
    <div className="le-backdrop">
      <div className="le-modal le-premium-modal">
        <header className="le-head">
          <div><div className="le-kicker">LIVE TWIN / ARCHITECT MODE</div><h2>Layout Architect</h2><p>Koridoru değil, koridorun içindeki her modülü ayrı ayrı konumlandır.</p></div>
          <div className="le-actions">
            <select value={selectedAisle} onChange={(e)=>setSelectedAisle(e.target.value)}><option value="ALL">Tüm koridorlar</option>{aisles.map(a=><option key={a.aisle_id} value={a.aisle_id}>{a.aisle_id}</option>)}</select>
            <button className="ai" onClick={applyAiBestPlacement}>AI en optimal yerleşimi uygula</button>
            <button className={moveMode==="snap"?"active":""} onClick={()=>setMoveMode("snap")}>Snap</button>
            <button className={moveMode==="free"?"active":""} onClick={()=>setMoveMode("free")}>Free</button>
            <button className="primary" onClick={save}>Layout kaydet</button><button onClick={onClose}>Vazgeç</button>
          </div>
        </header>
        <div className="le-body le-architect-body">
          <aside className="le-toolbox"><h3>Obje Kataloğu</h3>
            <button onClick={()=>addObject("wall")}>Duvar Paneli</button><button onClick={()=>addObject("column_round")}>Yuvarlak Kolon</button><button onClick={()=>addObject("column_rect")}>Dikdörtgen Kolon</button><button onClick={()=>addObject("electrical_panel")}>Elektrik Panosu</button><button onClick={()=>addObject("fire_exit")}>Acil Çıkış</button><button onClick={()=>addObject("dispatch")}>Dispatch</button><button onClick={()=>addObject("horizontal_freezer")}>Yatay Dolap</button><button onClick={()=>addObject("algida_freezer")}>Algida Dolap</button>
            <small>Sürükle: taşı · Sağ tık: döndür · Çift tık: sil</small>
            <div className="le-warning-card"><b>Operasyon Uyarıları</b>{warnings.length?warnings.map((w,i)=><p key={i}>⚠ {w}</p>):<p>Çakışma görünmüyor.</p>}</div>
          </aside>
          <section className="le-grid le-architect-grid" onMouseMove={onMove} onMouseUp={()=>setDrag(null)} onMouseLeave={()=>setDrag(null)}>
            {visibleAisles.map(a=><div key={`walk-${a.aisle_id}`} className={`le-walkway ${a.type}`} style={{left:a.grid_x*CELL,top:(a.grid_y+1.25)*CELL,width:Math.max(3,Math.max(1,a.modules.length)*1.35)*CELL,height:Math.max(.7,Number(a.walkway_m||1.2))*CELL,transform:`rotate(${a.rotation||0}deg)`}}><b>{a.aisle_id}</b><span>{a.walkway_m}m</span></div>)}
            {objects.map(o=><div key={o.id} className={`le-object ${o.type} ${selectedId===o.id?"selected":""}`} style={{left:o.x*CELL,top:o.y*CELL,width:o.w*CELL,height:o.h*CELL,transform:`rotate(${o.rotation||0}deg)`}} onMouseDown={(e)=>startDrag("object",o.id,e)} onContextMenu={(e)=>{e.preventDefault();setSelectedId(o.id);rotateSelected(o.id)}} onDoubleClick={()=>deleteSelected(o.id)}>{o.label}</div>)}
            {visibleModules.map(m=><div key={m.id} data-short-label={m.short} className={`le-module-node ${m.side||""} ${m.fixture_type||""} ${selectedId===m.id?"selected":""}`} style={{left:m.x*CELL,top:m.y*CELL,width:m.w*CELL,height:m.h*CELL,transform:`rotate(${m.rotation||0}deg)`}} onMouseDown={(e)=>startDrag("module",m.id,e)} onContextMenu={(e)=>{e.preventDefault();setSelectedId(m.id);rotateSelected(m.id)}} onDoubleClick={()=>deleteSelected(m.id)} />)}
          </section>
          <aside className="le-module-inspector"><h3>İnce Ayar</h3>{!selected?<p>Modül, kolon veya obje seç.</p>:(
            <div className="le-inspector-form"><strong>{selected.label}</strong>
              <label>X <input type="number" step={moveMode==="free"?".1":"1"} value={selected.x} onChange={(e)=>patchSelected({x:Number(e.target.value)})}/></label>
              <label>Y <input type="number" step={moveMode==="free"?".1":"1"} value={selected.y} onChange={(e)=>patchSelected({y:Number(e.target.value)})}/></label>
              <label>Genişlik <input type="number" step=".1" value={selected.w} onChange={(e)=>patchSelected({w:Number(e.target.value)})}/></label>
              <label>Derinlik <input type="number" step=".1" value={selected.h} onChange={(e)=>patchSelected({h:Number(e.target.value)})}/></label>
              <label>Yön <select value={selected.rotation||0} onChange={(e)=>patchSelected({rotation:Number(e.target.value),orientation:Number(e.target.value)%180===90?"horizontal":"vertical"})}><option value={0}>0°</option><option value={90}>90°</option><option value={180}>180°</option><option value={270}>270°</option></select></label>
              {selected.kind==="module"&&<><label>Taraf <select value={selected.side||"L"} onChange={(e)=>patchSelected({side:e.target.value,short:`${e.target.value}${selected.module_id}`})}><option value="L">Sol</option><option value="R">Sağ</option><option value="C">Özel</option></select></label><label>Raf / Dolap Tipi <select value={selected.fixture_type||"regular_shelf"} onChange={(e)=>patchSelected({fixture_type:e.target.value})}><option value="regular_shelf">Çelik Raf</option><option value="steel_rack_new_gen">Yeni Nesil Çelik Raf</option><option value="hdr_heavy_rack">HDR Ağır Yük</option><option value="martek_plus4">Martek +4</option><option value="martek_frozen_minus18">Martek -18</option><option value="ice_cream_chest_freezer_large">Algida/Golf</option></select></label></>}
              {selected.kind!=="module"&&<label>Etiket <input value={selected.label||""} onChange={(e)=>patchSelected({label:e.target.value})}/></label>}
              <button onClick={()=>rotateSelected()}>Döndür</button><button className="danger" onClick={()=>deleteSelected()}>Sil</button>
            </div>)}</aside>
        </div>
      </div>
    </div>
  );
}
