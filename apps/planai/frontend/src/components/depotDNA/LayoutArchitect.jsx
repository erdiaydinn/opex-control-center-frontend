import { useMemo, useState } from 'react';
import { initialObjects } from '../data/mock.js';
import { tt } from '../i18n/dictionary.js';

function objStyle(o) {
  return {
    left: `${o.x}%`, top: `${o.y}%`, width: `${o.w}%`, height: `${o.d}%`, transform: `rotate(${o.rotation || 0}deg)`
  };
}

export default function LayoutArchitect({ lang, objects, setObjects }) {
  const [selectedId, setSelectedId] = useState(objects[0]?.id || 'A');
  const selected = useMemo(() => objects.find((o) => o.id === selectedId) || objects[0], [objects, selectedId]);
  const t = (k) => tt(lang, k);
  const addObject = (type, zone = 'AMBIENT') => {
    const id = `${type.toUpperCase().slice(0, 3)}-${objects.length + 1}`;
    const next = { id, type, label: type === 'corridor' ? `K${objects.length}` : type.toUpperCase(), x: 12 + objects.length * 2, y: 10 + objects.length * 3, w: type === 'column' ? 2 : 18, d: type === 'column' ? 2 : 8, h: 2.5, rotation: 0, zone, modules: type === 'corridor' ? 4 : 0 };
    setObjects([...objects, next]);
    setSelectedId(id);
  };
  const update = (patch) => setObjects(objects.map((o) => o.id === selected.id ? { ...o, ...patch } : o));
  const deleteSelected = () => {
    const next = objects.filter((o) => o.id !== selected.id);
    setObjects(next.length ? next : initialObjects);
    setSelectedId((next[0] || initialObjects[0]).id);
  };
  const suggest = () => {
    const corridors = objects.filter((o) => o.type === 'corridor').map((o, i) => ({ ...o, x: 10 + (i % 3) * 36, y: 20 + Math.floor(i / 3) * 23, rotation: 0 }));
    const rest = objects.filter((o) => o.type !== 'corridor').map((o) => {
      if (o.zone === 'CHILLED') return { ...o, x: 108, y: 5 };
      if (o.zone === 'FROZEN') return { ...o, x: 108, y: 66 };
      if (o.zone === 'DISPATCH') return { ...o, x: 110, y: 40 };
      return o;
    });
    setObjects([...corridors, ...rest]);
  };
  return (
    <div className="page">
      <div className="architect">
        <aside className="card pad catalog">
          <div className="section-eyebrow">ARCHITECT MODE</div>
          <h2>Layout Architect</h2>
          <p className="muted">Depo mimarisini düzenle. Seçilen obje hem planda hem property panelinde gerçek state’e işlenir.</p>
          <div className="list" style={{ marginTop: 20 }}>
            {['Wall Panel', 'Round Column', 'Dispatch', 'Chilled Room', 'Frozen Room', 'Algida Fridge', 'Horizontal Fridge'].map((x) => <div className="item" key={x}><b>{x}</b><span className="muted">⋮</span></div>)}
          </div>
        </aside>
        <section className="canvas-wrap">
          <div className="tools">
            <button className="btn ghost" onClick={() => addObject('corridor')}>＋ {t('addCorridor')}</button>
            <button className="btn ghost" onClick={() => addObject('column')}>＋ {t('addColumn')}</button>
            <button className="btn ghost" onClick={() => addObject('room', 'CHILLED')}>＋ {t('addChilled')}</button>
            <button className="btn ghost" onClick={() => addObject('room', 'FROZEN')}>＋ {t('addFrozen')}</button>
            <button className="btn primary" onClick={suggest}>✦ {t('suggest')}</button>
          </div>
          <div className="layout-canvas">
            {objects.map((o) => <button key={o.id} className={`layout-object ${o.zone} ${selected?.id === o.id ? 'selected' : ''}`} style={objStyle(o)} onClick={() => setSelectedId(o.id)}><span>{o.label}<br/><small>{o.w.toFixed(1)}m × {o.d.toFixed(1)}m</small></span></button>)}
          </div>
        </section>
        <aside className="card pad properties">
          <div className="section-eyebrow">PROPERTIES</div>
          <h2>{selected?.label}</h2>
          {selected && <>
            <div className="form-grid">
              <div className="field"><label>{t('objectType')}</label><input value={selected.type} onChange={(e) => update({ type: e.target.value })}/></div>
              <div className="field"><label>{t('zone')}</label><select value={selected.zone} onChange={(e) => update({ zone: e.target.value })}><option>AMBIENT</option><option>CHILLED</option><option>FROZEN</option><option>DISPATCH</option><option>RECEIVING</option></select></div>
              <div className="field"><label>X</label><input type="number" value={selected.x} onChange={(e) => update({ x: Number(e.target.value) })}/></div>
              <div className="field"><label>Y</label><input type="number" value={selected.y} onChange={(e) => update({ y: Number(e.target.value) })}/></div>
              <div className="field"><label>{t('width')} m</label><input type="number" value={selected.w} onChange={(e) => update({ w: Number(e.target.value) })}/></div>
              <div className="field"><label>{t('depth')} m</label><input type="number" value={selected.d} onChange={(e) => update({ d: Number(e.target.value) })}/></div>
              <div className="field"><label>{t('height')} m</label><input type="number" value={selected.h} onChange={(e) => update({ h: Number(e.target.value) })}/></div>
              <div className="field"><label>{t('rotation')}</label><input type="number" value={selected.rotation} onChange={(e) => update({ rotation: Number(e.target.value) })}/></div>
              <div className="field"><label>Modül</label><input type="number" value={selected.modules || 0} onChange={(e) => update({ modules: Number(e.target.value) })}/></div>
            </div>
            <div style={{ display: 'grid', gap: 10, marginTop: 20 }}>
              <button className="btn primary">{t('save')}</button>
              <button className="btn ghost" onClick={() => { const id = `${selected.id}-COPY`; setObjects([...objects, { ...selected, id, x: selected.x + 3, y: selected.y + 3 }]); setSelectedId(id); }}>{t('duplicate')}</button>
              <button className="btn ghost red" onClick={deleteSelected}>{t('delete')}</button>
            </div>
          </>}
        </aside>
      </div>
    </div>
  );
}
