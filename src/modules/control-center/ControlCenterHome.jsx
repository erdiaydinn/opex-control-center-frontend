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
import { translateControlCenter } from "../../platform/i18n/controlCenterMessages.js";
import { usePlatformPreferences } from "../../platform/preferences/PlatformPreferencesContext.jsx";
import "./control-center.css";

const PRODUCT_NAME = "EAY";
const PRODUCT_SUITE = "OneOps";

function greetingKey() {
  const hour = new Date().getHours();
  if (hour < 12) return "greetingMorning";
  if (hour < 18) return "greetingDay";
  return "greetingEvening";
}

function localizeModule(module, locale) {
  const text = (key) => translateControlCenter(locale, key);
  const owned = typeof module.localize === "function" ? module.localize(locale) : {};
  return {
    ...module,
    title: owned.title ?? text(module.titleKey),
    description: owned.description ?? text(module.descriptionKey),
    group: owned.group ?? text(module.groupKey),
    meta: owned.meta ?? text(module.metaKey),
    healthLabel: owned.healthLabel ?? text(module.healthLabelKey),
  };
}

export default function ControlCenterHome() {
  const { user, logout, can, isSuperAdmin } = useAuth();
  const { locale, formatDate, accessibility } = usePlatformPreferences();
  const cc = (key, params) => translateControlCenter(locale, key, params);
  const reduceMotion = Boolean(accessibility.reduceMotion);

  const [query, setQuery] = useState("");
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("opex_theme") === "dark";
  });

  const visibleModules = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase(locale);

    return commandModules
      .filter((module) => can(module.moduleKey, "view"))
      .map((module) => localizeModule(module, locale))
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
          .toLocaleLowerCase(locale)
          .includes(normalized);
      });
  }, [can, locale, query]);

  const readyCount = visibleModules.filter((module) => module.enabled).length;
  const lockedCount = visibleModules.length - readyCount;

  function toggleTheme() {
    setDarkMode((current) => {
      const next = !current;
      window.localStorage.setItem("opex_theme", next ? "dark" : "light");
      return next;
    });
  }

  const topbarMotion = reduceMotion
    ? { initial: false, transition: { duration: 0 } }
    : {
        initial: { opacity: 0, y: -18 },
        transition: { duration: 0.48, ease: [0.16, 0.86, 0.22, 1] },
      };
  const heroMotion = reduceMotion
    ? { initial: false, transition: { duration: 0 } }
    : {
        initial: { opacity: 0, x: -28, filter: "blur(10px)" },
        transition: { duration: 0.62, delay: 0.08, ease: [0.16, 0.86, 0.22, 1] },
      };
  const panelMotion = reduceMotion
    ? { initial: false, transition: { duration: 0 } }
    : {
        initial: { opacity: 0, x: 28, filter: "blur(10px)" },
        transition: { duration: 0.62, delay: 0.16, ease: [0.16, 0.86, 0.22, 1] },
      };

  return (
    <main className={`ocx-page ${darkMode ? "is-dark" : ""}`}>
      <div className="ocx-bg-grid" aria-hidden="true" />
      <div className="ocx-orb orb-a" aria-hidden="true" />
      <div className="ocx-orb orb-b" aria-hidden="true" />
      <div className="ocx-orb orb-c" aria-hidden="true" />
      <div className="ocx-noise" aria-hidden="true" />

      <section className="ocx-shell">
        <motion.header
          className="ocx-topbar"
          initial={topbarMotion.initial}
          animate={{ opacity: 1, y: 0 }}
          transition={topbarMotion.transition}
        >
          <div className="ocx-brand">
            <div className="ocx-brand-mark" aria-hidden="true">
              <Sparkles size={20} />
            </div>

            <div>
              <strong>{PRODUCT_NAME}</strong>
              <span>{PRODUCT_SUITE}</span>
            </div>
          </div>

          <div className="ocx-top-actions">
            <div className="ocx-user-pill">
              <strong>{user?.email || user?.name || "—"}</strong>
              <span>{isSuperAdmin() ? cc("superAdmin") : cc("authorizedUser")}</span>
            </div>

            <button type="button" className="ocx-icon-btn" onClick={toggleTheme}>
              {darkMode ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}
              {darkMode ? cc("lightTheme") : cc("darkTheme")}
            </button>

            <button type="button" className="ocx-icon-btn danger" onClick={logout}>
              <LogOut size={17} aria-hidden="true" />
              {cc("logout")}
            </button>
          </div>
        </motion.header>

        <section className="ocx-hero-grid">
          <motion.div
            className="ocx-hero"
            initial={heroMotion.initial}
            animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
            transition={heroMotion.transition}
          >
            <div className="ocx-eyebrow">
              <ShieldCheck size={16} aria-hidden="true" />
              {cc(greetingKey())}, {cc("controlReady")}
            </div>

            <h1>{PRODUCT_NAME} {PRODUCT_SUITE}</h1>

            <p>{cc("tagline")}</p>

            <div className="ocx-search">
              <Search size={18} aria-hidden="true" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={cc("searchPlaceholder")}
                aria-label={cc("searchPlaceholder")}
              />
            </div>
          </motion.div>

          <motion.aside
            className="ocx-command-panel"
            initial={panelMotion.initial}
            animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
            transition={panelMotion.transition}
          >
            <div className="ocx-panel-glare" aria-hidden="true" />

            <div className="ocx-panel-head">
              <span>{cc("commandStatus")}</span>
              <strong>{formatDate(new Date(), { weekday: "long", day: "2-digit", month: "long" })}</strong>
            </div>

            <div className="ocx-metric-row">
              <div>
                <small>{cc("visibleModules")}</small>
                <strong>{visibleModules.length}</strong>
              </div>

              <div>
                <small>{cc("activeAccess")}</small>
                <strong>{readyCount}</strong>
              </div>

              <div>
                <small>{cc("preparing")}</small>
                <strong>{lockedCount}</strong>
              </div>
            </div>

            <div className="ocx-live-strip">
              <Clock3 size={16} aria-hidden="true" />
              <span>{cc("roleBasedActive")}</span>
            </div>

            <div className="ocx-mini-map" aria-hidden="true">
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
            initial={reduceMotion ? false : { opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={reduceMotion ? { duration: 0 } : undefined}
            role="status"
            aria-live="polite"
          >
            <strong>{cc("emptyModules")}</strong>
            <p>{cc("emptyModulesDetail")}</p>
          </motion.section>
        )}
      </section>
    </main>
  );
}
