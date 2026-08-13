const ACCESS_STORAGE_KEY = "opex_access_config_v5";
const LEGACY_ACCESS_STORAGE_KEYS = [
  "opex_access_config_v4",
  "opex_access_config_v3",
  "opex_access_config_v2",
  "opex_access_config_v1",
];
const SESSION_STORAGE_KEY = "opex_current_user";

export const ACCESS_MODULES = [
  { key: "planogram", title: "Planogram Studio", description: "Raf, fixture, facing ve planogram operasyonu" },
  { key: "dockos", title: "DockOS", description: "Sevkiyat, randevu, PO ve depo kabul kontrolü" },
  { key: "budget", title: "Budget Control", description: "PR, PO, fatura ve bütçe görünürlüğü" },
  { key: "workforce", title: "Workforce Control", description: "Picker vardiyası, puantaj, konum ve bordro akışı" },
  { key: "recruitment", title: "Hiring Control", description: "Norm bazlı işe alım talebi, onay ve partner bildirimi" },
  { key: "academy", title: "OPEX Academy", description: "SOP, eğitim ve bilgi merkezi" },
  { key: "insight", title: "AI Insight Base", description: "Operasyon içgörüsü ve aksiyon önerileri" },
  { key: "inventory", title: "Inventory", description: "Kör sayım, fark mutabakatı, yeniden sayım ve tutanak yönetimi" },
  { key: "admin_access", title: "Access Control", description: "Kullanıcı, grup ve modül erişim yönetimi" },
];

