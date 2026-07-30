import { useEffect, useMemo, useState } from 'react';
import BrandLogo from './BrandLogo.jsx';
import { api } from '../services/api.js';
import { languages, tt } from '../i18n/dictionary.js';
import { stores } from '../data/mock.js';

const nav = [
  ['command', '⌂', 'command'], ['storeDna', '◈', 'storeDna'], ['live3d', '▣', 'live3d'], ['architect', '╬', 'architect'], ['placement', '▤', 'placement'],
  ['library', '⌕', 'library'], ['fixture', '▦', 'fixture'], ['planogram', '▥', 'planogram'], ['rules', '✦', 'rules'],
  ['delta', '↔', 'delta'], ['publishing', '⇪', 'publishing'], ['tasks', '☑', 'tasks'], ['photos', '◉', 'photos'], ['reports', '◎', 'reports'], ['admin', '⚙', 'admin']
];

export default function Shell({ children, lang, setLang, active, setActive, store, setStore, onGenerate, onUploadSku, onUploadLayout }) {
  const [session, setSession] = useState(null);
  const [authError, setAuthError] = useState('');
  const embedded = typeof window !== 'undefined' && window.parent !== window;
  const allowedParentOrigins = useMemo(() => {
    const configured = String(import.meta.env?.VITE_OPEX_PARENT_ORIGINS || '')
      .split(',')
      .map((value) => value.trim().replace(/\/$/, ''))
      .filter(Boolean);
    return new Set(configured.length ? configured : [
      'http://localhost:5173',
      'http://127.0.0.1:5173',
    ]);
  }, []);

  useEffect(() => {
    if (!embedded) {
      const opexUrl = import.meta.env?.VITE_OPEX_APP_URL || 'http://localhost:5173';
      const timer = window.setTimeout(() => {
        window.location.replace(`${opexUrl.replace(/\/$/, '')}/planogram`);
      }, 900);
      return () => window.clearTimeout(timer);
    }

    let mounted = true;

    async function acceptOpexSession(event) {
      if (!allowedParentOrigins.has(String(event.origin || '').replace(/\/$/, ''))) return;
      if (event.source !== window.parent) return;
      if (event.data?.type !== 'OPEX_PLANOGRAM_SESSION' || event.data?.version !== 1) return;

      const payload = event.data.payload || {};
      try {
        setAuthError('');
        let result;
        if (payload.accessToken) {
          result = api.adoptOpexSession({
            access_token: payload.accessToken,
            token_type: 'bearer',
            user: payload.user,
          });
        } else {
          result = await api.exchangeOpexDevSession({
            user: payload.user,
            permissions: payload.permissions,
            scope: payload.scope,
          });
        }
        if (mounted) {
          setSession(result);
          window.parent.postMessage({ type: 'PLANOGRAM_SESSION_ACCEPTED', version: 1 }, event.origin);
        }
      } catch (error) {
        if (mounted) setAuthError(error?.message || 'OPEX oturumu doğrulanamadı.');
      }
    }

    window.addEventListener('message', acceptOpexSession);
    window.parent.postMessage({ type: 'PLANOGRAM_READY', version: 1 }, '*');
    return () => {
      mounted = false;
      window.removeEventListener('message', acceptOpexSession);
    };
  }, [allowedParentOrigins, embedded]);

  const permissions = session?.user?.permissions || {};
  const features = permissions.features || {};
  const actions = permissions.actions || {};
  const isAdmin = Boolean(permissions.admin || actions.approve || actions.delete);

  const visibleNav = nav.filter(([key]) => {
    if (permissions.admin) return true;
    const featureByPage = {
      command: 'layoutView',
      storeDna: 'layoutView',
      live3d: 'layoutView',
      architect: 'layoutEdit',
      placement: 'productAssign',
      library: 'layoutView',
      fixture: 'fixtureEdit',
      planogram: 'layoutView',
      rules: 'ruleEdit',
      delta: 'layoutView',
      publishing: 'productAssign',
      tasks: 'layoutView',
      photos: 'productAssign',
      reports: 'layoutView',
    };
    if (key === 'admin') return isAdmin;
    const feature = featureByPage[key];
    return !feature || Boolean(features[feature]);
  });

  if (!session) {
    return (
      <main className="auth-gate">
        <section className="auth-card">
          <div className="section-eyebrow">OPEX CONTROL CENTER</div>
          <h1>{embedded ? 'Oturum doğrulanıyor' : 'OPEX’e yönlendiriliyorsun'}</h1>
          <p className="muted">
            {embedded
              ? 'Planogram yetkileri ve depo kapsamı merkezi Access Control üzerinden alınıyor.'
              : 'Planogram Studio yalnızca OPEX Control Center oturumu içinde açılır.'}
          </p>
          {authError && <div className="auth-error">{authError}</div>}
        </section>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block"><BrandLogo /></div>
        <nav className="nav">
          {visibleNav.map(([key, icon, label]) => (
            <button className={`nav-btn ${active === key ? 'active' : ''}`} key={key} onClick={() => setActive(key)}>
              <span className="nav-icon">{icon}</span><span className="hide-narrow">{tt(lang, label)}</span>
            </button>
          ))}
        </nav>
        <div className="user-card" title="OPEX oturumu">
          <div className="avatar">EA</div>
          <div className="hide-narrow"><b>{session?.user?.name || session?.user?.email || 'Aktif kullanıcı'}</b><br/><span className="muted" style={{ fontSize: 12 }}>OPEX oturumu</span></div>
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
            {(actions.create || permissions.admin) && <button className="btn ghost" onClick={onUploadSku}>↑ {tt(lang, 'uploadSku')}</button>}
            {(actions.edit || permissions.admin) && <button className="btn ghost" onClick={onUploadLayout}>▣ {tt(lang, 'uploadLayout')}</button>}
            {(actions.create || permissions.admin) && <button className="btn primary" onClick={onGenerate}>✦ {tt(lang, 'generate')}</button>}
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
