const CATALOG = {
  tr: { viewAssignedPlan: "Atanmış planı 2D/3D görüntüle", persistedExactPlan: "Atanmış exact plan versiyonu", viewLoading: "Plan yükleniyor…", viewError: "Atanmış plan görünümü yüklenemedi." },
  en: { viewAssignedPlan: "View assigned plan in 2D/3D", persistedExactPlan: "Assigned exact plan version", viewLoading: "Loading plan…", viewError: "Assigned plan view could not be loaded." },
  de: { viewAssignedPlan: "Zugewiesenen Plan in 2D/3D anzeigen", persistedExactPlan: "Zugewiesene exakte Planversion", viewLoading: "Plan wird geladen…", viewError: "Die Ansicht des zugewiesenen Plans konnte nicht geladen werden." },
  ar: { viewAssignedPlan: "عرض الخطة المعيّنة ثنائيًا/ثلاثيًا", persistedExactPlan: "نسخة الخطة الدقيقة المعيّنة", viewLoading: "جارٍ تحميل الخطة…", viewError: "تعذر تحميل عرض الخطة المعيّنة." },
  fr: { viewAssignedPlan: "Voir le plan affecté en 2D/3D", persistedExactPlan: "Version exacte du plan affecté", viewLoading: "Chargement du plan…", viewError: "Impossible de charger la vue du plan affecté." },
  es: { viewAssignedPlan: "Ver plan asignado en 2D/3D", persistedExactPlan: "Versión exacta del plan asignado", viewLoading: "Cargando plan…", viewError: "No se pudo cargar la vista del plan asignado." },
  it: { viewAssignedPlan: "Visualizza il piano assegnato in 2D/3D", persistedExactPlan: "Versione esatta del piano assegnato", viewLoading: "Caricamento piano…", viewError: "Impossibile caricare la vista del piano assegnato." },
  nl: { viewAssignedPlan: "Toegewezen plan in 2D/3D bekijken", persistedExactPlan: "Toegewezen exacte planversie", viewLoading: "Plan laden…", viewError: "De weergave van het toegewezen plan kon niet worden geladen." },
  pl: { viewAssignedPlan: "Wyświetl przypisany plan w 2D/3D", persistedExactPlan: "Przypisana dokładna wersja planu", viewLoading: "Ładowanie planu…", viewError: "Nie udało się wczytać widoku przypisanego planu." },
  "pt-BR": { viewAssignedPlan: "Ver plano atribuído em 2D/3D", persistedExactPlan: "Versão exata do plano atribuído", viewLoading: "Carregando plano…", viewError: "Não foi possível carregar a visualização do plano atribuído." },
};

const REQUIRED_KEYS = Object.freeze(Object.keys(CATALOG.en));

export function translatePlanogramView(locale, key) {
  const catalog = CATALOG[locale] || CATALOG.en;
  return catalog[key] ?? CATALOG.en[key] ?? key;
}

export function planogramViewMessageCoverage(locales) {
  const missing = {};
  const extra = {};
  for (const locale of locales) {
    const catalog = CATALOG[locale] || {};
    missing[locale] = REQUIRED_KEYS.filter((key) => !Object.prototype.hasOwnProperty.call(catalog, key));
    extra[locale] = Object.keys(catalog).filter((key) => !REQUIRED_KEYS.includes(key));
  }
  return { missing, extra };
}
