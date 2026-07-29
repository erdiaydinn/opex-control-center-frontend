import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import tr from "./locales/tr.json";
import en from "./locales/en.json";
import de from "./locales/de.json";
import ar from "./locales/ar.json";

export const SUPPORTED_LANGUAGES = [
  { code: "tr", label: "Türkçe", short: "TR", flag: "🇹🇷", dir: "ltr" },
  { code: "en", label: "English", short: "EN", flag: "🇬🇧", dir: "ltr" },
  { code: "de", label: "Deutsch", short: "DE", flag: "🇩🇪", dir: "ltr" },
  { code: "ar", label: "العربية", short: "AR", flag: "🇸🇦", dir: "rtl" },
];

const dictionaries = { tr, en, de, ar };
const FALLBACK = "en";
const STORAGE_KEY = "plonagram_language";

function getNested(obj, path) {
  return String(path || "").split(".").reduce((acc, part) => (acc && acc[part] !== undefined ? acc[part] : undefined), obj);
}

function formatValue(value, params = {}) {
  if (typeof value !== "string") return value;
  return value.replace(/\{(\w+)\}/g, (_, key) => (params[key] ?? `{${key}}`));
}

function safeLanguage(code) {
  return dictionaries[code] ? code : FALLBACK;
}

const I18nContext = createContext({
  lang: FALLBACK,
  dir: "ltr",
  setLang: () => {},
  t: (key) => key,
  languages: SUPPORTED_LANGUAGES,
});

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState(() => safeLanguage(localStorage.getItem(STORAGE_KEY) || "tr"));

  const current = SUPPORTED_LANGUAGES.find((x) => x.code === lang) || SUPPORTED_LANGUAGES[1];

  const setLang = (next) => {
    const safe = safeLanguage(next);
    localStorage.setItem(STORAGE_KEY, safe);
    setLangState(safe);
  };

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = current.dir;
  }, [lang, current.dir]);

  const value = useMemo(() => {
    const t = (key, params = {}) => {
      const selected = getNested(dictionaries[lang], key);
      const fallback = getNested(dictionaries[FALLBACK], key);
      const turkishFallback = getNested(dictionaries.tr, key);
      const finalValue = selected ?? fallback ?? turkishFallback ?? key;
      return formatValue(finalValue, params);
    };

    return {
      lang,
      dir: current.dir,
      language: current,
      setLang,
      t,
      languages: SUPPORTED_LANGUAGES,
    };
  }, [lang, current]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}

export function translateStatic(key, lang = "en", params = {}) {
  const safe = safeLanguage(lang);
  const value = getNested(dictionaries[safe], key) ?? getNested(dictionaries[FALLBACK], key) ?? key;
  return formatValue(value, params);
}
