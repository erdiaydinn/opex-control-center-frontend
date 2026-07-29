import { useMemo, useRef, useState } from 'react';
import { insights } from '../data/mock.js';
import { tt } from '../i18n/dictionary.js';
import { ProductThumb, storageTone } from './ProductVisuals.jsx';
import ShelfModal from './ShelfModal.jsx';
import TwinStudio3D from './Live3D/TwinStudio3D.jsx';

function cameraLabel(lang, c) {
  if (c === 'top') return tt(lang,'topView');
  if (c === 'chilled') return tt(lang,'chilled');
  if (c === 'frozen') return tt(lang,'frozen');
  if (c === 'dispatch') return tt(lang,'dispatch');
  return tt(lang,'overview');
}

function metricLabel(metric) {
  if (metric === 'modules') return 'Modül sayısı';
  if (metric === 'shelves') return 'Raf sayısı';
  if (metric === 'changed') return 'Yeri değişecek ürün';
  return 'Doluluk';
}

function shelfFromSelection(area, products, module = 1, shelf = 1) {
  if (!area) return null;
  const byExact = products.filter((p) => String(p.aisle) === String(area.id) && Number(p.module || 1) === Number(module) && Number(p.shelf || 1) === Number(shelf));
  const byArea = products.filter((p) => String(p.aisle) === String(area.id));
  const byStorage = products.filter((p) => String(p.storage) === String(area.zone));
  const shelfProducts = (byExact.length ? byExact : byArea.length ? byArea : byStorage).slice(0, 8);
  return {
    areaId: area.id,
    title: `${area.label} / Module ${module} / Shelf ${shelf}`,
    moduleId: `Module ${module}`,
    shelfNo: `Shelf ${shelf}`,
    products: shelfProducts,
  };
}

