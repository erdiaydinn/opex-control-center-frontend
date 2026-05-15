import React, { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { LogOut, Moon, ShieldCheck, Sparkles, Sun } from "lucide-react";

import CommandModuleCard from "./CommandModuleCard.jsx";
import { commandModules, commandStats } from "./commandCenterModules.js";
import { useAuth } from "../../auth/AuthContext.jsx";
import "./control-center.css";

export default function ControlCenterHome() {
  const { user, logout, can, isSuperAdmin } = useAuth();

  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("opex_theme") === "dark";
  });

  const greeting = useMemo(() => {
    const hour = new Date().getHours();

    if (hour < 12) return "Günaydın";
    if (hour < 18) return "İyi günler";
    return "İyi akşamlar";
  }, []);

  const visibleModules = useMemo(() => {
    return commandModules.filter((module) => can(module.moduleKey, "view"));
  }, [can]);

  const visibleStats = useMemo(() => {
    const activeCount = visibleModules.filter((module) => module.enabled).length;

    return [
      {
        label: "Görünen modül",
        value: String(visibleModules.length),
        detail: isSuperAdmin() ? "Super admin görünümü" : "Yetkine göre filtrelendi",
      },
      {
        label: "Aktif erişim",
        value: String(activeCount),
        detail: "Kullanıma açık modül",
      },
      {
        label: "OPEX ruhu",
        value: "Together",
        detail: "Omuz omuza gelişim",
      },
    ];
  }, [visibleModules, isSuperAdmin]);

  const toggleTheme = () => {
    setDarkMode((current) => {
      const next = !current;
      window.localStorage.setItem("opex_theme", next ? "dark" : "light");
      return next;
    });
  };

  const handleLogout = () => {
    logout();
  };

  return (
    <main className={`opgrid-page ${darkMode ? "is-dark" : ""}`}>
      <div className="opgrid-bg-grid" />
      <div className="opgrid-light opgrid-light-a" />
      <div className="opgrid-light opgrid-light-b" />
      <div className="opgrid-noise" />

      <section className="opgrid-shell">
        <motion.header
          className="opgrid-topbar"
          initial={{ opacity: 0, y: -18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: "easeOut" }}
        >
          <div className="opgrid-brand">
            <div className="opgrid-brand-mark">
              <Sparkles size={20} />
            </div>

            <div>
              <strong>OPEX</strong>
              <span>Control Center</span>
            </div>
          </div>

          <div className="opgrid-user-actions">
            <div className="opgrid-user-pill">
              <strong>{user?.email}</strong>
              <span>{isSuperAdmin() ? "Super Admin" : "User"}</span>
            </div>

            <button className="opgrid-theme-btn" onClick={toggleTheme} type="button">
              {darkMode ? <Sun size={17} /> : <Moon size={17} />}
              {darkMode ? "Light Mode" : "Dark Mode"}
            </button>

            <button className="opgrid-theme-btn danger" onClick={handleLogout} type="button">
              <LogOut size={17} />
              Çıkış
            </button>
          </div>
        </motion.header>

        <motion.section
          className="opgrid-hero"
          initial={{ opacity: 0, y: 26 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.62, delay: 0.05, ease: "easeOut" }}
        >
          <div className="opgrid-eyebrow">
            <ShieldCheck size={16} />
            {greeting}, kontrol merkezi hazır.
          </div>

          <h1>OPEX</h1>

          <p>Operasyonel mükemmellik için omuz omuza.</p>
        </motion.section>

        <motion.section
          className="opgrid-stats"
          initial={{ opacity: 0, y: 22 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.52, delay: 0.16, ease: "easeOut" }}
        >
          {visibleStats.map((stat) => (
            <div className="opgrid-stat" key={stat.label}>
              <span>{stat.label}</span>
              <strong>{stat.value}</strong>
              <p>{stat.detail}</p>
            </div>
          ))}
        </motion.section>

        {visibleModules.length ? (
          <section className="opgrid-module-grid">
            {visibleModules.map((module, index) => (
              <CommandModuleCard key={module.id} module={module} index={index} />
            ))}
          </section>
        ) : (
          <section className="opgrid-empty-state">
            <strong>Bu kullanıcı için atanmış modül yok.</strong>
            <p>Ana admin tarafından modül erişimi verilmesi gerekiyor.</p>
          </section>
        )}
      </section>
    </main>
  );
}
