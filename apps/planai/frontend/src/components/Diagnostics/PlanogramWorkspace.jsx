import { useMemo, useState } from 'react';
import { tt } from '../i18n/dictionary.js';
import ShelfModal from './ShelfModal.jsx';
import { ProductChip, storageTone } from './ProductVisuals.jsx';

function moduleProducts(products, aisle, moduleNo, shelfNo) {
  const filtered = products.filter((p, idx) => (p.aisle === aisle || (aisle === 'A' && idx % 2 === 0)) && ((idx + moduleNo + shelfNo) % 4 !== 0));
  return filtered.slice(0, Math.max(2, 7 - shelfNo));
}

export default function PlanogramWorkspace({ lang, objects, products, setProducts, notify }) {
  const [open, setOpen] = useState('A');
  const [view, setView] = useState('2d');
  const [heat, setHeat] = useState('sales');
  const [modalShelf, setModalShelf] = useState(null);
  const corridors = useMemo(() => objects.filter((o) => o.type === 'corridor').slice(0, 8), [objects]);
  const modules = corridors.reduce((s,o)=>s+Number(o.modules||0),0);
  const shelves = corridors.reduce((s,o)=>s+Number(o.shelves||0),0);
  function updateProduct(sku, patch, show = true) {
    setProducts((prev) => prev.map((p) => p.sku === sku ? { ...p, ...patch } : p));
    if (show) notify?.('Raf içi düzen güncellendi.');
  }
  function addProduct(product, shelf) {
    updateProduct(product.sku, { aisle: shelf.aisle, module: shelf.moduleNo, shelf: shelf.shelfNo });
  }
  function addModule(c) {
    notify?.(`${c.label} koridoruna yeni modül eklendi.`);
  }
  const kpis = [['Koridor', corridors.length], ['Modül', modules], ['Raf', shelves], ['Doluluk', '87%'], ['Facing', '2,842'], ['Yerleşen SKU', '1,126']];
  return (
    <div className="page">
      <div style={{ display:'flex', justifyContent:'space-between', gap:12, flexWrap:'wrap' }}>
        <div><div className="section-eyebrow">PLANOGRAM ÇALIŞMA ALANI</div><h1 style={{fontSize:42,margin:'8px 0'}}>{tt(lang,'planogram')}</h1><p className="page-sub">Koridor, modül, raf ve SKU düzeyinde uygulanabilir planogram.</p></div>
        <div className="tabs"><button className={`tab ${view==='3d'?'active':''}`} onClick={() => setView('3d')}>3D Görünüm</button><button className={`tab ${view==='2d'?'active':''}`} onClick={() => setView('2d')}>2D Planogram</button><button className={`tab ${view==='heatmap'?'active':''}`} onClick={() => setView('heatmap')}>Isı Haritası</button></div>
      </div>
      <section className="grid cols-6" style={{ marginTop: 18 }}>{kpis.map(([l,v])=><div className="card kpi" key={l}><div className="kpi-label">{l}</div><div className="kpi-value">{v}</div><div className="kpi-trend">Toplam</div></div>)}</section>
      {view === 'heatmap' && <div className="card pad" style={{ marginTop: 18 }}><div className="tabs">{['sales','refill','cold'].map(h=><button className={`tab ${heat===h?'active':''}`} onClick={()=>setHeat(h)} key={h}>{h==='sales'?'Satış':h==='refill'?'Refill Risk':'Cold Chain'}</button>)}</div><div className="grid cols-3" style={{ marginTop: 16 }}>{corridors.map(c=><div key={c.id} className={`card pad heat-${heat}-bg`}><h3>Koridor {c.label}</h3><p>{tt(lang,'fill')}: {c.utilization}%</p><p>{tt(lang,'changedProducts')}: {c.changed}</p></div>)}</div></div>}
      {view === '3d' && <div className="card pad" style={{ marginTop: 18 }}><p className="muted">3D görünüm için Canlı 3D ekranındaki aynı dijital ikiz state'i kullanılır.</p><button className="btn primary" onClick={() => notify?.('3D Planogram modu açıldı.')}>3D Planogram odakla</button></div>}
      {view === '2d' && <section className="card pad" style={{ marginTop: 18 }}>
        {corridors.map((c) => (
          <div key={c.id} style={{ borderBottom: '1px solid var(--line)', padding: '14px 0' }}>
            <button className="item" style={{ width: '100%' }} onClick={() => setOpen(open === c.id ? '' : c.id)}>
              <div><b>Koridor {c.label}</b> <span className="badge green">{c.utilization > 80 ? 'Optimal' : 'Fırsat'}</span></div>
              <div className="muted">{c.modules} Modül • Doluluk {c.utilization}%</div>
            </button>
            {open === c.id && <div className="planogram-row" style={{ marginTop: 14 }}>
              {[1,2,3].map((m) => <div className="card module-card" key={`${c.id}-${m}`}><b>Modül {c.label}.{m}</b><span className="badge pink" style={{ marginLeft: 8 }}>{m===2?'120':'100'} cm</span>{[1,2,3,4].slice(0, m===2?4:3).map((s) => { const ps = moduleProducts(products, c.id, m, s); return <button className="shelf" key={s} onClick={() => setModalShelf({ title: `Koridor ${c.label} / Modül ${c.label}.${m} / Raf ${s}`, aisle: c.id, moduleId: `${c.label}.${m}`, moduleNo: m, shelfNo: s, products: ps })} style={{ width:'100%' }}><small className="shelf-label">Raf {c.label}.{m}.{s}</small>{ps.map((p) => <ProductChip key={p.sku} product={p} />)}</button>; })}</div>)}
              <div className="card pad" style={{ display: 'grid', placeItems: 'center', borderStyle: 'dashed' }}><button className="btn ghost" onClick={() => addModule(c)}>＋ Module</button></div>
            </div>}
          </div>
        ))}
      </section>}
      <ShelfModal lang={lang} shelf={modalShelf} products={products} onClose={() => setModalShelf(null)} onUpdateProduct={updateProduct} onAddProduct={addProduct} notify={notify} />
    </div>
  );
}
