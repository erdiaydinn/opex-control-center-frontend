export const PLANOGRAM_STATUS_MESSAGES = Object.freeze({
  tr: { draft: "Taslak", submitted: "İncelemede", approved: "Onaylı", rejected: "Reddedildi", superseded: "Yerine yenisi geçti", assigned: "Atandı", acknowledged: "Teslim alındı", closed: "Kapandı" },
  en: { draft: "Draft", submitted: "Submitted", approved: "Approved", rejected: "Rejected", superseded: "Superseded", assigned: "Assigned", acknowledged: "Acknowledged", closed: "Closed" },
  de: { draft: "Entwurf", submitted: "Eingereicht", approved: "Freigegeben", rejected: "Abgelehnt", superseded: "Abgelöst", assigned: "Zugewiesen", acknowledged: "Bestätigt", closed: "Geschlossen" },
  ar: { draft: "مسودة", submitted: "مُرسل للمراجعة", approved: "معتمد", rejected: "مرفوض", superseded: "تم استبداله", assigned: "مُعيّن", acknowledged: "تم الاستلام", closed: "مغلق" },
  fr: { draft: "Brouillon", submitted: "Soumis", approved: "Approuvé", rejected: "Rejeté", superseded: "Remplacé", assigned: "Affecté", acknowledged: "Réceptionné", closed: "Clôturé" },
  es: { draft: "Borrador", submitted: "Enviado", approved: "Aprobado", rejected: "Rechazado", superseded: "Sustituido", assigned: "Asignado", acknowledged: "Confirmado", closed: "Cerrado" },
  it: { draft: "Bozza", submitted: "Inviato", approved: "Approvato", rejected: "Rifiutato", superseded: "Sostituito", assigned: "Assegnato", acknowledged: "Confermato", closed: "Chiuso" },
  nl: { draft: "Concept", submitted: "Ingediend", approved: "Goedgekeurd", rejected: "Afgewezen", superseded: "Vervangen", assigned: "Toegewezen", acknowledged: "Bevestigd", closed: "Gesloten" },
  pl: { draft: "Szkic", submitted: "Przesłany", approved: "Zatwierdzony", rejected: "Odrzucony", superseded: "Zastąpiony", assigned: "Przypisany", acknowledged: "Potwierdzony", closed: "Zamknięty" },
  "pt-BR": { draft: "Rascunho", submitted: "Enviado", approved: "Aprovado", rejected: "Rejeitado", superseded: "Substituído", assigned: "Atribuído", acknowledged: "Confirmado", closed: "Fechado" },
});

export function translatePlanogramStatus(locale, status) {
  return PLANOGRAM_STATUS_MESSAGES[locale]?.[status]
    || PLANOGRAM_STATUS_MESSAGES.en[status]
    || status;
}

export function planogramStatusMessageCoverage(locales) {
  const keys = Object.keys(PLANOGRAM_STATUS_MESSAGES.en).sort();
  return {
    missing: Object.fromEntries(
      locales.map((locale) => [
        locale,
        keys.filter((key) => typeof PLANOGRAM_STATUS_MESSAGES[locale]?.[key] !== "string"),
      ])
    ),
    extra: Object.fromEntries(
      locales.map((locale) => [
        locale,
        Object.keys(PLANOGRAM_STATUS_MESSAGES[locale] || {})
          .filter((key) => !keys.includes(key))
          .sort(),
      ])
    ),
  };
}
