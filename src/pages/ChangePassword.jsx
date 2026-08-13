import React, { useState } from "react";
import { Eye, EyeOff, KeyRound, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";

export default function ChangePassword() {
  const navigate = useNavigate();
  const { user, changePassword, logout } = useAuth();
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (form.next.length < 12) {
      setError("Yeni parola en az 12 karakter olmalıdır.");
      return;
    }
    if (form.next !== form.confirm) {
      setError("Yeni parola ile tekrar alanı eşleşmiyor.");
      return;
    }
    setBusy(true);
    try {
      await changePassword(form.current, form.next);
      navigate("/", { replace: true });
    } catch (requestError) {
      setError(requestError.message || "Parola değiştirilemedi.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="password-change-page">
      <section className="password-change-card">
        <div className="password-change-icon"><ShieldCheck size={28} /></div>
        <span>GÜVENLİK ADIMI</span>
        <h1>Geçici parolanı değiştir.</h1>
        <p>{user?.email} hesabı için yeni bir parola belirlemeden modüllere erişemezsin.</p>

        <form onSubmit={submit}>
          <label>
            Geçici parola
            <div><KeyRound size={17} /><input required type={show ? "text" : "password"} autoComplete="current-password" value={form.current} onChange={(event) => setForm({ ...form, current: event.target.value })} /></div>
          </label>
          <label>
            Yeni parola
            <div><KeyRound size={17} /><input required minLength="12" type={show ? "text" : "password"} autoComplete="new-password" value={form.next} onChange={(event) => setForm({ ...form, next: event.target.value })} /></div>
          </label>
          <label>
            Yeni parola tekrar
            <div><KeyRound size={17} /><input required minLength="12" type={show ? "text" : "password"} autoComplete="new-password" value={form.confirm} onChange={(event) => setForm({ ...form, confirm: event.target.value })} /></div>
          </label>
          <button type="button" className="password-visibility" onClick={() => setShow((current) => !current)}>
            {show ? <EyeOff size={16} /> : <Eye size={16} />}{show ? "Parolaları gizle" : "Parolaları göster"}
          </button>
          {error ? <p className="password-change-error">{error}</p> : null}
          <button className="password-change-submit" disabled={busy}>{busy ? "Güncelleniyor…" : "Parolayı değiştir ve devam et"}</button>
        </form>

        <button className="password-change-logout" onClick={logout}>Oturumu kapat</button>
      </section>
    </main>
  );
}
