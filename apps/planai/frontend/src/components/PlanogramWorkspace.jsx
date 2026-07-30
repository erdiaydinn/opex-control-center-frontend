import { useMemo, useState } from 'react';
import { tt } from '../i18n/dictionary.js';
import ShelfModal from './ShelfModal.jsx';
import { ProductChip, storageTone } from './ProductVisuals.jsx';
import TwinStudio3D from './Live3D/TwinStudio3D.jsx';

// Backend nested planogram'dan TAM eslesme ile raf bulur (tek dogru kaynak).
// Flat products / local allocator productsForShelf KULLANILMAZ.
function findBackendShelf(planogram, aisleId, moduleId, shelfNo) {
  const aisles = planogram?.aisles || [];
  for (const aisle of aisles) {
    if (String(aisle.aisle_id) !== String(aisleId)) continue;
    for (const module of aisle.modules || []) {
      const moduleMatches =
        String(module.module_id) === String(moduleId) ||
        String(module.module_id) === String(`${aisleId}.${moduleId}`) ||
        String(module.module_id) === String(`${aisleId}${moduleId}`);
      if (!moduleMatches) continue;
      for (const shelf of module.shelves || []) {
        if (String(shelf.shelf_no) === String(shelfNo)) {
          return { aisle, module, shelf };
        }
      }
    }
  }
  return null;
}

function shelfUsedWidth(shelf) {
  if (shelf?.used_width_cm != null) return Number(shelf.used_width_cm) || 0;
  return (shelf?.products || []).reduce((s, p) => s + (Number(p.used_width_cm) || 0), 0);
}

