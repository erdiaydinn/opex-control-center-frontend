import React, { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Clock3,
  LogOut,
  Moon,
  Search,
  ShieldCheck,
  Sparkles,
  Sun,
} from "lucide-react";

import CommandModuleCard from "./CommandModuleCard.jsx";
import { commandModules } from "./commandCenterModules.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import "./control-center.css";

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Günaydın";
  if (hour < 18) return "İyi günler";
  return "İyi akşamlar";
}

function formatDateTr() {
  return new Intl.DateTimeFormat("tr-TR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
  }).format(new Date());
}

export default function ControlCenterHome() {
  const { user, logout, can, isSuperAdmin } = useAuth();

  const [query, setQuery] = useState("");
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("opex_theme") === "dark";
  });

  const visibleModules = useMemo(() => {
    const normalized = query.trim().toLowerCase();

    return commandModules
      .filter((module) => can(module.moduleKey, "view"))
      .filter((module) => {
        if (!normalized) return true;

        return [
          module.title,
          module.description,
          module.group,
          module.meta,
          module.moduleKey,
        ]
          .join(" ")
          .toLowerCase()
          .includes(normalized);
      });
  }, [can, query]);

  const readyCount = visibleModules.filter((module) => module.enabled).length;
  const lockedCount = visibleModules.length - readyCount;

  function toggleTheme() {
    setDarkMode((current) => {
      const next = !current;
      window.localStorage.setItem("opex_theme", next ? "dark" : "light");
      return next;
    });
  }

  return (
    <main className={`ocx-page ${darkMode ? "is-dark" : ""}`}>
      <div className="ocx-bg-grid" />
      <div className="ocx-orb orb-a" />
      <div className="ocx-orb orb-b" />
      <div className="ocx-orb orb-c" />
      <div className="ocx-noise" />

      <section className="ocx-shell">
        <motion.header
          className="ocx-topbar"
          initial={{ opacity: 0, y: -18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.48, ease: [0.16, 0.86, 0.22, 1] }}
        >
          <div className="ocx-brand">
            <div className="ocx-brand-mark">
              <Sparkles size={20} />
            </div>

            <div>
              <strong>OPEX</strong>
              <span>Control Center</span>
            </div>
          </div>

          <div className="ocx-top-actions">
            <div className="ocx-user-pill">
              <strong>{user?.email || "unknown user"}</strong>
              <span>{isSuperAdmin() ? "Super Admin" : "Authorized User"}</span>
            </div>

            <button type="button" className="ocx-icon-btn" onClick={toggleTheme}>
              {darkMode ? <Sun size={17} /> : <Moon size={17} />}
              {darkMode ? "Light" : "Dark"}
            </button>

            <button type="button" className="ocx-icon-btn danger" onClick={logout}>
              <LogOut size={17} />
              Çıkış
            </button>
          </div>
        </motion.header>

        <section className="ocx-hero-grid">
          <motion.div
            className="ocx-hero"
            initial={{ opacity: 0, x: -28, filter: "blur(10px)" }}
            animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.62, delay: 0.08, ease: [0.16, 0.86, 0.22, 1] }}
          >
            <div className="ocx-eyebrow">
              <ShieldCheck size={16} />
              {getGreeting()}, kontrol merkezi hazır.
            </div>

            <h1>OPEX</h1>

            <p>Operasyonel mükemmellik için omuz omuza.</p>

            <div className="ocx-search">
              <Search size={18} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Modül, operasyon alanı veya yetki ara..."
              />
            </div>
          </motion.div>

          <motion.aside
            className="ocx-command-panel"
            initial={{ opacity: 0, x: 28, filter: "blur(10px)" }}
            animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.62, delay: 0.16, ease: [0.16, 0.86, 0.22, 1] }}
          >
            <div className="ocx-panel-glare" />

            <div className="ocx-panel-head">
              <span>Command Status</span>
              <strong>{formatDateTr()}</strong>
            </div>

            <div className="ocx-metric-row">
              <div>
                <small>Görünen modül</small>
                <strong>{visibleModules.length}</strong>
              </div>

              <div>
                <small>Aktif erişim</small>
                <strong>{readyCount}</strong>
              </div>

              <div>
                <small>Hazırlanan</small>
                <strong>{lockedCount}</strong>
              </div>
            </div>

            <div className="ocx-live-strip">
              <Clock3 size={16} />
              <span>Role based görünüm aktif</span>
            </div>

            <div className="ocx-mini-map">
              {visibleModules.slice(0, 7).map((module) => (
                <span
                  key={module.id}
                  className={module.enabled ? "active" : "soon"}
                  title={module.title}
                />
              ))}
            </div>
          </motion.aside>
        </section>

        {visibleModules.length ? (
          <section className="ocx-module-grid">
            {visibleModules.map((module, index) => (
              <CommandModuleCard key={module.id} module={module} index={index} />
            ))}
          </section>
        ) : (
          <motion.section
            className="ocx-empty"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <strong>Bu kullanıcı için görünen modül yok.</strong>
            <p>Ana admin tarafından modül erişimi verilmesi gerekiyor.</p>
          </motion.section>
        )}
      </section>
    </main>
  );
}
