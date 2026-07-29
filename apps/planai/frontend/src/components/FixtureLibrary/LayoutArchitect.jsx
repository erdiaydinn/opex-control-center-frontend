import { useState } from 'react';
import { objectCatalog } from '../data/mock.js';
import { tt } from '../i18n/dictionary.js';
import TwinStudio3D from './Live3D/TwinStudio3D.jsx';

function normalizeNumber(v, fallback = 0) { const n = Number(v); return Number.isFinite(n) ? n : fallback; }

function objectStyle(o) {
  return { left: `${o.x}%`, top: `${o.y}%`, width: `${Math.max(1, o.w)}%`, height: `${Math.max(1, o.d)}%`, transform: `rotate(${o.rotation || 0}deg)` };
}

function ThreeEditor({ objects, selectedId, setSelectedId, onMoveObject, dragMode, setDragMode }) {
  const selected = objects.find((o) => String(o.id) === String(selectedId));
  return (
    <div className={`stage three-stage editor3d-real ${dragMode ? 'drag-mode-on' : ''}`}>
      <div className="stage-toolbar stage-toolbar-clean">
        <div className="pill"><b>3D Architect</b><span className="muted">Seç · taşı · sağ panelde ölçülendir</span></div>
        <button className={`btn ${dragMode ? 'primary' : 'ghost'}`} onClick={() => setDragMode(!dragMode)}>{dragMode ? 'Taşıma modu açık' : 'Mouse ile taşı'}</button>
        <div className="pill">Seçili: <b>{selected?.label || '—'}</b></div>
      </div>
      <TwinStudio3D
        objects={objects}
        products={[]}
        cameraPreset="top"
        heatmap="facilities"
        selectedAreaId={selectedId}
        selectedProductSku=""
        editorMode
        dragMode={dragMode}
        onMoveObject={onMoveObject}
        onSelectArea={(area) => setSelectedId(area.id)}
        onSelectProduct={() => {}}
      />
      <div className="editor3d-help">Sol tık: seç · Mouse ile taşı: butonu açınca objeyi sürükle · Wheel: yakınlaş · Sağ panel: kesin ölçü</div>
    </div>
  );
}

