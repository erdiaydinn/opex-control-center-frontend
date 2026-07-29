
import React, { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import { apiGet, apiPost } from "./services/api";
import PlonagramLoader from "./components/Motion/PlonagramLoader";
import LiveDigitalTwin from "./components/Live3D/LiveDigitalTwin";
import LayoutArchitect from "./components/LayoutArchitect/LayoutArchitect";

const nav = [
  ["command", "⌂", "Komuta Merkezi"],
  ["live3d", "◈", "3D Studio"],
  ["layout", "▦", "Mimari Düzenleyici"],
  ["planogram", "▥", "2D Planogram"],
  ["placement", "▤", "Ürün Yerleşimi"],
  ["photo", "◎", "Foto Planogram"],
  ["rules", "✦", "Kurallar"],
  ["council", "◇", "AI Council"],
  ["security", "◉", "Security"],
  ["reports", "◷", "Raporlar"],
];

const fallbackProducts = [
  { sku: "SKU-1001", product_name: "Eti Burçak", brand: "Eti", category: "Bisküvi", storage_type: "AMBIENT", sales_qty_7d: 126, facing_count: 4, depth_count: 2, image: "🍪" },
  { sku: "SKU-1002", product_name: "Ülker Çikolatalı Gofret", brand: "Ülker", category: "Çikolata", storage_type: "AMBIENT", sales_qty_7d: 218, facing_count: 5, depth_count: 3, image: "🍫" },
  { sku: "SKU-1003", product_name: "Pınar Süt", brand: "Pınar", category: "Süt", storage_type: "CHILLED", sales_qty_7d: 144, facing_count: 4, depth_count: 2, image: "🥛" },
  { sku: "SKU-1004", product_name: "Algida Magnum", brand: "Algida", category: "Dondurma", storage_type: "FROZEN", sales_qty_7d: 92, facing_count: 3, depth_count: 2, image: "🍦" },
  { sku: "SKU-1005", product_name: "La Lorraine Kruvasan", brand: "La Lorraine", category: "Donuk Bakery", storage_type: "FROZEN", sales_qty_7d: 74, facing_count: 2, depth_count: 2, image: "🥐" },
  { sku: "SKU-1006", product_name: "Domestos", brand: "Domestos", category: "Temizlik", storage_type: "AMBIENT", sales_qty_7d: 35, facing_count: 1, depth_count: 1, image: "🧴" },
];

const fallbackLayout = {
  store_code: "ANKA",
  store_name: "Anka (İstanbul)",
  aisles: "ABCDEFGHI".split("").map((id, idx) => ({
    aisle_id: id,
    x: -20 + (idx % 3) * 20,
    z: -12 + Math.floor(idx / 3) * 12,
    width: 12,
    depth: 3.6,
    rotation: 0,
    storage: idx === 7 ? "CHILLED" : idx === 8 ? "FROZEN" : "AMBIENT",
    modules: Array.from({ length: 6 }, (_, m) => ({ module_id: m + 1, shelves: Array.from({ length: 5 }, (_, s) => ({ shelf_no: s + 1, products: [] })) })),
  })),
  zones: [
    { id: "receiving", label: "Receiving", x: -31, z: 18, w: 10, d: 6, type: "receiving" },
    { id: "dispatch", label: "Dispatch", x: 31, z: 18, w: 12, d: 6, type: "dispatch" },
    { id: "chilled", label: "+4 Chilled", x: 24, z: -13, w: 11, d: 9, type: "chilled" },
    { id: "frozen", label: "-18 Frozen", x: 24, z: 2, w: 11, d: 9, type: "frozen" },
    { id: "algida", label: "Algida", x: -29, z: -2, w: 5, d: 7, type: "frozen" },
  ],
};

function assignProducts(products, layout) {
  const plan = structuredClone(layout || fallbackLayout);
  const shelves = [];
  plan.aisles.forEach((a) => a.modules.forEach((m) => m.shelves.forEach((s) => shelves.push({ a, m, s }))));
  products.forEach((p, i) => {
    const target = shelves.find(({ a, s }) => (a.storage === p.storage_type || a.storage === "AMBIENT") && (s.products?.length || 0) < 5) || shelves[i % shelves.length];
    if (target) target.s.products.push({ ...p, aisle_id: target.a.aisle_id, module_id: target.m.module_id, shelf_no: target.s.shelf_no });
  });
  return plan;
}

function metrics(products, plan) {
  const shelves = plan.aisles.reduce((n, a) => n + a.modules.reduce((m, x) => m + x.shelves.length, 0), 0);
  const placed = plan.aisles.reduce((sum, a) => sum + a.modules.reduce((m, mo) => m + mo.shelves.reduce((s, sh) => s + (sh.products?.length || 0), 0), 0), 0);
  const refillCost = products.reduce((sum, p) => sum + Math.max(1, (p.sales_qty_7d || 0) / 7 / Math.max(1, (p.facing_count || 1) * (p.depth_count || 1) * 8)) * 24 * 9, 0);
  return { score: 92, utilization: Math.min(94, Math.max(6, Math.round((placed / Math.max(1, shelves)) * 100))), activeSku: products.length, placed, shelves, refillCost, cold: 74, implementation: 78 };
}

function Shell({ active, setActive, children }) {
  const label = nav.find(([key]) => key === active)?.[2] || "Komuta";
  return <div className="appShell"><aside className="sidebar"><div className="brand"><svg viewBox="0 0 64 64"><path d="M16 49V15l16-9 16 9v15L32 39v19L16 49Z"/><path d="M32 6v33l16 10V30"/><path d="M16 15l16 10 16-10"/><path className="hot" d="M32 39l16-9 12 7v16l-12 7-16-10"/></svg><strong>PLONAGRAM</strong><small>WAREHOUSE INTELLIGENCE</small></div><nav>{nav.map(([key, icon, name]) => <button key={key} className={active === key ? "active" : ""} onClick={() => setActive(key)}><i>{icon}</i><span>{name}</span></button>)}</nav><div className="userCard"><b>EA</b><span>Erdi A.<small>ADMIN</small></span></div></aside><main><header className="topbar"><div><small>PLONAGRAM OS · COMMAND LAYER</small><strong>{label}</strong><span>Store DNA · SKU graph · AI Council</span></div><div className="topActions"><span className="status"><i/>Online</span><select defaultValue="Anka (İstanbul)"><option>Anka (İstanbul)</option><option>Acıbadem</option><option>Güven (Kocaeli) FR</option></select><button>SKU yükle</button><button>Layout yükle</button><button className="primary">✦ Optimum plan üret</button></div></header>{children}</main></div>;
}

function Metric({ label, value, sub, tone }) { return <div className="metric"><span>{label}</span><strong className={tone || ""}>{value}</strong><small>{sub}</small></div>; }

function CommandCenter({ products, plan, m, setActive }) {
  return <div className="page"><section className="hero"><div><small>WELCOME TO PLONAGRAM OS</small><h1>Warehouse intelligence,<br/>beautifully orchestrated<span>.</span></h1><p>Planogram, raf, fixture, soğuk zincir, refill riski ve picker rotasını tek komuta ekranında yönet.</p><div className="actions"><button className="primary">✦ Optimum plan üret</button><button onClick={() => setActive("live3d")}>◈ 3D Studio aç</button></div></div><div className="heroScene"><LiveDigitalTwin plan={plan} products={products} compact /></div></section><div className="metrics"><Metric label="Planogram Score" value={m.score} sub="/100"/><Metric label="Space Utilization" value={`${m.utilization}%`} sub="raf/hacim"/><Metric label="Active SKU" value={m.activeSku} sub="master products"/><Metric label="Refill Labor Cost" value={`${Math.round(m.refillCost).toLocaleString("tr-TR")} ₺`} sub="estimated monthly" tone="amber"/><Metric label="Cold Chain" value={`${m.cold}%`} sub="+4 utilization" tone="cyan"/><Metric label="Implementation" value={`${m.implementation}%`} sub="published plans" tone="green"/></div><div className="homeGrid"><div className="panel wide"><div className="panelHead"><small>LIVE DIGITAL TWIN</small><h2>Okunabilir 3D operasyon alanı</h2><button onClick={() => setActive("live3d")}>Open 3D Studio →</button></div><LiveDigitalTwin plan={plan} products={products} compact /></div><AICouncil products={products} plan={plan} /></div></div>;
}

function AICouncil({ products, plan }) {
  const high = products.filter((p) => Number(p.sales_qty_7d || 0) > 100).length;
  return <div className="panel aiPanel"><div className="panelHead"><small>AI COUNCIL</small><h2>Akıllı öneriler</h2></div>{[
    ["Sales Optimizer", `${high} hızlı SKU için facing/depth artırımı önerilir.`],
    ["Operations Lead", "Ağır ürünler son rota ve alt raf önceliğiyle dizilmeli."],
    ["Cold Chain Guardian", "+4 ve -18 zone ambient akıştan izole tutulmalı."],
    ["Space Architect", `${plan.aisles.length} koridorda kolon/duvar çakışması kontrol edilmeli.`],
    ["Skeptic Auditor", "Koridor D pik saatlerde congestion üretmeye devam edebilir."],
  ].map(([r, t]) => <div className="agent" key={r}><b>{r}</b><p>{t}</p></div>)}<button className="primary full">Council review çalıştır</button></div>;
}

function Planogram2D({ plan }) {
  return <div className="page"><section className="sectionTitle"><small>2D PLANOGRAM</small><h1>Raf raf operasyon planı<span>.</span></h1><p>Koridor, modül, raf ve ürün yerleşimini okunabilir biçimde yönet.</p></section><div className="planogramBoard">{plan.aisles.slice(0, 3).map((a) => <div className="corridor" key={a.aisle_id}><header><h2>Koridor {a.aisle_id}</h2><span>{a.modules.length} modül</span></header><div className="moduleGrid">{a.modules.slice(0, 4).map((m) => <div className="moduleCard" key={m.module_id}><h3>{a.aisle_id} - Modül {m.module_id}</h3>{m.shelves.map((s) => <div className="shelfLine" key={s.shelf_no}><b>Raf {s.shelf_no}</b><div>{(s.products || []).map((p) => <span key={p.sku}>{p.image}</span>)}{!(s.products || []).length && <em>Boş raf · ürün ekle</em>}</div></div>)}</div>)}</div></div>)}</div></div>;
}

function SecurityHealth() {
  const [scan, setScan] = useState(null);
  const [loading, setLoading] = useState(false);
  async function run() { setLoading(true); const r = await apiPost("/system/security-scan", {}); setScan(r || mockScan()); setLoading(false); }
  useEffect(() => { apiGet("/system/security-scan/latest").then((r) => setScan(r || mockScan())); }, []);
  const s = scan || mockScan();
  return <div className="page"><section className="sectionTitle"><small>OSV SCANNER</small><h1>Security Health<span>.</span></h1><p>Frontend/backend dependency açıklarını OSV scanner ile denetle.</p><button className="primary" onClick={run}>{loading ? "Taranıyor..." : "Security scan çalıştır"}</button></section><div className="metrics"><Metric label="Critical" value={s.summary.critical} sub="must fix"/><Metric label="High" value={s.summary.high} sub="priority" tone="amber"/><Metric label="Medium" value={s.summary.medium} sub="monitor"/><Metric label="Packages" value={s.vulnerabilities.length} sub="affected"/></div><div className="panel"><h2>Bulunan Riskler</h2><table><tbody>{s.vulnerabilities.map((v, i) => <tr key={i}><td>{v.package}</td><td>{v.installed_version}</td><td>{v.severity}</td><td>{v.fixed_version || "review"}</td></tr>)}</tbody></table></div></div>;
}
function mockScan(){ return { summary: { critical: 0, high: 1, medium: 2, low: 3 }, vulnerabilities: [{ package: "vite", installed_version: "5.x", severity: "MEDIUM", fixed_version: "latest" }, { package: "@react-three/fiber", installed_version: "8.x", severity: "LOW", fixed_version: "review" }, { package: "fastapi", installed_version: "current", severity: "HIGH", fixed_version: "pin latest" }] }; }

function PhotoCompliance() { return <div className="page"><section className="sectionTitle"><small>OPENCV PHOTO PLANOGRAM</small><h1>Fotoğraftan planogram kontrolü<span>.</span></h1><p>Fotoğraf yükle, raf çizgileri ve ürün blokları çıkarılsın; planogramla karşılaştırılsın.</p></section><div className="photoGrid"><div className="uploadBox"><input type="file" accept="image/*"/><p>Koridor / modül / raf seçip fotoğraf yükle.</p><button className="primary">OpenCV compliance çalıştır</button></div><div className="panel"><h2>Beklenen çıktı</h2><ul><li>Raf çizgisi algılama</li><li>Perspektif düzeltme</li><li>Ürün blok segmentasyonu</li><li>Facing mismatch raporu</li></ul></div></div></div>; }
function DataPage({ title, products }) { return <div className="page"><section className="sectionTitle"><small>PLONAGRAM OS</small><h1>{title}<span>.</span></h1><p>Fonksiyon alanı izole edildi; export veya başka route tetiklemez.</p></section><div className="panel"><table><tbody>{products.slice(0, 12).map((p) => <tr key={p.sku}><td>{p.image}</td><td>{p.product_name}</td><td>{p.brand}</td><td>{p.storage_type}</td><td>{p.sales_qty_7d}</td></tr>)}</tbody></table></div></div>; }

export default function App() {
  const [boot, setBoot] = useState(true);
  const [active, setActive] = useState("command");
  const [products, setProducts] = useState(fallbackProducts);
  const [layout, setLayout] = useState(fallbackLayout);

  useEffect(() => {
    apiGet("/master-products?limit=200").then((r) => {
      const arr = r?.products || r?.items || r;
      if (Array.isArray(arr) && arr.length) {
        setProducts(arr.slice(0, 200).map((p, i) => ({ sku: p.sku || p.product_sku || `SKU-${i}`, product_name: p.product_name || p.name || p.product_name_local || `Product ${i}`, brand: p.brand_name || p.brand || "Brand", category: p.frontend_category_local || p.category || "Category", storage_type: String(p.storage_type || "AMBIENT").toUpperCase(), sales_qty_7d: Number(p.sales_qty_7d || p.qty_7d || Math.round(20 + Math.random() * 180)), facing_count: Number(p.facing_count || 1 + Math.round(Math.random() * 4)), depth_count: Number(p.depth_count || 1 + Math.round(Math.random() * 2)), image: p.image || ["🍪", "🍫", "🥛", "🧴", "🍦"][i % 5] })));
      }
    });
  }, []);

  const plan = useMemo(() => assignProducts(products, layout), [products, layout]);
  const m = useMemo(() => metrics(products, plan), [products, plan]);

  if (boot) return <PlonagramLoader onDone={() => setBoot(false)} />;
  let view = <CommandCenter products={products} plan={plan} m={m} setActive={setActive} />;
  if (active === "live3d") view = <div className="page"><section className="sectionTitle"><small>3D STUDIO</small><h1>Digital Twin<span>.</span></h1><p>Mouse ile orbit/pan/zoom; kamera presetleri, SKU fly-to ve AI insight paneli.</p></section><LiveDigitalTwin plan={plan} products={products} /></div>;
  if (active === "layout") view = <LayoutArchitect plan={layout} setPlan={setLayout} />;
  if (active === "planogram") view = <Planogram2D plan={plan} />;
  if (active === "photo") view = <PhotoCompliance />;
  if (active === "council") view = <div className="page"><AICouncil products={products} plan={plan} /></div>;
  if (active === "security") view = <SecurityHealth />;
  if (["placement", "rules", "reports"].includes(active)) view = <DataPage title={nav.find(([k]) => k === active)?.[2]} products={products} />;
  return <Shell active={active} setActive={setActive}>{view}</Shell>;
}
