import { useMemo, useState } from 'react';
import { buildPlanogramFromObjects } from '../data/mock.js';
import { tt } from '../i18n/dictionary.js';

export default function PlanogramWorkspace({ lang, objects }) {
  const rows = useMemo(() => buildPlanogramFromObjects(objects), [objects]);
  const [open, setOpen] = useState(rows[0]?.id || 'A');
  return (
    <div className="page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div><div className="section-eyebrow">PLANOGRAM WORKSPACE</div><h1 style={{ fontSize: 42, margin: '8px 0' }}>{tt(lang, 'planogram')}</h1><p className="page-sub">Koridor, modül, raf ve SKU düzeyinde uygulanabilir planogram.</p></div>
        <div className="tabs"><button className="tab">3D View</button><button className="tab active">2D Planogram</button><button className="tab">Heatmap</button></div>
      </div>
      <section className="grid cols-6" style={{ marginTop: 22 }}>
        {[['Corridors', rows.length], ['Modules', rows.reduce((a,r)=>a+r.modules.length,0)], ['Shelves', rows.reduce((a,r)=>a+r.modules.reduce((b,m)=>b+m.shelves.length,0),0)], ['Fill Rate', '87%'], ['Facings', '2,842'], ['SKUs Placed', '1,126']].map(([k,v]) => <div className="card kpi" key={k}><div className="kpi-label">{k}</div><div className="kpi-value">{v}</div><div className="kpi-trend">Total</div></div>)}
      </section>
      <section className="card pad" style={{ marginTop: 22 }}>
        {rows.map((row) => (
          <div key={row.id} style={{ borderBottom: '1px solid var(--line)', padding: '14px 0' }}>
            <button className="item" style={{ width: '100%' }} onClick={() => setOpen(open === row.id ? '' : row.id)}>
              <div><b>{row.label}</b> <span className="badge green">{row.status}</span></div>
              <div className="muted">{row.modules.length} Modules • Fill Rate {row.fill}%</div>
            </button>
            {open === row.id && <div className="planogram-row" style={{ marginTop: 14 }}>
              {row.modules.slice(0,3).map((m) => <div className="card module-card" key={m.id}><b>Module {m.id}</b><span className="badge" style={{ marginLeft: 8 }}>{m.width} cm</span>{m.shelves.map((s) => <div className="shelf" key={s.id}><small style={{ width: 80 }}>Shelf {s.id}</small>{s.products.map((p, i) => <div key={`${p.sku}-${i}`} className={`product-chip ${p.storage}`} title={p.name}>{p.brand.slice(0,2)}</div>)}</div>)}</div>)}
              <div className="card pad" style={{ display: 'grid', placeItems: 'center', borderStyle: 'dashed' }}><button className="btn ghost">＋ Module</button></div>
            </div>}
          </div>
        ))}
      </section>
    </div>
  );
}
