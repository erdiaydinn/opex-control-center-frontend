import React, { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";

const API_BASE = import.meta?.env?.VITE_PLONAGRAM_API || "http://127.0.0.1:8001";

const tr = {
  command: "Komuta Merkezi",
  live3d: "Canlı 3D",
  layout: "Mimari Düzenleyici",
  placement: "Ürün Yerleşimi",
  products: "Ürün Kütüphanesi",
  fixtures: "Fixture Kütüphanesi",
  planogram: "Planogram",
  delta: "Delta Planogram",
  publishing: "Yayınlama",
  tasks: "Görevler",
  reports: "Raporlar",
  admin: "Admin",
  systemOnline: "Çevrimiçi",
  uploadSku: "SKU yükle",
  uploadLayout: "Layout yükle",
  generate: "Optimum plan üret",
};

const en = {
  command: "Command Center",
  live3d: "Live 3D",
  layout: "Layout Architect",
  placement: "Product Placement",
  products: "Product Library",
  fixtures: "Fixture Library",
  planogram: "Planogram",
  delta: "Delta Planogram",
  publishing: "Publishing",
  tasks: "Tasks",
  reports: "Reports",
  admin: "Admin",
  systemOnline: "Online",
  uploadSku: "Upload SKUs",
  uploadLayout: "Upload Layout",
  generate: "Generate optimal plan",
};

const dict = { TR: tr, EN: en, DE: en, AR: en };

const nav = [
  ["command", "⌂"],
  ["live3d", "◈"],
  ["layout", "▦"],
  ["placement", "▤"],
  ["products", "□"],
  ["fixtures", "▱"],
  ["planogram", "▥"],
  ["delta", "⇄"],
  ["publishing", "↗"],
  ["tasks", "✓"],
  ["reports", "◷"],
  ["admin", "⚙"],
];

const palette = {
  ambient: "#F6F0DF",
  chilled: "#18C7DF",
  frozen: "#7B61FF",
  refill: "#F5B900",
  risk: "#E84A4A",
  pink: "#DF1067",
  success: "#17A66A",
};

const fallbackProducts = [
  { sku: "SKU-1001", barcode: "8690001", product_name: "Eti Burçak", brand: "Eti", category_l1: "Atıştırmalık", category_l2: "Bisküvi", storage_type: "AMBIENT", width_cm: 8, height_cm: 16, depth_cm: 4, sales_qty_7d: 126, facing_count: 4, shelf_capacity: 48, image: "🍪" },
  { sku: "SKU-1002", barcode: "8690002", product_name: "Ülker Çikolatalı Gofret", brand: "Ülker", category_l1: "Atıştırmalık", category_l2: "Çikolata", storage_type: "AMBIENT", width_cm: 7, height_cm: 15, depth_cm: 3, sales_qty_7d: 218, facing_count: 5, shelf_capacity: 70, image: "🍫" },
  { sku: "SKU-1003", barcode: "8690003", product_name: "Pınar Süt", brand: "Pınar", category_l1: "Süt Ürünleri", category_l2: "Süt", storage_type: "CHILLED", width_cm: 8, height_cm: 24, depth_cm: 8, sales_qty_7d: 144, facing_count: 4, shelf_capacity: 36, image: "🥛" },
  { sku: "SKU-1004", barcode: "8690004", product_name: "Algida Magnum", brand: "Algida", category_l1: "Donuk", category_l2: "Dondurma", storage_type: "FROZEN", width_cm: 10, height_cm: 15, depth_cm: 5, sales_qty_7d: 92, facing_count: 3, shelf_capacity: 30, image: "🍦" },
  { sku: "SKU-1005", barcode: "8690005", product_name: "La Lorraine Kruvasan", brand: "La Lorraine", category_l1: "Fırın", category_l2: "Donuk Bakery", storage_type: "FROZEN", width_cm: 15, height_cm: 10, depth_cm: 12, sales_qty_7d: 74, facing_count: 2, shelf_capacity: 24, image: "🥐" },
  { sku: "SKU-1006", barcode: "8690006", product_name: "Domestos", brand: "Domestos", category_l1: "Temizlik", category_l2: "Ağır Koku", storage_type: "AMBIENT", width_cm: 10, height_cm: 26, depth_cm: 8, sales_qty_7d: 35, facing_count: 1, shelf_capacity: 18, image: "🧴" },
];

const fallbackLayout = {
  store_code: "ANKA",
  store_name: "Anka (İstanbul)",
  aisles: ["A", "B", "C", "D", "E", "F", "G", "H", "I"].map((id, idx) => ({
    aisle_id: id,
    x: 10 + (idx % 3) * 24,
    y: 12 + Math.floor(idx / 3) * 20,
    w: 18,
    h: 6,
    rotation: 0,
    storage: idx === 1 ? "CHILLED" : idx === 2 ? "FROZEN" : "AMBIENT",
    modules: Array.from({ length: 6 }, (_, m) => ({
      module_id: m + 1,
      shelves: Array.from({ length: 5 }, (_, s) => ({
        shelf_no: s + 1,
        shelf_width_cm: 100,
        shelf_depth_cm: 50,
        allowed_storage_type: idx === 1 ? "CHILLED" : idx === 2 ? "FROZEN" : "AMBIENT",
        products: [],
      })),
    })),
  })),
  objects: [
    { id: "cold-room", type: "chilled", label: "SOĞUK ODA", x: 78, y: 10, w: 16, h: 16 },
    { id: "frozen-room", type: "frozen", label: "DONUK ODA", x: 78, y: 68, w: 16, h: 16 },
    { id: "dispatch", type: "dispatch", label: "DISPATCH", x: 45, y: 84, w: 26, h: 9 },
    { id: "receiving", type: "receiving", label: "MAL KABUL", x: 9, y: 82, w: 18, h: 10 },
    { id: "algida", type: "algida", label: "ALGIDA", x: 6, y: 62, w: 13, h: 8 },
    { id: "wall-1", type: "wall", label: "DUVAR", x: 5, y: 5, w: 90, h: 2 },
    ...Array.from({ length: 18 }, (_, i) => ({ id: `col-${i}`, type: "column", label: "KOLON", x: 18 + (i % 6) * 12, y: 25 + Math.floor(i / 6) * 18, w: 1.2, h: 1.2 })),
  ],
};

function cx(...names) { return names.filter(Boolean).join(" "); }
function n(v, d = 0) { const x = Number(v); return Number.isFinite(x) ? x : d; }
function formatMoney(v) { return `${Math.round(v).toLocaleString("tr-TR")} ₺`; }

function buildPlacedPlan(products, layout) {
  const plan = structuredClone(layout || fallbackLayout);
  const allShelves = [];
  plan.aisles.forEach((a) => a.modules.forEach((m) => m.shelves.forEach((s) => allShelves.push({ a, m, s }))));
  (products || fallbackProducts).forEach((p, idx) => {
    const target = allShelves.find(({ s }) => s.allowed_storage_type === p.storage_type && s.products.length < 4) || allShelves[idx % allShelves.length];
    if (target) {
      target.s.products.push({ ...p, aisle_id: target.a.aisle_id, module_id: target.m.module_id, shelf_no: target.s.shelf_no });
    }
  });
  return plan;
}

function getMetrics(products, plan) {
  const shelves = [];
  (plan?.aisles || []).forEach((a) => a.modules?.forEach((m) => m.shelves?.forEach((s) => shelves.push(s))));
  const placed = shelves.reduce((sum, s) => sum + (s.products?.length || 0), 0);
  const totalShelf = shelves.length || 1;
  const capacityUnits = shelves.reduce((sum, s) => sum + n(s.shelf_width_cm, 100) * n(s.shelf_depth_cm, 50) / 100, 0);
  const usedUnits = (products || []).reduce((sum, p) => sum + n(p.width_cm, 8) * n(p.depth_cm, 5) * n(p.facing_count, 1) / 10, 0);
  const refillCost = (products || []).reduce((sum, p) => {
    const daily = n(p.sales_qty_7d, 0) / 7;
    const cap = Math.max(1, n(p.shelf_capacity, 24));
    return sum + Math.max(0.2, daily / cap) * 8 * 22;
  }, 0);
  return {
    score: 92,
    utilization: Math.min(94, Math.round((usedUnits / Math.max(capacityUnits, 1)) * 100)),
    activeSku: products.length,
    placed,
    shelves: totalShelf,
    refillCost,
    coldUsage: 74,
    frozenUsage: 68,
    fixtureAvailability: 91,
    openTasks: 12,
    implementation: 78,
  };
}

async function api(path, opts = {}) {
  try {
    const res = await fetch(`${API_BASE}${path}`, { headers: { "Content-Type": "application/json", ...(opts.headers || {}) }, ...opts });
    if (!res.ok) throw new Error(`${res.status}`);
    return await res.json();
  } catch (err) {
    return null;
  }
}

function Logo({ compact = false }) {
  return <div className={cx("brand", compact && "brandCompact")}>
    <div className="mark"><span>P</span></div>
    {!compact && <div><strong>PLONAGRAM</strong><em>OS</em></div>}
  </div>;
}

function PremiumLoading({ onDone }) {
  const steps = ["Reading Store DNA", "Mapping Fixtures", "Building SKU Graph", "Calculating Refill Risk", "EA Intelligence Core Online"];
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setIdx((x) => Math.min(x + 1, steps.length - 1)), 460);
    const done = setTimeout(() => onDone?.(), 2600);
    return () => { clearInterval(t); clearTimeout(done); };
  }, []);
  return <div className="loadingScreen">
    <div className="loadingAura" />
    <div className="lineLogo" aria-label="Plonagram loading logo">
      <svg viewBox="0 0 160 160"><path d="M46 125V34l34-19 34 19v37L80 91v54l-34-20Z"/><path d="M80 15v76l34 20 0-40"/><path d="M46 34l34 19 34-19"/><path className="accentLine" d="M80 91l34-20 26 15v38l-26 15-34-20"/></svg>
    </div>
    <h1>PLONAGRAM OS</h1>
    <p>Warehouse Intelligence Core</p>
    <div className="loadSteps">{steps.map((s, i) => <span key={s} className={cx(i <= idx && "done", i === idx && "active")}>{s}</span>)}</div>
  </div>;
}

