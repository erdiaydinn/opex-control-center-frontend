import { useState } from 'react';
import { tt } from '../i18n/dictionary.js';
import ShelfModal from './ShelfModal.jsx';
import { ProductChip, ProductThumb, storageTone } from './ProductVisuals.jsx';

function buildShelves(products) {
  return [1,2,3,4,5].map((s) => ({ shelfNo: `Shelf ${s}`, products: products.filter((_, i) => (i + s) % 5 < 2) }));
}

export default function ProductPlacementStudio({ lang, products, setProducts, notify }) {
  const [selectedSku, setSelectedSku] = useState(products[1]?.sku);
  const [modalShelf, setModalShelf] = useState(null);
  const selected = products.find((p) => p.sku === selectedSku) || products[0];
  const shelves = buildShelves(products);
  function updateProduct(sku, patch, show = true) {
    setProducts((prev) => prev.map((p) => p.sku === sku ? { ...p, ...patch } : p));
    if (show) notify?.('Ürün bilgisi güncellendi.');
  }
  function addProduct(product, shelf) {
    updateProduct(product.sku, { aisle: 'A', module: 1, shelf: Number(String(shelf.shelfNo).replace(/\D/g,'')) || 1 });
    notify?.(`${product.name} rafa atandı.`);
  }
  function aiFacing() {
    updateProduct(selected.sku, { facing: Math.max(selected.facing, Math.ceil(selected.sales / 50)), depth: Math.max(selected.depth, Math.ceil(selected.sales / 70)) });
  }
  function sortProducts(mode) {
    setProducts((prev) => [...prev].sort((a,b) => mode === 'sales' ? b.sales - a.sales : String(a.brand).localeCompare(String(b.brand))));
    notify?.(mode === 'sales' ? 'Ürünler satışa göre dizildi.' : 'Ürünler markaya göre dizildi.');
  }
  const refill = (selected.sales / Math.max(1, selected.facing * selected.depth * 72)).toFixed(2);
  return (
    <div className="page">
      <div className="section-eyebrow">ÜRÜN YERLEŞİM STÜDYOSU</div>
      <h1 style={{fontSize:42,margin:'8px 0'}}>Ürün Yerleşimi</h1>
      <p className="page-sub">Görsel raf + teknik grid aynı ekranda. Facing, depth, refill riski ve ürün görselleri aktif çalışır.</p>
      <div className="grid cols-2" style={{ marginTop: 22 }}>
        <section className="card pad">
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
            <div><div className="section-eyebrow">GÖRSEL RAF</div><h2>Module A.1</h2><div className="placement-selectors"><select defaultValue="A"><option>A Koridoru</option><option>B Koridoru</option><option>+4 Soğuk Oda</option><option>-18 Donuk Oda</option></select><select defaultValue="1"><option>Modül 1</option><option>Modül 2</option><option>Modül 3</option></select><select defaultValue="2"><option>Raf 1</option><option>Raf 2</option><option>Raf 3</option><option>Raf 4</option></select></div></div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}><button className="btn ghost" onClick={() => sortProducts('sales')}>{tt(lang,'sortSales')}</button><button className="btn ghost" onClick={() => sortProducts('brand')}>{tt(lang,'sortBrand')}</button><button className="btn primary" onClick={aiFacing}>{tt(lang,'aiFacing')}</button></div>
          </div>
          {shelves.map((s) => <button className="shelf" key={s.shelfNo} onClick={() => setModalShelf({ title: `Module A.1 / ${s.shelfNo}`, moduleId: 'A.1', shelfNo: s.shelfNo, products: s.products })} style={{ width: '100%' }}>
            <span className="shelf-label">{s.shelfNo}</span>{s.products.map((p) => <ProductChip product={p} key={p.sku} onClick={(e) => { e.stopPropagation(); setSelectedSku(p.sku); }} />)}
          </button>)}
        </section>
        <aside className="card pad">
          <div className="section-eyebrow">SEÇİLİ ÜRÜN</div>
          <h2>{selected.name}</h2>
          <p className="muted">{selected.sku} • {selected.brand} • {selected.category} • {selected.storage}</p>
          <div className="grid cols-3">
            <div className="card kpi"><div className="kpi-label">Günlük satış</div><div className="kpi-value">{selected.sales}</div></div>
            <div className="card kpi"><div className="kpi-label">Facing</div><div className="kpi-value pink">{selected.facing}</div></div>
            <div className="card kpi"><div className="kpi-label">Depth</div><div className="kpi-value cyan">{selected.depth}</div></div>
          </div>
          <div className="grid cols-2" style={{ marginTop: 14 }}>
            <button className="btn ghost" onClick={() => updateProduct(selected.sku, { facing: Math.max(1, selected.facing - 1) })}>Facing azalt</button>
            <button className="btn ghost" onClick={() => updateProduct(selected.sku, { facing: selected.facing + 1 })}>Facing artır</button>
            <button className="btn ghost" onClick={() => updateProduct(selected.sku, { depth: selected.depth + 1 })}>Depth artır</button>
            <button className="btn primary" onClick={aiFacing}>{tt(lang,'aiFacing')}</button>
          </div>
          <div className="card pad" style={{ marginTop: 16 }}><b>Refill mantığı</b><p className="muted">daily_sales / shelf_capacity = refill_per_day. Bu üründe tahmini refill: <b>{refill}</b> / gün.</p></div>
        </aside>
      </div>
      <section className="card pad" style={{ marginTop: 20 }}>
        <div className="section-eyebrow">TEKNİK GRID</div>
        <table className="table"><thead><tr><th>Görsel</th><th>SKU</th><th>Ürün</th><th>Marka</th><th>Storage</th><th>Facing</th><th>Depth</th><th>Risk</th></tr></thead><tbody>{products.map(p=><tr key={p.sku} onClick={() => setSelectedSku(p.sku)}><td><ProductThumb product={p} small /></td><td>{p.sku}</td><td>{p.name}</td><td>{p.brand}</td><td><span className={`badge ${storageTone(p.storage)}`}>{p.storage}</span></td><td>{p.facing}</td><td>{p.depth}</td><td>{p.risk}</td></tr>)}</tbody></table>
      </section>
      <ShelfModal lang={lang} shelf={modalShelf} products={products} onClose={() => setModalShelf(null)} onUpdateProduct={updateProduct} onAddProduct={addProduct} notify={notify} />
    </div>
  );
}
