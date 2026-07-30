import React, { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import {
  DEFAULT_PRODUCTS,
  computeMetrics,
  generateDefaultLayout,
  localGeneratePlanogram,
  normalizeProduct,
  parseCSV,
} from "./utils/planogram";

const STRINGS = {
  tr: {
    loginTitle: "Operasyon zekâsına giriş",
    loginSub: "Planogram, fixture kapasitesi, refill riski ve canlı 3D operasyon tek merkezde.",
    username: "Kullanıcı adı",
    password: "Şifre",
    store: "Aktif depo",
    launch: "Komuta merkezini aç",
    command: "Komuta Merkezi",
    studio: "Canlı 3D",
    layout: "2D Plan",
    rules: "Kurallar",
    reports: "Raporlar",
    products: "Ürünler",
    headline: "Darkstore operasyonları için dünya sınıfı planogram zekâsı.",
    subline: "Satış hızı, raf hacmi, soğuk zincir, refill işçilik maliyeti ve picking rotası aynı dijital ikizde birleşir.",
    generate: "AI Planogram Üret",
    openStudio: "Canlı 3D'yi Aç",
    uploadSku: "SKU CSV Yükle",
    uploadLayout: "Layout Yükle",
    statusOnline: "EA Core Çevrimiçi",
    liveStudio: "Live Operations Command Center",
    aiRecommends: "AI En İyi Yerleşimi Öner",
    camera: "Kamera",
    searchSku: "SKU ara ve uç",
    fly: "Rafa uç",
    minimap: "Mini harita",
    insights: "AI İçgörüleri",
    reportTitle: "Operasyonel Kapasite Raporu",
    ruleTitle: "Planogram Kural Motoru",
    loading1: "Store DNA okunuyor",
    loading2: "Fixture ağı kuruluyor",
    loading3: "SKU satış grafı bağlanıyor",
    loading4: "Refill riski hesaplanıyor",
    loading5: "EA Intelligence Core online",
  },
  en: {
    loginTitle: "Enter operational intelligence",
    loginSub: "Planogram, fixture capacity, refill risk and live 3D operations in one command layer.",
    username: "Username",
    password: "Password",
    store: "Active store",
    launch: "Launch command center",
    command: "Command Center",
    studio: "Live 3D",
    layout: "2D Plan",
    rules: "Rules",
    reports: "Reports",
    products: "Products",
    headline: "World-class planogram intelligence for darkstore operations.",
    subline: "Sales velocity, shelf volume, cold chain, refill labor cost and picking route converge in one digital twin.",
    generate: "Generate AI Planogram",
    openStudio: "Open Live 3D",
    uploadSku: "Upload SKU CSV",
    uploadLayout: "Upload Layout",
    statusOnline: "EA Core Online",
    liveStudio: "Live Operations Command Center",
    aiRecommends: "Recommend optimal layout",
    camera: "Camera",
    searchSku: "Search SKU and fly",
    fly: "Fly to shelf",
    minimap: "Minimap",
    insights: "AI Insights",
    reportTitle: "Operational Capacity Report",
    ruleTitle: "Planogram Rule Engine",
    loading1: "Reading Store DNA",
    loading2: "Building fixture graph",
    loading3: "Connecting SKU sales graph",
    loading4: "Calculating refill risk",
    loading5: "EA Intelligence Core online",
  },
  de: {
    loginTitle: "Betriebsintelligenz starten",
    loginSub: "Planogramm, Kapazität, Nachfüllrisiko und Live-3D in einer Kommandoebene.",
    username: "Benutzername",
    password: "Passwort",
    store: "Aktiver Standort",
    launch: "Command Center öffnen",
    command: "Kommandozentrale",
    studio: "Live 3D",
    layout: "2D Plan",
    rules: "Regeln",
    reports: "Berichte",
    products: "Produkte",
    headline: "Weltklasse-Planogramm-Intelligenz für Darkstores.",
    subline: "Absatzgeschwindigkeit, Regalvolumen, Kühlkette, Nachfüllaufwand und Picking-Route in einem digitalen Zwilling.",
    generate: "AI-Planogramm erzeugen",
    openStudio: "Live 3D öffnen",
    uploadSku: "SKU CSV laden",
    uploadLayout: "Layout laden",
    statusOnline: "EA Core Online",
    liveStudio: "Live Operations Command Center",
    aiRecommends: "Optimales Layout empfehlen",
    camera: "Kamera",
    searchSku: "SKU suchen und anfliegen",
    fly: "Zum Regal fliegen",
    minimap: "Minikarte",
    insights: "AI Erkenntnisse",
    reportTitle: "Kapazitätsbericht",
    ruleTitle: "Planogramm-Regelwerk",
    loading1: "Store-DNA wird gelesen",
    loading2: "Fixture-Netz wird aufgebaut",
    loading3: "SKU-Verkaufsgraph wird verbunden",
    loading4: "Nachfüllrisiko wird berechnet",
    loading5: "EA Intelligence Core online",
  },
  ar: {
    loginTitle: "الدخول إلى ذكاء العمليات",
    loginSub: "المخطط، السعة، مخاطر التعبئة وعمليات 3D في طبقة واحدة.",
    username: "اسم المستخدم",
    password: "كلمة المرور",
    store: "المتجر النشط",
    launch: "فتح مركز القيادة",
    command: "مركز القيادة",
    studio: "3D مباشر",
    layout: "خطة 2D",
    rules: "القواعد",
    reports: "التقارير",
    products: "المنتجات",
    headline: "ذكاء Planogram عالمي المستوى لعمليات Darkstore.",
    subline: "سرعة البيع، حجم الرف، سلسلة التبريد، تكلفة التعبئة ومسار الالتقاط في توأم رقمي واحد.",
    generate: "إنشاء Planogram بالذكاء الاصطناعي",
    openStudio: "فتح 3D المباشر",
    uploadSku: "تحميل SKU CSV",
    uploadLayout: "تحميل Layout",
    statusOnline: "EA Core متصل",
    liveStudio: "مركز العمليات المباشر",
    aiRecommends: "اقتراح التخطيط الأمثل",
    camera: "الكاميرا",
    searchSku: "بحث SKU والانتقال",
    fly: "الانتقال إلى الرف",
    minimap: "خريطة مصغرة",
    insights: "رؤى AI",
    reportTitle: "تقرير السعة التشغيلية",
    ruleTitle: "محرك قواعد Planogram",
    loading1: "قراءة Store DNA",
    loading2: "بناء شبكة التجهيزات",
    loading3: "ربط مبيعات SKU",
    loading4: "حساب مخاطر التعبئة",
    loading5: "EA Intelligence Core online",
  },
};

const STORES = ["ACIBADEM", "Anka (İstanbul)", "Güven (Kocaeli) FR", "Çekirge (Bursa)", "Şükrüpaşa (Edirne)"];
const CAMERAS = {
  orbit: { label: "Orbit", className: "cam-orbit" },
  top: { label: "Top", className: "cam-top" },
  focus: { label: "Focus", className: "cam-focus" },
  chilled: { label: "+4", className: "cam-chilled" },
  frozen: { label: "-18", className: "cam-frozen" },
  dispatch: { label: "Dispatch", className: "cam-dispatch" },
};

function pct(v) {
  return `${Math.round(Number(v || 0))}%`;
}

function clamp(n, a, b) {
  return Math.max(a, Math.min(b, Number(n || 0)));
}

function productCount(plan) {
  let c = 0;
  for (const a of plan?.aisles || []) for (const m of a.modules || []) for (const s of m.shelves || []) c += (s.products || []).length;
  return c;
}

function countShelves(plan) {
  let c = 0;
  for (const a of plan?.aisles || []) for (const m of a.modules || []) c += (m.shelves || []).length;
  return c;
}

function getAisles(plan) {
  return (plan?.aisles || []).slice(0, 14);
}

function findProductLocation(plan, q) {
  const term = String(q || "").trim().toLowerCase();
  if (!term) return null;
  for (const a of plan?.aisles || []) {
    for (const m of a.modules || []) {
      for (const s of m.shelves || []) {
        for (const p of s.products || []) {
          const hay = `${p.sku || ""} ${p.product_name || ""} ${p.brand || ""}`.toLowerCase();
          if (hay.includes(term)) return { aisle: a.aisle_id, module: m.module_id, shelf: s.shelf_no, product: p };
        }
      }
    }
  }
  return null;
}

function buildInsights(metrics, products, plan) {
  const utilization = Number(metrics.capacity_utilization_pct || metrics.capacity || 0);
  return [
    { tone: "danger", title: "Congestion", text: "A/B ana aksta yoğunluk penceresi simüle edildi. Picker route kırılımı izlenmeli." },
    { tone: "risk", title: "Refill labor cost", text: `${products.length} SKU içinde yüksek satışlı ürünlere facing/depth koruması uygulanmalı.` },
    { tone: "cold", title: "Cold chain", text: "+4 ve -18 fixture akışı ambient ile kesişmeyecek şekilde ayrıştırıldı." },
    { tone: "good", title: "Capacity", text: `Raf kullanım oranı ${pct(utilization)}. Canlı doluluk kontrollü.` },
    { tone: "violet", title: "Architecture", text: `${(plan.aisles || []).length} koridor, ${countShelves(plan)} raf tek modelde bağlı.` },
  ];
}

function LanguageSwitch({ lang, setLang }) {
  return (
    <div className="lang-switch" role="group">
      {Object.keys(STRINGS).map((l) => (
        <button key={l} className={lang === l ? "active" : ""} onClick={() => setLang(l)}>
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

function PlonagramMark({ small = false }) {
  return (
    <div className={`mark ${small ? "mark-small" : ""}`} aria-label="Plonagram">
      <span className="mark-stem" />
      <span className="mark-top" />
      <span className="mark-mid" />
      <span className="mark-cut" />
    </div>
  );
}

function BootLoader({ t }) {
  const steps = [t.loading1, t.loading2, t.loading3, t.loading4, t.loading5];
  return (
    <div className="boot-screen">
      <div className="boot-card">
        <div className="boot-mark-wrap"><PlonagramMark /></div>
        <div className="boot-title">PLONAGRAM OS</div>
        <div className="boot-sub">Warehouse Intelligence Core</div>
        <div className="boot-rail">{steps.map((s, i) => <span key={s} style={{ "--i": i }}>{s}</span>)}</div>
        <div className="boot-progress"><i /></div>
      </div>
    </div>
  );
}

function AuthScreen({ lang, setLang, onLogin }) {
  const t = STRINGS[lang];
  const [username, setUsername] = useState(localStorage.getItem("plonagram_user") || "erdi");
  const [password, setPassword] = useState("1234");
  const [store, setStore] = useState(localStorage.getItem("plonagram_store") || STORES[0]);
  return (
    <main className={`auth-world ${lang === "ar" ? "rtl" : ""}`}>
      <div className="auth-top"><PlonagramMark small /><b>PLONAGRAM OS</b><LanguageSwitch lang={lang} setLang={setLang} /></div>
      <section className="auth-hero">
        <div className="auth-copy">
          <span className="eyebrow">AI RETAIL DIGITAL TWIN</span>
          <h1>{t.headline}</h1>
          <p>{t.subline}</p>
          <div className="auth-chips"><span>3D Digital Twin</span><span>Refill AI</span><span>Global i18n</span><span>Store DNA</span></div>
        </div>
        <div className="auth-scene-card">
          <MiniWarehouseScene />
        </div>
        <form className="login-panel" onSubmit={(e) => { e.preventDefault(); localStorage.setItem("plonagram_auth", "1"); localStorage.setItem("plonagram_user", username); localStorage.setItem("plonagram_store", store); onLogin({ username, role: "ADMIN", store }); }}>
          <span className="eyebrow">SECURE ACCESS</span>
          <h2>{t.loginTitle}</h2>
          <p>{t.loginSub}</p>
          <label>{t.username}<input value={username} onChange={(e) => setUsername(e.target.value)} /></label>
          <label>{t.password}<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          <label>{t.store}<select value={store} onChange={(e) => setStore(e.target.value)}>{STORES.map((s) => <option key={s}>{s}</option>)}</select></label>
          <button className="primary big">{t.launch}</button>
        </form>
      </section>
    </main>
  );
}

function MiniWarehouseScene() {
  const aisles = Array.from({ length: 7 });
  return (
    <div className="mini-world">
      <div className="mini-floor">
        <div className="mini-route" />
        <div className="mini-cold c1">+4</div>
        <div className="mini-cold c2">-18</div>
        <div className="mini-dispatch">DISPATCH</div>
        {aisles.map((_, i) => <div key={i} className={`mini-aisle a${i}`}>{Array.from({ length: 8 }).map((_, j) => <i key={j} />)}</div>)}
        <span className="mini-picker" />
      </div>
    </div>
  );
}

function Sidebar({ view, setView, t }) {
  const items = [
    ["COMMAND", t.command, "⌘"],
    ["STUDIO", t.studio, "◈"],
    ["LAYOUT", t.layout, "▦"],
    ["RULES", t.rules, "✦"],
    ["REPORTS", t.reports, "◎"],
  ];
  return (
    <aside className="side">
      <div className="brand"><PlonagramMark small /><div><b>PLONAGRAM</b><span>Warehouse Intelligence</span></div></div>
      <nav>{items.map(([id, label, icon]) => <button key={id} className={view === id ? "active" : ""} onClick={() => setView(id)}><i>{icon}</i>{label}</button>)}</nav>
      <div className="core-card"><span>EA CORE</span><b>ONLINE</b><small>Digital twin, refill and rule intelligence</small></div>
    </aside>
  );
}

function TopCommand({ t, lang, setLang, storeCode, setStoreCode, onUploadProducts, onUploadLayout, onGenerate, user }) {
  const productRef = useRef(null);
  const layoutRef = useRef(null);
  return (
    <header className="top-command">
      <div><span className="eyebrow">PLONAGRAM OS · COMMAND CENTER</span><h2>{storeCode}</h2><small>{t.statusOnline}</small></div>
      <div className="top-actions">
        <select value={storeCode} onChange={(e) => { setStoreCode(e.target.value); localStorage.setItem("plonagram_store", e.target.value); }}>{STORES.map((s) => <option key={s}>{s}</option>)}</select>
        <LanguageSwitch lang={lang} setLang={setLang} />
        <input ref={productRef} type="file" accept=".csv" hidden onChange={onUploadProducts} />
        <input ref={layoutRef} type="file" accept=".json,.dxf" hidden onChange={onUploadLayout} />
        <button onClick={() => productRef.current?.click()}>{t.uploadSku}</button>
        <button onClick={() => layoutRef.current?.click()}>{t.uploadLayout}</button>
        <button className="primary" onClick={onGenerate}>{t.generate}</button>
        <div className="avatar">{String(user?.username || "ER").slice(0, 2).toUpperCase()}</div>
      </div>
    </header>
  );
}

function StatGrid({ metrics, products, plan }) {
  const stats = [
    ["Space Utilization", pct(metrics.capacity_utilization_pct || metrics.capacity || 0), "+12% vs last plan"],
    ["Planogram Score", Math.max(72, Math.round(92 - (metrics.unplaced_products || 0) * 2)), "AI quality index"],
    ["Active SKUs", products.length, "Loaded catalog"],
    ["Placed Products", productCount(plan), "In active fixtures"],
    ["Architecture", (plan.aisles || []).length, `${countShelves(plan)} shelves`],
    ["Alerts", 3, "Requires attention"],
  ];
  return <div className="stats-grid">{stats.map(([a, b, c]) => <div className="stat" key={a}><span>{a}</span><b>{b}</b><small>{c}</small></div>)}</div>;
}

function CommandCenter({ t, setView, metrics, products, plan, onGenerate }) {
  const insights = buildInsights(metrics, products, plan).slice(0, 4);
  return (
    <section className="command-page">
      <div className="hero-pro">
        <div className="hero-copy"><span className="eyebrow">NEW GENERATION PLANOGRAM INTELLIGENCE</span><h1>{t.headline}</h1><p>{t.subline}</p><div className="hero-actions"><button className="primary big" onClick={onGenerate}>{t.generate}</button><button className="ghost big" onClick={() => setView("STUDIO")}>{t.openStudio}</button></div></div>
        <div className="hero-visual"><MiniWarehouseScene /></div>
      </div>
      <StatGrid metrics={metrics} products={products} plan={plan} />
      <div className="command-grid">
        <div className="preview-card"><div className="section-head"><span className="eyebrow">LIVE DIGITAL TWIN</span><h2>Command preview</h2></div><StudioScene plan={plan} compact /></div>
        <aside className="insight-panel"><h3>{t.insights}</h3>{insights.map((x) => <div className={`insight ${x.tone}`} key={x.title}><b>{x.title}</b><span>{x.text}</span></div>)}</aside>
      </div>
    </section>
  );
}

function StudioScene({ plan, compact = false, camera = "orbit", focusLoc = null }) {
  const aisles = getAisles(plan);
  return (
    <div className={`studio-stage ${compact ? "compact" : ""} ${CAMERAS[camera]?.className || "cam-orbit"}`}>
      <div className="stage-haze" />
      <div className="floor-plane">
        <div className="heat heat-red" /><div className="heat heat-cyan" /><div className="heat heat-purple" />
        <svg className="route-svg" viewBox="0 0 1000 620" preserveAspectRatio="none"><path d="M90,520 C180,440 250,500 320,405 S520,420 590,300 S735,260 825,375 S870,460 940,410" /></svg>
        <div className="pallet p1" /><div className="pallet p2" /><div className="pallet-jack" />
        <ZoneBlock className="zone-chilled" label="+4 CHILLED" />
        <ZoneBlock className="zone-frozen" label="-18 FROZEN" />
        <ZoneBlock className="zone-algida" label="ALGIDA" />
        <div className="dispatch-zone">DISPATCH</div>
        <div className="tag congestion">CONGESTION</div><div className="tag refill">REFILL RISK</div>
        {aisles.map((a, i) => <Aisle3D key={`${a.aisle_id}-${i}`} aisle={a} index={i} focused={focusLoc?.aisle === a.aisle_id} />)}
      </div>
    </div>
  );
}

function ZoneBlock({ className, label }) {
  return <div className={`zone-block ${className}`}><b>{label}</b></div>;
}

function Aisle3D({ aisle, index, focused }) {
  const products = [];
  for (const m of aisle.modules || []) for (const s of m.shelves || []) products.push(...(s.products || []));
  const density = clamp(products.length, 2, 18);
  return (
    <div className={`aisle3d aisle-pos-${index % 10} ${focused ? "focused" : ""}`}>
      <span className="aisle-badge">{aisle.aisle_id}</span>
      <div className="rack-side left">{Array.from({ length: density }).map((_, i) => <i key={i} />)}</div>
      <div className="rack-side right">{Array.from({ length: density }).map((_, i) => <i key={i} />)}</div>
    </div>
  );
}

function LiveStudio({ t, plan, products, metrics }) {
  const [camera, setCamera] = useState("orbit");
  const [query, setQuery] = useState("");
  const [focusLoc, setFocusLoc] = useState(null);
  const insights = buildInsights(metrics, products, plan);
  function fly() { const found = findProductLocation(plan, query) || { aisle: query.toUpperCase() }; setFocusLoc(found); setCamera("focus"); }
  return (
    <section className="studio-page">
      <div className="studio-shell">
        <div className="studio-left"><PlonagramMark small /><button className="active">3D Studio</button><button>2D Plan</button><button>Heatmap</button><button>Operations</button><button>{t.products}</button><button>{t.reports}</button><div className="zone-status"><b>ZONE STATUS</b><span>Kuru <i>82%</i></span><span>Soğuk <i>74%</i></span><span>Donuk <i>68%</i></span></div></div>
        <main className="studio-main"><div className="studio-head"><div><span className="eyebrow">EA INTELLIGENCE CORE · ONLINE</span><h2>DEPO / MARKET-44</h2><p>3.250 m² · {(plan.aisles || []).length} corridor · {countShelves(plan)} shelf</p></div><div className="studio-pills"><span>AMBIENT +22°C</span><span className="cyan">CHILLED +4°C</span><span className="violet">FROZEN -18°C</span><button>{t.aiRecommends}</button></div></div><StudioScene plan={plan} camera={camera} focusLoc={focusLoc} /><div className="camera-dock"><b>{t.camera}</b>{Object.entries(CAMERAS).map(([id, c]) => <button key={id} className={camera === id ? "active" : ""} onClick={() => setCamera(id)}>{c.label}</button>)}</div><div className="console-row"><ConsoleStep label="Booting Digital Twin" /><ConsoleStep label="Loading Layout" /><ConsoleStep label="Analyzing Traffic" /><ConsoleStep label="Optimizing Routes" /><ConsoleStep label="EA Intelligence Core" /></div></main>
        <aside className="studio-right"><h3>{t.minimap}</h3><div className="minimap-grid">{getAisles(plan).map((a) => <button key={a.aisle_id} onClick={() => { setFocusLoc({ aisle: a.aisle_id }); setCamera("focus"); }}>{a.aisle_id}</button>)}</div><h3>{t.insights}</h3>{insights.map((x) => <div className={`insight ${x.tone}`} key={x.title}><b>{x.title}</b><span>{x.text}</span></div>)}<h3>{t.searchSku}</h3><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Eti Burçak / SKU / A" /><button className="primary full" onClick={fly}>{t.fly}</button>{focusLoc && <div className="found-card"><b>{focusLoc.product?.product_name || focusLoc.aisle}</b><span>Corridor: {focusLoc.aisle} {focusLoc.module ? `· Module ${focusLoc.module}` : ""}</span></div>}</aside>
      </div>
    </section>
  );
}

function ConsoleStep({ label }) { return <div className="console-step"><i /> <span>{label}</span><b>100%</b></div>; }

function Layout2D({ plan }) {
  return (
    <section className="panel-page"><div className="section-head"><span className="eyebrow">ARCHITECT MODE</span><h1>2D Layout Architect</h1></div><div className="layout-board">{getAisles(plan).map((a, i) => <div className="layout-aisle" key={a.aisle_id} style={{ left: `${8 + (i % 5) * 17}%`, top: `${12 + Math.floor(i / 5) * 26}%` }}><b>{a.aisle_id}</b><span>{(a.modules || []).length} modül</span></div>)}<div className="layout-wall w1">DUVAR</div><div className="layout-wall w2">DUVAR</div><div className="layout-dispatch">DISPATCH</div></div></section>
  );
}

function RulesPage({ t, rules, setRules, onGenerate }) {
  const [draft, setDraft] = useState({ type: "brand", value: "Ülker", zone: "AMBIENT", priority: "Sales" });
  function addRule() { setRules((r) => [...r, { ...draft, id: Date.now() }]); }
  return (
    <section className="panel-page"><div className="section-head"><span className="eyebrow">AI OPTIMIZATION CENTER</span><h1>{t.ruleTitle}</h1></div><div className="rule-pro-grid"><label>Kural tipi<select value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value })}><option value="brand">Marka</option><option value="category">Kategori</option><option value="subcategory">Alt kategori</option><option value="sku">SKU</option></select></label><label>Değer<input value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value })} /></label><label>Zone<select value={draft.zone} onChange={(e) => setDraft({ ...draft, zone: e.target.value })}><option>AMBIENT</option><option>CHILLED</option><option>FROZEN</option></select></label><label>Öncelik<select value={draft.priority} onChange={(e) => setDraft({ ...draft, priority: e.target.value })}><option>Sales</option><option>Picking</option><option>Refill</option></select></label><button className="primary" onClick={addRule}>Kural ekle</button><button onClick={onGenerate}>Uygula</button></div><div className="rules-list">{rules.length ? rules.map((r) => <div key={r.id} className="rule-card"><b>{r.type}: {r.value}</b><span>{r.zone} · {r.priority}</span><button onClick={() => setRules((all) => all.filter((x) => x.id !== r.id))}>Sil</button></div>) : <div className="empty-state">Henüz özel kural yok. AI varsayılan darkstore mantığıyla çalışır.</div>}</div></section>
  );
}