function Shell({ active, setActive, lang, setLang, store, setStore, children }) {
  const t = dict[lang] || tr;
  return <div className="appShell">
    <aside className="sidebar">
      <Logo />
      <nav>{nav.map(([key, icon]) => <button key={key} onClick={() => setActive(key)} className={cx(active === key && "active")}><i>{icon}</i><span>{t[key]}</span></button>)}</nav>
      <div className="userCard"><div className="avatar">EA</div><div><b>Erdi A.</b><span>Admin</span></div></div>
      <button className="signOut">Oturumu kapat</button>
    </aside>
    <main className="workspace">
      <header className="topbar">
        <div className="topTitle"><small>PLONAGRAM OS · COMMAND LAYER</small><strong>{t[active] || t.command}</strong><span>Backend bağlantısı hazır. Aktif depo: {store}</span></div>
        <div className="topActions">
          <div className="statusPill"><span /> Sistem Durumu <b>{t.systemOnline}</b></div>
          <select value={store} onChange={(e) => setStore(e.target.value)}><option>Anka (İstanbul)</option><option>Acıbadem</option><option>Güven (Kocaeli) FR</option><option>Şükrüpaşa (Edirne)</option></select>
          <select value={lang} onChange={(e) => setLang(e.target.value)}><option>TR</option><option>EN</option><option>DE</option><option>AR</option></select>
          <button className="ghostBtn">{t.uploadSku}</button><button className="ghostBtn">{t.uploadLayout}</button><button className="primaryBtn">✦ {t.generate}</button>
        </div>
      </header>
      {children}
    </main>
  </div>;
}

