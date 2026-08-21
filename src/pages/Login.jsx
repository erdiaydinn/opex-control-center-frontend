import React, { useState } from "react";
import {
  Navigate,
  useLocation,
} from "react-router-dom";
import {
  ArrowRight,
  ShieldCheck,
} from "lucide-react";

import { useAuth } from "../auth/AuthContext.jsx";
import { branding } from "../config/branding.js";


function requestedReturnTo(location) {
  const from = location.state?.from;

  if (!from || typeof from.pathname !== "string") {
    return "/";
  }

  return (
    from.pathname +
    (from.search || "") +
    (from.hash || "")
  );
}


export default function Login() {
  const location = useLocation();

  const {
    user,
    booting,
    login,
    authError,
  } = useAuth();

  const [error, setError] = useState("");
  const [redirecting, setRedirecting] =
    useState(false);

  if (booting) {
    return (
      <main className="auth-loading-screen">
        <div className="auth-loading-card">
          <strong>OPEX</strong>
          <span>Oturum kontrol ediliyor...</span>
        </div>
      </main>
    );
  }

  if (user) {
    return <Navigate to="/" replace />;
  }

  async function signIn() {
    setError("");
    setRedirecting(true);

    try {
      await login({
        returnTo: requestedReturnTo(location),
      });
    } catch (err) {
      setRedirecting(false);
      setError(
        err?.message ||
          "SSO giri? ak??? ba?lat?lamad?."
      );
    }
  }

  return (
    <main className="ym-real-login inside">
      <section className="ym-real-inside">
        <div className="ym-real-inside-bg">
          {branding.loginImage ? (
            <img
              src={branding.loginImage}
              alt=""
            />
          ) : null}
        </div>

        <section className="ym-real-layout">
          <section className="ym-real-hero">
            <div className="ym-real-eyebrow">
              <ShieldCheck size={16} />
              Kurumsal kimlik do?rulama
            </div>

            <h1>
              {branding.companyName ||
                branding.productName}
            </h1>

            <p>
              {branding.productName}
            </p>

            <span>
              Eri?im, kimlik sa?lay?c?s? ve
              veritaban?ndaki tenant / rol /
              permission kay?tlar? ile do?rulan?r.
            </span>
          </section>

          <section className="ym-real-card">
            <div className="ym-real-head">
              <div className="ym-real-icon">
                <ShieldCheck size={24} />
              </div>

              <div>
                <span>Giri?</span>
                <h2>Kontrol merkezine eri?</h2>
              </div>
            </div>

            <div className="ym-real-form">
              <p>
                Yerel demo parola veya e-posta
                yetkilendirmesi devre d???d?r.
              </p>

              {authError ? (
                <p className="ym-real-error">
                  {authError}
                </p>
              ) : null}

              {error ? (
                <p className="ym-real-error">
                  {error}
                </p>
              ) : null}

              <button
                type="button"
                className="ym-real-submit"
                onClick={signIn}
                disabled={redirecting}
              >
                {redirecting
                  ? "Kimlik sa?lay?c?s?na y?nlendiriliyor..."
                  : "Kurumsal SSO ile giri? yap"}

                <ArrowRight size={18} />
              </button>
            </div>
          </section>
        </section>
      </section>
    </main>
  );
}
