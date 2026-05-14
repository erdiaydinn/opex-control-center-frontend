export const commandModules = [
  {
    id: "planogram",
    title: "Planogram Studio",
    subtitle: "Raf zekası, 3D yerleşim ve kategori optimizasyonu",
    route: "/planogram",
    status: "active",
    statusLabel: "Aktif",
    metric: "Layout Engine",
    signal: "Shelf Intelligence",
    icon: "layout",
  },
  {
    id: "dockos",
    title: "DockOS",
    subtitle: "Sevkiyat, randevu, tedarikçi ve kapasite kontrolü",
    route: "/dockos",
    status: "active",
    statusLabel: "Aktif",
    metric: "Inbound Ops",
    signal: "Dock Control",
    icon: "route",
  },
  {
    id: "budget",
    title: "Budget Control",
    subtitle: "PR, PO, maliyet ve bütçe görünürlüğü",
    route: "/budget",
    status: "active",
    statusLabel: "Aktif",
    metric: "Finance Ops",
    signal: "Cost Radar",
    icon: "budget",
  },
  {
    id: "academy",
    title: "OPEX Academy",
    subtitle: "SOP, eğitim, video ve yapay zeka bilgi asistanı",
    route: "#",
    status: "soon",
    statusLabel: "Yakında",
    metric: "Learning Hub",
    signal: "Knowledge Base",
    icon: "academy",
  },
  {
    id: "insight",
    title: "AI Insight Base",
    subtitle: "Operasyon verisinden otomatik yorum ve aksiyon önerisi",
    route: "#",
    status: "soon",
    statusLabel: "Yakında",
    metric: "AI Layer",
    signal: "Decision Engine",
    icon: "ai",
  },
  {
    id: "cycle-count",
    title: "Cycle Count Risk",
    subtitle: "Stok doğruluğu, şüpheli sayım ve aksiyon takibi",
    route: "#",
    status: "soon",
    statusLabel: "Yakında",
    metric: "Stock Accuracy",
    signal: "Risk Detection",
    icon: "cycle",
  },
];

export const commandStats = [
  {
    label: "Aktif Modül",
    value: "3",
    detail: "Planogram, DockOS, Budget",
  },
  {
    label: "Sistem Durumu",
    value: "Stable",
    detail: "Portal erişimi hazır",
  },
  {
    label: "Operasyon Modu",
    value: "Live",
    detail: "Kontrol, görünürlük, aksiyon",
  },
];

export const liveSignals = [
  {
    label: "System Status",
    value: "Stable",
    tone: "green",
  },
  {
    label: "Active Modules",
    value: "3",
    tone: "blue",
  },
  {
    label: "Pending Builds",
    value: "3",
    tone: "amber",
  },
  {
    label: "Last Sync",
    value: "Now",
    tone: "pink",
  },
];