export const MODULE_DETAIL_CONFIG = {
  inventory: {
    title: "Inventory Detay Yetkileri",
    features: [
      { key: "dashboard", label: "Sayım Dashboard", description: "Atanan, devam eden ve tamamlanan sayımları görür" },
      { key: "documents", label: "Sayım Belgeleri", description: "Sayım belgesi oluşturma ve belge durumları" },
      { key: "masterData", label: "Ana Veri", description: "Lokasyon ve SKU ana verisi yönetimi" },
      { key: "blindCount", label: "Kör Sayım", description: "Terminal ve web kör sayım ekranları" },
      { key: "reconciliation", label: "Fark Mutabakatı", description: "Lokasyon ve SKU fark inceleme ekranı" },
      { key: "recount", label: "Yeniden Sayım", description: "Müdür yeniden sayım görevi ve sonucu" },
      { key: "approvals", label: "Onay ve Kilitleme", description: "Belge onayı, kapatma ve kilitleme" },
      { key: "deviceManagement", label: "Terminal Yönetimi", description: "Zebra/Pelican cihaz bağlantıları ve durumları" },
      { key: "audit", label: "Audit Log", description: "Sayım değişikliklerinin denetim izi" },
    ],
    actions: [
      { key: "view", label: "Görüntüle" },
      { key: "createCount", label: "Sayım Oluştur" },
      { key: "importMasterData", label: "Ana Veri Yükle" },
      { key: "submitCount", label: "Sayım Gönder" },
      { key: "reconcile", label: "Farkı Sonuçlandır" },
      { key: "requestRecount", label: "Yeniden Sayım İste" },
      { key: "approveCount", label: "Sayımı Onayla" },
      { key: "lockCount", label: "Sayımı Kilitle" },
      { key: "export", label: "Tutanak / Excel Aktar" },
      { key: "manageDevices", label: "Terminalleri Yönet" },
    ],
    scope: {
      types: [
        { key: "all", label: "Tüm Türkiye" },
        { key: "region", label: "Bölge bazlı" },
        { key: "warehouse", label: "Depo bazlı" },
      ],
    },
  },
  recruitment: {
    title: "İşe Alım Talebi Yetkileri",
    features: [
      { key: "dashboard", label: "Norm ve Talep Dashboard", description: "Aktif çalışan, açık pozisyon ve norm açığı görünümü" },
      { key: "requests", label: "İşe Alım Talepleri", description: "Depo işe alım talep ve karar akışı" },
      { key: "evidence", label: "İstifa Belgeleri", description: "Önden talep için yüklenen istifa belgeleri" },
      { key: "notifications", label: "İK / Partner Bildirimleri", description: "Onay sonrası e-posta teslim kuyruğu" },
      { key: "settings", label: "Norm ve Bildirim Ayarları", description: "Depo normları, müdür kapasitesi ve alıcılar" },
    ],
    actions: [
      { key: "view", label: "Görüntüle" },
      { key: "viewRecruitment", label: "Talepleri Görüntüle" },
      { key: "createRecruitmentRequest", label: "İşe Alım Talebi Oluştur" },
      { key: "approveRecruitmentRequest", label: "Talebi Onayla / Reddet" },
      { key: "viewRecruitmentEvidence", label: "İstifa Belgesini Görüntüle" },
      { key: "manageRecruitmentNorms", label: "Depo Normlarını Yönet" },
      { key: "manageRecruitmentSettings", label: "İşe Alım Ayarlarını Yönet" },
      { key: "manageRecruitmentNotifications", label: "E-posta Kuyruğunu Yönet" },
    ],
    scope: {
      types: [
        { key: "all", label: "Tüm Türkiye" },
        { key: "region", label: "Bölge bazlı" },
        { key: "warehouse", label: "Depo bazlı" },
      ],
    },
  },
  workforce: {
    title: "Workforce Detay Yetkileri",
    features: [
      { key: "dashboard", label: "Canlı Operasyon", description: "Anlık vardiya ve istisna görünümü" },
      { key: "attendance", label: "Puantaj", description: "Kişisel ve depo bazlı puantaj raporları" },
      { key: "timesheet", label: "Puantaj Çıktısı", description: "Kişi/depo bazlı imzalı puantaj çıktısı" },
      { key: "periodClose", label: "Dönem Kapanışı", description: "Kesim tarihli kümülatif bordro, personel ve izin yükleme" },
      { key: "opexLab", label: "Geçici OPEX Roster Lab", description: "Uygulama geçişine kadar roster, 11 saat istisnası ve norm analizi" },
      { key: "shifts", label: "Vardiya Planı", description: "Vardiya atama ve planlama ekranı" },
      { key: "approvals", label: "Onay Akışı", description: "Eksik/fazla mesai ve düzeltme onayları" },
      { key: "managerTasks", label: "Yönetici Görevleri", description: "11 saat istisnası ve picker düzeltme talepleri" },
      { key: "communications", label: "Duyuru ve Bildirimler", description: "Vardiya hatırlatmaları ve hedefli mobil duyurular" },
      { key: "systemConfig", label: "Sistem Konfigürasyonu", description: "Şirket bazlı özellik açma ve kapatma" },
      { key: "warehouses", label: "Depo ve Konum", description: "Geofence ve doğrulama yöntemi ayarları" },
      { key: "rules", label: "Kural Setleri", description: "Mola, çalışma ve yasal limit kuralları" },
      { key: "leaves", label: "İzin Yönetimi", description: "İzin türleri ve çalışan izin girişleri" },
      { key: "devices", label: "Cihaz Yönetimi", description: "Picker cihaz eşleştirme ve risk görünümü" },
      { key: "audit", label: "Audit Log", description: "Workforce işlemlerinin değiştirilemez denetim izi" },
      { key: "pickerApp", label: "Picker Uygulaması", description: "Mobil vardiya ve arşiv deneyimi" },
    ],
    actions: [
      { key: "view", label: "Görüntüle" },
      { key: "createShift", label: "Vardiya Oluştur" },
      { key: "bulkShiftUpload", label: "Toplu Vardiya Yükle" },
      { key: "approveAttendance", label: "Puantaj Onayla" },
      { key: "bulkApprove", label: "Toplu Puantaj Onayla" },
      { key: "manualCorrection", label: "Puantajı Manuel Düzelt" },
      { key: "export", label: "Bordro / Excel Aktar" },
      { key: "printAttendance", label: "Puantaj Yazdır" },
      { key: "manageWarehouses", label: "Depo ve Konum Yönet" },
      { key: "manageRules", label: "Kuralları Yönet" },
      { key: "manageHolidays", label: "Resmî Tatilleri Yönet" },
      { key: "manageLeaves", label: "İzinleri Yönet" },
      { key: "manageDevices", label: "Cihazları Yönet" },
      { key: "viewAuditLog", label: "Audit Log Görüntüle" },
      { key: "viewFullNationalId", label: "TC Kimlik Numarasını Tam Gör" },
      { key: "manageEmployees", label: "Personel Ana Verisini Yönet" },
      { key: "importTimeOff", label: "Toplu İzin Yükle" },
      { key: "runPayrollClose", label: "Dönem Kapanışı Oluştur" },
      { key: "importRoster", label: "OPEX Roster Yükle" },
      { key: "overrideRoster", label: "Roster Simülasyonu Uygula" },
      { key: "assignRosterTask", label: "Roster Düzeltme Görevi Ata" },
      { key: "manageStaffingNorms", label: "BY ve Norm Eşlemesini Yönet" },
      { key: "resolveManagerTasks", label: "Yönetici Görevini Düzelt / Sonuçlandır" },
      { key: "manageAnnouncements", label: "Duyuru Yayınla" },
      { key: "manageNotifications", label: "Bildirim Politikalarını Yönet" },
      { key: "manageSystemConfig", label: "Sistem Özelliklerini Aç / Kapat" },
    ],
    scope: {
      types: [
        { key: "all", label: "Tüm Türkiye" },
        { key: "region", label: "Bölge bazlı" },
        { key: "warehouse", label: "Depo bazlı" },
      ],
    },
  },
  dockos: {
    title: "DockOS Detay Yetkileri",
    features: [
      { key: "dashboard", label: "Dashboard", description: "Genel DockOS özet ekranı" },
      { key: "livePurchaseOrders", label: "Canlı PO", description: "Canlı purchase order ekranı" },
      { key: "supplierAppointments", label: "Tedarikçi Randevu", description: "Tedarikçi randevu akışı" },
      { key: "shipmentDetails", label: "Sevkiyat Detayları", description: "Sevkiyat detay ve zorunlu alanları" },
      { key: "vehicleTracking", label: "Araç / Plaka Takibi", description: "Araç ve plaka alanları" },
      { key: "excelUpload", label: "Excel Upload", description: "Muhasebe / operasyon excel yükleme" },
      { key: "duplicateResolution", label: "Duplicate Karar", description: "Farklı tutarlı duplicate kayıt kararı" },
    ],
    actions: [
      { key: "view", label: "Görüntüle" },
      { key: "create", label: "Oluştur" },
      { key: "edit", label: "Düzenle" },
      { key: "approve", label: "Onayla" },
      { key: "export", label: "Export" },
      { key: "delete", label: "Sil" },
    ],
    scope: {
      types: [
        { key: "all", label: "Tüm Türkiye" },
        { key: "region", label: "Bölge bazlı" },
        { key: "warehouse", label: "Depo bazlı" },
        { key: "supplier", label: "Tedarikçi bazlı" },
      ],
    },
  },
  planogram: {
    title: "Planogram Detay Yetkileri",
    features: [
      { key: "layoutView", label: "Layout Görüntüle", description: "Planogram layout ekranını görür" },
      { key: "layoutEdit", label: "Layout Düzenle", description: "Layout üzerinde değişiklik yapar" },
      { key: "fixtureEdit", label: "Fixture Düzenle", description: "Raf, dolap, fixture düzenler" },
      { key: "ruleEdit", label: "Kural Düzenle", description: "Kategori / marka / raf kurallarını yönetir" },
      { key: "productAssign", label: "Ürün Atama", description: "Ürünleri raflara atar" },
      { key: "aiRecommend", label: "AI Öneri", description: "AI planogram önerilerini kullanır" },
    ],
    actions: [
      { key: "view", label: "Görüntüle" },
      { key: "create", label: "Oluştur" },
      { key: "edit", label: "Düzenle" },
      { key: "approve", label: "Onayla" },
      { key: "export", label: "Export" },
      { key: "delete", label: "Sil" },
    ],
    scope: {
      types: [
        { key: "all", label: "Tüm Türkiye" },
        { key: "region", label: "Bölge bazlı" },
        { key: "warehouse", label: "Depo bazlı" },
      ],
    },
  },
  budget: {
    title: "Budget Detay Yetkileri",
    features: [
      { key: "dashboard", label: "Dashboard", description: "Bütçe özet ekranı" },
      { key: "purchaseRequests", label: "PR Görünümü", description: "Purchase request kayıtları" },
      { key: "purchaseOrders", label: "PO Görünümü", description: "Purchase order kayıtları" },
      { key: "invoiceTracking", label: "Fatura Takibi", description: "Fatura ve ödeme takip alanı" },
      { key: "costCenter", label: "Cost Center", description: "Maliyet merkezi görünürlüğü" },
    ],
    actions: [
      { key: "view", label: "Görüntüle" },
      { key: "create", label: "Oluştur" },
      { key: "edit", label: "Düzenle" },
      { key: "approve", label: "Onayla" },
      { key: "export", label: "Export" },
      { key: "delete", label: "Sil" },
    ],
    scope: {
      types: [
        { key: "all", label: "Tüm Türkiye" },
        { key: "region", label: "Bölge bazlı" },
        { key: "warehouse", label: "Depo bazlı" },
        { key: "cost_center", label: "Cost Center bazlı" },
      ],
    },
  },
  academy: {
    title: "Academy Detay Yetkileri",
    features: [
      { key: "dashboard", label: "Eğitim Dashboard", description: "Atama, tamamlama ve başarı görünümü" },
      { key: "catalog", label: "Eğitim Kataloğu", description: "SOP, video ve eğitim içerikleri" },
      { key: "content", label: "İçerik Yönetimi", description: "İçerik oluşturma ve sürüm yönetimi" },
      { key: "assessments", label: "Sınav ve Sorular", description: "Video içi soru ve değerlendirmeler" },
      { key: "assignments", label: "Eğitim Atamaları", description: "Rol, bölge ve depo bazlı eğitim atama" },
      { key: "reports", label: "Eğitim Raporları", description: "Tamamlama ve başarı raporları" },
    ],
    actions: [
      { key: "view", label: "Görüntüle" },
      { key: "create", label: "İçerik Oluştur" },
      { key: "edit", label: "Düzenle" },
      { key: "publish", label: "Yayınla" },
      { key: "assign", label: "Eğitim Ata" },
      { key: "export", label: "Rapor Aktar" },
      { key: "delete", label: "Sil" },
    ],
    scope: {
      types: [
        { key: "all", label: "Tüm Türkiye" },
        { key: "region", label: "Bölge bazlı" },
        { key: "warehouse", label: "Depo bazlı" },
      ],
    },
  },
  insight: {
    title: "AI Insight Detay Yetkileri",
    features: [
      { key: "dashboard", label: "İçgörü Dashboard", description: "KPI ve risk özetlerini görür" },
      { key: "kpiExplorer", label: "KPI Explorer", description: "Metrik detay ve kırılımlarını inceler" },
      { key: "alerts", label: "Uyarılar", description: "Operasyon uyarıları ve eşik yönetimi" },
      { key: "recommendations", label: "Aksiyon Önerileri", description: "Önerileri inceleme ve karar akışı" },
      { key: "reports", label: "Raporlar", description: "Kaydedilmiş analiz ve raporlar" },
    ],
    actions: [
      { key: "view", label: "Görüntüle" },
      { key: "create", label: "Analiz Oluştur" },
      { key: "edit", label: "Düzenle" },
      { key: "approve", label: "Aksiyonu Onayla" },
      { key: "export", label: "Rapor Aktar" },
      { key: "delete", label: "Sil" },
    ],
    scope: {
      types: [
        { key: "all", label: "Tüm Türkiye" },
        { key: "region", label: "Bölge bazlı" },
        { key: "warehouse", label: "Depo bazlı" },
      ],
    },
  },
  admin_access: {
    title: "Access Control Detay Yetkileri",
    features: [
      { key: "users", label: "Kullanıcılar", description: "Kullanıcı hesapları ve durumları" },
      { key: "groups", label: "Gruplar", description: "Yetki grupları ve üyelikleri" },
      { key: "modulePermissions", label: "Modül Yetkileri", description: "View, admin ve detay yetkileri" },
      { key: "scopeManagement", label: "Veri Kapsamı", description: "Bölge, depo, tedarikçi ve cost center kapsamı" },
      { key: "audit", label: "Yetki Audit Log", description: "Yetki değişikliklerinin denetim izi" },
    ],
    actions: [
      { key: "view", label: "Görüntüle" },
      { key: "createUser", label: "Kullanıcı Oluştur" },
      { key: "editUser", label: "Kullanıcı Düzenle" },
      { key: "disableUser", label: "Kullanıcı Pasifleştir" },
      { key: "createGroup", label: "Grup Oluştur" },
      { key: "editGroup", label: "Grup Düzenle" },
      { key: "assignPermissions", label: "Yetki Ata" },
      { key: "refreshModules", label: "Modülleri Yenile" },
      { key: "exportAudit", label: "Audit Aktar" },
    ],
    scope: {
      types: [{ key: "all", label: "Tüm Platform" }],
    },
  },
};

