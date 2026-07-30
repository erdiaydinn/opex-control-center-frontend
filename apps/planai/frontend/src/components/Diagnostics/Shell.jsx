import BrandLogo from './BrandLogo.jsx';
import { languages, tt } from '../i18n/dictionary.js';
import { stores } from '../data/mock.js';

const nav = [
  ['command', '⌂', 'command'], ['live3d', '▣', 'live3d'], ['architect', '╬', 'architect'], ['placement', '▤', 'placement'],
  ['library', '⌕', 'library'], ['fixture', '▦', 'fixture'], ['planogram', '▥', 'planogram'], ['rules', '✦', 'rules'],
  ['delta', '↔', 'delta'], ['publishing', '⇪', 'publishing'], ['tasks', '☑', 'tasks'], ['photos', '◉', 'photos'], ['reports', '◎', 'reports'], ['admin', '⚙', 'admin']
];

export default function Shell({ children, lang, setLang, active, setActive, store, setStore, onGenerate, onUploadSku, onUploadLayout }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block"><BrandLogo /></div>
        <nav className="nav">
          {nav.map(([key, icon, label]) => (
            <button className={`nav-btn ${active === key ? 'active' : ''}`} key={key} onClick={() => setActive(key)}>
              <span className="nav-icon">{icon}</span><span className="hide-narrow">{tt(lang, label)}</span>
            </button>
          ))}
        </nav>
        <div className="user-card">
          <div className="avatar">EA</div>
          <div className="hide-narrow"><b>Erdi A.</b><br/><span className="muted" style={{ fontSize: 12 }}>Enterprise Admin</span></div>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div className="top-left">
            <div className="pill"><span className="icon-dot" /> {tt(lang, 'system')} <b>{tt(lang, 'online')}</b></div>
            <select className="select" value={store} onChange={(e) => setStore(e.target.value)}>
              {stores.filter(s => s.code !== 'ALL').map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
            </select>
            <select className="select" value={lang} onChange={(e) => setLang(e.target.value)}>
              {languages.map((l) => <option key={l} value={l}>{l.toUpperCase()}</option>)}
            </select>
          </div>
          <div className="top-actions">
            <button className="btn ghost" onClick={onUploadSku}>↑ {tt(lang, 'uploadSku')}</button>
            <button className="btn ghost" onClick={onUploadLayout}>▣ {tt(lang, 'uploadLayout')}</button>
            <button className="btn primary" onClick={onGenerate}>✦ {tt(lang, 'generate')}</button>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
