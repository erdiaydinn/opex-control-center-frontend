import { useState } from 'react';
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
  const [session, setSession] = useState(() => {
    try { return Boolean(localStorage.getItem('plonagram_access_token')); } catch { return false; }
  });
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState('');
  const [busy, setBusy] = useState(false);

  async function signIn(event) {
    event.preventDefault();
    setBusy(true);
    setAuthError('');
    try {
      const result = await api.login({ username, password });
      if (!result?.access_token) throw new Error(result?.message || 'Token alınamadı.');
      setSession(true);
    } catch (error) {
      setAuthError(error?.message || 'Giriş başarısız.');
    } finally {
      setBusy(false);
    }
  }

  function signOut() {
    api.logout();
    setSession(false);
  }

  if (!session) {
    return (
      <main className="auth-gate">
        <form className="auth-card" onSubmit={signIn}>
          <div className="section-eyebrow">PLONAGRAM FOUNDATION</div>
          <h1>Güvenli giriş</h1>
          <p className="muted">Plan üretimi, layout değişiklikleri ve audit kayıtları için oturum açın.</p>
          <label>Kullanıcı adı veya e-posta<input autoFocus value={username} onChange={(event) => setUsername(event.target.value)} /></label>
          <label>Şifre<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          {authError && <div className="auth-error">{authError}</div>}
          <button className="btn primary" disabled={busy || !username || !password}>{busy ? 'Giriş yapılıyor…' : 'Giriş yap'}</button>
          <small className="muted">Bootstrap parolası backend ortam değişkeninden belirlenir.</small>
        </form>
      </main>
    );
  }

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
        <button className="user-card" onClick={signOut} title="Oturumu kapat">
          <div className="avatar">EA</div>
          <div className="hide-narrow"><b>{username || 'Aktif kullanıcı'}</b><br/><span className="muted" style={{ fontSize: 12 }}>Oturumu kapat</span></div>
        </button>
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