export default function LayoutArchitect({ lang, objects, setObjects, notify }) {
  const [selectedId, setSelectedId] = useState(objects.find(o => o.type === 'corridor')?.id || 'A');
  const [view, setView] = useState('3d');
  const [dragMode, setDragMode] = useState(false);
  const [drag, setDrag] = useState(null);
  const selected = objects.find((o) => o.id === selectedId) || objects[0];

  function updateSelected(field, value) {
    setObjects((prev) => prev.map((o) => o.id === selectedId ? { ...o, [field]: ['x','y','w','d','h','rotation','modules','shelves','utilization','changed'].includes(field) ? normalizeNumber(value, o[field]) : value } : o));
  }

  function moveObject(id, delta) {
    setObjects((prev) => prev.map((o) => String(o.id) === String(id) ? { ...o, x: Math.max(0, Math.min(140, Math.round((Number(o.x || 0) + delta.dx) * 10) / 10)), y: Math.max(0, Math.min(100, Math.round((Number(o.y || 0) + delta.dy) * 10) / 10)) } : o));
  }

  function nudgeSelected(dx, dy) {
    if (!selected) return;
    moveObject(selected.id, { dx, dy });
  }

  function addObject(template) {
    const id = `${template.type.toUpperCase()}_${Date.now().toString().slice(-5)}`;
    const next = { ...template, id, label: template.label, x: 8 + Math.random() * 12, y: 10 + Math.random() * 12, rotation: 0, utilization: 0, changed: 0 };
    setObjects((prev) => [...prev, next]);
    setSelectedId(id);
    notify?.(`${template.label} eklendi.`);
  }

  function deleteSelected() {
    if (!selected) return;
    setObjects((prev) => prev.filter((o) => o.id !== selected.id));
    setSelectedId(objects.find((o) => o.id !== selected.id)?.id || '');
    notify?.('Nesne silindi.');
  }

  function duplicateSelected() {
    if (!selected) return;
    const copy = { ...selected, id: `${selected.id}_COPY_${Date.now().toString().slice(-4)}`, label: `${selected.label} Kopya`, x: selected.x + 4, y: selected.y + 4 };
    setObjects((prev) => [...prev, copy]);
    setSelectedId(copy.id);
    notify?.('Nesne kopyalandı.');
  }

  function suggestBestLayout() {
    const corridorIds = ['A','B','C','D','E','F','G','H','I'];
    setObjects((prev) => prev.map((o, idx) => {
      if (corridorIds.includes(o.id)) {
        const n = corridorIds.indexOf(o.id);
        return { ...o, x: 12 + (n % 3) * 38, y: 24 + Math.floor(n / 3) * 23, rotation: 0, utilization: Math.min(94, Math.max(70, o.utilization + 4)), changed: Math.max(3, o.changed - 2) };
      }
      if (o.type === 'chilled_room') return { ...o, x: 108, y: 5 };
      if (o.type === 'frozen_room') return { ...o, x: 108, y: 68 };
      if (o.type === 'dispatch') return { ...o, x: 108, y: 42 };
      if (o.type === 'algida_fridge') return { ...o, x: 8, y: 86 };
      return o;
    }));
    notify?.('AI yerleşim önerisi uygulandı: soğuk/donuk alanlar ayrıldı, dispatch rotası temizlendi.');
  }

  function onCanvasDown(e, o) {
    e.stopPropagation();
    setSelectedId(o.id);
    const rect = e.currentTarget.parentElement.getBoundingClientRect();
    setDrag({ id: o.id, dx: e.clientX - rect.left - (o.x / 100) * rect.width, dy: e.clientY - rect.top - (o.y / 100) * rect.height });
  }
  function onCanvasMove(e) {
    if (!drag) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.max(0, Math.min(96, ((e.clientX - rect.left - drag.dx) / rect.width) * 100));
    const y = Math.max(0, Math.min(96, ((e.clientY - rect.top - drag.dy) / rect.height) * 100));
    setObjects((prev) => prev.map((o) => o.id === drag.id ? { ...o, x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 } : o));
  }

  return (
    <div className="page">
      <div className="architect-shell">
        <aside className="card pad">
          <div className="section-eyebrow">ARCHITECT MODE</div>
          <h2>Layout Architect</h2>
          <p className="muted">Depo mimarisini düzenle. Seçilen obje hem planda hem property panelinde gerçek state'e işlenir.</p>
          <div className="object-catalog">
            {objectCatalog.map((item) => <button className="item" key={item.type} onClick={() => addObject(item)}><b>＋ {item.label}</b><span className="muted">{item.zone}</span></button>)}
          </div>
        </aside>
        <section>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 12, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button className="btn ghost" onClick={() => addObject(objectCatalog[0])}>＋ {tt(lang,'addCorridor')}</button>
              <button className="btn ghost" onClick={() => addObject(objectCatalog[2])}>＋ {tt(lang,'addColumn')}</button>
              <button className="btn ghost" onClick={() => addObject(objectCatalog[4])}>＋ {tt(lang,'addChilled')}</button>
              <button className="btn ghost" onClick={() => addObject(objectCatalog[5])}>＋ {tt(lang,'addFrozen')}</button>
              <button className="btn primary" onClick={suggestBestLayout}>✦ {tt(lang,'suggestLayout')}</button>
            </div>
            <div className="tabs"><button className={`tab ${view==='2d'?'active':''}`} onClick={() => setView('2d')}>2D</button><button className={`tab ${view==='3d'?'active':''}`} onClick={() => setView('3d')}>3D Editor</button></div>
          </div>
          {view === '2d' ? (
            <div className="canvas2d" onPointerMove={onCanvasMove} onPointerUp={() => setDrag(null)} onPointerLeave={() => setDrag(null)}>
              {objects.map((o) => <button key={o.id} className={`layout-object ${o.zone} ${selectedId === o.id ? 'selected' : ''}`} style={objectStyle(o)} onPointerDown={(e) => onCanvasDown(e, o)}><span>{o.label}</span><small>{o.w}m × {o.d}m</small></button>)}
            </div>
          ) : <ThreeEditor objects={objects} selectedId={selectedId} setSelectedId={setSelectedId} />}
        </section>
        <aside className="card pad">
          <div className="section-eyebrow">{tt(lang,'properties')}</div>
          <h2>{selected?.label}</h2>
          {selected && <div className="form-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <div className="field"><label>{tt(lang,'objectType')}</label><input value={selected.type} onChange={(e) => updateSelected('type', e.target.value)} /></div>
            <div className="field"><label>{tt(lang,'zone')}</label><select value={selected.zone} onChange={(e) => updateSelected('zone', e.target.value)}>{['AMBIENT','CHILLED','FROZEN','DISPATCH','INBOUND','STRUCTURE','FACILITY','SAFETY','EQUIPMENT'].map(z=><option key={z}>{z}</option>)}</select></div>
            {['x','y','w','d','h','rotation','modules','shelves'].map((f) => <div className="field" key={f}><label>{f}</label><input type="number" value={selected[f] ?? 0} onChange={(e) => updateSelected(f, e.target.value)} /></div>)}
          </div>}
          <div className="nudge-pad">
            <button className="btn ghost" onClick={() => nudgeSelected(0, -1)}>↑</button>
            <button className="btn ghost" onClick={() => nudgeSelected(-1, 0)}>←</button>
            <button className="btn ghost" onClick={() => nudgeSelected(1, 0)}>→</button>
            <button className="btn ghost" onClick={() => nudgeSelected(0, 1)}>↓</button>
          </div>
          <div className="list" style={{ marginTop: 16 }}>
            <button className="btn primary" onClick={() => notify?.('Layout kaydedildi.')}>{tt(lang,'save')}</button>
            <button className="btn ghost" onClick={duplicateSelected}>{tt(lang,'duplicate')}</button>
            <button className="btn ghost danger" onClick={deleteSelected}>{tt(lang,'delete')}</button>
          </div>
        </aside>
      </div>
    </div>
  );
}
