import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";

const InventoryUiContext = createContext(null);

const EN = {
  "Inventory": "Inventory",
  "Veri yükle": "Upload data",
  "Sayım başlat": "Start count",
  "Kapsamı yükle": "Upload scope",
  "Kör sayım": "Blind count",
  "Fark düzelt": "Resolve variance",
  "Onayla ve bitir": "Approve & close",
  "Resmî tutanak": "Official report",
  "Kör sayım ve denetlenebilir mutabakat": "Blind count and auditable reconciliation",
  "Stok gerçeğini lokasyonda yakala.": "Capture the stock truth at location.",
  "Terminal sayımı, PC kontrolü, fark yönetimi ve tutanak tek akışta.": "Terminal counting, desktop review, variance management and reporting in one flow.",
  "SEÇİLİ BELGE": "SELECTED DOCUMENT",
  "Henüz belge yok": "No document yet",
  "Yeni sayım başlatarak ilerleyin": "Start a new count to continue",
  "Genel Bakış": "Overview",
  "Terminal Sayımı": "Terminal Count",
  "PC Kontrol": "Desktop Review",
  "Fark & Onay": "Variance & Approval",
  "Ana Veriler": "Master Data",
  "Aktif belge": "Active document",
  "Sayım ilerleme": "Count progress",
  "Farklı SKU": "SKU with variance",
  "Mutlak etki": "Absolute impact",
  "Sayım belgeleri": "Count documents",
  "Yeni": "New",
  "İlk sayımı başlatın": "Start the first count",
  "Denetim izi": "Audit trail",
  "OPEX INVENTORY · TERMİNAL": "OPEX INVENTORY · TERMINAL",
  "Çevrimiçi": "Online",
  "Okuyucu hazır": "Scanner ready",
  "Sistem stoku ve fark bilgisi bu ekranda gösterilmez.": "System stock and variance are hidden on this screen.",
  "AKTİF LOKASYON": "ACTIVE LOCATION",
  "Lokasyon bekleniyor": "Waiting for location",
  "Değiştir": "Change",
  "Lokasyon etiketini okut": "Scan location label",
  "Ürün barkodunu okut": "Scan product barcode",
  "Miktarı gir": "Enter quantity",
  "Kaydet ve sıradaki ürüne geç": "Save and scan next product",
  "SON KAYIT BAŞARILI": "LAST RECORD SAVED",
  "Enter ve Tab sonlandırmalı fiziksel okuyucular desteklenir.": "Physical scanners ending with Enter or Tab are supported.",
  "Sayımı kapat": "Close count",
  "İlerleme": "Progress",
  "PC kontrol sayımı": "Desktop review count",
  "Düzeltmeler anında kaydolmaz. Değişiklikleri hazırlayın, gerekçe girin ve tek işlem olarak kaydedin. İlk sayım asla silinmez.": "Corrections are not saved immediately. Prepare changes, enter a reason and save them as one transaction. The original count is never deleted.",
  "Lokasyon": "Location",
  "Ürün": "Product",
  "Sistem": "System",
  "Sayım": "Count",
  "Fark": "Variance",
  "Etki": "Impact",
  "Kaynak": "Source",
  "Durum": "Status",
  "Düzeltme gerekçesi": "Correction reason",
  "Düzeltmeleri kaydet": "Save corrections",
  "Fark mutabakatı": "Variance reconciliation",
  "Fark bulunmuyor": "No variance",
  "Sayımı sonuçlandır": "Finalize count",
  "Onayla ve bitir işleminden sonra belge kilitlenir ve resmî tutanak üretilebilir.": "After approval, the document is locked and an official report can be generated.",
  "Sayılan adet": "Counted quantity",
  "Artı": "Positive",
  "Eksi": "Negative",
  "Mutlak fark": "Absolute variance",
  "Resmî sayım tutanağı oluştur": "Generate official count report",
  "Fark detayını indir": "Download variance details",
  "Ürünler": "Products",
  "Lokasyonlar": "Locations",
  "Stok satırları": "Stock rows",
  "ADIM 1 · ZORUNLU": "STEP 1 · REQUIRED",
  "Sayım kapsamı dosyasını yükle": "Upload count scope",
  "Excel / CSV seç": "Choose Excel / CSV",
  "Şablon indir": "Download template",
  "Dosya doğrulama sonucu": "File validation result",
  "AKTİF SAYIM KAPSAMI": "ACTIVE COUNT SCOPE",
  "Bu kapsamla sayımı başlat": "Start count with this scope",
  "Görünüm": "Appearance",
  "Dil": "Language",
  "Açık tema": "Light theme",
  "Koyu tema": "Dark theme",
  "Geri": "Back",
  "SKU, ürün, lokasyon ara": "Search SKU, product or location",
  "Lokasyon barkodu": "Location barcode",
  "İki dosyayı yükle": "Upload both files",
  "Lokasyon ilerlemesi": "Location progress",
  "Fark detay raporunu indir": "Download variance report",
  "FİRMA DOSYASI · ZORUNLU": "COMPANY FILE · REQUIRED",
  "Lokasyon listesini yükle": "Upload location list",
  "Bu dosyayı merkez/firma hazırlar. Ürün, SKU veya barkod içermez; yalnızca sayım rotasını oluşturur.": "This file is prepared by the company. It contains no product, SKU or barcode data; it only defines the count route.",
  "Lokasyon dosyası seç": "Choose location file",
  "DEPO DOSYASI · ZORUNLU": "WAREHOUSE FILE · REQUIRED",
  "Stok karşılaştırma verisini yükle": "Upload stock comparison data",
  "Depo yalnızca ürün ana bilgilerini, sistem stok miktarını ve fiyatı sağlar. Lokasyon bu dosyada bulunmaz.": "The warehouse provides product master data, system quantity and price. This file contains no location field.",
  "Depo": "Warehouse",
  "Ürün adı": "Product name",
  "Sistem stoku": "System stock",
  "Birim fiyat": "Unit price",
  "Stok dosyası seç": "Choose stock file",
  "Lokasyon dosyası doğrulaması": "Location file validation",
  "Stok dosyası doğrulaması": "Stock file validation",
  "Dosya geçerli ve kullanıma hazır.": "The file is valid and ready to use.",
  "SAYIM GİRDİLERİ HAZIR": "COUNT INPUTS READY",
};