export const SCOPE_OPTIONS = {
  regions: ["Marmara", "İç Anadolu", "Ege", "Akdeniz", "Karadeniz", "Doğu Anadolu", "Güneydoğu Anadolu"],
  warehouses: [
    "Fulya (İstanbul)",
    "Çeliktepe (İstanbul)",
    "Aydınlı (İstanbul) FR",
    "Anka (İstanbul)",
    "Bağcılar Sancak (İstanbul)",
    "Pamukkale (Denizli)",
    "Şükrüpaşa (Edirne)",
    "İsmetpaşa (Çanakkale)",
    "Bostancı (İstanbul)",
    "Göktürk (İstanbul)",
    "Kozyatağı (İstanbul)",
    "Göztepe (İstanbul)",
  ],
  suppliers: ["Tedarikçi A", "Tedarikçi B", "Tedarikçi C", "Everyday Roastery", "Yerel Üretici"],
  costCenters: ["OPEX", "DMart Operations", "Inbound", "Finance Ops", "Store Excellence"],
};

function safeJsonParse(value, fallback) {
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function normalizeEmail(email) {
  return String(email || "").trim().toLowerCase();
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function unique(values = []) {
  return [...new Set(values.filter(Boolean))];
}

function createDetailAccess(moduleKey, level = "none") {
  const detailConfig = MODULE_DETAIL_CONFIG[moduleKey];

  if (!detailConfig) {
    return {
      features: {},
      actions: {},
      scope: { type: "all", regions: [], warehouses: [], suppliers: [], costCenters: [] },
    };
  }

  const full = level === "admin" || level === "super";
  const viewOnly = level === "view";

  return {
    features: detailConfig.features.reduce((acc, feature) => {
      acc[feature.key] = full || viewOnly;
      return acc;
    }, {}),
    actions: detailConfig.actions.reduce((acc, action) => {
      if (full) acc[action.key] = true;
      else if (viewOnly) acc[action.key] = action.key === "view" || action.key === "export";
      else acc[action.key] = false;
      return acc;
    }, {}),
    scope: { type: "all", regions: [], warehouses: [], suppliers: [], costCenters: [] },
  };
}

function createModuleAccess(moduleKey, level = "none") {
  const view = level === "view" || level === "admin" || level === "super";
  const admin = level === "admin" || level === "super";

  return {
    view,
    admin,
    details: createDetailAccess(moduleKey, level),
  };
}

function createModulesForLevel(levelByModule = {}) {
  return ACCESS_MODULES.reduce((acc, module) => {
    acc[module.key] = createModuleAccess(module.key, levelByModule[module.key] || "none");
    return acc;
  }, {});
}

function createWorkforceManagerModules() {
  const modules = createModulesForLevel({ workforce: "view" });
  const allowedActions = [
    "view",
    "createShift",
    "bulkShiftUpload",
    "approveAttendance",
    "bulkApprove",
    "export",
    "printAttendance",
    "manageLeaves",
    "importTimeOff",
    "resolveManagerTasks",
  ];
  Object.keys(modules.workforce.details.actions).forEach((action) => {
    modules.workforce.details.actions[action] = allowedActions.includes(action);
  });
  modules.workforce.admin = false;
  modules.workforce.details.features.periodClose = false;
  modules.workforce.details.features.opexLab = false;
  return modules;
}

function createWorkforceHrModules() {
  const modules = createModulesForLevel({ workforce: "view" });
  const allowedFeatures = ["dashboard", "attendance", "timesheet", "periodClose", "leaves"];
  const allowedActions = ["view", "export", "printAttendance", "viewFullNationalId", "manageEmployees", "importTimeOff", "runPayrollClose"];
  Object.keys(modules.workforce.details.features).forEach((feature) => { modules.workforce.details.features[feature] = allowedFeatures.includes(feature); });
  Object.keys(modules.workforce.details.actions).forEach((action) => { modules.workforce.details.actions[action] = allowedActions.includes(action); });
  modules.workforce.admin = false;
  return modules;
}

function createRecruitmentManagerModules() {
  const modules = createModulesForLevel({ recruitment: "view" });
  const allowed = ["view", "viewRecruitment", "createRecruitmentRequest"];
  Object.keys(modules.recruitment.details.actions).forEach((action) => {
    modules.recruitment.details.actions[action] = allowed.includes(action);
  });
  modules.recruitment.admin = false;
  return modules;
}

export const DEFAULT_ACCESS_CONFIG = {
  groups: {
    super_admins: {
      id: "super_admins",
      name: "Super Admins",
      description: "Tüm modüller ve tüm yönetim alanları",
      status: "active",
      modules: createModulesForLevel({
        planogram: "super",
        dockos: "super",
        budget: "super",
        workforce: "super",
        recruitment: "super",
        academy: "super",
        insight: "super",
        inventory: "super",
        admin_access: "super",
      }),
    },
    dockos_admins: {
      id: "dockos_admins",
      name: "DockOS Admins",
      description: "DockOS yönetimi, PO, sevkiyat ve randevu operasyonları",
      status: "active",
      modules: createModulesForLevel({
        dockos: "admin",
      }),
    },
    workforce_admins: {
      id: "workforce_admins",
      name: "Workforce Admins",
      description: "Vardiya, puantaj, manuel düzeltme, onay ve bordro yönetimi",
      status: "active",
      modules: createModulesForLevel({
        workforce: "admin",
      }),
    },
    workforce_managers: {
      id: "workforce_managers",
      name: "Workforce Depo Müdürleri",
      description: "Vardiya, toplu yükleme, izin ve puantaj onayı; manuel düzeltme ve kural yönetimi hariç",
      status: "active",
      modules: createWorkforceManagerModules(),
    },
    workforce_hr: {
      id: "workforce_hr",
      name: "Workforce İK ve Bordro",
      description: "Tam TC, personel ana verisi, toplu izin ve dönem kapanışı; manuel puantaj düzeltme hariç",
      status: "active",
      modules: createWorkforceHrModules(),
    },
    recruitment_managers: {
      id: "recruitment_managers",
      name: "İşe Alım Talebi Oluşturan Müdürler",
      description: "Kendi kapsamındaki depo için norm kontrollü işe alım talebi oluşturur",
      status: "active",
      modules: createRecruitmentManagerModules(),
    },
    recruitment_hr: {
      id: "recruitment_hr",
      name: "İşe Alım İK Onay Ekibi",
      description: "Talepleri, istifa belgelerini, normları ve partner bildirimlerini yönetir",
      status: "active",
      modules: createModulesForLevel({ recruitment: "admin" }),
    },
    construction_team: {
      id: "construction_team",
      name: "İnşaat Ekibi",
      description: "İnşaat, bakım, tadilat, saha geliştirme ve sevkiyat takip görünümü",
      status: "active",
      modules: createModulesForLevel({
        dockos: "view",
        budget: "view",
      }),
    },
    finance_team: {
      id: "finance_team",
      name: "Finans Ekibi",
      description: "Budget, PR, PO, fatura ve maliyet merkezi görünürlüğü",
      status: "active",
      modules: createModulesForLevel({
        budget: "admin",
        dockos: "view",
      }),
    },
    operation_leaders: {
      id: "operation_leaders",
      name: "Operasyon Liderleri",
      description: "Operasyon modüllerinde geniş görüntüleme ve export",
      status: "active",
      modules: createModulesForLevel({
        planogram: "view",
        dockos: "view",
        budget: "view",
        inventory: "view",
        workforce: "view",
        recruitment: "view",
      }),
    },
    viewers: {
      id: "viewers",
      name: "Viewer",
      description: "Temel görüntüleme grubu",
      status: "active",
      modules: createModulesForLevel({
        planogram: "view",
        dockos: "view",
      }),
    },
  },
  users: {
    "erdi.aydin@yemeksepeti.com": {
      email: "erdi.aydin@yemeksepeti.com",
      name: "Erdi Aydın",
      role: "super_admin",
      status: "active",
      groups: ["super_admins"],
      modules: createModulesForLevel({}),
    },
    "admin@yemeksepeti.com": {
      email: "admin@yemeksepeti.com",
      name: "Admin User",
      role: "admin",
      status: "active",
      groups: ["dockos_admins", "workforce_admins", "recruitment_hr"],
      modules: createModulesForLevel({
        planogram: "admin",
        budget: "admin",
        workforce: "admin",
        recruitment: "admin",
      }),
    },
    "viewer@yemeksepeti.com": {
      email: "viewer@yemeksepeti.com",
      name: "Viewer User",
      role: "viewer",
      status: "active",
      groups: ["viewers"],
      modules: createModulesForLevel({}),
    },
    "noaccess@yemeksepeti.com": {
      email: "noaccess@yemeksepeti.com",
      name: "No Access User",
      role: "viewer",
      status: "active",
      groups: [],
      modules: createModulesForLevel({}),
    },
  },
};

function normalizeModuleAccess(moduleKey, access = {}) {
  const base = createModuleAccess(moduleKey, "none");

  return {
    ...base,
    ...access,
    view: Boolean(access.view),
    admin: Boolean(access.admin),
    details: {
      ...base.details,
      ...(access.details || {}),
      features: {
        ...(base.details.features || {}),
        ...(access.details?.features || {}),
      },
      actions: {
        ...(base.details.actions || {}),
        ...(access.details?.actions || {}),
      },
      scope: {
        ...(base.details.scope || {}),
        ...(access.details?.scope || {}),
      },
    },
  };
}

function normalizeModules(modules = {}, role = "viewer") {
  const normalized = clone(modules || {});

  return ACCESS_MODULES.reduce((acc, module) => {
    if (role === "super_admin") acc[module.key] = createModuleAccess(module.key, "super");
    else {
      const legacyAccess =
        module.key === "inventory" ? modules.cycle_count : undefined;
      acc[module.key] = normalizeModuleAccess(
        module.key,
        modules[module.key] || legacyAccess || {}
      );
    }
    return acc;
  }, normalized);
}

function normalizeUser(email, user = {}) {
  const cleanEmail = normalizeEmail(email || user.email);
  const existingDefault = DEFAULT_ACCESS_CONFIG.users[cleanEmail];

  const role = user.role || existingDefault?.role || "viewer";

  return {
    email: cleanEmail,
    name: user.name || existingDefault?.name || cleanEmail,
    role,
    status: user.status || existingDefault?.status || "active",
    groups: Array.isArray(user.groups)
      ? unique(user.groups)
      : unique(existingDefault?.groups || []),
    modules: normalizeModules(user.modules || existingDefault?.modules || {}, role),
  };
}

function normalizeGroup(id, group = {}) {
  const groupId = String(id || group.id || "").trim();
  const existingDefault = DEFAULT_ACCESS_CONFIG.groups[groupId];

  return {
    id: groupId,
    name: group.name || existingDefault?.name || groupId,
    description: group.description || existingDefault?.description || "",
    status: group.status || existingDefault?.status || "active",
    modules: normalizeModules(group.modules || existingDefault?.modules || {}, "group"),
  };
}

function loadStoredConfig() {
  if (typeof window === "undefined") return null;

  const current = window.localStorage.getItem(ACCESS_STORAGE_KEY);
  if (current) {
    return {
      config: safeJsonParse(current, null),
      storageKey: ACCESS_STORAGE_KEY,
    };
  }

  for (const key of LEGACY_ACCESS_STORAGE_KEYS) {
    const value = window.localStorage.getItem(key);
    if (value) {
      return {
        config: safeJsonParse(value, null),
        storageKey: key,
      };
    }
  }

  return null;
}

export function refreshAccessConfig(config, { includeDefaultEntities = false } = {}) {
  const source = config && typeof config === "object" ? config : {};
  const sourceGroups = source.groups && typeof source.groups === "object" ? source.groups : {};
  const sourceUsers = source.users && typeof source.users === "object" ? source.users : {};

  const groupEntries = includeDefaultEntities
    ? { ...DEFAULT_ACCESS_CONFIG.groups, ...sourceGroups }
    : sourceGroups;
  const userEntries = includeDefaultEntities
    ? { ...DEFAULT_ACCESS_CONFIG.users, ...sourceUsers }
    : sourceUsers;

  return {
    groups: Object.entries(groupEntries).reduce((acc, [id, group]) => {
      const groupId = String(id || group?.id || "").trim();
      if (groupId) acc[groupId] = normalizeGroup(groupId, group);
      return acc;
    }, {}),
    users: Object.entries(userEntries).reduce((acc, [email, accessUser]) => {
      const cleanEmail = normalizeEmail(email || accessUser?.email);
      if (cleanEmail) acc[cleanEmail] = normalizeUser(cleanEmail, accessUser);
      return acc;
    }, {}),
  };
}

export function getAccessConfig() {
  if (typeof window === "undefined") return clone(DEFAULT_ACCESS_CONFIG);

  const stored = loadStoredConfig();
  const parsed = stored?.config;

  if (!parsed || !parsed.users) {
    window.localStorage.setItem(ACCESS_STORAGE_KEY, JSON.stringify(DEFAULT_ACCESS_CONFIG));
    return clone(DEFAULT_ACCESS_CONFIG);
  }

  const merged = refreshAccessConfig(parsed, {
    includeDefaultEntities: stored.storageKey !== ACCESS_STORAGE_KEY,
  });

  window.localStorage.setItem(ACCESS_STORAGE_KEY, JSON.stringify(merged));
  return merged;
}

export function saveAccessConfig(config) {
  if (typeof window === "undefined") return;

  const normalized = refreshAccessConfig(config);

  window.localStorage.setItem(ACCESS_STORAGE_KEY, JSON.stringify(normalized));
  window.dispatchEvent(new CustomEvent("opex-access-config-updated", { detail: normalized }));
}

export function getSessionUser() {
  if (typeof window === "undefined") return null;
  return safeJsonParse(window.localStorage.getItem(SESSION_STORAGE_KEY), null);
}

export function saveSessionUser(user) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(user));
}

