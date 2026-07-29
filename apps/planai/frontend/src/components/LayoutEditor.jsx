import { useMemo, useState } from 'react';
import './LayoutEditor.css';

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function layoutObjects(plan) {
  if (Array.isArray(plan?.layout_objects) && plan.layout_objects.length) return plan.layout_objects;
  return (plan?.aisles || []).map((aisle, index) => ({
    id: String(aisle.aisle_id || `A${index + 1}`), label: String(aisle.aisle_id || `A${index + 1}`), type: 'corridor', zone: aisle.zone || 'AMBIENT',
    x: 8 + (index % 3) * 34, y: 12 + Math.floor(index / 3) * 22, w: 28, d: 9, h: 2.5,
  }));
}

function validate(objects) {
  const warnings = [];
  objects.forEach((object) => {
    if (object.x < 0 || object.y < 0 || object.x + object.w > 100 || object.y + object.d > 100) warnings.push(`${object.label}: depo sınırının dışında.`);
  });
  for (let i = 0; i < objects.length; i += 1) for (let j = i + 1; j < objects.length; j += 1) {
    const a = objects[i]; const b = objects[j];
    if (a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.d && a.y + a.d > b.y) warnings.push(`${a.label} / ${b.label}: çakışma.`);
  }
  return warnings;
}

export default function LayoutEditor({ open, plan, onClose, onSave, lang = 'tr' }) {
  const initial = useMemo(() => layoutObjects(plan).map((item) => ({ ...item })), [plan]);
  const [objects, setObjects] = useState(initial);
  const [selectedId, setSelectedId] = useState(initial[0]?.id || '');
  if (!open) return null;
  const selected = objects.find((object) => object.id === selectedId);
  const warnings = validate(objects);
  function update(field, value) {
    setObjects((items) => items.map((item) => item.id === selectedId ? { ...item, [field]: number(value, item[field]) } : item));
  }
  function save() {
    if (warnings.length) return;
    const aisles = objects.filter((item) => item.type === 'corridor').map((item) => ({ aisle_id: item.id, grid_x: item.x, grid_y: item.y, rotation: item.rotation || 0 }));
    onSave?.({ objects, aisles, validation: { valid: true, warnings: [] } });
    onClose?.();
  }
  return <div className="layout-editor-overlay"><div className="layout-editor-modal"><header><div><div className="section-eyebrow">VALIDATED EDITOR</div><h2>Layout düzenle</h2></div><button className="btn ghost" onClick={onClose}>Kapat</button></header><div className="layout-editor-content"><div className="layout-editor-list">{objects.map((object) => <button className={object.id === selectedId ? 'active' : ''} key={object.id} onClick={() => setSelectedId(object.id)}><strong>{object.label}</strong><small>{object.zone}</small></button>)}</div>{selected ? <div className="layout-editor-form"><h3>{selected.label}</h3>{[['x','X %'],['y','Y %'],['w','Genişlik %'],['d','Derinlik %'],['rotation','Dönüş °']].map(([field, label]) => <label key={field}>{label}<input type="number" value={selected[field] || 0} onChange={(event) => update(field, event.target.value)} /></label>)}{warnings.length > 0 && <div className="layout-editor-warnings">{warnings.map((warning) => <div key={warning}>{warning}</div>)}</div>}</div> : <div className="muted">Bir obje seçin.</div>}</div><footer><span className={warnings.length ? 'layout-editor-invalid' : 'layout-editor-valid'}>{warnings.length ? `${warnings.length} uyarı` : 'Geçerli layout'}</span><button className="btn primary" disabled={warnings.length > 0} onClick={save}>Doğrula ve kaydet</button></footer></div></div>;
}