const DE = {
  ...EN,
  "Veri yükle": "Daten hochladen",
  "Sayım başlat": "Zählung starten",
  "Kapsamı yükle": "Umfang hochladen",
  "Kör sayım": "Blindzählung",
  "Fark düzelt": "Differenz klären",
  "Onayla ve bitir": "Freigeben & abschließen",
  "Resmî tutanak": "Offizielles Protokoll",
  "Kör sayım ve denetlenebilir mutabakat": "Blindzählung und prüfbare Abstimmung",
  "Stok gerçeğini lokasyonda yakala.": "Bestand direkt am Lagerplatz erfassen.",
  "Genel Bakış": "Übersicht",
  "Terminal Sayımı": "Terminalzählung",
  "PC Kontrol": "PC-Kontrolle",
  "Fark & Onay": "Differenz & Freigabe",
  "Ana Veriler": "Stammdaten",
  "Sayım belgeleri": "Zähldokumente",
  "Denetim izi": "Audit-Protokoll",
  "Çevrimiçi": "Online",
  "Okuyucu hazır": "Scanner bereit",
  "AKTİF LOKASYON": "AKTIVER LAGERPLATZ",
  "Lokasyon bekleniyor": "Warte auf Lagerplatz",
  "Değiştir": "Ändern",
  "Lokasyon etiketini okut": "Lagerplatzetikett scannen",
  "Ürün barkodunu okut": "Produktbarcode scannen",
  "Miktarı gir": "Menge eingeben",
  "Kaydet ve sıradaki ürüne geç": "Speichern und nächstes Produkt scannen",
  "İlerleme": "Fortschritt",
  "Fark mutabakatı": "Differenzabstimmung",
  "Sayımı sonuçlandır": "Zählung abschließen",
  "Resmî sayım tutanağı oluştur": "Offizielles Zählprotokoll erstellen",
  "Fark detayını indir": "Differenzdetails herunterladen",
  "Görünüm": "Darstellung",
  "Dil": "Sprache",
  "Açık tema": "Helles Design",
  "Koyu tema": "Dunkles Design",
  "İki dosyayı yükle": "Beide Dateien hochladen",
  "Lokasyon ilerlemesi": "Lagerplatzfortschritt",
  "Fark detay raporunu indir": "Differenzbericht herunterladen",
  "FİRMA DOSYASI · ZORUNLU": "FIRMENDATEI · ERFORDERLICH",
  "Lokasyon listesini yükle": "Lagerplatzliste hochladen",
  "Lokasyon dosyası seç": "Lagerplatzdatei wählen",
  "DEPO DOSYASI · ZORUNLU": "LAGERDATEI · ERFORDERLICH",
  "Stok karşılaştırma verisini yükle": "Bestandsvergleichsdaten hochladen",
  "Depo": "Lager",
  "Ürün adı": "Produktname",
  "Sistem stoku": "Systembestand",
  "Birim fiyat": "Stückpreis",
  "Stok dosyası seç": "Bestandsdatei wählen",
  "SAYIM GİRDİLERİ HAZIR": "ZÄHLUNGSDATEN BEREIT",
};

