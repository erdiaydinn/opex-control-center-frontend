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


function _norm(v) {
  return String(v ?? '').trim().toUpperCase();
}

function _productText(p) {
  return [
    p?.sku,
    p?.SKU,
    p?.name,
    p?.product_name,
    p?.productName,
    p?.['Product Name'],
    p?.brand,
    p?.brand_name,
    p?.category_l1,
    p?.category_l2,
    p?.['Category L1'],
    p?.['Category L2'],
    p?.frontend_category_local,
    p?.frontend_subcategory_local,
    p?.storage,
    p?.storage_type,
    p?.storage_class,
    p?.storage_type_hint,
  ].filter(Boolean).join(' ').toUpperCase();
}

function _categoryText(p) {
  return [
    p?.category_l1,
    p?.category_l2,
    p?.['Category L1'],
    p?.['Category L2'],
    p?.frontend_category_local,
    p?.frontend_subcategory_local,
  ].filter(Boolean).join(' ').toUpperCase();
}

function _shelfText(shelf) {
  return [
    shelf?.title,
    shelf?.name,
    shelf?.moduleId,
    shelf?.fixture_type,
    shelf?.fixture_class,
    shelf?.fixture_pool,
    shelf?.storage,
    shelf?.storage_type,
    shelf?.storage_class,
    shelf?.allowed_storage_type,
    shelf?.allowed_storage_class,
  ].filter(Boolean).join(' ').toUpperCase();
}

function isExcludedOperationalProduct(p) {
  const raw = _productText(p);

  if (
    raw.includes('SHOPPING BAG') ||
    raw.includes('ALI?VER?? PO?ET') ||
    raw.includes('ALISVERIS POSET') ||
    raw.includes('PO?ET') ||
    raw.includes('POSET') ||
    raw.includes('CARRIER BAG') ||
    raw.includes('MARKET BAG') ||
    raw.includes('DISPOSABLE BAG')
  ) return true;

  if (
    raw.includes('EVERYDAY') ||
    raw.includes('COFFEE MACHINE') ||
    raw.includes('KAHVE MAKINESI') ||
    raw.includes('KAHVE MAK?NES?') ||
    raw.includes('EQUIPMENT') ||
    raw.includes('EKIPMAN') ||
    raw.includes('EK?PMAN')
  ) return true;

  if (
    raw.includes('LA LORRAINE') ||
    raw.includes('BAGUETTE') ||
    raw.includes('BAGEL') ||
    raw.includes('S?M?T') ||
    raw.includes('SIMIT') ||
    raw.includes('RAMAZAN PIDESI') ||
    raw.includes('RAMAZAN P?DES?') ||
    raw.includes('PIDE') ||
    raw.includes('P?DE') ||
    raw.includes('BAKERY') ||
    raw.includes('FIRIN') ||
    raw.includes('EKMEK') ||
    raw.includes('BREAD')
  ) return true;

  return false;
}

function productStorageClass(p) {
  const raw = _productText(p);
  const explicit = _norm(
    p?.storage ||
    p?.storage_type ||
    p?.storage_class ||
    p?.storage_type_hint ||
    p?.['Storage Type']
  );

  if (
    explicit.includes('FROZEN') ||
    explicit.includes('DONUK') ||
    raw.includes('DONDURMA') ||
    raw.includes('ICE CREAM') ||
    raw.includes('ALGIDA') ||
    raw.includes('MAGNUM')
  ) return 'FROZEN';

  if (
    explicit.includes('CHILLED') ||
    explicit.includes('SO?UK') ||
    explicit.includes('SOGUK') ||
    raw.includes('YOGURT') ||
    raw.includes('YO?URT') ||
    raw.includes('MILK') ||
    raw.includes('S?T') ||
    raw.includes('SUT') ||
    raw.includes('DAIRY') ||
    raw.includes('CHEESE') ||
    raw.includes('PEYNIR') ||
    raw.includes('PEYN?R') ||
    raw.includes('EGG') ||
    raw.includes('YUMURTA')
  ) return 'CHILLED';

  return 'AMBIENT';
}

