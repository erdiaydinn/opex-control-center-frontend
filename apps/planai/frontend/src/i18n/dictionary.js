const base = {
  command: 'Command Center', storeDna: 'Store DNA', live3d: 'Live 3D', architect: 'Layout Architect', placement: 'Product Placement', library: 'Product Library', fixture: 'Fixture Library', planogram: 'Planogram', delta: 'Delta Planogram', publishing: 'Publishing', tasks: 'Tasks', reports: 'Reports', admin: 'Admin', rules: 'Rule Engine', photos: 'Photo Evidence',
  online: 'Online', system: 'System Status', uploadSku: 'Upload SKUs', uploadLayout: 'Upload Layout', generate: 'Generate Optimal Plan', open3d: 'Open 3D Studio',
  title: 'Warehouse intelligence, beautifully orchestrated.', subtitle: 'Optimize planograms. Operate your digital twin. Make smarter refill and space decisions every day.',
  liveTitle: 'Live Digital Twin', liveSub: 'Shelves, rooms, routes, temperature and congestion in one operational scene.',
  overview: 'Overview', topView: 'Top View', chilled: '+4 Chilled', frozen: '-18 Frozen', dispatch: 'Dispatch', fullscreen: 'Fullscreen', exitFullscreen: 'Exit fullscreen',
  camera: 'Camera', skuSearch: 'Search SKU / product', selected: 'Selected Object', insights: 'AI Insights', minimap: 'Mini Map', heatmap: 'Heatmap', layers: 'Layers', traffic: 'Traffic', facilities: 'Facilities',
  addCorridor: 'Add Corridor', addColumn: 'Add Column', addChilled: 'Add Chilled Room', addFrozen: 'Add Frozen Room', suggestLayout: 'Suggest Best Layout', save: 'Save', duplicate: 'Duplicate', delete: 'Delete',
  properties: 'Properties', objectType: 'Object type', zone: 'Zone', width: 'Width', depth: 'Depth', height: 'Height', rotation: 'Rotation', modules: 'Modules', shelves: 'Shelves', fill: 'Fill rate',
  shelfEditor: 'Shelf Interior Editor', printShelf: 'Print Shelf', printModule: 'Print Module', addProduct: 'Assign Product', sortSales: 'Sort by Sales', sortBrand: 'Sort by Brand', aiFacing: 'AI Facing Suggestion',
  assignTask: 'Assign Task', adminAnswer: 'Admin Response', store: 'Store', assignee: 'Owner', priority: 'Priority', status: 'Status', deadline: 'Deadline', response: 'Response', totalView: 'Total View', storeView: 'Store View',
  ambient: 'Ambient', coldCapacity: 'Cold Capacity', frozenCapacity: 'Frozen Capacity', changedProducts: 'Products to Move', occupancy: 'Occupancy', productImages: 'Product Images'
  , loadingStores: 'Loading depots…', noAuthorizedStores: 'No authorized depot'
};

