const COPY = {
  tr: { committed: "Taahhütlü kadro", incoming: "Başlayacak", exits: "Kesin çıkış", uncovered: "Karşılanmamış açık", forecast: "30 / 60 / 90 gün", fresh: "Güncel", stale: "Eski veri", daysOld: "{days} gün eski" },
  en: { committed: "Committed HC", incoming: "Incoming", exits: "Confirmed exits", uncovered: "Uncovered gap", forecast: "30 / 60 / 90 days", fresh: "Fresh", stale: "Stale data", daysOld: "{days} days old" },
  de: { committed: "Gebundener Personalbestand", incoming: "Zugänge", exits: "Bestätigte Abgänge", uncovered: "Ungedeckte Lücke", forecast: "30 / 60 / 90 Tage", fresh: "Aktuell", stale: "Veraltete Daten", daysOld: "{days} Tage alt" },
  ar: { committed: "القوة العاملة المؤكدة", incoming: "القادمون", exits: "المغادرات المؤكدة", uncovered: "الفجوة غير المغطاة", forecast: "30 / 60 / 90 يومًا", fresh: "محدّث", stale: "بيانات قديمة", daysOld: "عمر البيانات {days} يوم" },
  fr: { committed: "Effectif engagé", incoming: "Arrivées", exits: "Départs confirmés", uncovered: "Écart non couvert", forecast: "30 / 60 / 90 jours", fresh: "À jour", stale: "Données anciennes", daysOld: "{days} jours" },
  es: { committed: "Plantilla comprometida", incoming: "Próximas altas", exits: "Bajas confirmadas", uncovered: "Brecha sin cubrir", forecast: "30 / 60 / 90 días", fresh: "Actualizado", stale: "Datos antiguos", daysOld: "{days} días" },
  it: { committed: "Organico impegnato", incoming: "Nuovi ingressi", exits: "Uscite confermate", uncovered: "Fabbisogno scoperto", forecast: "30 / 60 / 90 giorni", fresh: "Aggiornato", stale: "Dati obsoleti", daysOld: "{days} giorni" },
  nl: { committed: "Toegezegde bezetting", incoming: "Instroom", exits: "Bevestigde uitstroom", uncovered: "Ongevulde kloof", forecast: "30 / 60 / 90 dagen", fresh: "Actueel", stale: "Verouderde data", daysOld: "{days} dagen oud" },
  pl: { committed: "Zaangażowana obsada", incoming: "Nowe osoby", exits: "Potwierdzone odejścia", uncovered: "Niepokryta luka", forecast: "30 / 60 / 90 dni", fresh: "Aktualne", stale: "Nieaktualne dane", daysOld: "Dane sprzed {days} dni" },
  "pt-BR": { committed: "Quadro comprometido", incoming: "Entradas previstas", exits: "Saídas confirmadas", uncovered: "Lacuna descoberta", forecast: "30 / 60 / 90 dias", fresh: "Atualizado", stale: "Dados antigos", daysOld: "{days} dias" },
};

export function recruitmentProjectionMessage(locale, key, params = {}) {
  const dictionary = COPY[locale] || COPY.en;
  const template = dictionary[key] || COPY.en[key] || key;
  return String(template).replace(/\{(\w+)\}/g, (_, token) => String(params[token] ?? `{${token}}`));
}