export function clearSessionUser() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(SESSION_STORAGE_KEY);
}

export function buildUserFromEmail(email) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();

  if (!cleanEmail) return null;

  const existing = config.users[cleanEmail];

  if (existing) {
    return {
      email: cleanEmail,
      name: existing.name || cleanEmail,
      role: existing.role || "viewer",
      status: existing.status || "active",
    };
  }

  return {
    email: cleanEmail,
    name: cleanEmail,
    role: "viewer",
    status: "active",
  };
}

function mergeScope(currentScope, incomingScope) {
  const current = currentScope || { type: "none", regions: [], warehouses: [], suppliers: [], costCenters: [] };
  const incoming = incomingScope || { type: "none", regions: [], warehouses: [], suppliers: [], costCenters: [] };

  if (current.type === "all" || incoming.type === "all") {
    return { type: "all", regions: [], warehouses: [], suppliers: [], costCenters: [] };
  }

  return {
    type: incoming.type !== "none" ? incoming.type : current.type,
    regions: unique([...(current.regions || []), ...(incoming.regions || [])]),
    warehouses: unique([...(current.warehouses || []), ...(incoming.warehouses || [])]),
    suppliers: unique([...(current.suppliers || []), ...(incoming.suppliers || [])]),
    costCenters: unique([...(current.costCenters || []), ...(incoming.costCenters || [])]),
  };
}