function Hero3D({ compact = false, camera = "overview", selectedSku, setCamera, onOpen3D }) {
  const cameraClass = camera === "top" ? "camTop" : camera === "chilled" ? "camChilled" : camera === "frozen" ? "camFrozen" : camera === "dispatch" ? "camDispatch" : "";
  return <div className={cx("hero3d", compact && "compact", cameraClass)}>
    <div className="warehouseFog" />
    <div className="gridFloor">
      <div className="routeLine"><span /><span /><span /><span /></div>
      {Array.from({ length: 9 }, (_, i) => <div key={i} className={cx("rack3d", `r${i + 1}`, i === 1 && "chilled", i === 2 && "frozen", i === 4 && "risk")}>{Array.from({ length: 26 }, (_, j) => <b key={j} />)}</div>)}
      <div className="zoneCube chilledZone"><b>+4 CHILLED</b><span>Zone B-12</span></div>
      <div className="zoneCube frozenZone"><b>-18 FROZEN</b><span>Isolated</span></div>
      <div className="dispatchBox">DISPATCH</div>
      <div className="forklift" />
      <Callout cls="c1" title="CONGESTION" text="Aisle 07" tone="risk" />
      <Callout cls="c2" title="REFILL RISK" text="23 SKUs" tone="refill" />
      <Callout cls="c3" title="COLD CHAIN" text="Stable" tone="success" />
      {selectedSku && <Callout cls="cSku" title={selectedSku.product_name} text={`${selectedSku.aisle_id || "E"}-${selectedSku.module_id || 4}-${selectedSku.shelf_no || 3}`} tone="pink" />}
    </div>
    <div className="cameraDock">
      {[["overview","Overview"],["top","Top"],["chilled","Chilled"],["frozen","Frozen"],["dispatch","Dispatch"]].map(([k,l]) => <button key={k} className={cx(camera===k && "on")} onClick={() => setCamera?.(k)}>{l}</button>)}
      <button onClick={onOpen3D}>Open 3D</button>
    </div>
  </div>;
}

function Callout({ cls, title, text, tone }) { return <div className={cx("callout", cls, tone)}><b>{title}</b><span>{text}</span></div>; }

function MetricCard({ label, value, sub, icon, tone }) {
  return <div className={cx("metricCard", tone)}><div><span>{label}</span><strong>{value}</strong><small>{sub}</small></div><i>{icon}</i></div>;
}

function CommandCenter({ metrics, setActive, products, plan }) {
  return <section className="page commandPage">
    <div className="heroPanel split">
      <div><small>WELCOME TO PLONAGRAM OS</small><h1>Warehouse intelligence,<br/>beautifully orchestrated<span>.</span></h1><p>Planogram, raf, fixture, soğuk zincir, refill riski ve picker rotasını tek komuta ekranında yönet.</p><div className="heroActions"><button className="primaryBtn">✦ Optimum plan üret</button><button className="ghostBtn" onClick={() => setActive("live3d")}>◈ 3D Studio aç</button></div></div>
      <Hero3D compact onOpen3D={() => setActive("live3d")} />
    </div>
    <div className="metricGrid six">
      <MetricCard label="Planogram Score" value={metrics.score} sub="↑ 8 vs last 7 days" icon="✦" tone="pink" />
      <MetricCard label="Space Utilization" value={`${metrics.utilization}%`} sub="healthy" icon="◷" />
      <MetricCard label="Active SKU" value={metrics.activeSku.toLocaleString("tr-TR")} sub="master products" icon="□" />
      <MetricCard label="Refill Labor Cost" value={formatMoney(metrics.refillCost)} sub="estimated monthly" icon="↺" tone="amber" />
      <MetricCard label="Cold Chain" value={`${metrics.coldUsage}%`} sub="+4 utilization" icon="❄" tone="cyan" />
      <MetricCard label="Implementation" value={`${metrics.implementation}%`} sub="published plans" icon="✓" tone="green" />
    </div>
    <div className="twoCol">
      <div className="glassCard"><div className="cardHead"><div><small>LIVE DIGITAL TWIN</small><h2>Okunabilir 3D operasyon alanı</h2></div><button onClick={() => setActive("live3d")}>Open 3D Studio →</button></div><Hero3D compact onOpen3D={() => setActive("live3d")} /></div>
      <AIInsights />
    </div>
    <RecentOps products={products} plan={plan} />
  </section>;
}

