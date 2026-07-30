import { tt } from '../i18n/dictionary.js';
import { ProductThumb, storageTone } from './ProductVisuals.jsx';

function escapeHtml(v) {
  return String(v ?? '').replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
}

function groupedByShelf(products, aisle, moduleNo) {
  const filtered = (products || []).filter((p) => String(p.aisle) === String(aisle) && Number(p.module || 1) === Number(moduleNo));
  const map = new Map();
  filtered.forEach((p) => {
    const key = Number(p.shelf || 1);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(p);
  });
  return [...map.entries()].sort((a,b)=>a[0]-b[0]).map(([s, ps]) => [s, ps.sort((a,b)=>Number(a.position||0)-Number(b.position||0))]);
}

function groupedByModule(products, aisle) {
  const filtered = (products || []).filter((p) => String(p.aisle) === String(aisle));
  const map = new Map();
  filtered.forEach((p) => {
    const key = Number(p.module || 1);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(p);
  });
  return [...map.entries()].sort((a,b)=>a[0]-b[0]);
}

function printDocument({ title, subtitle, groups }) {
  const visual = groups.map((g) => `
    <section class="print-section">
      <h2>${escapeHtml(g.title)}</h2>
      <div class="visual-row">${g.products.map((p) => `<div class="mini-prod"><span>${escapeHtml((p.brand || p.name || '?').slice(0,2))}</span><small>${escapeHtml(p.facing || 1)}F</small></div>`).join('')}</div>
      <table><thead><tr><th>SKU</th><th>Ürün</th><th>Marka</th><th>Storage</th><th>Facing</th><th>Depth</th><th>Lokasyon</th></tr></thead><tbody>${g.products.map(p=>`<tr><td>${escapeHtml(p.sku)}</td><td>${escapeHtml(p.name)}</td><td>${escapeHtml(p.brand)}</td><td>${escapeHtml(p.storage)}</td><td>${escapeHtml(p.facing)}</td><td>${escapeHtml(p.depth)}</td><td>${escapeHtml(`${p.aisle}.${p.module}.${p.shelf}`)}</td></tr>`).join('')}</tbody></table>
    </section>`).join('');
  const html = `<html><head><title>${escapeHtml(title)}</title><style>
    body{font-family:Arial,Helvetica,sans-serif;padding:24px;color:#10131a} h1{margin:0 0 6px;font-size:30px} h2{font-size:18px;margin:22px 0 10px}.sub{color:#657085;margin-bottom:20px}.print-section{page-break-inside:avoid;margin-bottom:24px}.visual-row{display:flex;gap:6px;flex-wrap:wrap;border:1px solid #ddd;border-radius:14px;padding:12px;margin-bottom:10px}.mini-prod{width:34px;height:46px;border-radius:8px;background:#df1067;color:#fff;display:grid;place-items:center;font-weight:800}.mini-prod small{font-size:9px} table{width:100%;border-collapse:collapse;margin-top:8px;font-size:12px}td,th{border:1px solid #ddd;padding:7px;text-align:left}th{background:#f7f4ef}@media print{body{padding:12px}.pagebreak{page-break-before:always}}
  </style></head><body><h1>${escapeHtml(title)}</h1><div class="sub">${escapeHtml(subtitle)}</div>${visual}</body></html>`;
  const w = window.open('', '_blank');
  if (w) { w.document.write(html); w.document.close(); setTimeout(() => w.print(), 180); }
}

