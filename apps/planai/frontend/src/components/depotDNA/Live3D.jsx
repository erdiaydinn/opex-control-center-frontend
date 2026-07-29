import { useMemo, useState } from 'react';
import { insights, products } from '../data/mock.js';
import { tt } from '../i18n/dictionary.js';

export default function Live3D({ lang }) {
  const [camera, setCamera] = useState('overview');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(products[0]);
  const filtered = useMemo(() => products.filter((p) => `${p.sku} ${p.name} ${p.brand}`.toLowerCase().includes(query.toLowerCase())).slice(0, 4), [query]);
  const stageClass = `stage camera-${camera} ${selected ? 'focused' : ''}`;
  const t = (k) => tt(lang, k);
  return (
    <div className="page">
      <div className="section-eyebrow">3D STUDIO</div>
      <h1 style={{ margin: '8px 0 4px', fontSize: 42 }}>{t('liveTitle')} <span className="pink">•</span></h1>
      <p className="page-sub" style={{ marginTop: 0 }}>{t('liveSub')}</p>
      <div className="live-layout" style={{ marginTop: 22 }}>
        <div className={stageClass}>
          <div className="overlay-head">
            <div className="card pad" style={{ padding: '14px 18px' }}><b>Occupancy</b><br/><span style={{ fontSize: 28, fontWeight: 900 }}>87%</span></div>
            <div className="tabs">
              {[['overview', t('overview')], ['top', t('topView')], ['chilled', t('chilled')], ['frozen', t('frozen')], ['dispatch', t('dispatch')]].map(([k, label]) => <button key={k} className={`tab ${camera === k ? 'active' : ''}`} onClick={() => setCamera(k)}>{label}</button>)}
            </div>
          </div>
          <div className="warehouse3d">
            <div className="rack a focus"/><div className="rack b"/><div className="rack c"/><div className="rack d"/><div className="rack e"/>
            <div className="chilled-block">+4<br/>CHILLED</div><div className="frozen-block">-18<br/>FROZEN</div><div className="dispatch-block">DISPATCH</div>
            <div className="route"/><div className="marker m1"/><div className="marker m2"/>
          </div>
          <div className="float-tag" style={{ left: 60, bottom: 120 }}>⚠ Refill Needed<br/><span className="muted">Aisle 04 • Shelf 12</span></div>
          <div className="float-tag" style={{ left: '48%', bottom: 90 }}>△ High Congestion<br/><span className="muted">Aisle 07</span></div>
          <div className="float-tag" style={{ right: 110, bottom: 115 }}>▣ Dispatch<br/><span className="muted">Zone D1-D4</span></div>
          <div className="stage-toolbar">
            {['Layers', 'Heatmap', t('followRoute'), 'Traffic', 'Facilities'].map((x) => <button className="tab" key={x} onClick={() => setCamera(x === t('followRoute') ? 'followRoute' : camera)}>{x}</button>)}
          </div>
        </div>
        <aside className="side-panel">
          <div className="card pad">
            <div className="section-eyebrow">{t('camera')}</div>
            <div className="grid cols-2" style={{ marginTop: 14 }}>
              {[['overview', 'Overview'], ['chilled', 'Chilled'], ['frozen', 'Frozen'], ['dispatch', 'Dispatch']].map(([k, l]) => <button className={`tab ${camera === k ? 'active' : ''}`} key={k} onClick={() => setCamera(k)}>{l}</button>)}
            </div>
          </div>
          <div className="card pad">
            <div className="section-eyebrow">{t('searchSku')}</div>
            <input className="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t('searchSku')} />
            <div className="list" style={{ marginTop: 12 }}>
              {filtered.map((p) => <button className="item" key={p.sku} onClick={() => setSelected(p)}><div><b>{p.sku}</b><div className="muted">{p.name}<br/>Zone {p.storage} • Shelf 07</div></div><span className={`badge ${p.storage === 'CHILLED' ? 'cyan' : p.storage === 'FROZEN' ? 'purple' : 'green'}`}>{p.storage}</span></button>)}
            </div>
          </div>
          <div className="card pad"><div className="section-eyebrow">{t('selected')}</div><h3>{selected?.name}</h3><p className="muted">{selected?.brand} • {selected?.category} • Facing {selected?.facing}</p><span className="badge">Camera focus active</span></div>
          <div className="card pad"><div className="section-eyebrow">{t('insights')}</div><div className="list">{insights.slice(0,3).map((i) => <div className="item" key={i.title}><div><b>{i.title}</b><div className="muted">{i.text}</div></div></div>)}</div></div>
        </aside>
      </div>
    </div>
  );
}
