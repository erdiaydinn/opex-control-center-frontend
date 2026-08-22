import React, { useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ArrowRight, ShieldCheck } from "lucide-react";

import { useAuth } from "../auth/AuthContext.jsx";
import { branding } from "../config/branding.js";
import EayBrand from "../platform/brand/EayBrand.jsx";
import { translateLogin } from "../platform/i18n/loginMessages.js";
import { usePlatformPreferences } from "../platform/preferences/PlatformPreferencesContext.jsx";

function requestedReturnTo(location) {
  const from = location.state?.from;
  if (!from || typeof from.pathname !== "string") return "/";
  return from.pathname + (from.search || "") + (from.hash || "");
}

export default function Login() {
  const location = useLocation();
  const { user, booting, login, authError } = useAuth();
  const { locale } = usePlatformPreferences();
  const tx = (key) => translateLogin(locale, key);
  const [error, setError] = useState("");
  const [redirecting, setRedirecting] = useState(false);

  if (booting) {
    return (
      <main className="auth-loading-screen">
        <div className="auth-loading-card">
          <EayBrand variant="one" compact />
          <span>{tx("checkingSession")}</span>
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
      setError(err?.message || tx("ssoFlowFailed"));
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
              {tx("identityVerification")}
            </div>
            <h1>{branding.slogan}</h1>
            <p>{tx("platformStatement")}</p>
            <span>{tx("accessStatement")}</span>
          </section>

          <section className="ym-real-card">
            <div className="ym-real-head">
              <div className="ym-real-icon"><ShieldCheck size={24} aria-hidden="true" /></div>
              <div>
                <span>{tx("signIn")}</span>
                <h2>{tx("accessEayOne")}</h2>
              </div>
            </div>

            <div className="ym-real-form">
              <p>{tx("ssoOnly")}</p>
              {authError ? <p className="ym-real-error">{authError}</p> : null}
              {error ? <p className="ym-real-error">{error}</p> : null}
              <button type="button" className="ym-real-submit" onClick={signIn} disabled={redirecting}>
                {redirecting ? tx("redirecting") : tx("signInWithSso")}
                <ArrowRight size={18} aria-hidden="true" />
              </button>
            </div>
          </section>
        </section>
      </section>
    </main>
  );
}