function AIInsights() {
  const rows = [
    ["Space Optimization Opportunity", "Zone C could increase efficiency by 14% with a 2-shelf shift.", "High Impact"],
    ["Refill Recommendation", "23 SKUs need refill review within the next 48 hours.", "Action Needed"],
    ["Overstock Alert", "18 SKUs in Zone B showing high overstock risk.", "High Impact"],
    ["Planogram Performance", "Beverage category score improved by 12%.", "Positive"],
  ];
  return <div className="glassCard insightCard"><div className="cardHead"><div><small>AI INSIGHTS</small><h2>Akıllı öneriler</h2></div><button>Tümünü gör</button></div>{rows.map((r,i)=><div className="insightRow" key={r[0]}><i>{i===0?"◎":i===1?"△":i===2?"⚠":"✓"}</i><div><b>{r[0]}</b><span>{r[1]}</span></div><em>{r[2]}</em></div>)}</div>;
}

function RecentOps({ products }) {
  return <div className="glassCard"><div className="cardHead"><div><small>RECENT OPERATIONS</small><h2>Son aksiyonlar</h2></div><select><option>Last 7 days</option></select></div><div className="table clean"><div className="tr th"><span>SKU</span><span>Ürün</span><span>Aksiyon</span><span>Risk</span><span>Durum</span></div>{products.slice(0,5).map((p,i)=><div className="tr" key={p.sku}><span>{p.sku}</span><span>{p.product_name}</span><span>{i%2?"Facing artırıldı":"Raf konumu değişti"}</span><span>{p.sales_qty_7d>120?"High":"Medium"}</span><span><b className="ok">Completed</b></span></div>)}</div></div>;
}

function Live3D({ products, metrics }) {
  const [camera, setCamera] = useState("overview");
  const [query, setQuery] = useState("Eti");
  const [selected, setSelected] = useState(products[0]);
  const find = () => {
    const q = query.toLowerCase();
    const p = products.find(x => `${x.sku} ${x.product_name} ${x.brand}`.toLowerCase().includes(q));
    if (p) { setSelected(p); setCamera(p.storage_type === "CHILLED" ? "chilled" : p.storage_type === "FROZEN" ? "frozen" : "overview"); }
  };
  return <section className="page livePage">
    <div className="sectionHero"><div><small>CANLI 3D</small><h1>Canlı Dijital İkiz</h1><p>Depo operasyonlarının gerçek zamanlı, okunabilir ve müdahale edilebilir 3D görünümü.</p><div className="microLegend"><span>✓ Gerçek zamanlı güncelleme</span><span>✦ AI destekli içgörüler</span><span>⚠ Kritik alan izleme</span><span>↗ Akıllı yönlendirme</span></div></div><div className="seg"><button className="on">3D View</button><button>2D Plan</button><button>Heatmap</button></div></div>
    <div className="liveGrid">
      <div className="liveStage"><Hero3D camera={camera} selectedSku={selected} setCamera={setCamera} /><div className="metricGrid six slim"><MetricCard label="Planogram Skoru" value={metrics.score} sub="/100"/><MetricCard label="Doluluk" value={`${metrics.utilization}%`} sub="raf/hacim"/><MetricCard label="SKU" value={metrics.activeSku} sub="aktif"/><MetricCard label="Refill Riski" value="Orta" sub="23 SKU"/><MetricCard label="Picker Rotası" value="1.35 dk" sub="ortalama"/><MetricCard label="Cold Chain" value="Sağlıklı" sub="normal"/></div></div>
      <aside className="rightPanel"><MiniMap/><div className="panelBox"><h3>SKU Ara</h3><div className="searchBox"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="SKU veya ürün adı..."/><button onClick={find}>Bul</button></div>{selected && <div className="selectedSku"><i>{selected.image}</i><b>{selected.product_name}</b><span>{selected.sku} · {selected.brand}</span><button onClick={find}>Fly to Location</button></div>}</div><AIList/><CameraPresets camera={camera} setCamera={setCamera}/></aside>
    </div>
  </section>;
}