const AR = {
  ...EN,
  "Veri yükle": "رفع البيانات",
  "Sayım başlat": "بدء الجرد",
  "Kapsamı yükle": "رفع نطاق الجرد",
  "Kör sayım": "جرد أعمى",
  "Fark düzelt": "معالجة الفروقات",
  "Onayla ve bitir": "اعتماد وإغلاق",
  "Resmî tutanak": "المحضر الرسمي",
  "Kör sayım ve denetlenebilir mutabakat": "جرد أعمى وتسوية قابلة للتدقيق",
  "Stok gerçeğini lokasyonda yakala.": "سجّل حقيقة المخزون في موقعه.",
  "Terminal sayımı, PC kontrolü, fark yönetimi ve tutanak tek akışta.": "الجرد الطرفي والمراجعة وإدارة الفروقات والمحضر ضمن مسار واحد.",
  "SEÇİLİ BELGE": "المستند المحدد",
  "Henüz belge yok": "لا يوجد مستند بعد",
  "Genel Bakış": "نظرة عامة",
  "Terminal Sayımı": "جرد الجهاز",
  "PC Kontrol": "مراجعة الحاسوب",
  "Fark & Onay": "الفروقات والاعتماد",
  "Ana Veriler": "البيانات الأساسية",
  "Sayım belgeleri": "مستندات الجرد",
  "Denetim izi": "سجل التدقيق",
  "Çevrimiçi": "متصل",
  "Okuyucu hazır": "الماسح جاهز",
  "AKTİF LOKASYON": "الموقع النشط",
  "Lokasyon bekleniyor": "بانتظار الموقع",
  "Değiştir": "تغيير",
  "Lokasyon etiketini okut": "امسح ملصق الموقع",
  "Ürün barkodunu okut": "امسح باركود المنتج",
  "Miktarı gir": "أدخل الكمية",
  "Kaydet ve sıradaki ürüne geç": "احفظ وانتقل للمنتج التالي",
  "Sayımı kapat": "إغلاق الجرد",
  "İlerleme": "التقدم",
  "Fark mutabakatı": "تسوية الفروقات",
  "Sayımı sonuçlandır": "إنهاء الجرد",
  "Resmî sayım tutanağı oluştur": "إنشاء محضر الجرد الرسمي",
  "Fark detayını indir": "تنزيل تفاصيل الفروقات",
  "Görünüm": "المظهر",
  "Dil": "اللغة",
  "Açık tema": "الوضع الفاتح",
  "Koyu tema": "الوضع الداكن",
  "İki dosyayı yükle": "رفع الملفين",
  "Lokasyon ilerlemesi": "تقدم المواقع",
  "Fark detay raporunu indir": "تنزيل تقرير تفاصيل الفروقات",
  "FİRMA DOSYASI · ZORUNLU": "ملف الشركة · إلزامي",
  "Lokasyon listesini yükle": "رفع قائمة المواقع",
  "Lokasyon dosyası seç": "اختر ملف المواقع",
  "DEPO DOSYASI · ZORUNLU": "ملف المستودع · إلزامي",
  "Stok karşılaştırma verisini yükle": "رفع بيانات مقارنة المخزون",
  "Depo": "المستودع",
  "Ürün adı": "اسم المنتج",
  "Sistem stoku": "مخزون النظام",
  "Birim fiyat": "سعر الوحدة",
  "Stok dosyası seç": "اختر ملف المخزون",
  "SAYIM GİRDİLERİ HAZIR": "مدخلات الجرد جاهزة",
};

