import React, { useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ArrowRight, ShieldCheck } from "lucide-react";

import { useAuth } from "../auth/AuthContext.jsx";
import { branding } from "../config/branding.js";
import EayBrand from "../platform/brand/EayBrand.jsx";

function requestedReturnTo(location) {
  const from = location.state?.from;
  if (!from || typeof from.pathname !== "string") return "/";
  return from.pathname + (from.search || "") + (from.hash || "");
}

export default function Login() {
  const location = useLocation();
  const { user, booting, login, authError } = useAuth();
  const [error, setError] = useState("");
  const [redirecting, setRedirecting] = useState(false);

  if (booting) {
    return (
      <main className="auth-loading-screen">
        <div className="auth-loading-card">
          <EayBrand variant="one" compact />
          <span>Oturum kontrol ediliyor…</span>
        </div>
      </main>
    );
  }

  if (user) return <Navigate to="/" replace />;

  async function signIn() {
    setError("");
    setRedirecting(true);
    try {
      await login({ returnTo: requestedReturnTo(location) });
    } catch (err) {
      setRedirecting(false);
      setError(err?.message || "SSO giriş akışı başlatılamadı.");
    }
  }

  return (
    <main className="ym-real-login inside eay-login">
      <section className="ym-real-inside">
        <div className="ym-real-inside-bg">
          {branding.loginImage ? <img src={branding.loginImage} alt="" /> : null}
        </div>

        <section className="ym-real-layout">
          <section className="ym-real-hero">
            <EayBrand variant="one" />
            <div className="ym-real-eyebrow">
              <ShieldCheck size={16} aria-hidden="true" />
              Kurumsal kimlik doğrulama
            </div>
            <h1>{branding.slogan}</h1>
            <p>Saha, envanter, iş gücü ve karar akışlarını EAY One altında birleştirin.</p>
            <span>
              Erişim yalnız kurumsal kimlik sağlayıcısı ve sunucu tarafından doğrulanan yetki kayıtlarıyla açılır.
            </span>
          </section>

          <section className="ym-real-card">
            <div className="ym-real-head">
              <div className="ym-real-icon"><ShieldCheck size={24} aria-hidden="true" /></div>
              <div>
                <span>Giriş</span>
                <h2>EAY One&apos;a eriş</h2>
              </div>
            </div>

            <div className="ym-real-form">
              <p>Yerel demo parola veya e-posta yetkilendirmesi kapalıdır. Kurumsal SSO kullanılır.</p>
              {authError ? <p className="ym-real-error">{authError}</p> : null}
              {error ? <p className="ym-real-error">{error}</p> : null}
              <button type="button" className="ym-real-submit" onClick={signIn} disabled={redirecting}>
                {redirecting ? "Kimlik sağlayıcısına yönlendiriliyor…" : "Kurumsal SSO ile giriş yap"}
                <ArrowRight size={18} aria-hidden="true" />
              </button>
            </div>
          </section>
        </section>
      </section>
    </main>
  );
}
