import { metrics, insights } from '../data/mock.js';
import { tt } from '../i18n/dictionary.js';

function Kpi({ m, lang }) {
  return (
    <div className="card kpi">
      <div className="kpi-label">{tt(lang, m.key)}</div>
      <div><span className={`kpi-value ${m.tone}`}>{m.value}</span> <span className="muted">{m.suffix}</span></div>
      <div className="kpi-trend">↗ {m.trend} vs last 7 days</div>
    </div>
  );
}

export default function CommandCenter({ lang, setActive }) {
  return (
    <div className="page">
      <section className="hero">
        <div className="hero-copy">
          <div className="section-eyebrow">WELCOME TO PLONAGRAM OS</div>
          <h1 className="page-title">{tt(lang, 'heroTitle')}</h1>
          <p className="page-sub">{tt(lang, 'heroSub')}</p>
          <div style={{ display: 'flex', gap: 12, marginTop: 30, flexWrap: 'wrap' }}>
            <button className="btn primary" onClick={() => setActive('planogram')}>✦ {tt(lang, 'generate')}</button>
            <button className="btn ghost" onClick={() => setActive('live3d')}>▧ {tt(lang, 'openStudio')}</button>
          </div>
        </div>
        <div className="hero-visual">
          <div className="iso-grid" />
          <div className="iso-rack r1 hot" />
          <div className="iso-rack r2" />
          <div className="iso-rack r3" />
          <div className="route-line" />
          <div className="float-tag" style={{ left: '18%', top: '60%' }}><span className="pink">Refill Priority</span><br/>High</div>
          <div className="float-tag" style={{ right: '12%', top: '20%' }}>Overstock Risk<br/><span className="pink">-18%</span></div>
          <div className="float-tag" style={{ right: '10%', bottom: '18%' }}>DISPATCH<br/><span className="muted">Zone B-12</span></div>
        </div>
      </section>
      <section className="grid cols-4" style={{ marginTop: 24 }}>
        {metrics.map((m) => <Kpi key={m.key} m={m} lang={lang} />)}
      </section>
      <section className="grid cols-2" style={{ marginTop: 24 }}>
        <div className="card pad">
          <div className="section-eyebrow">LIVE DIGITAL TWIN</div>
          <h2>Real-time warehouse replica</h2>
          <div className="hero-visual" style={{ minHeight: 310, marginTop: 16 }}>
            <div className="iso-grid" /><div className="iso-rack r1 hot"/><div className="iso-rack r2"/><div className="iso-rack r3"/>
          </div>
          <button className="btn ghost" onClick={() => setActive('live3d')} style={{ marginTop: 14 }}>Open 3D Studio →</button>
        </div>
        <div className="card pad">
          <div className="section-eyebrow">AI INSIGHTS</div>
          <h2>Intelligent recommendations</h2>
          <div className="list" style={{ marginTop: 18 }}>
            {insights.map((i) => <div key={i.title} className="item"><div><b>{i.title}</b><div className="muted">{i.text}</div></div><span className={`badge ${i.tone}`}>{i.impact}</span></div>)}
          </div>
        </div>
      </section>
    </div>
  );
}