function MiniMap(){ return <div className="panelBox"><h3>Mini Map</h3><div className="miniMap">{["A","B","C","D","E","F","G","H","I"].map((x,i)=><span key={x} className={i===4?"hot":""}>{x}</span>)}<b>DISPATCH</b></div></div> }
function AIList(){ return <div className="panelBox"><h3>AI Insights</h3>{["Congestion detected","Refill risk","Temperature transition","Efficiency opportunity"].map((x,i)=><div className={cx("tinyInsight", i===0&&"red", i===1&&"amber", i===2&&"cyan", i===3&&"green")} key={x}><b>{x}</b><span>{i===0?"Corridor D · high traffic":"Action suggested"}</span></div>)}</div> }
function CameraPresets({camera,setCamera}){ return <div className="panelBox"><h3>Camera Presets</h3><div className="presetGrid">{["overview","top","chilled","frozen","dispatch"].map(x=><button key={x} className={camera===x?"on":""} onClick={()=>setCamera(x)}>{x}</button>)}</div></div> }

function LayoutArchitect({ plan, setPlan }) {
  const [selected, setSelected] = useState(plan.aisles[0]);
  const [mode, setMode] = useState("snap");
  const objects = [...plan.aisles.map(a => ({...a, kind:"aisle"})), ...(plan.objects || []).map(o=>({...o, kind:"object"}))];
  const updateSelected = (patch) => {
    if (!selected) return;
    const id = selected.aisle_id || selected.id;
    const next = structuredClone(plan);
    const a = next.aisles.find(x => x.aisle_id === id);
    if (a) Object.assign(a, patch); else { const o = next.objects.find(x => x.id === id); if (o) Object.assign(o, patch); }
    setPlan(next);
    setSelected({ ...selected, ...patch });
  };
  const addObject = (type) => {
    const next = structuredClone(plan);
    if (type === "aisle") next.aisles.push({ aisle_id: String.fromCharCode(65 + next.aisles.length), x: 18, y: 18, w: 18, h: 6, rotation: 0, storage: "AMBIENT", modules: fallbackLayout.aisles[0].modules });
    else next.objects.push({ id: `${type}-${Date.now()}`, type, label: type.toUpperCase(), x: 35, y: 35, w: 12, h: 8 });
    setPlan(next);
  };
  const optimize = () => {
    const next = structuredClone(plan);
    next.aisles.forEach((a,i)=>{ a.x = 14 + (i%3)*24; a.y = 18 + Math.floor(i/3)*18; });
    setPlan(next);
  };
  return <section className="page architectPage">
    <div className="architectTop"><div><small>ARCHITECT MODE</small><h1>Mimari Düzenleyici</h1><p>Koridor, modül, kolon, soğuk oda, donuk oda, dispatch, duvar ve fixture alanlarını düzenle.</p></div><div className="archActions"><button className="primaryBtn" onClick={optimize}>✦ AI en optimal yerleşimi öner</button><button className={mode==="snap"?"on":""} onClick={()=>setMode("snap")}>Snap</button><button className={mode==="free"?"on":""} onClick={()=>setMode("free")}>Free</button><button>Layout kaydet</button></div></div>
    <div className="architectGrid"><aside className="catalogPanel"><h3>Obje Kataloğu</h3>{[["aisle","Koridor"],["wall","Duvar Paneli"],["column","Yuvarlak Kolon"],["chilled","Soğuk Oda"],["frozen","Donuk Oda"],["algida","Algida Dolabı"],["dispatch","Dispatch"],["receiving","Mal Kabul"],["exit","Acil Çıkış"],["office","Müdür Masası"]].map(([k,l])=><button key={k} onClick={()=>addObject(k)}><span className={`objIcon ${k}`}/>{l}</button>)}</aside>
      <div className="blueprint"><div className="meters x">{Array.from({length:13},(_,i)=><span key={i}>{i*10}</span>)}</div><div className="meters y">{Array.from({length:10},(_,i)=><span key={i}>{i*10}</span>)}</div>{objects.map(o=><button key={o.aisle_id||o.id} className={cx("bpObj", o.type, o.storage?.toLowerCase(), selected && (selected.aisle_id||selected.id)===(o.aisle_id||o.id)&&"selected")} style={{left:`${o.x}%`, top:`${o.y}%`, width:`${o.w}%`, height:`${o.h}%`, transform:`rotate(${o.rotation||0}deg)`}} onClick={()=>setSelected(o)}><b>{o.aisle_id||o.label}</b><span>{o.w}m × {o.h}m</span></button>)}</div>
      <aside className="propsPanel"><h3>Özellikler</h3>{selected ? <><div className="selectedTitle"><span className="objPreview"/><div><b>{selected.aisle_id ? `Koridor ${selected.aisle_id}` : selected.label}</b><small>{selected.type || selected.storage || "Raf Modülü"}</small></div></div><FormNum label="X" value={selected.x} onChange={v=>updateSelected({x:v})}/><FormNum label="Y" value={selected.y} onChange={v=>updateSelected({y:v})}/><FormNum label="Genişlik" value={selected.w} onChange={v=>updateSelected({w:v})}/><FormNum label="Derinlik" value={selected.h} onChange={v=>updateSelected({h:v})}/><FormNum label="Rotation" value={selected.rotation||0} onChange={v=>updateSelected({rotation:v})}/><div className="aiNote"><b>AI Notu</b><p>Bu alan dispatch rotasına yakın. Refill riski yüksek ürünleri bu koridora yaklaştır.</p><button>Öneriyi uygula</button></div></> : <p>Nesne seç.</p>}</aside>
    </div>
  </section>;
}
function FormNum({label,value,onChange}){ return <label className="formNum"><span>{label}</span><input type="number" value={value} onChange={e=>onChange(n(e.target.value))}/></label>; }