export default function ShelfModal({ lang, shelf, products, onClose, onUpdateProduct, onAddProduct, notify }) {
  if (!shelf) return null;
  const shelfProducts = (shelf.products || []).sort((a,b)=>Number(a.position||0)-Number(b.position||0));
  const aisle = shelf.aisle || shelf.areaId || String(shelf.moduleId || 'A').split('.')[0] || 'A';
  const moduleNo = Number(shelf.moduleNo || String(shelf.moduleId || '1').match(/\d+/)?.[0] || 1) || 1;
  const shelfNo = Number(String(shelf.shelfNo || '1').match(/\d+/)?.[0] || 1) || 1;
  const shelfWidthCm = Math.max(40, Number(shelf.shelf_width_cm || shelf.width_cm || 100));
  const shelfDepthCm = Math.max(20, Number(shelf.shelf_depth_cm || shelf.depth_cm || 50));
  const productWidthCm = (p) => Math.max(4, Number(p.width_cm || p.width || p.product_width_in_cm || 8));
  const productDepthCm = (p) => Math.max(1, Number(p.product_depth_cm || p.depth_cm || p.product_length_in_cm || 10));
  const productUsedWidth = (p) => productWidthCm(p) * Math.max(1, Number(p.facing || 1));
  const usedWidthCm = shelfProducts.reduce((sum, p) => sum + productUsedWidth(p), 0);
  const overCapacity = usedWidthCm > shelfWidthCm + 0.001;

  function updateFacingSafe(product, nextFacing) {
    const currentFacing = Math.max(1, Number(product.facing || 1));
    const safeNext = Math.max(1, Number(nextFacing || 1));
    const usedWithout = usedWidthCm - productWidthCm(product) * currentFacing;
    const maxFacing = Math.max(1, Math.floor((shelfWidthCm - usedWithout) / productWidthCm(product)));
    if (safeNext > maxFacing) {
      notify?.(`Bu rafta maksimum ${maxFacing} facing mümkün. Raf genişliği ${shelfWidthCm} cm.`);
      onUpdateProduct(product.sku, { facing: maxFacing });
      return;
    }
    onUpdateProduct(product.sku, { facing: safeNext });
  }

  function updateDepthSafe(product, nextDepth) {
    const maxDepth = Math.max(1, Math.floor(shelfDepthCm / productDepthCm(product)));
    const safeNext = Math.max(1, Number(nextDepth || 1));
    if (safeNext > maxDepth) {
      notify?.(`Bu rafta maksimum ${maxDepth} depth mümkün. Raf derinliği ${shelfDepthCm} cm.`);
      onUpdateProduct(product.sku, { depth: maxDepth });
      return;
    }
    onUpdateProduct(product.sku, { depth: safeNext });
  }

  function canAddProduct(product) {
    return usedWidthCm + productWidthCm(product) <= shelfWidthCm + 0.001;
  }

  function sortBy(field) {
    const sorted = [...shelfProducts].sort((a,b) => field === 'sales' ? Number(b.sales || 0) - Number(a.sales || 0) : String(a.brand).localeCompare(String(b.brand), 'tr'));
    sorted.forEach((p, idx) => onUpdateProduct(p.sku, { position: idx + 1 }, false));
    notify?.(field === 'sales' ? 'Raf satışa göre sıralandı.' : 'Raf markaya göre sıralandı.');
  }
  function printShelf() {
    printDocument({ title: `Raf Yazdır - ${aisle}.${moduleNo}.${shelfNo}`, subtitle: shelf.title, groups: [{ title: `Raf ${shelfNo}`, products: shelfProducts }] });
  }
  function printModule() {
    const groups = groupedByShelf(products, aisle, moduleNo).map(([s, ps]) => ({ title: `Raf ${aisle}.${moduleNo}.${s}`, products: ps }));
    printDocument({ title: `Modül Yazdır - ${aisle}.${moduleNo}`, subtitle: '1. bölüm görsel raf sıraları, 2. bölüm raf raf ürün listesi.', groups: groups.length ? groups : [{ title: 'Boş modül', products: [] }] });
  }
  function printCorridor() {
    const groups = groupedByModule(products, aisle).flatMap(([m, ps]) => groupedByShelf(ps, aisle, m).map(([s, shelfPs]) => ({ title: `Modül ${aisle}.${m} / Raf ${s}`, products: shelfPs })));
    printDocument({ title: `Koridor Yazdır - ${aisle}`, subtitle: 'Bu koridordaki tüm modüller ve raflar.', groups: groups.length ? groups : [{ title: 'Boş koridor', products: [] }] });
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div><div className="section-eyebrow">{tt(lang,'shelfEditor')}</div><h2 style={{ margin: '4px 0 0' }}>{shelf.title}</h2></div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn ghost" onClick={printShelf}>▤ Rafı yazdır</button>
            <button className="btn ghost" onClick={printModule}>▥ Modülü yazdır</button>
            <button className="btn ghost" onClick={printCorridor}>▦ Koridoru yazdır</button>
            <button className="btn primary" onClick={onClose}>Kapat</button>
          </div>
        </div>
        <div className="modal-body">
          <div className="modal-grid">
            <section className="card pad">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <div><h3>Görsel raf</h3><p className="muted">Ürün görselleri, facing ve depth aynı ekranda.</p><p className={overCapacity ? 'danger-text' : 'muted'}>Kapasite: {Math.round(usedWidthCm)} / {shelfWidthCm} cm {overCapacity ? '· AŞIM VAR' : ''}</p></div>
                <div style={{ display: 'flex', gap: 8 }}><button className="btn small ghost" onClick={() => sortBy('sales')}>{tt(lang,'sortSales')}</button><button className="btn small ghost" onClick={() => sortBy('brand')}>{tt(lang,'sortBrand')}</button></div>
              </div>
              <div className="shelf-visual">
                <div className="shelf" style={{ minHeight: 120 }}>
                  <span className="shelf-label">Raf {shelfNo}</span>
                  {shelfProducts.slice(0, 60).flatMap((p) => Array.from({ length: Math.max(1, Math.min(8, Number(p.facing || 1))) }).map((_, i) => <ProductThumb key={`${p.sku}-${i}`} product={p} small />))}
                  {!shelfProducts.length && <span className="muted">Bu raf boş. Sağ panelden ürün atayabilirsin.</span>}
                </div>
              </div>
              <h3>Ürün listesi</h3>
              <div className="list">
                {shelfProducts.map((p) => <div className="item" key={p.sku}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}><ProductThumb product={p} small /><div><b>{p.name}</b><br/><span className="muted">{p.sku} • {p.brand} • {p.aisle}.{p.module}.{p.shelf}</span></div></div>
                  <span className={`badge ${storageTone(p.storage)}`}>{p.storage}</span>
                  <div className="counter"><span>Facing</span><button onClick={() => updateFacingSafe(p, Math.max(1, Number(p.facing || 1) - 1))}>−</button><b>{p.facing}</b><button onClick={() => updateFacingSafe(p, Number(p.facing || 1) + 1)}>+</button></div>
                  <div className="counter"><span>Depth</span><button onClick={() => updateDepthSafe(p, Math.max(1, Number(p.depth || 1) - 1))}>−</button><b>{p.depth}</b><button onClick={() => updateDepthSafe(p, Number(p.depth || 1) + 1)}>+</button></div>
                </div>)}
              </div>
            </section>
            <aside className="card pad">
              <h3>{tt(lang,'addProduct')}</h3>
              <div className="list">
                {products.filter((p) => !shelfProducts.some((x) => x.sku === p.sku) && String(p.storage) === String(shelfProducts[0]?.storage || p.storage)).slice(0,12).map((p) => <button className="product-hit" key={p.sku} onClick={() => canAddProduct(p) ? onAddProduct(p, { ...shelf, aisle, moduleNo, shelfNo }) : notify?.(`Bu ürün bu rafa sığmıyor. Kalan genişlik ${Math.max(0, Math.round(shelfWidthCm - usedWidthCm))} cm.`)}><ProductThumb product={p} small /><div><b>{p.name}</b><br/><span className="muted">{p.sku}</span></div><span className={`badge ${storageTone(p.storage)}`}>{p.storage}</span></button>)}
              </div>
              <div className="card pad" style={{ marginTop: 16, background: 'rgba(223,16,103,.05)' }}>
                <div className="section-eyebrow">REFILL LOGIC</div>
                <p className="muted">daily_sales / shelf_capacity = refill_per_day. Hızlı ürünlerde facing ve depth önerisi satışa göre artırılır.</p>
                <button className="btn primary" onClick={() => shelfProducts.forEach(p => updateFacingSafe(p, Math.max(Number(p.facing || 1), Math.ceil(Number(p.sales || 0) / 120))))}>{tt(lang,'aiFacing')}</button>
              </div>
              <button className="btn ghost" style={{ width: '100%', marginTop: 12 }} onClick={() => navigator.clipboard?.writeText(JSON.stringify(shelfProducts, null, 2)).then(() => notify?.('Raf JSON kopyalandı.'))}>JSON Export</button>
            </aside>
          </div>
        </div>
      </div>
    </div>
  );
}