const dict = {
  en: base,
  tr: {
    ...base,
    command: 'Komuta Merkezi', storeDna: 'Depo Kurulumu', live3d: 'Canlı 3D', architect: 'Mimari Düzenleyici', placement: 'Ürün Yerleşimi', library: 'Ürün Kütüphanesi', fixture: 'Ekipman Kütüphanesi', planogram: 'Planogram', delta: 'Delta Planogram', publishing: 'Yayınlama', tasks: 'Görevler', reports: 'Raporlar', admin: 'Admin', rules: 'Kural ve Ağırlık Motoru', photos: 'Fotoğraf Kanıtı / Görev Kapatma',
    online: 'Çevrimiçi', system: 'Sistem Durumu', uploadSku: 'SKU yükle', uploadLayout: 'Layout yükle', generate: 'Optimum plan üret', open3d: '3D stüdyoyu aç',
    title: 'Depo zekâsı, kusursuz operasyon orkestrasyonu.', subtitle: 'Planogramı optimize et. Dijital ikizi yönet. Refill ve alan kararlarını her gün daha akıllı ver.',
    liveTitle: 'Canlı Dijital İkiz', liveSub: 'Raf, oda, rota, ısı ve sıkışıklık bölgeleri tek operasyon sahnesinde.',
    overview: 'Genel Bakış', topView: 'Üst Görünüm', chilled: '+4 Soğuk', frozen: '-18 Donuk', dispatch: 'Sevkiyat', fullscreen: 'Tam ekran', exitFullscreen: 'Tam ekrandan çık',
    camera: 'Kamera', skuSearch: 'SKU / ürün ara', selected: 'Seçili Obje', insights: 'AI İçgörüler', minimap: 'Mini Harita', heatmap: 'Heatmap', layers: 'Katmanlar', traffic: 'Trafik', facilities: 'Tesisler',
    addCorridor: 'Koridor ekle', addColumn: 'Kolon ekle', addChilled: 'Soğuk oda ekle', addFrozen: 'Donuk oda ekle', suggestLayout: 'En iyi yerleşimi öner', save: 'Kaydet', duplicate: 'Kopyala', delete: 'Sil',
    properties: 'Özellikler', objectType: 'Nesne tipi', zone: 'Zone', width: 'Genişlik', depth: 'Derinlik', height: 'Yükseklik', rotation: 'Yön', modules: 'Modül', shelves: 'Raf', fill: 'Doluluk',
    shelfEditor: 'Raf İç Düzenleyici', printShelf: 'Rafı yazdır', printModule: 'Modülü yazdır', addProduct: 'Ürün ata', sortSales: 'Satışa göre diz', sortBrand: 'Markaya göre diz', aiFacing: 'AI facing öner',
    assignTask: 'Görev ata', adminAnswer: 'Admin yanıtı', store: 'Depo', assignee: 'Sorumlu', priority: 'Öncelik', status: 'Durum', deadline: 'Termin', response: 'Yanıt', totalView: 'Toplam görünüm', storeView: 'Depo görünümü',
    ambient: 'Kuru', coldCapacity: 'Soğuk Kapasite', frozenCapacity: 'Donuk Kapasite', changedProducts: 'Yeri değişecek ürün', occupancy: 'Doluluk', productImages: 'Ürün görselleri', loadingStores: 'Depolar yükleniyor…', noAuthorizedStores: 'Yetkili depo yok'
  },
  de: {
    ...base,
    command: 'Kommandozentrale', storeDna: 'Store DNA', live3d: 'Live 3D', architect: 'Layout-Architekt', placement: 'Produktplatzierung', library: 'Produktbibliothek', fixture: 'Fixture-Bibliothek', delta: 'Delta-Planogramm', publishing: 'Veröffentlichung', tasks: 'Aufgaben', reports: 'Berichte', admin: 'Admin', rules: 'Regel-Engine', photos: 'Fotodokumentation',
    online: 'Online', system: 'Systemstatus', uploadSku: 'SKUs hochladen', uploadLayout: 'Layout hochladen', generate: 'Optimalen Plan erzeugen', open3d: '3D Studio öffnen',
    title: 'Lagerintelligenz, sauber orchestriert.', subtitle: 'Planogramme optimieren. Digitalen Zwilling steuern. Refill- und Flächenentscheidungen smarter treffen.',
    liveTitle: 'Live Digitaler Zwilling', overview: 'Übersicht', topView: 'Draufsicht', chilled: '+4 Gekühlt', frozen: '-18 Tiefkühl', dispatch: 'Dispatch', camera: 'Kamera', skuSearch: 'SKU / Produkt suchen', selected: 'Ausgewähltes Objekt',
    addCorridor: 'Korridor hinzufügen', addColumn: 'Säule hinzufügen', addChilled: 'Kühlraum hinzufügen', addFrozen: 'Tiefkühlraum hinzufügen', suggestLayout: 'Bestes Layout vorschlagen', save: 'Speichern', duplicate: 'Duplizieren', delete: 'Löschen', properties: 'Eigenschaften', loadingStores: 'Lager werden geladen…', noAuthorizedStores: 'Kein berechtigtes Lager'
  },
  ar: {
    ...base,
    command: 'مركز القيادة', storeDna: 'إعداد المستودع', live3d: 'التوأم ثلاثي الأبعاد', architect: 'مصمم التخطيط', placement: 'توزيع المنتجات', library: 'مكتبة المنتجات', fixture: 'مكتبة المعدات', planogram: 'مخطط الرفوف', delta: 'تغييرات المخطط', publishing: 'النشر والمتابعة', tasks: 'المهام', reports: 'التقارير', admin: 'الإدارة', rules: 'محرك القواعد', photos: 'توثيق الصور',
    online: 'متصل', system: 'حالة النظام', uploadSku: 'رفع SKU', uploadLayout: 'رفع التخطيط', generate: 'إنشاء الخطة المثلى', open3d: 'فتح استوديو 3D',
    title: 'ذكاء المستودع، بتنظيم تشغيلي متقن.', subtitle: 'حسّن مخطط الرفوف. أدر التوأم الرقمي. اتخذ قرارات أذكى للمساحة وإعادة التعبئة.',
    liveTitle: 'التوأم الرقمي المباشر', liveSub: 'الرفوف والغرف والمسارات والحرارة والازدحام في مشهد واحد.',
    overview: 'نظرة عامة', topView: 'عرض علوي', chilled: '+4 مبرد', frozen: '-18 مجمد', dispatch: 'الشحن', fullscreen: 'ملء الشاشة', exitFullscreen: 'الخروج من ملء الشاشة',
    camera: 'الكاميرا', skuSearch: 'بحث SKU / منتج', selected: 'العنصر المحدد', insights: 'رؤى الذكاء', minimap: 'الخريطة المصغرة', heatmap: 'خريطة حرارية', layers: 'الطبقات', traffic: 'الحركة', facilities: 'المرافق',
    addCorridor: 'إضافة ممر', addColumn: 'إضافة عمود', addChilled: 'إضافة غرفة تبريد', addFrozen: 'إضافة غرفة تجميد', suggestLayout: 'اقتراح أفضل توزيع', save: 'حفظ', duplicate: 'نسخ', delete: 'حذف',
    properties: 'الخصائص', objectType: 'نوع العنصر', zone: 'المنطقة', width: 'العرض', depth: 'العمق', height: 'الارتفاع', rotation: 'الاتجاه', modules: 'الوحدات', shelves: 'الرفوف', fill: 'نسبة الامتلاء',
    shelfEditor: 'محرر داخل الرف', printShelf: 'طباعة الرف', printModule: 'طباعة الوحدة', addProduct: 'إضافة منتج', sortSales: 'ترتيب حسب المبيعات', sortBrand: 'ترتيب حسب العلامة', aiFacing: 'اقتراح Facing بالذكاء',
    assignTask: 'إسناد مهمة', adminAnswer: 'رد الإدارة', store: 'المستودع', assignee: 'المسؤول', priority: 'الأولوية', status: 'الحالة', deadline: 'الموعد', response: 'الرد', totalView: 'العرض الكلي', storeView: 'عرض المستودع',
    ambient: 'جاف', coldCapacity: 'سعة التبريد', frozenCapacity: 'سعة التجميد', changedProducts: 'منتجات سيتم نقلها', occupancy: 'الامتلاء', productImages: 'صور المنتجات', loadingStores: 'جارٍ تحميل المستودعات…', noAuthorizedStores: 'لا يوجد مستودع مصرح'
  }
};

export function tt(lang, key) {
  return (dict[lang] && dict[lang][key]) || dict.en[key] || key;
}

export const languages = ['tr', 'en', 'de', 'ar'];
