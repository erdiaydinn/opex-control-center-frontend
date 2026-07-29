import { useMemo, useState } from 'react';
import { tt } from '../i18n/dictionary.js';
import ShelfModal from './ShelfModal.jsx';
import { ProductChip, ProductThumb, storageTone } from './ProductVisuals.jsx';
import { moduleShelfCount, productsForShelf } from '../utils/planogramAllocatorV2.js';

function corridorOptions(objects) {
  return (objects || []).filter((o) => Number(o.modules || 0) > 0 && Number(o.shelves || 0) > 0);
}

export default function ProductPlacementStudio({ lang, objects, products, setProducts, unplacedProducts = [], notify }) {
  const corridors = useMemo(() => corridorOptions(objects), [objects]);
  const [aisle, setAisle] = useState(corridors[0]?.id || 'A');
  const selectedArea = corridors.find((c) => String(c.id) === String(aisle)) || corridors[0];
  const [moduleNo, setModuleNo] = useState(1);
  const [selectedSku, setSelectedSku] = useState(products[0]?.sku);
  const [modalShelf, setModalShelf] = useState(null);
  const selected = products.find((p) => p.sku === selectedSku) || products[0];
  const moduleCount = Math.max(1, Number(selectedArea?.modules || 1));
  const shelfCount = Math.max(1, Math.ceil(Number(selectedArea?.shelves || moduleCount * 5) / moduleCount), moduleShelfCount(products, aisle, moduleNo));

  function updateProduct(sku, patch, show = true) {
    setProducts((prev) => prev.map((p) => p.sku === sku ? { ...p, ...patch } : p));
    if (show) notify?.('Ürün bilgisi güncellendi.');
  }
  function addProduct(product, shelf) {
    updateProduct(product.sku, { aisle: shelf.aisle, aisle_id: shelf.aisle, module: shelf.moduleNo, module_id: shelf.moduleNo, shelf: shelf.shelfNo, shelf_no: shelf.shelfNo });
    notify?.(`${product.name} ${shelf.aisle}.${shelf.moduleNo}.${shelf.shelfNo} rafına atandı.`);
  }
  function aiFacing() {
    if (!selected) return;
    updateProduct(selected.sku, { facing: Math.max(selected.facing, Math.ceil(Number(selected.sales || 0) / 120)), depth: Math.max(selected.depth, Math.ceil(Number(selected.sales || 0) / 180)) });
  }
  function sortProducts(mode) {
    const scope = products.filter((p) => String(p.aisle) === String(aisle) && Number(p.module || 1) === Number(moduleNo));
    const sorted = [...scope].sort((a,b) => mode === 'sales' ? Number(b.sales || 0) - Number(a.sales || 0) : String(a.brand).localeCompare(String(b.brand), 'tr'));
    const updates = new Map(sorted.map((p, idx) => [p.sku, { shelf: Math.floor(idx / 18) + 1, shelf_no: Math.floor(idx / 18) + 1, position: (idx % 18) + 1 }]));
    setProducts((prev) => prev.map((p) => updates.has(p.sku) ? { ...p, ...updates.get(p.sku) } : p));
    notify?.(mode === 'sales' ? 'Seçili modül satışa göre yeniden dizildi.' : 'Seçili modül markaya göre yeniden dizildi.');
  }

  const refill = selected ? (Number(selected.sales || 0) / Math.max(1, Number(selected.facing || 1) * Number(selected.depth || 1) * 72)).toFixed(2) : '0.00';

  return (
    <div className="page">
      <div className="section-eyebrow">ÜRÜN YERLEŞİM STÜDYOSU</div>
      <h1 style={{fontSize:42,margin:'8px 0'}}>Ürün Yerleşimi</h1>
      <p className="page-sub">Görsel raf + teknik grid aynı ekranda. Raflar artık gerçek koridor/modül/raf lokasyonundan beslenir; tek rafa binlerce ürün yığılmaz.</p>
      <div className="grid cols-2" style={{ marginTop: 22 }}>
        <section className="card pad">
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
            <div>
              <div className="section-eyebrow">GÖRSEL RAF</div>
              <h2>{selectedArea?.label || aisle} / Modül {moduleNo}</h2>
              <div className="placement-selectors">
                <select value={aisle} onChange={(e) => { setAisle(e.target.value); setModuleNo(1); }}>
                  {corridors.map((c) => <option key={c.id} value={c.id}>{c.label} · {c.zone}</option>)}
                </select>
                <select value={moduleNo} onChange={(e) => setModuleNo(Number(e.target.value))}>
                  {Array.from({ length: moduleCount }, (_, i) => <option key={i+1} value={i+1}>Modül {i+1}</option>)}
                </select>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button className="btn ghost" onClick={() => sortProducts('sales')}>{tt(lang,'sortSales')}</button>
              <button className="btn ghost" onClick={() => sortProducts('brand')}>{tt(lang,'sortBrand')}</button>
              <button className="btn primary" onClick={aiFacing}>{tt(lang,'aiFacing')}</button>
            </div>
          </div>
          {Array.from({ length: shelfCount }, (_, i) => i + 1).map((s) => {
            const ps = productsForShelf(products, aisle, moduleNo, s).sort((a,b) => Number(a.position || 0) - Number(b.position || 0));
            return <button className="shelf" key={s} onClick={() => setModalShelf({ title: `Koridor ${selectedArea?.label || aisle} / Modül ${moduleNo} / Raf ${s}`, aisle, moduleNo, shelfNo: s, moduleId: `${aisle}.${moduleNo}`, products: ps })} style={{ width: '100%' }}>
              <span className="shelf-label">Raf {s}</span>
              {ps.slice(0, 34).map((p) => <ProductChip product={p} key={p.sku} onClick={(e) => { e.stopPropagation(); setSelectedSku(p.sku); }} />)}
              {ps.length > 34 && <span className="more-chip">+{ps.length - 34}</span>}
              {!ps.length && <span className="muted">Boş raf · ürün atamak için aç</span>}
            </button>;
          })}
        </section>
        <aside className="card pad">
          <div className="section-eyebrow">SEÇİLİ ÜRÜN</div>
          {selected ? <>
            <div style={{ display:'flex', gap:14, alignItems:'center' }}><ProductThumb product={selected} /><div><h2 style={{margin:0}}>{selected.name}</h2><p className="muted" style={{margin:'6px 0 0'}}>{selected.sku} • {selected.brand} • {selected.category} • {selected.storage}</p></div></div>
            <div className="grid cols-3" style={{ marginTop: 16 }}>
              <div className="card kpi"><div className="kpi-label">Satış skoru</div><div className="kpi-value">{selected.sales_label || selected.sales}</div></div>
              <div className="card kpi"><div className="kpi-label">Facing</div><div className="kpi-value pink">{selected.facing}</div></div>
              <div className="card kpi"><div className="kpi-label">Depth</div><div className="kpi-value cyan">{selected.depth}</div></div>
            </div>
            <div className="grid cols-2" style={{ marginTop: 14 }}>
              <button className="btn ghost" onClick={() => updateProduct(selected.sku, { facing: Math.max(1, selected.facing - 1) })}>Facing azalt</button>
              <button className="btn ghost" onClick={() => updateProduct(selected.sku, { facing: selected.facing + 1 })}>Facing artır</button>
              <button className="btn ghost" onClick={() => updateProduct(selected.sku, { depth: Math.max(1, selected.depth - 1) })}>Depth azalt</button>
              <button className="btn primary" onClick={aiFacing}>{tt(lang,'aiFacing')}</button>
            </div>
            <div className="card pad" style={{ marginTop: 16 }}><b>Refill mantığı</b><p className="muted">daily_sales / shelf_capacity = refill_per_day. Bu üründe tahmini refill: <b>{refill}</b> / gün.</p></div>
          </> : <p className="muted">Ürün seçilmedi.</p>}
        </aside>
      </div>
      <section className="card pad" style={{ marginTop: 20 }}>
        <div className="section-eyebrow">TEKNİK GRID</div>
        <div className="muted" style={{ marginBottom: 10 }}>{products.length.toLocaleString('tr-TR')} yerleşen SKU · {unplacedProducts.length.toLocaleString('tr-TR')} atanamayan SKU</div>
        <table className="table"><thead><tr><th>Görsel</th><th>SKU</th><th>Ürün</th><th>Marka</th><th>Lokasyon</th><th>Storage</th><th>Facing</th><th>Depth</th><th>Risk</th></tr></thead><tbody>{products.slice(0, 600).map(p=><tr key={p.sku} onClick={() => setSelectedSku(p.sku)}><td><ProductThumb product={p} small /></td><td>{p.sku}</td><td>{p.name}</td><td>{p.brand}</td><td>{p.aisle}.{p.module}.{p.shelf}</td><td><span className={`badge ${storageTone(p.storage)}`}>{p.storage}</span></td><td>{p.facing}</td><td>{p.depth}</td><td>{p.risk}</td></tr>)}</tbody></table>
      </section>
      <ShelfModal lang={lang} shelf={modalShelf} products={products} onClose={() => setModalShelf(null)} onUpdateProduct={updateProduct} onAddProduct={addProduct} notify={notify} />
    </div>
  );
}
