import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "eay_platform_preferences_v1";

export const SUPPORTED_LOCALES = Object.freeze([
  { code: "tr", label: "Türkçe", nativeLabel: "Türkçe", dir: "ltr" },
  { code: "en", label: "English", nativeLabel: "English", dir: "ltr" },
  { code: "de", label: "Deutsch", nativeLabel: "Deutsch", dir: "ltr" },
  { code: "ar", label: "Arabic", nativeLabel: "العربية", dir: "rtl" },
  { code: "fr", label: "French", nativeLabel: "Français", dir: "ltr" },
  { code: "es", label: "Spanish", nativeLabel: "Español", dir: "ltr" },
  { code: "it", label: "Italian", nativeLabel: "Italiano", dir: "ltr" },
  { code: "nl", label: "Dutch", nativeLabel: "Nederlands", dir: "ltr" },
  { code: "pl", label: "Polish", nativeLabel: "Polski", dir: "ltr" },
  { code: "pt-BR", label: "Portuguese (Brazil)", nativeLabel: "Português (Brasil)", dir: "ltr" },
]);

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

const STRINGS = {
  tr: {
    accessibility: "Erişilebilirlik",
    accessibilitySettings: "Erişilebilirlik ve dil ayarları",
    language: "Dil",
    textSize: "Metin boyutu",
    standard: "Standart",
    large: "Büyük",
    extraLarge: "Çok büyük",
    contrast: "Kontrast",
    highContrast: "Yüksek kontrast",
    reduceMotion: "Hareketi azalt",
    readableFont: "Okunabilir yazı tipi",
    underlineLinks: "Bağlantıları altı çizili göster",
    largeTargets: "Büyük dokunma hedefleri",
    focusMode: "Sade / odak modu",
    media: "Medya tercihleri",
    captions: "Altyazıları varsayılan açık tut",
    transcript: "Transkripti önceliklendir",
    audioDescription: "Sesli betimlemeyi tercih et",
    visualAlerts: "Sesli uyarıları görsel olarak da göster",
    reset: "Varsayılana dön",
    close: "Kapat",
    openSettings: "Erişilebilirlik ayarlarını aç",
    skipToContent: "Ana içeriğe geç",
    noDiagnosis: "Bu ayarlar ihtiyaç tercihleridir; sağlık/engel teşhisi kaydedilmez.",
  },
  en: {
    accessibility: "Accessibility",
    accessibilitySettings: "Accessibility and language settings",
    language: "Language",
    textSize: "Text size",
    standard: "Standard",
    large: "Large",
    extraLarge: "Extra large",
    contrast: "Contrast",
    highContrast: "High contrast",
    reduceMotion: "Reduce motion",
    readableFont: "Readable font",
    underlineLinks: "Underline links",
    largeTargets: "Large touch targets",
    focusMode: "Simplified / focus mode",
    media: "Media preferences",
    captions: "Keep captions on by default",
    transcript: "Prefer transcript",
    audioDescription: "Prefer audio description",
    visualAlerts: "Show visual equivalents for audio alerts",
    reset: "Reset defaults",
    close: "Close",
    openSettings: "Open accessibility settings",
    skipToContent: "Skip to main content",
    noDiagnosis: "These are access preferences; no disability or health diagnosis is stored.",
  },
  de: { accessibility: "Barrierefreiheit", accessibilitySettings: "Barrierefreiheit und Sprache", language: "Sprache", textSize: "Textgröße", standard: "Standard", large: "Groß", extraLarge: "Sehr groß", contrast: "Kontrast", highContrast: "Hoher Kontrast", reduceMotion: "Bewegung reduzieren", readableFont: "Gut lesbare Schrift", underlineLinks: "Links unterstreichen", largeTargets: "Große Bedienflächen", focusMode: "Fokusmodus", media: "Medienpräferenzen", captions: "Untertitel standardmäßig ein", transcript: "Transkript bevorzugen", audioDescription: "Audiodeskription bevorzugen", visualAlerts: "Akustische Hinweise auch visuell anzeigen", reset: "Zurücksetzen", close: "Schließen", openSettings: "Einstellungen zur Barrierefreiheit öffnen", skipToContent: "Zum Hauptinhalt springen", noDiagnosis: "Gespeichert werden nur Zugangspräferenzen, keine Diagnose." },
  ar: { accessibility: "إمكانية الوصول", accessibilitySettings: "إعدادات إمكانية الوصول واللغة", language: "اللغة", textSize: "حجم النص", standard: "قياسي", large: "كبير", extraLarge: "كبير جداً", contrast: "التباين", highContrast: "تباين عالٍ", reduceMotion: "تقليل الحركة", readableFont: "خط سهل القراءة", underlineLinks: "تسطير الروابط", largeTargets: "أهداف لمس كبيرة", focusMode: "وضع التركيز المبسط", media: "تفضيلات الوسائط", captions: "تشغيل التسميات التوضيحية افتراضياً", transcript: "تفضيل النص المكتوب", audioDescription: "تفضيل الوصف الصوتي", visualAlerts: "إظهار بديل مرئي للتنبيهات الصوتية", reset: "إعادة الضبط", close: "إغلاق", openSettings: "فتح إعدادات إمكانية الوصول", skipToContent: "الانتقال إلى المحتوى الرئيسي", noDiagnosis: "يتم حفظ تفضيلات الوصول فقط ولا يتم حفظ أي تشخيص صحي أو إعاقة." },
};

const PlatformPreferencesContext = createContext(null);

function browserLocale() {
  if (typeof navigator === "undefined") return "tr";
  const raw = String(navigator.language || "tr");
  const direct = SUPPORTED_LOCALES.find((item) => item.code.toLowerCase() === raw.toLowerCase());
  if (direct) return direct.code;
  const base = raw.split("-")[0].toLowerCase();
  return SUPPORTED_LOCALES.find((item) => item.code.toLowerCase() === base)?.code || "tr";
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
  const [locale, setLocale] = useState(stored?.locale || browserLocale());
  const [accessibility, setAccessibility] = useState({
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

  const value = useMemo(() => ({
    locale,
    localeMeta,
    supportedLocales: SUPPORTED_LOCALES,
    accessibility,
    setLocale,
    setAccessibility: (patch) => setAccessibility((current) => ({ ...current, ...patch })),
    resetAccessibility: () => setAccessibility({ ...DEFAULT_ACCESSIBILITY }),
    t: (key) => STRINGS[locale]?.[key] || STRINGS.en[key] || STRINGS.tr[key] || key,
  }), [accessibility, locale, localeMeta]);

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