export default function Live3D({ lang, objects, setObjects, products, setProducts, setActive, notify }) {
  const [camera, setCamera] = useState('overview');
  const [heatmap, setHeatmap] = useState('sales');
  const [selected, setSelected] = useState(products[2]);
  const [selectedAreaId, setSelectedAreaId] = useState('A');
  const [selectedProductSku, setSelectedProductSku] = useState(products[2]?.sku || '');
  const [metric, setMetric] = useState('utilization');
  const [isFull, setIsFull] = useState(false);
  const [shelfModal, setShelfModal] = useState(null);
  const stageRef = useRef(null);

  const selectableObjects = useMemo(() => objects.filter((o) => !String(o.id).startsWith('COL_')), [objects]);
  const selectedArea = objects.find(o => o.id === selectedAreaId) || objects.find(o => o.id === 'A') || objects[0];

  function focusProduct(p) {
    setSelected(p);
    setSelectedProductSku(p.sku);
    setSelectedAreaId(p.aisle || selectedAreaId);
    if (p.storage === 'CHILLED') setCamera('chilled');
    else if (p.storage === 'FROZEN') setCamera('frozen');
    else setCamera('overview');
  }

  function selectArea(area, shelfMeta = {}) {
    setSelectedAreaId(area.id);
    setSelectedProductSku('');
    setSelected({ name: area.label, sku: area.id, brand: area.type, storage: area.zone, facing: area.modules, depth: area.shelves });
    if (area.zone === 'CHILLED') setCamera('chilled');
    else if (area.zone === 'FROZEN') setCamera('frozen');
    else if (area.zone === 'DISPATCH') setCamera('dispatch');
    if (area.isRack || area.type === 'corridor' || area.type === 'steel_rack' || area.type === 'rack_module') {
      setShelfModal(shelfFromSelection(area, products, shelfMeta.module || 1, shelfMeta.shelf || 1));
    }
  }

  function chooseCamera(c) {
    setCamera(c);
    setSelectedProductSku('');
  }

  function toggleFullscreen() {
    if (!document.fullscreenElement && stageRef.current?.requestFullscreen) {
      stageRef.current.requestFullscreen().then(() => setIsFull(true)).catch(() => setIsFull(v => !v));
    } else if (document.fullscreenElement && document.exitFullscreen) {
      document.exitFullscreen().then(() => setIsFull(false)).catch(() => setIsFull(v => !v));
    } else setIsFull((v) => !v);
  }

  function updateArea(delta) {
    setObjects((prev) => prev.map(o => {
      if (o.id !== selectedAreaId) return o;
      const key = metric === 'modules' ? 'modules' : metric === 'shelves' ? 'shelves' : metric === 'changed' ? 'changed' : 'utilization';
      const step = key === 'utilization' ? delta * 2 : delta;
      const max = key === 'utilization' ? 100 : 999;
      return { ...o, [key]: Math.max(0, Math.min(max, Number(o[key] || 0) + step)) };
    }));
    notify?.(`${selectedArea?.label || selectedAreaId}: ${metricLabel(metric)} güncellendi.`);
  }

  function onUpdateProduct(sku, patch, showToast = true) {
    setProducts((prev) => prev.map((p) => String(p.sku) === String(sku) ? { ...p, ...patch } : p));
    setShelfModal((prev) => prev ? { ...prev, products: prev.products.map((p) => String(p.sku) === String(sku) ? { ...p, ...patch } : p) } : prev);
    if (showToast) notify?.(`${sku} güncellendi.`);
  }

  function onAddProduct(product, shelf) {
    const areaId = shelf?.areaId || selectedAreaId;
    const next = { ...product, aisle: areaId, module: Number(String(shelf?.moduleId || '1').replace(/\D/g, '')) || 1, shelf: Number(String(shelf?.shelfNo || '1').replace(/\D/g, '')) || 1 };
    setProducts((prev) => prev.map((p) => String(p.sku) === String(product.sku) ? next : p));
    setShelfModal((prev) => prev ? { ...prev, products: [...prev.products.filter((p) => p.sku !== next.sku), next] } : prev);
    notify?.(`${product.name} ${selectedArea?.label || areaId} alanına atandı.`);
  }

  const currentMetricValue = selectedArea?.[metric === 'modules' ? 'modules' : metric === 'shelves' ? 'shelves' : metric === 'changed' ? 'changed' : 'utilization'] ?? 0;

  return (
    <div className="page">
      <div className="section-eyebrow">TWIN STUDIO ENGINE v1</div>
      <h1 style={{ fontSize: 44, margin: '8px 0 4px' }}>{tt(lang, 'liveTitle')}</h1>
      <p className="page-sub">Gerçek WebGL dijital ikiz: raf, oda, rota, ürün, uyarı ve kamera kontrolleri tek sahnede.</p>
      <div className="live-layout" style={{ marginTop: 20 }}>
        <div ref={stageRef} className={`live-stage-wrap ${isFull ? 'is-fullscreen' : ''}`}>
          <div className="stage three-stage">
            <div className="stage-toolbar stage-toolbar-clean">
              <div className="pill"><b>Doluluk</b> <span style={{ fontSize: 28 }}>87%</span></div>
              <div className="pill subtle">Kamera sağ panelden yönetilir</div>
              <button className="btn ghost" onClick={toggleFullscreen}>{isFull ? tt(lang,'exitFullscreen') : tt(lang,'fullscreen')}</button>
            </div>
            <TwinStudio3D
              objects={objects}
              products={products.slice(0, 1200)}
              cameraPreset={camera}
              heatmap={heatmap}
              selectedAreaId={selectedAreaId}
              selectedProductSku={selectedProductSku}
              onSelectArea={selectArea}
              onSelectProduct={focusProduct}
            />
            <div className="stage-bottom">
              {['sales','refill','cold','traffic','facilities'].map((m) => <button key={m} className={`btn small ${heatmap === m ? 'primary' : 'ghost'}`} onClick={() => setHeatmap(m)}>{m === 'sales' ? 'Satış' : m === 'refill' ? 'Refill' : m === 'cold' ? 'Soğuk' : m === 'traffic' ? 'Trafik' : 'Tesisler'}</button>)}
              <span className="muted">Sol sürükle: döndür · sağ sürükle: pan · wheel: zoom · W/A/S/D: kaydır</span>
            </div>
          </div>
        </div>
        <aside className="side-panel">
          <div className="card pad camera-panel-fixed">
            <div className="section-eyebrow">{tt(lang,'camera')}</div>
            <div className="field"><label>Kamera preset</label><select value={camera} onChange={(e) => chooseCamera(e.target.value)}>{['overview','top','chilled','frozen','dispatch'].map((c) => <option key={c} value={c}>{cameraLabel(lang,c)}</option>)}</select></div>
            <div className="camera-preset-list">
              {['overview','top','chilled','frozen','dispatch'].map((c) => <button key={c} className={camera === c ? 'active' : ''} onClick={() => chooseCamera(c)}>{cameraLabel(lang,c)}</button>)}
            </div>
            <p className="muted small-note">Dropdown seçimi kamerayı doğrudan ilgili zone'a uçurur; SKU aramada ürün ayrıca highlight edilir.</p>
          </div>
          <div className="card pad">
            <div className="section-eyebrow">ALAN KONTROLÜ</div>
            <div className="field"><label>Seçili alan</label><select value={selectedAreaId} onChange={(e)=>{ const area = objects.find(o => o.id === e.target.value); if (area) selectArea(area); }}>{selectableObjects.map(o=><option key={o.id} value={o.id}>{o.label} · {o.zone}</option>)}</select></div>
            <div className="field"><label>Değiştirilecek metrik</label><select value={metric} onChange={(e)=>setMetric(e.target.value)}><option value="utilization">Doluluk</option><option value="modules">Modül sayısı</option><option value="shelves">Raf sayısı</option><option value="changed">Yeri değişecek ürün</option></select></div>
            <div className="adjust-box"><button className="btn ghost" onClick={()=>updateArea(-1)}>− Azalt</button><b>{currentMetricValue}</b><button className="btn ghost" onClick={()=>updateArea(1)}>＋ Artır</button></div>
            <button className="btn primary" style={{ width: '100%', marginTop: 12 }} onClick={() => setShelfModal(shelfFromSelection(selectedArea, products, 1, 1))}>Seçili rafı aç</button>
          </div>
          <div className="card pad"><div className="section-eyebrow">{tt(lang,'skuSearch')}</div><input className="search" placeholder="Eti Burçak, Algida, SKU..." onChange={(e) => { const q = e.target.value.toLowerCase(); const p = products.find(x => `${x.name} ${x.sku} ${x.brand}`.toLowerCase().includes(q)); if (q && p) focusProduct(p); }} /><div className="list" style={{ marginTop: 12 }}>{products.slice(0,5).map((p) => <button className="product-hit" key={p.sku} onClick={() => focusProduct(p)}><ProductThumb product={p} small /><div><b>{p.sku}</b><br/><span className="muted">{p.name}</span></div><span className={`badge ${storageTone(p.storage)}`}>{p.storage}</span></button>)}</div></div>
          <div className="card pad"><div className="section-eyebrow">{tt(lang,'selected')}</div><h3>{selected?.name || selectedArea?.label || '—'}</h3><p className="muted">{selected?.brand} • {selected?.storage} • Facing {selected?.facing}</p><span className="badge pink">WebGL kamera odak aktif</span></div>
          <div className="card pad"><div className="section-eyebrow">{tt(lang,'insights')}</div><div className="list">{insights.slice(0,3).map((i)=><div className="item" key={i.title}><b>{i.title}</b><span className={`badge ${i.tone}`}>{i.impact}</span></div>)}</div><button className="btn ghost" style={{ marginTop: 12 }} onClick={() => setActive('reports')}>Tümünü gör</button></div>
        </aside>
      </div>
      <ShelfModal lang={lang} shelf={shelfModal} products={products} onClose={() => setShelfModal(null)} onUpdateProduct={onUpdateProduct} onAddProduct={onAddProduct} notify={notify} />
    </div>
  );
}
