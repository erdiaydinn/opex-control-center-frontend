import React, { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { useAuth } from "../auth/AuthContext.jsx";

const DEMO_USERS = [
  "admin@yemeksepeti.com",
  "viewer@yemeksepeti.com",
  "noaccess@yemeksepeti.com",
];

const t = {
  badge: "OPEX",
  title: "OPEX Control Center",
  desc: "Yetkili operasyon ekranlar\u0131na eri\u015fim i\u00e7in giri\u015f yap\u0131n.",
  email: "Email",
  login: "Giri\u015f yap",
};

export default function Login() {
  const navigate = useNavigate();
  const { user, login } = useAuth();
  const [email, setEmail] = useState(DEMO_USERS[0]);
  const [error, setError] = useState("");

  if (user) return <Navigate to="/" replace />;

  async function submit(e) {
    e.preventDefault();
    setError("");

    try {
      await login(email);
      navigate("/");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-card">
        <div className="brand-mark">
          <ShieldCheck size={30} />
        </div>

        <p className="eyebrow">{t.badge}</p>
        <h1>{t.title}</h1>
        <p className="muted">{t.desc}</p>

        <form onSubmit={submit} className="login-form">
          <label>{t.email}</label>

          <select value={email} onChange={(e) => setEmail(e.target.value)}>
            {DEMO_USERS.map((demo) => (
              <option key={demo} value={demo}>
                {demo}
              </option>
            ))}
          </select>

          {error ? <p className="error-text">{error}</p> : null}

          <button type="submit">{t.login}</button>
        </form>
      </section>
    </main>
  );
}
