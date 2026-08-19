export const PLANOGRAM_STORE_SCAN_MESSAGES = Object.freeze({
  en: {
    title: "Store Scan Review",
    subtitle: "Review measured RoomPlan, ARCore Depth, CAD or survey captures before Store DNA approval.",
    upload: "Load capture JSON",
    noFile: "No capture loaded",
    loaded: "Capture loaded: {name}",
    run: "Review scan",
    running: "Reviewing…",
    previewOnly: "PREVIEW · HUMAN REVIEW REQUIRED",
    permissionRequired: "Planogram create permission is required.",
    invalidFile: "Capture file is invalid or contains unsupported/raw-media fields.",
    unavailable: "Store Scan review is unavailable.",
    quality: "Capture quality",
    provider: "Provider",
    elements: "Elements",
    fixtures: "Fixtures",
    lowConfidence: "Low confidence",
    preservedV2: "V2 geometry",
    blockers: "Required review",
    warnings: "Warnings",
    none: "None",
    fingerprint: "Scan fingerprint",
    geometryPreview: "Measured geometry preview",
    rawMedia: "Raw photo/video bytes are not stored by this review endpoint.",
    notStoreDna: "This scan is not approved Store DNA and cannot release an installation or production plan.",
  },
  tr: {
    title: "Mağaza Tarama İncelemesi",
    subtitle: "Store DNA onayından önce RoomPlan, ARCore Depth, CAD veya ölçüm kayıtlarını inceleyin.",
    upload: "Tarama JSON'u yükle",
    noFile: "Tarama yüklenmedi",
    loaded: "Tarama yüklendi: {name}",
    run: "Taramayı incele",
    running: "İnceleniyor…",
    previewOnly: "ÖNİZLEME · İNSAN İNCELEMESİ GEREKLİ",
    permissionRequired: "Planogram oluşturma yetkisi gerekli.",
    invalidFile: "Tarama dosyası geçersiz veya desteklenmeyen/ham medya alanları içeriyor.",
    unavailable: "Mağaza tarama incelemesi kullanılamıyor.",
    quality: "Tarama kalitesi",
    provider: "Kaynak",
    elements: "Elemanlar",
    fixtures: "Fixture'lar",
    lowConfidence: "Düşük güven",
    preservedV2: "V2 geometri",
    blockers: "Gerekli inceleme",
    warnings: "Uyarılar",
    none: "Yok",
    fingerprint: "Tarama fingerprint'i",
    geometryPreview: "Ölçülü geometri önizlemesi",
    rawMedia: "Ham fotoğraf/video baytları bu inceleme endpoint'inde saklanmaz.",
    notStoreDna: "Bu tarama onaylı Store DNA değildir; kurulum veya production planı yayınlayamaz.",
  },
  de: {
    title: "Store-Scan-Prüfung", subtitle: "Gemessene RoomPlan-, ARCore-, CAD- oder Survey-Daten vor Store-DNA-Freigabe prüfen.", upload: "Capture-JSON laden", noFile: "Kein Capture geladen", loaded: "Capture geladen: {name}", run: "Scan prüfen", running: "Prüfung…", previewOnly: "VORSCHAU · MENSCHLICHE PRÜFUNG NÖTIG", permissionRequired: "Planogram-Erstellrecht erforderlich.", invalidFile: "Ungültige Capture-Datei oder nicht erlaubte Rohmedienfelder.", unavailable: "Store-Scan-Prüfung nicht verfügbar.", quality: "Capture-Qualität", provider: "Quelle", elements: "Elemente", fixtures: "Fixtures", lowConfidence: "Niedrige Sicherheit", preservedV2: "V2-Geometrie", blockers: "Erforderliche Prüfung", warnings: "Warnungen", none: "Keine", fingerprint: "Scan-Fingerprint", geometryPreview: "Gemessene Geometrie", rawMedia: "Rohe Foto-/Video-Bytes werden nicht gespeichert.", notStoreDna: "Dieser Scan ist keine freigegebene Store DNA und erlaubt keine Installation oder Produktion."
  },
  ar: {
    title: "مراجعة مسح المتجر", subtitle: "راجع قياسات RoomPlan أو ARCore Depth أو CAD قبل اعتماد Store DNA.", upload: "تحميل JSON للمسح", noFile: "لم يتم تحميل مسح", loaded: "تم تحميل المسح: {name}", run: "مراجعة المسح", running: "جارٍ المراجعة…", previewOnly: "معاينة · مراجعة بشرية مطلوبة", permissionRequired: "يلزم إذن إنشاء المخطط.", invalidFile: "ملف المسح غير صالح أو يحتوي حقول وسائط خام غير مسموحة.", unavailable: "مراجعة المسح غير متاحة.", quality: "جودة المسح", provider: "المصدر", elements: "العناصر", fixtures: "التجهيزات", lowConfidence: "ثقة منخفضة", preservedV2: "هندسة V2", blockers: "مراجعة مطلوبة", warnings: "تحذيرات", none: "لا يوجد", fingerprint: "بصمة المسح", geometryPreview: "معاينة الهندسة المقاسة", rawMedia: "لا يتم حفظ بيانات الصور أو الفيديو الخام.", notStoreDna: "هذا المسح ليس Store DNA معتمدًا ولا يمنح صلاحية تركيب أو إنتاج."
  },
  fr: {
    title: "Revue Store Scan", subtitle: "Vérifiez les captures RoomPlan, ARCore Depth, CAD ou relevé avant validation Store DNA.", upload: "Charger le JSON", noFile: "Aucune capture", loaded: "Capture chargée : {name}", run: "Analyser le scan", running: "Analyse…", previewOnly: "APERÇU · REVUE HUMAINE REQUISE", permissionRequired: "Permission de création Planogram requise.", invalidFile: "Capture invalide ou champs média bruts interdits.", unavailable: "Revue Store Scan indisponible.", quality: "Qualité", provider: "Source", elements: "Éléments", fixtures: "Fixtures", lowConfidence: "Faible confiance", preservedV2: "Géométrie V2", blockers: "Revue requise", warnings: "Avertissements", none: "Aucun", fingerprint: "Empreinte du scan", geometryPreview: "Aperçu géométrique mesuré", rawMedia: "Les octets photo/vidéo bruts ne sont pas stockés.", notStoreDna: "Ce scan n'est pas un Store DNA approuvé et n'autorise ni installation ni production."
  },
  es: {
    title: "Revisión Store Scan", subtitle: "Revise capturas RoomPlan, ARCore Depth, CAD o medición antes de aprobar Store DNA.", upload: "Cargar JSON", noFile: "Sin captura", loaded: "Captura cargada: {name}", run: "Revisar escaneo", running: "Revisando…", previewOnly: "VISTA PREVIA · REVISIÓN HUMANA", permissionRequired: "Se requiere permiso para crear planogramas.", invalidFile: "Captura inválida o con campos de medios sin procesar.", unavailable: "Revisión no disponible.", quality: "Calidad", provider: "Fuente", elements: "Elementos", fixtures: "Fixtures", lowConfidence: "Baja confianza", preservedV2: "Geometría V2", blockers: "Revisión requerida", warnings: "Avisos", none: "Ninguno", fingerprint: "Huella del escaneo", geometryPreview: "Geometría medida", rawMedia: "No se almacenan bytes de foto/vídeo sin procesar.", notStoreDna: "Este escaneo no es Store DNA aprobado ni autoriza instalación o producción."
  },
  it: {
    title: "Revisione Store Scan", subtitle: "Controlla acquisizioni RoomPlan, ARCore Depth, CAD o rilievo prima dell'approvazione Store DNA.", upload: "Carica JSON", noFile: "Nessuna acquisizione", loaded: "Acquisizione caricata: {name}", run: "Rivedi scansione", running: "Revisione…", previewOnly: "ANTEPRIMA · REVISIONE UMANA", permissionRequired: "Serve il permesso di creazione Planogram.", invalidFile: "File non valido o con campi media grezzi non consentiti.", unavailable: "Revisione non disponibile.", quality: "Qualità", provider: "Fonte", elements: "Elementi", fixtures: "Fixture", lowConfidence: "Bassa confidenza", preservedV2: "Geometria V2", blockers: "Revisione richiesta", warnings: "Avvisi", none: "Nessuno", fingerprint: "Fingerprint scansione", geometryPreview: "Anteprima geometria misurata", rawMedia: "I byte grezzi di foto/video non vengono salvati.", notStoreDna: "Questa scansione non è Store DNA approvato e non autorizza installazione o produzione."
  },
  nl: {
    title: "Store Scan Review", subtitle: "Controleer RoomPlan-, ARCore Depth-, CAD- of meetcaptures vóór Store DNA-goedkeuring.", upload: "Capture-JSON laden", noFile: "Geen capture geladen", loaded: "Capture geladen: {name}", run: "Scan beoordelen", running: "Beoordelen…", previewOnly: "PREVIEW · MENSELIJKE REVIEW VEREIST", permissionRequired: "Planogram-aanmaakrecht vereist.", invalidFile: "Ongeldige capture of niet-toegestane ruwe mediavelden.", unavailable: "Store Scan review niet beschikbaar.", quality: "Kwaliteit", provider: "Bron", elements: "Elementen", fixtures: "Fixtures", lowConfidence: "Lage zekerheid", preservedV2: "V2-geometrie", blockers: "Vereiste review", warnings: "Waarschuwingen", none: "Geen", fingerprint: "Scan-fingerprint", geometryPreview: "Gemeten geometrie", rawMedia: "Ruwe foto-/videobytes worden niet opgeslagen.", notStoreDna: "Deze scan is geen goedgekeurde Store DNA en geeft geen installatie- of productiebevoegdheid."
  },
  pl: {
    title: "Przegląd Store Scan", subtitle: "Sprawdź pomiary RoomPlan, ARCore Depth, CAD lub survey przed zatwierdzeniem Store DNA.", upload: "Wczytaj JSON", noFile: "Brak skanu", loaded: "Wczytano: {name}", run: "Sprawdź skan", running: "Sprawdzanie…", previewOnly: "PODGLĄD · WYMAGANA WERYFIKACJA", permissionRequired: "Wymagane uprawnienie tworzenia planogramu.", invalidFile: "Nieprawidłowy plik lub niedozwolone surowe pola mediów.", unavailable: "Przegląd skanu niedostępny.", quality: "Jakość", provider: "Źródło", elements: "Elementy", fixtures: "Fixture", lowConfidence: "Niska pewność", preservedV2: "Geometria V2", blockers: "Wymagana weryfikacja", warnings: "Ostrzeżenia", none: "Brak", fingerprint: "Fingerprint skanu", geometryPreview: "Podgląd zmierzonej geometrii", rawMedia: "Surowe bajty zdjęć/wideo nie są przechowywane.", notStoreDna: "Ten skan nie jest zatwierdzonym Store DNA i nie zezwala na instalację ani produkcję."
  },
  "pt-BR": {
    title: "Revisão Store Scan", subtitle: "Revise capturas RoomPlan, ARCore Depth, CAD ou medição antes da aprovação do Store DNA.", upload: "Carregar JSON", noFile: "Nenhuma captura", loaded: "Captura carregada: {name}", run: "Revisar scan", running: "Revisando…", previewOnly: "PRÉVIA · REVISÃO HUMANA OBRIGATÓRIA", permissionRequired: "Permissão para criar planograma é necessária.", invalidFile: "Arquivo inválido ou com campos de mídia bruta não permitidos.", unavailable: "Revisão indisponível.", quality: "Qualidade", provider: "Fonte", elements: "Elementos", fixtures: "Fixtures", lowConfidence: "Baixa confiança", preservedV2: "Geometria V2", blockers: "Revisão necessária", warnings: "Avisos", none: "Nenhum", fingerprint: "Fingerprint do scan", geometryPreview: "Prévia da geometria medida", rawMedia: "Bytes brutos de foto/vídeo não são armazenados.", notStoreDna: "Este scan não é Store DNA aprovado e não autoriza instalação ou produção."
  },
});

export function translatePlanogramStoreScan(locale, key, params = {}) {
  const table = PLANOGRAM_STORE_SCAN_MESSAGES[locale] || PLANOGRAM_STORE_SCAN_MESSAGES.en;
  let value = table[key] ?? PLANOGRAM_STORE_SCAN_MESSAGES.en[key] ?? key;
  for (const [name, replacement] of Object.entries(params)) {
    value = value.replaceAll(`{${name}}`, String(replacement));
  }
  return value;
}
