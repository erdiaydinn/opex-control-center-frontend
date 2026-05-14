import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Activity,
  ArrowRight,
  Gauge,
  Radar,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  Zap,
} from "lucide-react";

import CommandBackground from "./CommandBackground.jsx";
import CommandModuleCard from "./CommandModuleCard.jsx";
import { commandModules, commandStats, liveSignals } from "./commandCenterModules.js";
import "./control-center.css";

export default function ControlCenterHome() {
  const greeting = useMemo(() => {
    const hour = new Date().getHours();

    if (hour < 12) return "Günaydın";
    if (hour < 18) return "İyi günler";
    return "İyi akşamlar";
  }, []);

  return (
    <main className="cc-page">
      <CommandBackground />

      <section className="cc-shell">
        <motion.header
          className="cc-topbar"
          initial={{ opacity: 0, y: -18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: "easeOut" }}
        >
          <div className="cc-brand">
            <div className="cc-brand-mark">
              <Sparkles size={20} />
            </div>
            <div>
              <strong>OPEX</strong>
              <span>Control Center</span>
            </div>
          </div>

          <div className="cc-live-pill">
            <span className="cc-live-dot" />
            Command Center V2
          </div>
        </motion.header>

        <section className="cc-hero">
          <motion.div
            className="cc-hero-copy"
            initial={{ opacity: 0, y: 34, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.7, ease: "easeOut" }}
          >
            <div className="cc-eyebrow">
              <ShieldCheck size={17} />
              {greeting}, kontrol merkezi hazır.
            </div>

            <h1>
              Tek ekran.
              <span> Tam hakimiyet.</span>
            </h1>

            <p className="cc-lead">
              Kritik operasyon modüllerini tek merkezden açın. Öncelikleri görün,
              riskleri yakalayın, aksiyonu hızlandırın.
            </p>

            <div className="cc-hero-actions">
              <Link to="/planogram" className="cc-primary-btn">
                Planogram Studio
                <ArrowRight size={18} />
              </Link>

              <Link to="/dockos" className="cc-secondary-btn">
                DockOS
                <TerminalSquare size={17} />
              </Link>
            </div>

            <div className="cc-mini-strip">
              <span>
                <Gauge size={15} />
                Live module deck
              </span>
              <span>
                <Radar size={15} />
                Risk visibility
              </span>
              <span>
                <Zap size={15} />
                Fast action
              </span>
            </div>
          </motion.div>

          <motion.aside
            className="cc-command-panel"
            initial={{ opacity: 0, x: 32, rotateY: -7 }}
            animate={{ opacity: 1, x: 0, rotateY: 0 }}
            transition={{ duration: 0.72, delay: 0.08, ease: "easeOut" }}
          >
            <div className="cc-panel-header">
              <div>
                <span>Live Operations</span>
                <strong>Command Deck</strong>
              </div>
              <Activity size={22} />
            </div>

            <div className="cc-radar-core">
              <div className="cc-radar-visual">
                <span className="cc-radar-sweep" />
                <i className="r1" />
                <i className="r2" />
                <i className="r3" />
                <b className="dot d1" />
                <b className="dot d2" />
                <b className="dot d3" />
              </div>

              <div>
                <strong>Operational Pulse</strong>
                <span>Sistem açık. Modüller erişime hazır.</span>
              </div>
            </div>

            <div className="cc-live-grid">
              {liveSignals.map((item) => (
                <div className={`cc-live-card tone-${item.tone}`} key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          </motion.aside>
        </section>

        <motion.section
          className="cc-stats-grid"
          initial={{ opacity: 0, y: 26 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.58, delay: 0.16, ease: "easeOut" }}
        >
          {commandStats.map((stat) => (
            <div className="cc-stat-card" key={stat.label}>
              <span>{stat.label}</span>
              <strong>{stat.value}</strong>
              <p>{stat.detail}</p>
            </div>
          ))}
        </motion.section>

        <section className="cc-section-head">
          <div>
            <span>Module Access</span>
            <h2>Operasyon modülleri</h2>
          </div>
          <p>
            Aktif modüller doğrudan açılır. Hazırlık aşamasındaki alanlar kilitli
            kalır; ana akış sade ve kontrollü tutulur.
          </p>
        </section>

        <section className="cc-module-grid">
          {commandModules.map((module, index) => (
            <CommandModuleCard key={module.id} module={module} index={index} />
          ))}
        </section>
      </section>
    </main>
  );
}