function ProductPlacement({ products, setProducts, plan }) {
  const [selected, setSelected] = useState(products[0]);
  const incFacing = (delta) => { setProducts(ps => ps.map(p => p.sku === selected.sku ? { ...p, facing_count: Math.max(1, n(p.facing_count,1)+delta) } : p)); setSelected(s => ({...s, facing_count: Math.max(1,n(s.facing_count,1)+delta)})); };
  const daily = n(selected.sales_qty_7d,0)/7;
  const refill = daily / Math.max(1,n(selected.shelf_capacity,24));
  return <section className="page placementPage"><div className="sectionHero"><div><small>PRODUCT PLACEMENT STUDIO</small><h1>Raf üstü ürün yerleşimi</h1><p>Ürünü sadece liste olarak değil; facing, depth, kapasite, refill maliyeti ve saha aksiyonu olarak yönet.</p></div><div className="seg"><button className="on">Visual Shelf</button><button>Technical Grid</button><button>AI Suggest</button></div></div>
    <div className="placementGrid"><div className="visualShelf"><div className="shelfHeader"><b>Koridor E · Modül 04 · Raf 03</b><span>Doluluk {Math.min(96, Math.round(products.reduce((a,p)=>a+n(p.width_cm,8)*n(p.facing_count,1),0)/4))}%</span></div>{[1,2,3,4,5].map(row=><div className="shelfLine" key={row}>{products.slice(0,6).map(p=><button key={`${row}-${p.sku}`} className={cx(selected.sku===p.sku&&"selected", p.storage_type.toLowerCase())} style={{width:`${50+n(p.facing_count,1)*16}px`}} onClick={()=>setSelected(p)}><i>{p.image}</i><span>{p.brand}</span><em>F{p.facing_count}</em></button>)}</div>)}<div className="placementToolbar"><button onClick={()=>incFacing(1)}>Facing +</button><button onClick={()=>incFacing(-1)}>Facing -</button><button>Depth +</button><button>AI facing öner</button><button>ABC sırala</button><button>Yazdır</button></div></div>
      <div className="technicalGrid"><h3>Teknik grid</h3>{products.map(p=><button key={p.sku} className={cx(selected.sku===p.sku&&"selected")} onClick={()=>setSelected(p)}><b>{p.sku}</b><span>{p.product_name}</span><em>{p.storage_type} · F{p.facing_count}</em></button>)}</div>
      <aside className="productPanel"><h3>Seçili ürün</h3><div className="productBig"><i>{selected.image}</i><b>{selected.product_name}</b><span>{selected.sku} · {selected.brand}</span></div><Info label="Kategori" value={`${selected.category_l1} / ${selected.category_l2}`}/><Info label="Storage" value={selected.storage_type}/><Info label="Ölçü" value={`${selected.width_cm}×${selected.depth_cm}×${selected.height_cm} cm`}/><Info label="7G satış" value={selected.sales_qty_7d}/><Info label="Facing" value={selected.facing_count}/><Info label="Tahmini kapasite" value={selected.shelf_capacity}/><Info label="Refill / gün" value={refill.toFixed(2)}/><Info label="Refill labor cost" value={formatMoney(refill*8*22)}/><button className="primaryBtn">Bu ürüne AI aksiyon üret</button></aside>
    </div>
  </section>;
}
function Info({label,value}){ return <div className="infoLine"><span>{label}</span><b>{value}</b></div>; }

function ProductLibrary({ products }) {
  const [q,setQ]=useState(""); const rows=products.filter(p=>`${p.sku} ${p.product_name} ${p.brand} ${p.category_l1}`.toLowerCase().includes(q.toLowerCase()));
  return <DataPage title="Ürün Kütüphanesi" kicker="PRODUCT LIBRARY" desc="SKU, barkod, marka, kategori, ölçü, satış ve refill riskini tek tabloda yönet." toolbar={<input className="wideSearch" value={q} onChange={e=>setQ(e.target.value)} placeholder="SKU, barkod, ürün adı, marka ara..."/>}><div className="table library"><div className="tr th"><span>SKU</span><span>Ürün</span><span>Marka</span><span>Kategori</span><span>Storage</span><span>Ölçü</span><span>7G Satış</span><span>Risk</span></div>{rows.map(p=><div className="tr" key={p.sku}><span>{p.sku}</span><span><i>{p.image}</i>{p.product_name}</span><span>{p.brand}</span><span>{p.category_l2}</span><span><b className={`tag ${p.storage_type.toLowerCase()}`}>{p.storage_type}</b></span><span>{p.width_cm}×{p.depth_cm}×{p.height_cm}</span><span>{p.sales_qty_7d}</span><span>{p.sales_qty_7d>120?"High":"Medium"}</span></div>)}</div></DataPage>;
}

