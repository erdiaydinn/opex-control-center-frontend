import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

import { SUPPORTED_LOCALES, translate } from "../i18n/messages.js";

const STORAGE_KEY = "eay_platform_preferences_v1";

export { SUPPORTED_LOCALES };

const DEFAULT_ACCESSIBILITY = Object.freeze({
  textScale: "100",
  contrast: "standard",
  reduceMotion: false,
  readableFont: false,
  underlineLinks: false,
  largeTargets: false,
  focusMode: false,
  captions: true,
  transcriptPreferred: false,
  audioDescriptionPreferred: false,
  visualAlerts: true,
});

const PlatformPreferencesContext = createContext(null);

function browserLocale() {
  if (typeof navigator === "undefined") return "tr";
  const raw = String(navigator.language || "tr");
  const direct = SUPPORTED_LOCALES.find((item) => item.code.toLowerCase() === raw.toLowerCase());
  if (direct) return direct.code;
  const base = raw.split("-")[0].toLowerCase();
  return SUPPORTED_LOCALES.find((item) => item.code.toLowerCase() === base)?.code || "tr";
}

function normalizeLocale(value) {
  const raw = String(value || "").trim();
  const direct = SUPPORTED_LOCALES.find((item) => item.code.toLowerCase() === raw.toLowerCase());
  return direct?.code || "tr";
}

function readStored() {
  if (typeof window === "undefined") return null;
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null");
    return value && typeof value === "object" ? value : null;
  } catch {
    return null;
  }
}

export function PlatformPreferencesProvider({ children }) {
  const stored = readStored();
  const [locale, setLocaleState] = useState(normalizeLocale(stored?.locale || browserLocale()));
  const [accessibility, setAccessibilityState] = useState({
    ...DEFAULT_ACCESSIBILITY,
    ...(stored?.accessibility || {}),
  });

  const localeMeta = SUPPORTED_LOCALES.find((item) => item.code === locale) || SUPPORTED_LOCALES[0];

  useEffect(() => {
    const root = document.documentElement;
    root.lang = locale;
    root.dir = localeMeta.dir;
    root.dataset.eayTextScale = accessibility.textScale;
    root.dataset.eayContrast = accessibility.contrast;
    root.dataset.eayReduceMotion = accessibility.reduceMotion ? "true" : "false";
    root.dataset.eayReadableFont = accessibility.readableFont ? "true" : "false";
    root.dataset.eayUnderlineLinks = accessibility.underlineLinks ? "true" : "false";
    root.dataset.eayLargeTargets = accessibility.largeTargets ? "true" : "false";
    root.dataset.eayFocusMode = accessibility.focusMode ? "true" : "false";

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ locale, accessibility }));
  }, [accessibility, locale, localeMeta.dir]);

  const value = useMemo(() => {
    const numberFormatter = new Intl.NumberFormat(locale);
    const percentFormatter = new Intl.NumberFormat(locale, {
      style: "percent",
      maximumFractionDigits: 1,
    });

    return {
      locale,
      localeMeta,
      supportedLocales: SUPPORTED_LOCALES,
      accessibility,
      setLocale: (next) => setLocaleState(normalizeLocale(next)),
      setAccessibility: (patch) => setAccessibilityState((current) => ({ ...current, ...patch })),
      resetAccessibility: () => setAccessibilityState({ ...DEFAULT_ACCESSIBILITY }),
      t: (key, params) => translate(locale, key, params),
      formatNumber: (value) => numberFormatter.format(Number(value || 0)),
      formatPercent: (value) => percentFormatter.format(Number(value || 0)),
      formatDate: (value, options = {}) => new Intl.DateTimeFormat(locale, options).format(new Date(value)),
      formatCurrency: (value, currency = "EUR", options = {}) => new Intl.NumberFormat(locale, {
        style: "currency",
        currency,
        ...options,
      }).format(Number(value || 0)),
    };
  }, [accessibility, locale, localeMeta]);

  return (
    <PlatformPreferencesContext.Provider value={value}>
      {children}
    </PlatformPreferencesContext.Provider>
  );
}

export function usePlatformPreferences() {
  const value = useContext(PlatformPreferencesContext);
  if (!value) throw new Error("usePlatformPreferences must be used inside PlatformPreferencesProvider");
  return value;
}