const DICTIONARIES = { en: EN, de: DE, ar: AR };
const LOCALES = { tr: "tr-TR", en: "en-US", de: "de-DE", ar: "ar-SA" };

function translate(raw, locale) {
  if (locale === "tr") return raw;
  const match = String(raw).match(/^(\s*)(.*?)(\s*)$/s);
  const core = match?.[2] || raw;
  return `${match?.[1] || ""}${DICTIONARIES[locale]?.[core] || core}${match?.[3] || ""}`;
}

function useDomLocalization(rootRef, locale) {
  const originals = useRef(new WeakMap());
  const rendered = useRef(new WeakMap());
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;
    let applying = false;
    const localize = (node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        const last = rendered.current.get(node);
        if (!originals.current.has(node) || (last !== undefined && node.nodeValue !== last)) {
          originals.current.set(node, node.nodeValue);
        }
        const next = translate(originals.current.get(node), locale);
        rendered.current.set(node, next);
        if (node.nodeValue !== next) node.nodeValue = next;
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      ["placeholder", "title", "aria-label"].forEach((attr) => {
        if (!node.hasAttribute?.(attr)) return;
        const key = `invOriginal${attr.replace(/-([a-z])/g, (_, value) => value.toUpperCase()).replace(/^./, (value) => value.toUpperCase())}`;
        if (!node.dataset[key]) node.dataset[key] = node.getAttribute(attr);
        node.setAttribute(attr, translate(node.dataset[key], locale));
      });
      node.childNodes.forEach(localize);
    };
    applying = true;
    localize(root);
    applying = false;
    const observer = new MutationObserver((mutations) => {
      if (applying) return;
      applying = true;
      mutations.forEach((mutation) => mutation.type === "characterData"
        ? localize(mutation.target)
        : mutation.addedNodes.forEach(localize));
      applying = false;
    });
    observer.observe(root, { subtree: true, childList: true, characterData: true });
    return () => observer.disconnect();
  }, [rootRef, locale]);
}

export function InventoryUiProvider({ children }) {
  const [theme, setThemeState] = useState(() => localStorage.getItem("opex_theme") === "dark" ? "dark" : "light");
  const [locale, setLocaleState] = useState(() => {
    const saved = localStorage.getItem("opex_inventory_locale") || localStorage.getItem("opex_workforce_locale");
    return ["tr", "en", "de", "ar"].includes(saved) ? saved : "tr";
  });
  const setTheme = (value) => {
    localStorage.setItem("opex_theme", value);
    setThemeState(value);
  };
  const setLocale = (value) => {
    localStorage.setItem("opex_inventory_locale", value);
    localStorage.setItem("opex_workforce_locale", value);
    setLocaleState(value);
  };
  const value = useMemo(() => ({
    theme,
    setTheme,
    locale,
    setLocale,
    dir: locale === "ar" ? "rtl" : "ltr",
    localeCode: LOCALES[locale],
    useDomLocalization,
  }), [theme, locale]);
  return <InventoryUiContext.Provider value={value}>{children}</InventoryUiContext.Provider>;
}

export function useInventoryUi() {
  const context = useContext(InventoryUiContext);
  if (!context) throw new Error("useInventoryUi must be used inside InventoryUiProvider");
  return context;
}