function FixtureLibrary() {
  const fixtures=[
    ["F-001","Yeni Nesil Çelik Raf","100×60×250",6,"Ambient",91], ["F-002","Algida Dolabı","200×80×210",4,"Frozen",72], ["F-003","Yatay Dolap","180×90×120",3,"Chilled",65], ["F-004","Soğuk Oda","20 m²",0,"+4",74], ["F-005","Donuk Oda","14 m²",0,"-18",68],
  ];
  return <DataPage title="Fixture Kütüphanesi" kicker="FIXTURE LIBRARY" desc="Raf, dolap, soğuk oda ve donuk oda kapasitesini store DNA ile birlikte yönet."><div className="fixtureGrid">{fixtures.map(f=><div className="fixtureCard" key={f[0]}><div className="fixtureIcon"/><small>{f[0]}</small><h3>{f[1]}</h3><p>{f[2]} · {f[3] ? `${f[3]} raf` : "oda/alan"}</p><b>{f[4]}</b><div className="bar"><span style={{width:`${f[5]}%`}}/></div><em>{f[5]}% availability</em></div>)}</div></DataPage>;
}

function PlanogramWorkspace({ plan }) {
  return <section className="page planogramPage"><div className="sectionHero"><div><small>PLANOGRAM WORKSPACE</small><h1>Raf raf operasyon planı</h1><p>Koridor, modül, raf ve ürün yerleşimini okunabilir saha aksiyonlarına dönüştür.</p></div><div className="seg"><button>3D View</button><button className="on">2D Plan</button><button>Heatmap</button></div></div><div className="planogramBoard">{plan.aisles.map(a=><div className="aisleBlock" key={a.aisle_id}><div className="aisleHead"><b>Koridor {a.aisle_id}</b><span>{a.modules.length} modül</span><em>{a.storage}</em></div><div className="moduleGrid">{a.modules.slice(0,6).map(m=><div className="moduleCard" key={m.module_id}><h3>{a.aisle_id} · Modül {m.module_id}</h3>{m.shelves.map(s=><div className="smallShelf" key={s.shelf_no}><b>Raf {s.shelf_no}</b><div>{(s.products||[]).map(p=><span key={p.sku} title={p.product_name}>{p.image}</span>)}{!(s.products||[]).length&&<em>Boş raf · ürün ekle</em>}</div></div>)}</div>)}</div></div>)}</div></section>;
}

function Analytics({ metrics }) {
  return <DataPage title="Operasyon analitiği" kicker="ANALYTICS" desc="Alan, hacim, doluluk, fixture, cold chain ve refill maliyeti metrikleri."><div className="analyticsGrid"><MetricCard label="Toplam Raf" value={metrics.shelves} sub="aktif raf"/><MetricCard label="Yerleşen SKU" value={metrics.placed} sub="planogram"/><MetricCard label="Raf Genişlik Kullanımı" value={`${metrics.utilization}%`} sub="ölçü bazlı"/><MetricCard label="Refill Labor Cost" value={formatMoney(metrics.refillCost)} sub="aylık tahmin"/><MetricCard label="+4 Hacim Kullanımı" value={`${metrics.coldUsage}%`} sub="chilled"/><MetricCard label="-18 Hacim Kullanımı" value={`${metrics.frozenUsage}%`} sub="frozen"/></div><div className="glassCard"><h2>Yorum</h2><p>Doluluk artık ham raf adediyle değil; ürün ölçüsü, raf ölçüsü, facing ve depth mantığıyla yorumlanır. Soğuk oda ve donuk oda için hacimden önce m² ve fixture availability ayrı izlenir.</p></div></DataPage>;
}