function escapeCsv(value) {
  const raw = String(value ?? '').replace(/\r?\n/g, ' ');
  return /[",;\t]/.test(raw) ? `"${raw.replace(/"/g, '""')}"` : raw;
}

function downloadText(filename, content, type = 'text/csv;charset=utf-8') {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function unplacedRows(unplacedProducts = []) {
  return (unplacedProducts || []).map((p) => ({
    sku: p.sku || '',
    product: p.name || p.product_name || '',
    brand: p.brand || '',
    storage: p.storage || p.storage_type || '',
    reason: p.reason || p.constraint_reason || '',
    action: p.suggested_action || 'Fixture kapasitesi, storage type ve ürün ölçüsünü kontrol et.',
  }));
}

export default function PlanogramWorkspace({ lang, objects, products, setProducts, unplacedProducts = [], notify, backendPlan = null }) {
  const [open, setOpen] = useState('A');
  const [view, setView] = useState('2d');
  const [heat, setHeat] = useState('sales');
  const [modalShelf, setModalShelf] = useState(null);
  const corridors = useMemo(() => objects.filter((o) => Number(o.modules || 0) > 0 && Number(o.shelves || 0) > 0), [objects]);
  const modules = corridors.reduce((s,o)=>s+Number(o.modules||0),0);
  const shelves = corridors.reduce((s,o)=>s+Number(o.shelves||0),0);

  // HYDRATION: gorsel kaynak = backend planogram (hydrate edilmis). Store DNA objects yalniz fallback.
  const viewAisles = useMemo(() => {
    const aisles = backendPlan?.aisles || [];
    return aisles.map((a) => {
      const mods = (a.modules || []).map((m) => ({
        module_id: m.module_id,
        sku_count: m.sku_count != null ? m.sku_count : (m.shelves || []).reduce((s, sh) => s + (sh.products || []).length, 0),
        shelves: m.shelves || [],
        module_width_cm: m.module_width_cm,
      }));
      const skuCount = a.sku_count != null ? a.sku_count : mods.reduce((s, m) => s + m.sku_count, 0);
      return { aisle_id: a.aisle_id, zone: a.zone || 'AMBIENT', utilization: a.utilization || 0, sku_count: skuCount, modules: mods };
    });
  }, [backendPlan]);

  const totalPlacedFromPlan = useMemo(
    () => viewAisles.reduce((s, a) => s + a.sku_count, 0),
    [viewAisles]
  );
  function updateProduct(sku, patch, show = true) {
    setProducts((prev) => prev.map((p) => p.sku === sku ? { ...p, ...patch } : p));
    if (show) notify?.('Raf içi düzen güncellendi.');
  }
  function addProduct(product, shelf) {
    updateProduct(product.sku, { aisle: shelf.aisle, aisle_id: shelf.aisle, module: shelf.moduleNo, module_id: shelf.moduleNo, shelf: shelf.shelfNo, shelf_no: shelf.shelfNo });
  }
  function addModule(c) {
    notify?.(`${c.label} koridoruna yeni modül eklendi.`);
  }

  function downloadUnplacedCsv() {
    const rows = unplacedRows(unplacedProducts);
    const head = ['SKU', 'Ürün', 'Marka', 'Storage', 'Neden', 'Aksiyon'];
    const body = rows.map((r) => [r.sku, r.product, r.brand, r.storage, r.reason, r.action].map(escapeCsv).join(';'));
    downloadText('atanamayan_urun_raporu.csv', [head.join(';'), ...body].join('\n'));
    notify?.('Atanamayan ürün raporu CSV olarak indirildi.');
  }

  function downloadUnplacedExcel() {
    const rows = unplacedRows(unplacedProducts);
    const table = `<table><thead><tr><th>SKU</th><th>Ürün</th><th>Marka</th><th>Storage</th><th>Neden</th><th>Aksiyon</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${r.sku}</td><td>${r.product}</td><td>${r.brand}</td><td>${r.storage}</td><td>${r.reason}</td><td>${r.action}</td></tr>`).join('')}</tbody></table>`;
    downloadText('atanamayan_urun_raporu.xls', table, 'application/vnd.ms-excel;charset=utf-8');
    notify?.('Atanamayan ürün raporu Excel uyumlu dosya olarak indirildi.');
  }
  // KPI'lar hydrate edilmis backend planogram'dan (yoksa Store DNA objects fallback)
  const planModules = viewAisles.reduce((s, a) => s + a.modules.length, 0);
  const planShelves = viewAisles.reduce((s, a) => s + a.modules.reduce((ss, m) => ss + m.shelves.length, 0), 0);
  const planFillPct = (() => {
    let used = 0, cap = 0;
    viewAisles.forEach((a) => a.modules.forEach((m) => m.shelves.forEach((sh) => {
      used += Number(sh.used_width_cm) || 0; cap += Number(sh.shelf_width_cm) || 0;
    })));
    return cap > 0 ? Math.round((used / cap) * 100) : 0;
  })();
  const hasPlan = viewAisles.length > 0;
  const kpis = hasPlan
    ? [['Koridor', viewAisles.length], ['Modül', planModules], ['Raf', planShelves], ['Doluluk', `${planFillPct}%`], ['Yerleşen SKU', totalPlacedFromPlan.toLocaleString('tr-TR')], ['Atanamayan', unplacedProducts.length.toLocaleString('tr-TR')]]
    : [['Koridor', corridors.length], ['Modül', modules], ['Raf', shelves], ['Doluluk', '0%'], ['Yerleşen SKU', products.length.toLocaleString('tr-TR')], ['Atanamayan', unplacedProducts.length.toLocaleString('tr-TR')]];
  return (
    <div className="page">
      <div style={{ display:'flex', justifyContent:'space-between', gap:12, flexWrap:'wrap' }}>
        <div><div className="section-eyebrow">PLANOGRAM ÇALIŞMA ALANI</div><h1 style={{fontSize:42,margin:'8px 0'}}>{tt(lang,'planogram')}</h1><p className="page-sub">Koridor, modül, raf ve SKU düzeyinde uygulanabilir planogram.</p></div>
        <div className="tabs"><button className={`tab ${view==='3d'?'active':''}`} onClick={() => setView('3d')}>3D Görünüm</button><button className={`tab ${view==='2d'?'active':''}`} onClick={() => setView('2d')}>2D Planogram</button><button className={`tab ${view==='heatmap'?'active':''}`} onClick={() => setView('heatmap')}>Isı Haritası</button><button className={`tab ${view==='unplaced'?'active':''}`} onClick={() => setView('unplaced')}>Atanamayanlar</button></div>
      </div>
      <section className="grid cols-6" style={{ marginTop: 18 }}>{kpis.map(([l,v])=><div className="card kpi" key={l}><div className="kpi-label">{l}</div><div className="kpi-value">{v}</div><div className="kpi-trend">Toplam</div></div>)}</section>
      {view === 'heatmap' && <div className="card pad" style={{ marginTop: 18 }}><div className="tabs">{['sales','refill','cold'].map(h=><button className={`tab ${heat===h?'active':''}`} onClick={()=>setHeat(h)} key={h}>{h==='sales'?'Satış':h==='refill'?'Refill Risk':'Cold Chain'}</button>)}</div><div className="grid cols-3" style={{ marginTop: 16 }}>{(hasPlan ? viewAisles : []).map(a=><div key={a.aisle_id} className={`card pad heat-${heat}-bg`}><h3>{a.aisle_id} <span className="badge">{a.zone}</span></h3><p>{tt(lang,'fill')}: {a.utilization}%</p><p>SKU: {a.sku_count}</p></div>)}{!hasPlan && <div className="empty-state">Plan üretilmedi.</div>}</div></div>}
      {view === '3d' && <div className="planogram-3d card" style={{ marginTop: 18 }}><TwinStudio3D objects={objects} products={(hasPlan ? products : []).slice(0, 500)} cameraPreset="overview" heatmap={heat} selectedAreaId={open || (viewAisles[0]?.aisle_id) || 'A'} selectedProductSku="" onSelectArea={(area)=>setOpen(area.id)} onSelectProduct={(p)=>notify?.(`${p.name} seçildi.`)} /></div>}
      {view === 'unplaced' && <section className="card pad" style={{ marginTop: 18 }}>
        <div className="report-head"><div><h2>Atanamayan ürün raporu</h2><p className="muted">Fixture/storage/kapasite nedeniyle yerleşemeyen ürünler. Bu liste saha aksiyonuna dönüştürülmeli.</p></div><div className="report-actions"><button className="btn ghost" onClick={downloadUnplacedCsv}>CSV indir</button><button className="btn ghost" onClick={downloadUnplacedExcel}>Excel indir</button></div></div>
        <table className="table"><thead><tr><th>SKU</th><th>Ürün</th><th>Marka</th><th>Storage</th><th>Neden</th><th>Aksiyon</th></tr></thead><tbody>{unplacedRows(unplacedProducts).slice(0, 300).map((p, i)=><tr key={`${p.sku}-${i}`}><td>{p.sku}</td><td>{p.product}</td><td>{p.brand}</td><td><span className={`badge ${storageTone(p.storage)}`}>{p.storage}</span></td><td>{p.reason}</td><td>{p.action}</td></tr>)}</tbody></table>{!unplacedProducts.length && <div className="empty-state">Atanamayan ürün yok.</div>}{unplacedProducts.length > 300 && <p className="muted" style={{ marginTop: 12 }}>Ekranda ilk 300 satır gösteriliyor; indirilen dosyada tüm kayıtlar var.</p>}
      </section>}
      {view === '2d' && <section className="card pad" style={{ marginTop: 18 }}>
        {!hasPlan && <div className="empty-state">Henüz plan üretilmedi veya görsel kaynak boş. "Optimum plan üret" ile backend planogram oluştur.</div>}
        {viewAisles.map((a) => {
          const zoneBadge = a.zone === 'FROZEN' ? 'purple' : a.zone === 'CHILLED' ? 'cyan' : a.zone === 'PRODUCE' ? 'green' : a.zone === 'PALLET' ? 'orange' : 'green';
          return <div key={a.aisle_id} style={{ borderBottom: '1px solid var(--line)', padding: '14px 0' }}>
            <button className="item" style={{ width: '100%' }} onClick={() => setOpen(open === a.aisle_id ? '' : a.aisle_id)}>
              <div><b>{a.aisle_id}</b> <span className={`badge ${zoneBadge}`}>{a.zone}</span></div>
              <div className="muted">{a.modules.length} Modül • Doluluk {a.utilization}% • {a.sku_count} SKU</div>
            </button>
            {open === a.aisle_id && <div className="planogram-row" style={{ marginTop: 14 }}>
              {a.modules.map((m) => <div className="card module-card" key={`${a.aisle_id}-${m.module_id}`}>
                <b>Modül {a.aisle_id}.{m.module_id}</b>
                <span className="badge pink" style={{ marginLeft: 8 }}>{Math.round(Number(m.module_width_cm) || 100)} cm</span>
                <span className="muted" style={{ marginLeft: 8 }}>{m.sku_count} SKU</span>
                {m.shelves.map((sh) => {
                  const ps = (sh.products || []).slice().sort((x, y) => Number(x.position_order || x.position || 0) - Number(y.position_order || y.position || 0));
                  return <button className="shelf" key={sh.shelf_no} onClick={() => setModalShelf({
                    ...sh,
                    title: `${a.aisle_id} / Modül ${a.aisle_id}.${m.module_id} / Raf ${sh.shelf_no}`,
                    aisle: a.aisle_id, aisle_id: a.aisle_id, moduleId: `${a.aisle_id}.${m.module_id}`, moduleNo: m.module_id,
                    module_id: m.module_id, shelfNo: sh.shelf_no, shelf_no: sh.shelf_no,
                    shelf_width_cm: sh.shelf_width_cm ?? 100, shelf_depth_cm: sh.shelf_depth_cm ?? 50, products: ps
                  })} style={{ width: '100%' }}>
                    <small className="shelf-label">Raf {a.aisle_id}.{m.module_id}.{sh.shelf_no} · {Math.round(Number(sh.used_width_cm) || 0)}/{Math.round(Number(sh.shelf_width_cm) || 100)} cm</small>
                    {ps.slice(0, 18).map((p) => <ProductChip key={p.sku} product={p} />)}
                    {ps.length > 18 && <span className="more-chip">+{ps.length - 18}</span>}
                    {!ps.length && <span className="muted">Boş</span>}
                  </button>;
                })}
              </div>)}
            </div>}
          </div>;
        })}
      </section>}
      <ShelfModal lang={lang} shelf={modalShelf} products={products} onClose={() => setModalShelf(null)} onUpdateProduct={updateProduct} onAddProduct={addProduct} notify={notify} />
    </div>
  );
}