function ReportsPage({ t, metrics, plan, products }) {
  const rows = [
    ["Toplam raf", countShelves(plan)], ["Yerleşen SKU", productCount(plan)], ["Yüklenen SKU", products.length], ["Alan kullanımı", pct(metrics.capacity_utilization_pct || metrics.capacity || 0)], ["Raf hacim kullanımı", "118.21 m³"], ["+4 hacim", "74%"], ["-18 hacim", "68%"], ["Refill labor risk", "Medium"],
  ];
  return <section className="panel-page"><div className="section-head"><span className="eyebrow">EXECUTIVE REPORTING</span><h1>{t.reportTitle}</h1></div><div className="report-grid">{rows.map(([k, v]) => <div className="report-tile" key={k}><span>{k}</span><b>{v}</b></div>)}</div><div className="report-note"><b>AI summary</b><p>Kolon/duvar blokajı hacme değil erişilebilir zemine etki eder. Soğuk ve donuk fixture kapasitesi ayrı takip edilir. Refill labor cost anlık facing/depth mantığıyla okunur.</p></div></section>;
}

export default function App() {
  const [lang, setLang] = useState(localStorage.getItem("plonagram_lang") || "tr");
  const [user, setUser] = useState(() => localStorage.getItem("plonagram_auth") === "1" ? { username: localStorage.getItem("plonagram_user") || "erdi" } : null);
  const [storeCode, setStoreCode] = useState(localStorage.getItem("plonagram_store") || "ACIBADEM");
  const [view, setView] = useState("COMMAND");
  const [layout, setLayout] = useState(() => generateDefaultLayout(storeCode));
  const [plan, setPlan] = useState(() => generateDefaultLayout(storeCode));
  const [products, setProducts] = useState(() => DEFAULT_PRODUCTS.map(normalizeProduct));
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("Ready");
  const t = STRINGS[lang] || STRINGS.tr;
  const metrics = useMemo(() => computeMetrics(plan), [plan]);

  useEffect(() => { localStorage.setItem("plonagram_lang", lang); document.documentElement.dir = lang === "ar" ? "rtl" : "ltr"; }, [lang]);
  useEffect(() => { const tm = setTimeout(() => setLoading(false), 1450); return () => clearTimeout(tm); }, []);
  useEffect(() => { setLayout(generateDefaultLayout(storeCode)); setPlan(generateDefaultLayout(storeCode)); }, [storeCode]);

  async function handleUploadProducts(e) {
    const file = e.target.files?.[0]; if (!file) return;
    const text = await file.text();
    const parsed = parseCSV(text).map(normalizeProduct);
    setProducts(parsed.length ? parsed : DEFAULT_PRODUCTS.map(normalizeProduct));
    setToast(`${parsed.length} SKU loaded`);
  }
  async function handleUploadLayout(e) {
    const file = e.target.files?.[0]; if (!file) return;
    try { const text = await file.text(); const json = JSON.parse(text); const next = json.planogram || json.layout || json; setLayout(next); setPlan(next); setToast("Layout loaded"); } catch { setToast("Layout file read; DXF parser backend required for CAD."); }
  }
  function generate() {
    setLoading(true);
    setTimeout(() => {
      const result = localGeneratePlanogram(products, layout, "DARKSTORE_AI", { advancedRules: rules });
      setPlan(result.planogram || result.plan || layout);
      setToast("AI planogram generated");
      setLoading(false);
    }, 650);
  }
  function logout() { localStorage.removeItem("plonagram_auth"); setUser(null); }

  if (loading) return <BootLoader t={t} />;
  if (!user) return <AuthScreen lang={lang} setLang={setLang} onLogin={setUser} />;

  return (
    <div className={`plona-world ${lang === "ar" ? "rtl" : ""}`}>
      <Sidebar view={view} setView={setView} t={t} />
      <main className="app-shell">
        <TopCommand t={t} lang={lang} setLang={setLang} storeCode={storeCode} setStoreCode={setStoreCode} onUploadProducts={handleUploadProducts} onUploadLayout={handleUploadLayout} onGenerate={generate} user={user} />
        <div className="content-shell">
          {view === "COMMAND" && <CommandCenter t={t} setView={setView} metrics={metrics} products={products} plan={plan} onGenerate={generate} />}
          {view === "STUDIO" && <LiveStudio t={t} plan={plan} products={products} metrics={metrics} />}
          {view === "LAYOUT" && <Layout2D plan={plan} />}
          {view === "RULES" && <RulesPage t={t} rules={rules} setRules={setRules} onGenerate={generate} />}
          {view === "REPORTS" && <ReportsPage t={t} metrics={metrics} plan={plan} products={products} />}
        </div>
      </main>
      <button className="logout" onClick={logout}>⎋</button>
      <div className="toast">{toast}</div>
    </div>
  );
}