function mergeModuleAccess(moduleKey, list = []) {
  const base = createModuleAccess(moduleKey, "none");

  return list.reduce((acc, item) => {
    if (!item) return acc;

    const normalized = normalizeModuleAccess(moduleKey, item);

    return {
      view: acc.view || normalized.view,
      admin: acc.admin || normalized.admin,
      details: {
        features: Object.keys(base.details.features || {}).reduce((obj, key) => {
          obj[key] = Boolean(acc.details.features?.[key] || normalized.details.features?.[key]);
          return obj;
        }, {}),
        actions: Object.keys(base.details.actions || {}).reduce((obj, key) => {
          obj[key] = Boolean(acc.details.actions?.[key] || normalized.details.actions?.[key]);
          return obj;
        }, {}),
        scope: mergeScope(acc.details.scope, normalized.details.scope),
      },
    };
  }, base);
}

export function getEffectiveAccess(email) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") {
    return createModulesForLevel({});
  }

  if (accessUser.role === "super_admin") {
    return createModulesForLevel(
      ACCESS_MODULES.reduce((acc, module) => {
        acc[module.key] = "super";
        return acc;
      }, {})
    );
  }

  return ACCESS_MODULES.reduce((acc, module) => {
    const groupAccessList = (accessUser.groups || [])
      .map((groupId) => config.groups?.[groupId])
      .filter((group) => group && group.status === "active")
      .map((group) => group.modules?.[module.key]);

    acc[module.key] = mergeModuleAccess(module.key, [
      ...groupAccessList,
      accessUser.modules?.[module.key],
    ]);

    return acc;
  }, {});
}

