import React, { useEffect, useRef, useState } from "react";
import { Accessibility, Languages, RotateCcw, X } from "lucide-react";
import { usePlatformPreferences } from "./PlatformPreferencesContext.jsx";
import "./platform-preferences.css";

const FOCUSABLE_SELECTOR = [
  "button:not([disabled])",
  "select:not([disabled])",
  "input:not([disabled])",
  "textarea:not([disabled])",
  "a[href]",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function Toggle({ checked, onChange, label }) {
  return (
    <label className="eay-pref-toggle">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span aria-hidden="true" className="eay-pref-toggle-track"><span /></span>
      <span>{label}</span>
    </label>
  );
}

export default function AccessibilityControl() {
  const {
    locale,
    supportedLocales,
    accessibility,
    setLocale,
    setAccessibility,
    resetAccessibility,
    t,
  } = usePlatformPreferences();
  const [open, setOpen] = useState(false);
  const dialogRef = useRef(null);
  const triggerRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.activeElement;
    const first = dialogRef.current?.querySelector(FOCUSABLE_SELECTOR);
    first?.focus();

    function onKeyDown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = Array.from(dialogRef.current?.querySelectorAll(FOCUSABLE_SELECTOR) || [])
        .filter((element) => !element.hasAttribute("hidden") && element.getAttribute("aria-hidden") !== "true");
      if (focusable.length === 0) {
        event.preventDefault();
        dialogRef.current?.focus?.();
        return;
      }

      const firstFocusable = focusable[0];
      const lastFocusable = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === firstFocusable || !dialogRef.current?.contains(active))) {
        event.preventDefault();
        lastFocusable.focus();
      } else if (!event.shiftKey && active === lastFocusable) {
        event.preventDefault();
        firstFocusable.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      (previous || triggerRef.current)?.focus?.();
    };
  }, [open]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="eay-accessibility-trigger"
        aria-label={t("openSettings")}
        aria-expanded={open}
        aria-controls="eay-accessibility-panel"
        onClick={() => setOpen((value) => !value)}
      >
        <Accessibility size={20} aria-hidden="true" />
        <span>{t("accessibility")}</span>
      </button>

      {open ? (
        <div className="eay-pref-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setOpen(false);
        }}>
          <section
            ref={dialogRef}
            id="eay-accessibility-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="eay-accessibility-title"
            className="eay-pref-panel"
            tabIndex="-1"
          >
            <header>
              <div>
                <span className="eay-pref-kicker"><Accessibility size={16} aria-hidden="true" /> EAY Inclusive UX</span>
                <h2 id="eay-accessibility-title">{t("accessibilitySettings")}</h2>
              </div>
              <button type="button" className="eay-pref-icon" onClick={() => setOpen(false)} aria-label={t("close")}>
                <X size={20} aria-hidden="true" />
              </button>
            </header>

            <div className="eay-pref-section">
              <label className="eay-pref-field">
                <span><Languages size={17} aria-hidden="true" /> {t("language")}</span>
                <select value={locale} onChange={(event) => setLocale(event.target.value)}>
                  {supportedLocales.map((item) => (
                    <option key={item.code} value={item.code}>{item.nativeLabel}</option>
                  ))}
                </select>
              </label>
            </div>

            <div className="eay-pref-section">
              <strong>{t("textSize")}</strong>
              <div className="eay-pref-segmented" role="group" aria-label={t("textSize")}>
                {[{ value: "100", label: t("standard") }, { value: "115", label: t("large") }, { value: "130", label: t("extraLarge") }].map((item) => (
                  <button
                    type="button"
                    key={item.value}
                    className={accessibility.textScale === item.value ? "active" : ""}
                    aria-pressed={accessibility.textScale === item.value}
                    onClick={() => setAccessibility({ textScale: item.value })}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="eay-pref-section eay-pref-grid">
              <Toggle checked={accessibility.contrast === "high"} onChange={(checked) => setAccessibility({ contrast: checked ? "high" : "standard" })} label={t("highContrast")} />
              <Toggle checked={accessibility.reduceMotion} onChange={(checked) => setAccessibility({ reduceMotion: checked })} label={t("reduceMotion")} />
              <Toggle checked={accessibility.readableFont} onChange={(checked) => setAccessibility({ readableFont: checked })} label={t("readableFont")} />
              <Toggle checked={accessibility.underlineLinks} onChange={(checked) => setAccessibility({ underlineLinks: checked })} label={t("underlineLinks")} />
              <Toggle checked={accessibility.largeTargets} onChange={(checked) => setAccessibility({ largeTargets: checked })} label={t("largeTargets")} />
              <Toggle checked={accessibility.focusMode} onChange={(checked) => setAccessibility({ focusMode: checked })} label={t("focusMode")} />
            </div>

            <div className="eay-pref-section">
              <strong>{t("media")}</strong>
              <div className="eay-pref-grid">
                <Toggle checked={accessibility.captions} onChange={(checked) => setAccessibility({ captions: checked })} label={t("captions")} />
                <Toggle checked={accessibility.transcriptPreferred} onChange={(checked) => setAccessibility({ transcriptPreferred: checked })} label={t("transcript")} />
                <Toggle checked={accessibility.audioDescriptionPreferred} onChange={(checked) => setAccessibility({ audioDescriptionPreferred: checked })} label={t("audioDescription")} />
                <Toggle checked={accessibility.visualAlerts} onChange={(checked) => setAccessibility({ visualAlerts: checked })} label={t("visualAlerts")} />
              </div>
            </div>

            <p className="eay-pref-privacy">{t("noDiagnosis")}</p>

            <footer>
              <button type="button" className="eay-pref-reset" onClick={resetAccessibility}>
                <RotateCcw size={16} aria-hidden="true" /> {t("reset")}
              </button>
              <button type="button" className="eay-pref-done" onClick={() => setOpen(false)}>{t("close")}</button>
            </footer>
          </section>
        </div>
      ) : null}
    </>
  );
}
