export const ACADEMY_CONTENT_MESSAGES = Object.freeze({
  tr: { video: "Video", document: "Doküman", sop: "Prosedür", interactive: "Etkileşimli", live: "Canlı yayın", announcement: "Duyuru", poster: "Afiş", survey: "Anket", revoked: "İptal edildi" },
  en: { video: "Video", document: "Document", sop: "SOP", interactive: "Interactive", live: "Live", announcement: "Announcement", poster: "Poster", survey: "Survey", revoked: "Revoked" },
  de: { video: "Video", document: "Dokument", sop: "Arbeitsanweisung", interactive: "Interaktiv", live: "Live", announcement: "Ankündigung", poster: "Plakat", survey: "Umfrage", revoked: "Widerrufen" },
  ar: { video: "فيديو", document: "مستند", sop: "إجراء تشغيلي", interactive: "تفاعلي", live: "بث مباشر", announcement: "إعلان", poster: "ملصق", survey: "استبيان", revoked: "ملغى" },
  fr: { video: "Vidéo", document: "Document", sop: "Procédure", interactive: "Interactif", live: "Direct", announcement: "Annonce", poster: "Affiche", survey: "Enquête", revoked: "Révoqué" },
  es: { video: "Vídeo", document: "Documento", sop: "Procedimiento", interactive: "Interactivo", live: "En directo", announcement: "Anuncio", poster: "Cartel", survey: "Encuesta", revoked: "Revocado" },
  it: { video: "Video", document: "Documento", sop: "Procedura", interactive: "Interattivo", live: "Diretta", announcement: "Annuncio", poster: "Poster", survey: "Sondaggio", revoked: "Revocato" },
  nl: { video: "Video", document: "Document", sop: "Werkinstructie", interactive: "Interactief", live: "Live", announcement: "Aankondiging", poster: "Poster", survey: "Enquête", revoked: "Ingetrokken" },
  pl: { video: "Wideo", document: "Dokument", sop: "Procedura", interactive: "Interaktywny", live: "Transmisja na żywo", announcement: "Ogłoszenie", poster: "Plakat", survey: "Ankieta", revoked: "Cofnięto" },
  "pt-BR": { video: "Vídeo", document: "Documento", sop: "Procedimento", interactive: "Interativo", live: "Ao vivo", announcement: "Comunicado", poster: "Cartaz", survey: "Pesquisa", revoked: "Revogado" },
});

export function translateAcademyContent(locale, key) {
  return ACADEMY_CONTENT_MESSAGES[locale]?.[key] || ACADEMY_CONTENT_MESSAGES.en[key] || key;
}

export function academyContentMessageCoverage(locales) {
  const referenceKeys = Object.keys(ACADEMY_CONTENT_MESSAGES.en).sort();
  return {
    missing: Object.fromEntries(locales.map((locale) => [locale, referenceKeys.filter((key) => typeof ACADEMY_CONTENT_MESSAGES[locale]?.[key] !== "string")])),
    extra: Object.fromEntries(locales.map((locale) => [locale, Object.keys(ACADEMY_CONTENT_MESSAGES[locale] || {}).filter((key) => !referenceKeys.includes(key)).sort()])),
  };
}
