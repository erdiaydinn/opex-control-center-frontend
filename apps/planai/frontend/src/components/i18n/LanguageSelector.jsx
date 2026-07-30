import React, { useEffect, useRef, useState } from "react";
import { useI18n } from "../../i18n/I18nProvider";
import "./LanguageSelector.css";

export default function LanguageSelector({ compact = false, embedded = false }) {
  const { lang, setLang, languages, t } = useI18n();
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const active = languages.find((x) => x.code === lang) || languages[0];

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    window.dispatchEvent(new CustomEvent("plg:language-changed", { detail: { lang } }));
  }, [lang]);

  useEffect(() => {
    const onClick = (e) => { if (!rootRef.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  return (
    <div ref={rootRef} className={`plg-lang ${compact ? "plg-lang-compact" : ""} ${embedded ? "plg-lang-embedded" : ""}`}>
      <button type="button" className="plg-lang-trigger" onClick={() => setOpen((v) => !v)} aria-label={t("ui.language.select") || "Language"}>
        <span className="plg-lang-globe">◎</span>
        <span className="plg-lang-code">{active.short}</span>
        <span className="plg-lang-chevron">⌄</span>
      </button>
      {open && (
        <div className="plg-lang-menu" role="menu">
          {languages.map((item) => (
            <button type="button" key={item.code} className={`plg-lang-item ${item.code === lang ? "active" : ""}`} onClick={() => { setLang(item.code); setOpen(false); window.dispatchEvent(new CustomEvent("plg:language-changed", { detail: { lang: item.code } })); }}>
              <span className="plg-lang-item-code">{item.short}</span>
              <span className="plg-lang-item-label">{item.label}</span>
              {item.code === lang && <b>✓</b>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