function Rules() {
  const rules=["Ağır ürün en sona yakın yerleşir","FROZEN sadece -18 alanına atanır","CHILLED +4 zone veya soğuk oda yakınında kalır","Aynı marka blok halinde tutulur","Hızlı SKU dispatch rotasına yakın konumlanır","Temizlik / ağır koku gıda koridorundan ayrılır"];
  return <DataPage title="Kural Motoru" kicker="RULE ENGINE" desc="Kategori, marka, storage, picking, refill ve fixture kurallarını merkezi olarak yönet."><div className="ruleGrid">{rules.map((r,i)=><div className="ruleCard" key={r}><b>Rule {String(i+1).padStart(2,"0")}</b><p>{r}</p><select><option>Aktif</option><option>Pasif</option></select></div>)}</div></DataPage>;
}
function Reports({ metrics }) { return <DataPage title="Executive View" kicker="REPORTS" desc="Yönetici için karar odaklı özet; risk, kapasite, refill cost ve implementation status."><div className="reportHero"><h2>Bu hafta öne çıkan karar</h2><p>Refill riski yüksek 23 SKU için facing/depth artışı ve dispatch rotasına yakınlaştırma öneriliyor. Frozen kapasite %68, chilled kapasite %74 seviyesinde; kritik eşik altında ama yeni ürün girişi öncesi fixture kontrolü şart.</p></div><div className="metricGrid four"><MetricCard label="High Risk Store" value="4" sub="aksiyon bekliyor"/><MetricCard label="Open Tasks" value={metrics.openTasks} sub="saha"/><MetricCard label="Delta Workload" value="27" sub="ürün hareketi"/><MetricCard label="Compliance" value={`${metrics.implementation}%`} sub="uygulama"/></div></DataPage>; }
function Delta({ products }) { return <DataPage title="Delta Planogram" kicker="DELTA" desc="Eski plan ile yeni plan arasındaki farkları saha aksiyonuna dönüştür."><div className="table clean"><div className="tr th"><span>Aksiyon</span><span>SKU</span><span>Ürün</span><span>Eski</span><span>Yeni</span></div>{products.slice(0,5).map((p,i)=><div className="tr" key={p.sku}><span>{i%2?"Facing değiştir":"Ürünü taşı"}</span><span>{p.sku}</span><span>{p.product_name}</span><span>A-{i+1}-2</span><span>E-{i+2}-3</span></div>)}</div></DataPage>; }
function Publishing(){ return <DataPage title="Yayınlama & Uygulama Takibi" kicker="PUBLISHING" desc="Merkez planı yayınlar; depo gördüm, başladım, uyguladım ve fotoğraf yükledim akışıyla ilerler."><Kanban/></DataPage>; }
function Tasks(){ return <DataPage title="Görevler" kicker="TASK MANAGEMENT" desc="Planogramdan doğan aksiyonları sorumlu, deadline ve durum ile takip et."><Kanban tasks/></DataPage>; }
function Admin(){ return <DataPage title="Admin" kicker="ADMIN" desc="Kullanıcı, rol, depo erişimi, store DNA ve onay akışlarını yönet."><div className="adminGrid"><div className="glassCard"><h2>Roller</h2>{["ADMIN","SUPER_USER","STORE_MANAGER","USER"].map(r=><div className="infoLine" key={r}><span>{r}</span><b>Aktif</b></div>)}</div><div className="glassCard"><h2>Onay Bekleyenler</h2><p>Ürün ölçüsü değişikliği, fixture ekleme ve store DNA revizyonları burada onaylanır.</p><button className="primaryBtn">Onay kuyruğunu aç</button></div></div></DataPage>; }
function Kanban(){ const cols=["Bekliyor","Uygulanıyor","Fotoğraf Bekliyor","Tamamlandı"]; return <div className="kanban">{cols.map((c,i)=><div className="kanbanCol" key={c}><h3>{c}</h3>{[1,2,3].map(n=><div className="taskCard" key={n}><b>{i===0?"Refill riski yüksek SKU":i===1?"Fixture ölçüsü eksik":i===2?"Fotoğraf bekleniyor":"Plan uygulandı"}</b><span>Anka · Koridor {String.fromCharCode(65+n)}</span><em>{i===3?"Low":"High"}</em></div>)}</div>)}</div> }

function DataPage({ kicker, title, desc, toolbar, children }) { return <section className="page dataPage"><div className="sectionHero"><div><small>{kicker}</small><h1>{title}</h1><p>{desc}</p></div>{toolbar}</div>{children}</section>; }

export default function App() {
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState("command");
  const [lang, setLang] = useState("TR");
  const [store, setStore] = useState("Anka (İstanbul)");
  const [products, setProducts] = useState(fallbackProducts);
  const [plan, setPlan] = useState(buildPlacedPlan(fallbackProducts, fallbackLayout));
  const fileRef = useRef(null);
  const layoutRef = useRef(null);
  useEffect(() => {
    api("/master-products?limit=200").then((data) => {
      const rows = data?.products;
      if (Array.isArray(rows) && rows.length) {
        const normalized = rows.slice(0, 120).map((p, i) => ({ ...fallbackProducts[i % fallbackProducts.length], ...p, image: fallbackProducts[i % fallbackProducts.length].image, facing_count: n(p.facing_count, 1), sales_qty_7d: n(p.sales_qty_7d || p.sales_7d, Math.round(20 + Math.random()*120)), shelf_capacity: n(p.shelf_capacity, 36) }));
        setProducts(normalized);
        setPlan(buildPlacedPlan(normalized.slice(0, 60), fallbackLayout));
      }
    });
  }, []);
  const metrics = useMemo(() => getMetrics(products, plan), [products, plan]);
  if (loading) return <PremiumLoading onDone={() => setLoading(false)} />;
  const screen = {
    command: <CommandCenter metrics={metrics} setActive={setActive} products={products} plan={plan} />,
    live3d: <Live3D products={products} metrics={metrics} />,
    layout: <LayoutArchitect plan={plan} setPlan={setPlan} />,
    placement: <ProductPlacement products={products} setProducts={setProducts} plan={plan} />,
    products: <ProductLibrary products={products} />,
    fixtures: <FixtureLibrary />,
    planogram: <PlanogramWorkspace plan={plan} />,
    analytics: <Analytics metrics={metrics} />,
    rules: <Rules />,
    reports: <Reports metrics={metrics} />,
    delta: <Delta products={products} />,
    publishing: <Publishing />,
    tasks: <Tasks />,
    admin: <Admin />,
  }[active] || <CommandCenter metrics={metrics} setActive={setActive} products={products} plan={plan} />;
  return <>
    <input ref={fileRef} type="file" accept=".csv" hidden />
    <input ref={layoutRef} type="file" accept=".json,.dxf" hidden />
    <Shell active={active} setActive={setActive} lang={lang} setLang={setLang} store={store} setStore={setStore}>{screen}</Shell>
  </>;
}
