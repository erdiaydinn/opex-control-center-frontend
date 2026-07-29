import { useMemo, useRef, useState } from 'react';
import { objectCatalog } from '../data/mock.js';
import { tt } from '../i18n/dictionary.js';
import { api } from '../services/api.js';
import './LayoutArchitect.css';

function numeric(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalizedObject(item, index) {
  return {
    ...item,
    id: String(item?.id || `OBJECT_${index + 1}`),
    label: item?.label || item?.name || item?.type || `Object ${index + 1}`,
    type: item?.type || 'structure',
    zone: item?.zone || item?.storage_type || 'STRUCTURE',
    x: numeric(item?.x, 4),
    y: numeric(item?.y, 4),
    w: Math.max(1, numeric(item?.w ?? item?.width, 10)),
    d: Math.max(1, numeric(item?.d ?? item?.depth, 8)),
    h: Math.max(0.2, numeric(item?.h ?? item?.height, 2.5)),
    rotation: numeric(item?.rotation, 0),
    modules: Math.max(0, numeric(item?.modules, 0)),
    shelves: Math.max(0, numeric(item?.shelves, 0)),
  };
}

function bounds(item) {
  return { left: numeric(item.x), right: numeric(item.x) + numeric(item.w), top: numeric(item.y), bottom: numeric(item.y) + numeric(item.d) };
}

function overlaps(a, b) {
  const x = bounds(a);
  const y = bounds(b);
  return x.left < y.right && x.right > y.left && x.top < y.bottom && x.bottom > y.top;
}

function validate(objects) {
  const warnings = [];
  objects.forEach((item) => {
    const b = bounds(item);
    if (b.left < 0 || b.top < 0 || b.right > 100 || b.bottom > 100) warnings.push({ type: 'bounds', id: item.id, message: `${item.label}: depo sınırının dışında.` });
  });
  for (let i = 0; i < objects.length; i += 1) {
    for (let j = i + 1; j < objects.length; j += 1) {
      const a = objects[i];
      const b = objects[j];
      if (overlaps(a, b)) warnings.push({ type: 'collision', id: a.id, otherId: b.id, message: `${a.label} ile ${b.label} çakışıyor.` });
    }
  }
  return warnings;
}

function firstFreePosition(objects, width, depth) {
  for (let y = 3; y <= 90; y += 5) {
    for (let x = 3; x <= 90; x += 5) {
      const candidate = { x, y, w: width, d: depth };
      if (!objects.some((item) => overlaps(candidate, item))) return { x, y };
    }
  }
  return { x: 4, y: 4 };
}

export default function LayoutArchitect({ lang = 'tr', objects = [], setObjects, notify, store = 'AUTO' }) {
  const [selectedId, setSelectedId] = useState(objects[0]?.id || '');
  const [drag, setDrag] = useState(null);
  const [history, setHistory] = useState([]);
  const [future, setFuture] = useState([]);
  const canvasRef = useRef(null);
  const normalized = useMemo(() => objects.map(normalizedObject), [objects]);
  const selected = normalized.find((item) => item.id === selectedId) || normalized[0];
  const warnings = useMemo(() => validate(normalized), [normalized]);

  function commit(next, message = '') {
    const current = normalized;
    setHistory((previous) => [...previous.slice(-29), current]);
    setFuture([]);
    setObjects(next);
    if (message) notify?.(message);
  }

  function updateSelected(field, value) {
    if (!selected) return;
    const nextValue = ['x', 'y', 'w', 'd', 'h', 'rotation', 'modules', 'shelves'].includes(field) ? numeric(value, selected[field]) : value;
    commit(normalized.map((item) => item.id === selected.id ? { ...item, [field]: nextValue } : item));
  }

  function addObject(template) {
    const dims = { w: numeric(template.w ?? template.width, 12), d: numeric(template.d ?? template.depth, 8), h: numeric(template.h ?? template.height, 2.5) };
    const position = firstFreePosition(normalized, dims.w, dims.d);
    const item = normalizedObject({ ...template, ...dims, ...position, id: `${template.type || 'OBJECT'}_${Date.now().toString(36)}`, label: template.label || template.name }, normalized.length);
    commit([...normalized, item], `${item.label} eklendi; ilk boş güvenli alana yerleştirildi.`);
    setSelectedId(item.id);
  }

  function removeSelected() {
    if (!selected) return;
    commit(normalized.filter((item) => item.id !== selected.id), `${selected.label} silindi.`);
    setSelectedId(normalized.find((item) => item.id !== selected.id)?.id || '');
  }

  function undo() {
    const previous = history[history.length - 1];
    if (!previous) return;
    setHistory((items) => items.slice(0, -1));
    setFuture((items) => [normalized, ...items]);
    setObjects(previous);
  }

  function redo() {
    const next = future[0];
    if (!next) return;
    setFuture((items) => items.slice(1));
    setHistory((items) => [...items, normalized]);
    setObjects(next);
  }

  function onPointerDown(event, item) {
    event.stopPropagation();
    setSelectedId(item.id);
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    setDrag({ id: item.id, offsetX: event.clientX - rect.left - (item.x / 100) * rect.width, offsetY: event.clientY - rect.top - (item.y / 100) * rect.height });
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function onPointerMove(event) {
    if (!drag || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const item = normalized.find((entry) => entry.id === drag.id);
    if (!item) return;
    const x = Math.max(0, Math.min(100 - item.w, ((event.clientX - rect.left - drag.offsetX) / rect.width) * 100));
    const y = Math.max(0, Math.min(100 - item.d, ((event.clientY - rect.top - drag.offsetY) / rect.height) * 100));
    setObjects(normalized.map((entry) => entry.id === item.id ? { ...entry, x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 } : entry));
  }

  function onPointerUp() {
    if (!drag) return;
    const next = (canvasRef.current ? Array.from(canvasRef.current.querySelectorAll('[data-layout-id]')) : []);
    setDrag(null);
    // Dragging is committed once, so undo/redo stays meaningful.
    setHistory((previous) => [...previous.slice(-29), normalized]);
    setFuture([]);
    if (next.length) notify?.('Konum güncellendi; çakışma kontrolü yeniden hesaplandı.');
  }

  async function save() {
    if (warnings.length) {
      notify?.(`Kaydetme durduruldu: ${warnings.length} mimari çakışma/sınır uyarısı var.`);
      return;
    }
    try {
      await api.saveLayout(store, { objects: normalized, validation: { valid: true, warnings: [] } }, 'Layout Architect validated save');
    } catch (error) {
      notify?.(`Layout API kaydı başarısız: ${error?.message || error}`);
      return;
    }
    notify?.('Layout kaydedildi: 2D/3D aynı doğrulanmış yerleşimi kullanacak.');
  }

  return (
    <div className="page layout-architect-page">
      <header className="layout-architect-header">
        <div><div className="section-eyebrow">LAYOUT ARCHITECT · FOUNDATION</div><h1>Depo mimarisi</h1><p className="page-sub">Ölçekli 2D düzenleyici. Her taşıma ölçü, sınır ve çakışma doğrulamasından geçer.</p></div>
        <div className="layout-architect-actions"><button className="btn ghost" onClick={undo} disabled={!history.length}>Geri al</button><button className="btn ghost" onClick={redo} disabled={!future.length}>İleri al</button><button className="btn primary" onClick={save}>Doğrula ve kaydet</button></div>
      </header>
      <div className="layout-architect-grid">
        <aside className="card pad layout-catalog"><div className="section-eyebrow">EKİPMAN</div><div className="layout-catalog-list">{objectCatalog.map((item) => <button className="layout-catalog-item" key={item.type} onClick={() => addObject(item)}><strong>＋ {item.label}</strong><span>{item.zone || item.type}</span></button>)}</div></aside>
        <section className="card pad layout-canvas-card">
          <div className="layout-canvas-toolbar"><span><b>{normalized.length}</b> nesne</span><span className={warnings.length ? 'layout-warning-count' : 'layout-valid-count'}>{warnings.length ? `${warnings.length} uyarı` : 'Çakışma yok'}</span><span className="muted">Izgara 1 kare = 1% depo genişliği</span></div>
          <div ref={canvasRef} className="layout-canvas" onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerLeave={onPointerUp}>
            <div className="layout-axis axis-x">0% ───────── 50% ───────── 100%</div><div className="layout-axis axis-y">0%<br/><br/>50%<br/><br/>100%</div>
            {normalized.map((item) => {
              const itemWarnings = warnings.filter((warning) => warning.id === item.id || warning.otherId === item.id);
              return <button type="button" key={item.id} data-layout-id={item.id} className={`layout-canvas-object ${itemWarnings.length ? 'has-warning' : ''} ${selected?.id === item.id ? 'is-selected' : ''}`} style={{ left: `${item.x}%`, top: `${item.y}%`, width: `${item.w}%`, height: `${item.d}%`, transform: `rotate(${item.rotation || 0}deg)` }} onPointerDown={(event) => onPointerDown(event, item)}><strong>{item.label}</strong><small>{item.w} × {item.d} · {item.zone}</small></button>;
            })}
            {!normalized.length && <div className="layout-empty">Soldan bir fixture ekleyin veya Store DNA yükleyin.</div>}
          </div>
        </section>
        <aside className="card pad layout-properties"><div className="section-eyebrow">SEÇİLİ NESNE</div>{selected ? <><h2>{selected.label}</h2><p className="muted">{selected.id} · {selected.zone}</p><div className="layout-property-grid">{[['x','X %'],['y','Y %'],['w','Genişlik %'],['d','Derinlik %'],['h','Yükseklik m'],['rotation','Dönüş °'],['modules','Modül'],['shelves','Raf']].map(([field, label]) => <label key={field}>{label}<input type="number" step="0.1" value={selected[field] ?? 0} onChange={(event) => updateSelected(field, event.target.value)} /></label>)}</div><label className="layout-property-wide">Etiket<input value={selected.label} onChange={(event) => updateSelected('label', event.target.value)} /></label><button className="btn danger layout-delete" onClick={removeSelected}>Seçili nesneyi kaldır</button><div className="layout-validation-list">{warnings.filter((warning) => warning.id === selected.id || warning.otherId === selected.id).map((warning) => <div key={`${warning.type}-${warning.id}-${warning.otherId}`}>{warning.message}</div>)}</div></> : <div className="layout-empty">Bir nesne seçin.</div>}</aside>
      </div>
    </div>
  );
}