function isProduceProduct(p) {
  const raw = _productText(p);
  const cat = _categoryText(p);

  const categorySaysProduce =
    cat.includes('PRODUCE') ||
    cat.includes('FRUIT') ||
    cat.includes('VEGETABLE') ||
    cat.includes('MEYVE') ||
    cat.includes('SEBZE') ||
    cat.includes('FRESH');

  const fakeProduce =
    raw.includes('CHIPS') ||
    raw.includes('CIPS') ||
    raw.includes('??PS') ||
    raw.includes('CAKE') ||
    raw.includes('KEK') ||
    raw.includes('YOGURT') ||
    raw.includes('YO?URT') ||
    raw.includes('SNACK') ||
    raw.includes('BABY') ||
    raw.includes('MOISTUR') ||
    raw.includes('BATH') ||
    raw.includes('SHOWER') ||
    raw.includes('WATER') ||
    raw.includes('DRINK') ||
    raw.includes('JUICE') ||
    raw.includes('BOTTLE');

  const nameSaysProduce =
    raw.includes('BANANA') ||
    raw.includes('MUZ') ||
    raw.includes('APPLE') ||
    raw.includes('ELMA') ||
    raw.includes('POTATO') ||
    raw.includes('PATATES') ||
    raw.includes('TOMATO') ||
    raw.includes('DOMATES') ||
    raw.includes('CUCUMBER') ||
    raw.includes('SALATALIK') ||
    raw.includes('LETTUCE') ||
    raw.includes('MARUL') ||
    raw.includes('PARSLEY') ||
    raw.includes('MAYDANOZ') ||
    raw.includes('ONION') ||
    raw.includes('SO?AN') ||
    raw.includes('SOGAN') ||
    raw.includes('CARROT') ||
    raw.includes('HAVU?') ||
    raw.includes('HAVUC') ||
    raw.includes('LEMON') ||
    raw.includes('LIMON') ||
    raw.includes('ORANGE') ||
    raw.includes('PORTAKAL') ||
    raw.includes('MANDALINA');

  return (categorySaysProduce || nameSaysProduce) && !fakeProduce;
}

function shelfDomainClass(shelf) {
  const raw = _shelfText(shelf);

  if (
    raw.includes('MEYVE') ||
    raw.includes('SEBZE') ||
    raw.includes('PRODUCE') ||
    raw.includes('FRESH')
  ) return 'PRODUCE';

  if (
    raw.includes('CHILLED') ||
    raw.includes('SO?UK') ||
    raw.includes('SOGUK') ||
    raw.includes('+4')
  ) return 'CHILLED';

  if (
    raw.includes('FROZEN') ||
    raw.includes('DONUK') ||
    raw.includes('-18') ||
    raw.includes('ALGIDA') ||
    raw.includes('ICE_CREAM')
  ) return 'FROZEN';

  return 'AMBIENT';
}

function canAssignProductToShelf(product, shelf) {
  if (!product) return false;
  if (isExcludedOperationalProduct(product)) return false;

  const shelfDomain = shelfDomainClass(shelf);
  const productStorage = productStorageClass(product);
  const produce = isProduceProduct(product);

  if (shelfDomain === 'PRODUCE') {
    return produce && productStorage === 'AMBIENT';
  }

  if (shelfDomain === 'CHILLED') {
    return productStorage === 'CHILLED';
  }

  if (shelfDomain === 'FROZEN') {
    return productStorage === 'FROZEN';
  }

  // Regular ambient shelf.
  if (produce) return false;
  return productStorage === 'AMBIENT';
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
  const rawShelfProducts = (shelf.products || []).sort((a,b)=>Number(a.position||0)-Number(b.position||0));
  const shelfProducts = rawShelfProducts.filter((p) => canAssignProductToShelf(p, shelf));
  const blockedShelfProducts = rawShelfProducts.filter((p) => !canAssignProductToShelf(p, shelf));
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
                {(products || []).filter((p) => !shelfProducts.some((x) => x.sku === p.sku) && canAssignProductToShelf(p, shelf)).slice(0,12).map((p) => <button className="product-hit" key={p.sku} onClick={() => canAddProduct(p) ? onAddProduct(p, { ...shelf, aisle, moduleNo, shelfNo }) : notify?.(`Bu ürün bu rafa sığmıyor. Kalan genişlik ${Math.max(0, Math.round(shelfWidthCm - usedWidthCm))} cm.`)}><ProductThumb product={p} small /><div><b>{p.name}</b><br/><span className="muted">{p.sku}</span></div><span className={`badge ${storageTone(p.storage)}`}>{p.storage}</span></button>)}
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