export function getUserPermissions(email) {
  return getEffectiveAccess(email);
}

export function canUser(email, moduleKey, action = "view") {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") return false;
  if (accessUser.role === "super_admin") return true;

  const moduleAccess = getEffectiveAccess(cleanEmail)?.[moduleKey];

  if (action === "admin") return Boolean(moduleAccess?.admin);
  return Boolean(moduleAccess?.view);
}

export function canUserFeature(email, moduleKey, featureKey) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") return false;
  if (accessUser.role === "super_admin") return true;

  const moduleAccess = getEffectiveAccess(cleanEmail)?.[moduleKey];

  if (!moduleAccess?.view) return false;
  return Boolean(moduleAccess?.details?.features?.[featureKey]);
}

export function canUserAction(email, moduleKey, actionKey) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") return false;
  if (accessUser.role === "super_admin") return true;

  const moduleAccess = getEffectiveAccess(cleanEmail)?.[moduleKey];

  if (!moduleAccess?.view) return false;
  return Boolean(moduleAccess?.details?.actions?.[actionKey]);
}

export function getUserModuleScope(email, moduleKey) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  const accessUser = config.users[cleanEmail];

  if (!accessUser || accessUser.status !== "active") {
    return { type: "none", regions: [], warehouses: [], suppliers: [], costCenters: [] };
  }

  if (accessUser.role === "super_admin") {
    return { type: "all", regions: [], warehouses: [], suppliers: [], costCenters: [] };
  }

  return getEffectiveAccess(cleanEmail)?.[moduleKey]?.details?.scope || {
    type: "all",
    regions: [],
    warehouses: [],
    suppliers: [],
    costCenters: [],
  };
}

export function isUserSuperAdmin(email) {
  const cleanEmail = normalizeEmail(email);
  const config = getAccessConfig();
  return config.users[cleanEmail]?.role === "super_admin";
}
