import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "./AuthContext.jsx";


export default function AuthCallback() {
  const navigate = useNavigate();
  const { completeLogin } = useAuth();
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    completeLogin()
      .then((returnTo) => {
        if (!active) return;

        navigate(returnTo || "/", {
          replace: true,
        });
      })
      .catch(() => {
        if (!active) return;

        setError(
          "Kimlik do?rulama tamamlanamad? veya bu kullan?c? i?in aktif uygulama eri?imi bulunamad?."
        );
      });

    return () => {
      active = false;
    };
  }, [completeLogin, navigate]);

  if (error) {
    return (
      <main className="auth-loading-screen">
        <div className="auth-loading-card">
          <strong>Giri? reddedildi</strong>
          <span>{error}</span>
          <button
            type="button"
            onClick={() =>
              navigate("/login", {
                replace: true,
              })
            }
          >
            Giri? ekran?na d?n
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="auth-loading-screen">
      <div className="auth-loading-card">
        <strong>OPEX</strong>
        <span>
          Kimlik ve veritaban? yetkileri do?rulan?yor...
        </span>
      </div>
    </main>
  );
}
