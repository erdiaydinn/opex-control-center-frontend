import BrandLogo from './BrandLogo.jsx';
import { languages, tt } from '../i18n/dictionary.js';
import { stores } from '../data/mock.js';

const navItems = [
  ['command', '⌂'], ['live3d', '▧'], ['architect', '⌗'], ['placement', '▦'], ['library', '⌕'], ['fixture', '▤'], ['planogram', '▥'], ['delta', '↔'], ['publishing', '⇪'], ['tasks', '☑'], ['reports', '◷'], ['admin', '⚙']
];

export default function Shell({ lang, setLang, active, setActive, children, store, setStore }) {
  const t = (key) => tt(lang, key);
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <BrandLogo />
        <nav className="nav">
          {navItems.map(([key, icon]) => (
            <button key={key} className={`nav-btn ${active === key ? 'active' : ''}`} onClick={() => setActive(key)}>
              <span>{icon}</span><span className="hide-narrow">{t(key)}</span>
            </button>
          ))}
        </nav>
        <div className="user-card">
          <div className="avatar">EA</div>
          <div className="hide-narrow">
            <div style={{ fontWeight: 900 }}>Erdi A.</div>
            <div className="muted" style={{ fontSize: 12 }}>Enterprise Admin</div>
          </div>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div className="top-left">
            <div className="pill"><span className="icon-dot" /> <span className="muted">{t('status')}</span> <b>{t('online')}</b></div>
            <select className="select" value={store} onChange={(e) => setStore(e.target.value)} aria-label={t('activeStore')}>
              {stores.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
            </select>
            <select className="select" value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Language">
              {languages.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </div>
          <div className="top-actions">
            <button className="btn ghost">↥ {t('uploadSku')}</button>
            <button className="btn ghost">▧ {t('uploadLayout')}</button>
            <button className="btn primary" onClick={() => setActive('planogram')}>✦ {t('generate')}</button>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
