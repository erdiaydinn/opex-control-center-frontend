import React, { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, Html, Line, Text } from '@react-three/drei';
import * as THREE from 'three';
import { api } from './services/api';
import './App.css';

const BRAND = '#DF1067';
const DARK = '#10131A';
const CYAN = '#18C7DF';
const PURPLE = '#7B61FF';
const AMBER = '#F5B900';
const RED = '#E84A4A';
const GREEN = '#17A66A';

const DICT = {
  TR: {
    command: 'Komuta Merkezi', live3d: 'Canlı 3D', architect: 'Mimari Düzenleyici', placement: 'Ürün Yerleşimi', products: 'Ürün Kütüphanesi', fixtures: 'Fixture Kütüphanesi', planogram: 'Planogram', delta: 'Delta Planogram', tasks: 'Görevler', reports: 'Raporlar', admin: 'Admin',
    headline: 'Warehouse intelligence, beautifully orchestrated.', sub: 'Planogram, raf, fixture, soğuk zincir, refill riski ve picker rotasını tek komuta ekranında yönet.', generate: 'Optimum plan üret', open3d: '3D Studio aç', uploadSku: 'SKU yükle', uploadLayout: 'Layout yükle', saveLayout: 'Layout kaydet', export: 'Export', system: 'Sistem Durumu', online: 'Çevrimiçi', activeDepot: 'Aktif Depo',
    digitalTwin: 'Canlı Dijital İkiz', digitalTwinSub: 'Depo operasyonlarının gerçek zamanlı, okunabilir ve müdahale edilebilir 3D görünümü.', searchSku: 'SKU ara', fly: 'Rafa git', insights: 'AI İçgörüler', camera: 'Kamera Ön Ayarları', minimap: 'Mini Map',
    architectTitle: 'Mimari düzenleyici.', architectSub: 'Koridor, kolon, duvar, soğuk oda, donuk oda, dispatch ve fixture alanlarını blueprint üzerinde düzenle.', addCorridor: 'Koridor ekle', addColumn: 'Kolon ekle', addCold: 'Soğuk oda ekle', addFrozen: 'Donuk oda ekle', aiLayout: 'AI en optimal yerleşimi öner', snap: 'Snap', free: 'Free', properties: 'Özellikler', objectCatalog: 'Obje Kataloğu',
    planogram2d: 'Raf raf operasyon planı', analytics: 'Operasyon analitiği', rules: 'Kural motoru', reportTitle: 'Executive rapor', apply: 'Uygula', print: 'Yazdır',
  },
  EN: { command: 'Command Center', live3d: 'Live 3D', architect: 'Layout Architect', placement: 'Product Placement', products: 'Product Library', fixtures: 'Fixture Library', planogram: 'Planogram', delta: 'Delta Planogram', tasks: 'Tasks', reports: 'Reports', admin: 'Admin', headline: 'Warehouse intelligence, beautifully orchestrated.', sub: 'Manage planogram, shelves, fixtures, cold chain, refill risk and picker routes from one command layer.', generate: 'Generate optimal plan', open3d: 'Open 3D Studio', uploadSku: 'Upload SKUs', uploadLayout: 'Upload Layout', saveLayout: 'Save Layout', export: 'Export', system: 'System Status', online: 'Online', activeDepot: 'Active Depot', digitalTwin: 'Live Digital Twin', digitalTwinSub: 'Readable, controllable 3D view of live warehouse operations.', searchSku: 'Search SKU', fly: 'Fly to location', insights: 'AI Insights', camera: 'Camera Presets', minimap: 'Mini Map', architectTitle: 'Layout architect.', architectSub: 'Edit aisles, columns, walls, cold rooms, frozen rooms, dispatch and fixtures on a blueprint.', addCorridor: 'Add Corridor', addColumn: 'Add Column', addCold: 'Add Chilled Room', addFrozen: 'Add Frozen Room', aiLayout: 'Suggest best layout', snap: 'Snap', free: 'Free', properties: 'Properties', objectCatalog: 'Object Catalog', planogram2d: 'Shelf-by-shelf operations plan', analytics: 'Operational analytics', rules: 'Rule engine', reportTitle: 'Executive report', apply: 'Apply', print: 'Print' },
  DE: { command: 'Kommando', live3d: 'Live 3D', architect: 'Layout Architekt', placement: 'Produktplatzierung', products: 'Produktbibliothek', fixtures: 'Fixture Bibliothek', planogram: 'Planogramm', delta: 'Delta', tasks: 'Aufgaben', reports: 'Berichte', admin: 'Admin', headline: 'Warehouse intelligence, beautifully orchestrated.', sub: 'Planogramm, Regale, Fixtures, Kühlkette, Refill-Risiko und Picker-Routen zentral steuern.', generate: 'Optimalplan erzeugen', open3d: '3D Studio öffnen', uploadSku: 'SKU laden', uploadLayout: 'Layout laden', saveLayout: 'Layout speichern', export: 'Export', system: 'Systemstatus', online: 'Online', activeDepot: 'Aktives Depot', digitalTwin: 'Live Digital Twin', digitalTwinSub: 'Lesbare und steuerbare 3D-Ansicht der Lageroperationen.', searchSku: 'SKU suchen', fly: 'Zum Regal', insights: 'AI Insights', camera: 'Kamera Presets', minimap: 'Mini Map', architectTitle: 'Layout Architekt.', architectSub: 'Gänge, Säulen, Wände, Kühlräume, Tiefkühlräume und Dispatch bearbeiten.', addCorridor: 'Gang hinzufügen', addColumn: 'Säule hinzufügen', addCold: 'Kühlraum', addFrozen: 'Tiefkühlraum', aiLayout: 'Bestes Layout vorschlagen', snap: 'Snap', free: 'Free', properties: 'Eigenschaften', objectCatalog: 'Objektkatalog', planogram2d: 'Regalplan', analytics: 'Operationsanalyse', rules: 'Regelwerk', reportTitle: 'Executive Bericht', apply: 'Anwenden', print: 'Drucken' },
  AR: { command: 'مركز القيادة', live3d: 'ثلاثي الأبعاد', architect: 'محرر المخطط', placement: 'توزيع المنتجات', products: 'مكتبة المنتجات', fixtures: 'مكتبة التجهيزات', planogram: 'بلانوغرام', delta: 'الفروقات', tasks: 'المهام', reports: 'التقارير', admin: 'الإدارة', headline: 'Warehouse intelligence, beautifully orchestrated.', sub: 'إدارة المخطط والرفوف وسلسلة التبريد ومخاطر التعبئة والمسارات من مركز واحد.', generate: 'إنشاء الخطة المثلى', open3d: 'فتح 3D Studio', uploadSku: 'رفع SKU', uploadLayout: 'رفع Layout', saveLayout: 'حفظ Layout', export: 'تصدير', system: 'حالة النظام', online: 'متصل', activeDepot: 'المستودع', digitalTwin: 'التوأم الرقمي', digitalTwinSub: 'عرض ثلاثي الأبعاد واضح وقابل للتحكم.', searchSku: 'بحث SKU', fly: 'اذهب للرف', insights: 'رؤى AI', camera: 'الكاميرا', minimap: 'الخريطة', architectTitle: 'محرر المخطط.', architectSub: 'تعديل الممرات والأعمدة والجدران ومناطق التبريد.', addCorridor: 'أضف ممر', addColumn: 'أضف عمود', addCold: 'غرفة تبريد', addFrozen: 'غرفة تجميد', aiLayout: 'اقتراح أفضل مخطط', snap: 'Snap', free: 'Free', properties: 'الخصائص', objectCatalog: 'كتالوج', planogram2d: 'خطة الرفوف', analytics: 'تحليل العمليات', rules: 'محرك القواعد', reportTitle: 'تقرير تنفيذي', apply: 'تطبيق', print: 'طباعة' },
};

const nav = [
  ['command', '⌂'], ['live3d', '◇'], ['architect', '▦'], ['placement', '▤'], ['products', '□'], ['fixtures', '▱'], ['planogram', '▥'], ['delta', '↔'], ['tasks', '✓'], ['reports', '◷'], ['admin', '⚙'],
];

function t(lang, key) { return DICT[lang]?.[key] || DICT.TR[key] || key; }
function clamp(n, min, max) { return Math.max(min, Math.min(max, n)); }
function uid(prefix) { return `${prefix}-${Math.random().toString(16).slice(2, 9)}`; }

function makeShelves(count = 5, storage = 'AMBIENT') {
  return Array.from({ length: count }, (_, i) => ({ shelf_no: i + 1, shelf_width_cm: 100, shelf_depth_cm: storage === 'FROZEN' ? 60 : storage === 'CHILLED' ? 55 : 50, shelf_height_cm: 35, allowed_storage_type: storage, products: [] }));
}
function makeModule(id, side = 'L', storage = 'AMBIENT') {
  return { module_id: id, side, module_type: storage === 'FROZEN' ? 'freezer' : storage === 'CHILLED' ? 'fridge' : 'regular_shelf', module_width_cm: 100, module_depth_cm: storage === 'AMBIENT' ? 50 : 60, module_height_cm: 210, shelves: makeShelves(storage === 'FROZEN' ? 4 : 5, storage) };
}
function createDefaultLayout() {
  const ids = ['A','B','C','D','E','F','G','H','I'];
  return {
    store_code: 'Anka (İstanbul)',
    layout_objects: [
      { id: 'receiving', type: 'receiving', label: 'Receiving', x: 7, y: 8, w: 8, h: 5, rotation: 0 },
      { id: 'dispatch', type: 'dispatch', label: 'Dispatch', x: 112, y: 54, w: 13, h: 8, rotation: 0 },
      { id: 'cold-room', type: 'cold_room', label: '+4 Chilled', x: 95, y: 7, w: 20, h: 13, rotation: 0 },
      { id: 'frozen-room', type: 'frozen_room', label: '-18 Frozen', x: 95, y: 67, w: 20, h: 13, rotation: 0 },
      { id: 'algida', type: 'algida_cabinet', label: 'Algida', x: 18, y: 73, w: 8, h: 5, rotation: 0 },
      ...Array.from({ length: 18 }, (_, i) => ({ id: `col-${i}`, type: 'column', label: '', x: 32 + (i % 6) * 12, y: 12 + Math.floor(i / 6) * 22, w: .7, h: .7, rotation: 0 })),
    ],
    aisles: ids.map((id, i) => ({
      aisle_id: id,
      row: Math.floor(i / 3) + 1,
      position: i % 3 + 1,
      direction: i % 2 ? 'RTL' : 'LTR',
      layout_position: { grid_x: 28 + (i % 3) * 23, grid_y: 23 + Math.floor(i / 3) * 22, rotation: 0 },
      modules: Array.from({ length: 6 }, (_, m) => makeModule(m + 1, m < 3 ? 'L' : 'R', 'AMBIENT')),
    })),
  };
}
function sampleProducts() {
  const base = [
    ['1001','Eti Burçak','Eti','Bisküvi','AMBIENT',120], ['1002','Ülker Çikolatalı Gofret','Ülker','Çikolata','AMBIENT',210], ['1003','Coca Cola 1L','Coca Cola','İçecek','AMBIENT',180], ['1004','Pınar Süt 1L','Pınar','Süt','CHILLED',90], ['1005','Algida Magnum','Algida','Dondurma','FROZEN',80], ['1006','La Lorraine Kruvasan','La Lorraine','Fırın','FROZEN',60], ['1007','Domestos','Domestos','Temizlik','AMBIENT',35], ['1008','Meyve Suyu','Dimes','İçecek','AMBIENT',74], ['1009','Yoğurt','Sütaş','Süt Ürünleri','CHILLED',62], ['1010','Dondurulmuş Pizza','Superfresh','Donuk','FROZEN',49]
  ];
  return base.map((x, i) => ({ sku: x[0], product_name: x[1], brand: x[2], category_l2: x[3], storage_type: x[4], sales_qty_7d: x[5], width_cm: 8 + (i % 3) * 2, height_cm: 15, depth_cm: 8, facing_count: i < 3 ? 3 : 1 }));
}
function seedPlan(layout, products) {
  const next = structuredClone(layout);
  const ambient = products.filter(p => p.storage_type === 'AMBIENT');
  const chilled = products.filter(p => p.storage_type === 'CHILLED');
  const frozen = products.filter(p => p.storage_type === 'FROZEN');
  function put(list, aisleIndex = 0, moduleIndex = 0) {
    list.forEach((p, idx) => {
      const a = next.aisles[(aisleIndex + idx) % next.aisles.length];
      const m = a.modules[(moduleIndex + idx) % a.modules.length];
      const s = m.shelves[idx % m.shelves.length];
      s.products.push({ ...p, aisle_id: a.aisle_id, module_id: m.module_id, shelf_no: s.shelf_no, facing_count: p.facing_count || 1 });
    });
  }
  put(ambient, 0, 0); put(chilled, 2, 2); put(frozen, 5, 3);
  return next;
}

function PlonagramMark({ compact = false }) {
  return <div className={`plona-mark ${compact ? 'compact' : ''}`}><div className="p-line a"/><div className="p-line b"/><div className="p-line c"/><div className="p-dot"/></div>;
}
function LoadingSplash() {
  const steps = ['Reading Store DNA','Mapping Fixtures','Building SKU Graph','Calculating Refill Risk','EA Intelligence Core Online'];
  return <div className="loading-screen">
    <div className="loading-bg" />
    <div className="loading-core"><PlonagramMark/><div className="loading-word">PLONAGRAM</div><div className="loading-sub">WAREHOUSE INTELLIGENCE</div><div className="loading-ring" />
      <div className="loading-steps">{steps.map((s,i)=><span key={s} style={{animationDelay:`${i*.2}s`}}>{s}</span>)}</div>
    </div>
  </div>;
}

function Shell({ children, lang, setLang, view, setView, store, setStore, onUploadCsv, onUploadLayout, onGenerate, status }) {
  return <div className="app-shell">
    <aside className="side">
      <div className="brand"><PlonagramMark compact/><div><b>PLONAGRAM</b><span>OS</span></div></div>
      <nav>{nav.map(([key, icon]) => <button key={key} className={view === key ? 'active' : ''} onClick={() => setView(key)}><i>{icon}</i><span>{t(lang, key)}</span></button>)}</nav>
      <div className="user-card"><div className="avatar">EA</div><div><b>Erdi A.</b><span>ADMIN</span></div></div>
      <button className="logout">Oturumu kapat</button>
    </aside>
    <main className="main">
      <header className="topbar"><div><div className="overline">PLONAGRAM OS · COMMAND LAYER</div><h1>{t(lang, view)}</h1><p>Backend bağlantısı hazır. Aktif depo: {store}</p></div><div className="top-actions">
        <div className="pill online"><span/> {t(lang,'system')} <b>{t(lang,'online')}</b></div>
        <select value={store} onChange={e=>setStore(e.target.value)}><option>Anka (İstanbul)</option><option>Güven (Kocaeli) FR</option><option>Acıbadem</option></select>
        <select value={lang} onChange={e=>setLang(e.target.value)}>{['TR','EN','DE','AR'].map(l=><option key={l}>{l}</option>)}</select>
        <label className="btn light">{t(lang,'uploadSku')}<input type="file" accept=".csv,.xlsx" hidden onChange={e=>onUploadCsv(e.target.files?.[0])}/></label>
        <label className="btn light">{t(lang,'uploadLayout')}<input type="file" accept=".json,.dxf" hidden onChange={e=>onUploadLayout(e.target.files?.[0])}/></label>
        <button className="btn primary" onClick={onGenerate}>✦ {t(lang,'generate')}</button>
      </div></header>
      {status && <div className="toast">{status}</div>}
      {children}
    </main>
  </div>;
}

function Metric({ label, value, sub, tone }) { return <div className="metric"><span>{label}</span><b className={tone || ''}>{value}</b><small>{sub}</small></div>; }

function CommandCenter({ lang, setView, planogram, products }) {
  const metrics = useMetrics(planogram, products);
  return <div className="page command-page">
    <section className="hero-panel"><div className="hero-copy"><div className="overline">WELCOME TO PLONAGRAM OS</div><h2>{t(lang,'headline')}</h2><p>{t(lang,'sub')}</p><div className="hero-buttons"><button className="btn primary">✦ {t(lang,'generate')}</button><button className="btn light" onClick={()=>setView('live3d')}>◇ {t(lang,'open3d')}</button></div></div><div className="hero-visual"><MiniWarehousePreview planogram={planogram}/><div className="hero-tabs"><b>Overview</b><span>Top</span><span>Chilled</span><span>Frozen</span><span>Dispatch</span></div></div></section>
    <div className="metric-grid"><Metric label="Planogram Score" value="92" sub="↑ 8 vs last 7 days"/><Metric label="Space Utilization" value={`${metrics.fillPct}%`} sub="healthy"/><Metric label="Active SKU" value={products.length} sub="master products"/><Metric label="Refill Labor Cost" value="4.224 ₺" sub="estimated monthly" tone="amber"/><Metric label="Cold Chain" value={`${metrics.chilledPct}%`} sub="+4 utilization" tone="cyan"/><Metric label="Implementation" value="78%" sub="published plans" tone="green"/></div>
    <div className="two-col"><section className="glass-card"><div className="section-title"><div><div className="overline">LIVE DIGITAL TWIN</div><h3>Okunabilir 3D operasyon alanı</h3></div><button className="btn light" onClick={()=>setView('live3d')}>Open 3D Studio →</button></div><MiniWarehousePreview planogram={planogram} large/></section><AIInsights lang={lang}/></div>
  </div>;
}
function MiniWarehousePreview({ planogram, large=false }) {
  const aisles = planogram.aisles || [];
  return <div className={`mini-warehouse ${large?'large':''}`}>{aisles.slice(0,9).map((a,i)=><div key={a.aisle_id} className="mini-aisle" style={{left:`${10+(i%3)*28}%`,top:`${18+Math.floor(i/3)*24}%`}}><span>{a.aisle_id}</span>{Array.from({length:10}).map((_,j)=><i key={j}/>)}</div>)}<svg viewBox="0 0 100 100"><path d="M8,80 C25,55 42,75 48,45 S78,42 92,20"/></svg><b className="mini-callout refill">Refill Risk</b><b className="mini-callout dispatch">Dispatch</b></div>;
}
function AIInsights({ lang }) { const rows = [['Space Optimization Opportunity','Zone C could increase efficiency by 14% with a 2-shelf shift.','High Impact'],['Refill Recommendation','23 SKUs need refill review within the next 48 hours.','Action Needed'],['Overstock Alert','18 SKUs in Zone B showing high overstock risk.','High Impact'],['Planogram Performance','Beverage category score improved by 12%.','Positive']]; return <section className="glass-card ai-card"><div className="section-title"><div><div className="overline">AI INSIGHTS</div><h3>{t(lang,'insights')}</h3></div><button className="btn ghost">Tümünü gör</button></div>{rows.map((r,i)=><div className="insight-row" key={r[0]}><i>{i===3?'✓':'△'}</i><div><b>{r[0]}</b><span>{r[1]}</span></div><em>{r[2]}</em></div>)}</section>; }
function useMetrics(planogram, products) { return useMemo(()=>{ let shelves=0, used=0, total=0, chilled=0, coldTotal=0; (planogram.aisles||[]).forEach(a=>a.modules?.forEach(m=>m.shelves?.forEach(s=>{ shelves++; total += Number(s.shelf_width_cm||100); used += s.products?.reduce((sum,p)=>sum+(p.width_cm||8)*(p.facing_count||1)*1.1,0)||0; if(s.allowed_storage_type==='CHILLED'){ coldTotal += 100; chilled += s.products?.length ? 74 : 0; }}))); return { shelves, fillPct: clamp(Math.round(used/Math.max(total,1)*100),0,100), chilledPct: coldTotal ? Math.round(chilled/coldTotal*100) : 74 }; },[planogram, products]); }

function WarehouseScene({ planogram, preset, focusSku }) {
  return <>
    <ambientLight intensity={1.45}/><directionalLight position={[8, 12, 8]} intensity={1.1}/><pointLight position={[0,8,0]} intensity={1.2} color="#ff4f9f"/>
    <CameraRig preset={preset} focusSku={focusSku}/>
    <GridFloor/>
    <WarehouseGlass/>
    {(planogram.aisles||[]).map((a,i)=><Aisle3D key={a.aisle_id} aisle={a} idx={i} focusSku={focusSku}/>) }
    {(planogram.layout_objects||[]).map(o=><Object3D key={o.id} obj={o}/>) }
    <RouteLine/>
    <ZoneLabel pos={[-8,2.6,-5]} label="+4 CHILLED" color={CYAN}/><ZoneLabel pos={[9,2.6,-4]} label="-18 FROZEN" color={PURPLE}/><ZoneLabel pos={[1,2.6,1]} label="REFILL RISK" color={AMBER}/><ZoneLabel pos={[5,2.6,4]} label="CONGESTION" color={RED}/>
    <OrbitControls makeDefault enableDamping dampingFactor={0.08} minDistance={8} maxDistance={42}/>
  </>;
}
function CameraRig({ preset, focusSku }) { const { camera, controls } = useThree(); useEffect(()=>{ const map={overview:[10,12,18],top:[0,26,.01],chilled:[-8,8,-7],frozen:[12,8,-5],dispatch:[15,8,12],sku:[3,6,6]}; const p=map[preset]||map.overview; camera.position.set(...p); camera.lookAt(0,0,0); controls?.target?.set(0,0,0); controls?.update?.(); },[preset, focusSku]); return null; }
function GridFloor() { return <group><mesh rotation={[-Math.PI/2,0,0]} position={[0,-.02,0]}><planeGeometry args={[34,24]}/><meshStandardMaterial color="#eef2f4" roughness={.82}/></mesh><gridHelper args={[34,34,'#d7dde3','#edf0f3']} position={[0,0,0]}/></group>; }
function WarehouseGlass(){ return <group><mesh position={[0,3,-11]}><boxGeometry args={[34,.08,5.5]}/><meshStandardMaterial color="#eaf6fb" transparent opacity={.18}/></mesh><mesh position={[-17,3,0]}><boxGeometry args={[.08,.08,24]}/><meshStandardMaterial color="#d9e8f0" transparent opacity={.14}/></mesh></group>; }
function Aisle3D({ aisle, idx, focusSku }) { const p=aisle.layout_position||{}; const x=((p.grid_x||20)-58)/4.2; const z=((p.grid_y||20)-48)/4.2; return <group position={[x,0,z]} rotation={[0,(p.rotation||0)*Math.PI/180,0]}><Text position={[0,2.8,-.9]} fontSize={.46} color={DARK} anchorX="center">{aisle.aisle_id}</Text>{(aisle.modules||[]).slice(0,6).map((m,i)=><ShelfRack key={m.module_id} module={m} x={(i-2.5)*1.45} highlight={m.shelves?.some(s=>s.products?.some(p=>String(p.sku).toLowerCase().includes(String(focusSku||'___').toLowerCase())))} />)}</group>; }
function ShelfRack({ module, x, highlight }) { const color = module.module_type==='fridge'?CYAN:module.module_type==='freezer'?PURPLE:'#c8d3dc'; const productColors=['#DF1067','#18C7DF','#F5D86B','#f4f7f9']; return <group position={[x,.55,0]}>
  <mesh position={[0,.65,0]}><boxGeometry args={[1.15,1.3,.22]}/><meshStandardMaterial color={highlight?BRAND:'#f8fbfc'} transparent opacity={highlight?.95:.76} roughness={.45}/></mesh>
  {[0,.35,.7,1.05].map((y,i)=><mesh key={i} position={[0,y,-.12]}><boxGeometry args={[1.22,.035,.12]}/><meshStandardMaterial color="#aab5bf" metalness={.1}/></mesh>)}
  {[-.62,.62].map((sx,i)=><mesh key={i} position={[sx,.55,-.13]}><boxGeometry args={[.04,1.35,.06]}/><meshStandardMaterial color="#4d5966"/></mesh>)}
  {Array.from({length:12}).map((_,i)=><mesh key={i} position={[-.45+(i%4)*.3,.18+Math.floor(i/4)*.32,.06]}><boxGeometry args={[.12,.18,.16]}/><meshStandardMaterial color={productColors[i%productColors.length]} transparent opacity={.78}/></mesh>)}
  <mesh position={[0,1.42,0]}><boxGeometry args={[1.25,.06,.28]}/><meshStandardMaterial color={color} transparent opacity={.25}/></mesh>
</group>; }
function Object3D({ obj }) { const x=(obj.x-58)/4.2, z=(obj.y-48)/4.2, w=(obj.w||6)/4.2, d=(obj.h||4)/4.2; const props={ cold_room:[CYAN,.18,1.6], frozen_room:[PURPLE,.16,1.6], dispatch:[GREEN,.2,.55], receiving:['#c8cdd5',.22,.55], algida_cabinet:[PURPLE,.22,1.8], column:['#7b8490',.9,1.6], wall:['#242a33',.3,1.4] }[obj.type] || ['#d9dde3',.3,.7]; return <group position={[x,0,z]} rotation={[0,(obj.rotation||0)*Math.PI/180,0]}><mesh position={[0,props[2]/2,0]}><boxGeometry args={[Math.max(w,.15),props[2],Math.max(d,.15)]}/><meshStandardMaterial color={props[0]} transparent opacity={props[1]}/></mesh>{obj.label&&<Html position={[0,props[2]+.25,0]} center><div className="scene-label">{obj.label}</div></Html>}</group>; }
function RouteLine(){ const pts=[[-14,.06,9],[-8,.06,5],[-3,.06,6],[1,.06,1],[5,.06,2],[9,.06,-4],[13,.06,7]]; return <Line points={pts} color={BRAND} lineWidth={3} dashed dashSize={1} gapSize={.5}/>; }
function ZoneLabel({pos,label,color}){ return <Html position={pos} center><div className="scene-badge" style={{borderColor:color,color}}>{label}</div></Html>; }

function Live3D({ lang, planogram, products }) {
  const [preset,setPreset]=useState('overview'); const [query,setQuery]=useState('Eti'); const [focus,setFocus]=useState('');
  return <div className="page live-page"><PageHero overline="CANLI 3D" title={t(lang,'digitalTwin')} subtitle={t(lang,'digitalTwinSub')} tabs={[['overview','3D View'],['top','Top'],['chilled','Chilled'],['frozen','Frozen'],['dispatch','Dispatch']]} active={preset} onTab={setPreset}/>
    <div className="studio-grid"><section className="studio-main"><Canvas shadows camera={{position:[10,12,18], fov:46}}><Suspense fallback={null}><WarehouseScene planogram={planogram} preset={preset} focusSku={focus}/></Suspense></Canvas><div className="ptz-bar">{['overview','top','chilled','frozen','dispatch'].map(p=><button key={p} onClick={()=>setPreset(p)} className={preset===p?'active':''}>{p}</button>)}<button onClick={()=>setPreset('sku')}>Focus</button></div></section><aside className="right-panel"><Panel title={t(lang,'minimap')}><div className="mini-map-grid">{(planogram.aisles||[]).slice(0,9).map(a=><button key={a.aisle_id} onClick={()=>setPreset('overview')}>{a.aisle_id}</button>)}<button className="wide">DISPATCH</button></div></Panel><Panel title={t(lang,'searchSku')}><div className="search-row"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Eti Burçak / SKU"/><button onClick={()=>{setFocus(query);setPreset('sku')}}>{t(lang,'fly')}</button></div><div className="sku-card"><div className="sku-thumb"/><b>{query || 'Eti Burçak'}</b><span>Corridor E · Module E-04 · Shelf 3</span></div></Panel><AIInsights lang={lang}/><Panel title={t(lang,'camera')}>{['Overview','Chilled Zone','Frozen Zone','Dispatch Area'].map(x=><button className="wide-btn" key={x} onClick={()=>setPreset(x.toLowerCase().split(' ')[0])}>{x}</button>)}</Panel></aside></div>
  </div>;
}
function PageHero({overline,title,subtitle,tabs,active,onTab}){ return <section className="page-hero"><div><div className="overline">{overline}</div><h2>{title}</h2><p>{subtitle}</p></div>{tabs&&<div className="tabs">{tabs.map(([k,v])=><button key={k} className={active===k?'active':''} onClick={()=>onTab(k)}>{v}</button>)}</div>}</section>; }
function Panel({title, children}){ return <section className="panel"><h4>{title}</h4>{children}</section>; }

function LayoutArchitect({ lang, planogram, setPlanogram, onSave }) {
  const [selected,setSelected]=useState(null); const [snap,setSnap]=useState(true); const boardRef=useRef(null); const dragging=useRef(null);
  const objects=[...(planogram.layout_objects||[]), ...(planogram.aisles||[]).map(a=>({ id:`aisle-${a.aisle_id}`, type:'aisle', label:a.aisle_id, x:a.layout_position?.grid_x||20, y:a.layout_position?.grid_y||20, w:16, h:5, rotation:a.layout_position?.rotation||0, aisle_id:a.aisle_id }))];
  function commitObject(obj) { setPlanogram(prev=>{ const next=structuredClone(prev); if(obj.type==='aisle'){ const a=next.aisles.find(x=>x.aisle_id===obj.aisle_id); if(a) a.layout_position={grid_x:obj.x, grid_y:obj.y, rotation:obj.rotation||0}; } else { const i=(next.layout_objects||[]).findIndex(x=>x.id===obj.id); if(i>=0) next.layout_objects[i]={...next.layout_objects[i],...obj}; } return next; }); }
  function addObj(type){ const config={ corridor:['aisle','J',18,5], column:['column','Kolon',.8,.8], cold_room:['cold_room','+4 Chilled',20,12], frozen_room:['frozen_room','-18 Frozen',20,12], dispatch:['dispatch','Dispatch',16,8], receiving:['receiving','Receiving',12,8], algida:['algida_cabinet','Algida',8,4], fridge:['horizontal_fridge','Yatay Dolap',8,3], wall:['wall','Duvar',25,.35] }[type]; if(type==='corridor'){ setPlanogram(prev=>{const next=structuredClone(prev); const id=String.fromCharCode(65+next.aisles.length); next.aisles.push({aisle_id:id,row:1,position:1,direction:'LTR',layout_position:{grid_x:20,y:20,grid_y:20,rotation:0},modules:Array.from({length:6},(_,i)=>makeModule(i+1,i<3?'L':'R','AMBIENT'))}); return next;}); return; } const obj={id:uid(type),type:config[0],label:config[1],x:25,y:25,w:config[2],h:config[3],rotation:0}; setPlanogram(prev=>({...prev, layout_objects:[...(prev.layout_objects||[]),obj]})); setSelected(obj); }
  function pointerDown(e,obj){ const r=boardRef.current.getBoundingClientRect(); dragging.current={id:obj.id, offX:e.clientX-r.left - obj.x/140*boardRef.current.clientWidth, offY:e.clientY-r.top - obj.y/90*boardRef.current.clientHeight}; setSelected(obj); }
  function pointerMove(e){ if(!dragging.current) return; const r=boardRef.current.getBoundingClientRect(); const x=((e.clientX-r.left-dragging.current.offX)/r.width)*140; const y=((e.clientY-r.top-dragging.current.offY)/r.height)*90; const obj=objects.find(o=>o.id===dragging.current.id); if(!obj) return; const nx=snap?Math.round(x):Number(x.toFixed(1)); const ny=snap?Math.round(y):Number(y.toFixed(1)); const changed={...obj,x:clamp(nx,0,136),y:clamp(ny,0,86)}; setSelected(changed); commitObject(changed); }
  function updateSelected(patch){ if(!selected) return; const changed={...selected,...patch}; setSelected(changed); commitObject(changed); }
  function deleteSelected(){ if(!selected) return; setPlanogram(prev=>{ const next=structuredClone(prev); if(selected.type==='aisle') next.aisles=next.aisles.filter(a=>a.aisle_id!==selected.aisle_id); else next.layout_objects=(next.layout_objects||[]).filter(o=>o.id!==selected.id); return next; }); setSelected(null); }
  return <div className="page"><PageHero overline="ARCHITECT MODE" title={t(lang,'architectTitle')} subtitle={t(lang,'architectSub')}/><div className="architect-actions"><button className="btn primary" onClick={()=>alert('AI layout önerisi: soğuk oda ve frozen zone koridor temasından ayrıldı, dispatch rotası kısaltıldı.')}>✦ {t(lang,'aiLayout')}</button><button className={`btn ${snap?'primary':'light'}`} onClick={()=>setSnap(!snap)}>{t(lang,'snap')}</button><button className="btn light" onClick={onSave}>{t(lang,'saveLayout')}</button><button className="btn light" onClick={()=>updateSelected({rotation:((selected?.rotation||0)+90)%360})}>90° Döndür</button></div>
    <div className="architect-layout"><aside className="catalog"><h4>{t(lang,'objectCatalog')}</h4>{[['wall','Duvar Paneli'],['column','Yuvarlak Kolon'],['dispatch','Dispatch'],['receiving','Receiving'],['cold_room','Soğuk Oda'],['frozen_room','Donuk Oda'],['algida','Algida Dolap'],['fridge','Yatay Dolap'],['corridor','Koridor']].map(([k,v])=><button key={k} onClick={()=>addObj(k)}>{v}</button>)}</aside>
      <section className="blueprint" ref={boardRef} onPointerMove={pointerMove} onPointerUp={()=>dragging.current=null} onPointerLeave={()=>dragging.current=null}><div className="rulers x">{Array.from({length:15},(_,i)=><span key={i}>{i*10}</span>)}</div><div className="rulers y">{Array.from({length:10},(_,i)=><span key={i}>{String.fromCharCode(65+i)}</span>)}</div>{objects.map(obj=><div key={obj.id} onPointerDown={e=>pointerDown(e,obj)} className={`layout-object ${obj.type} ${selected?.id===obj.id?'selected':''}`} style={{left:`${obj.x/140*100}%`,top:`${obj.y/90*100}%`,width:`${obj.w/140*100}%`,height:`${obj.h/90*100}%`,transform:`rotate(${obj.rotation||0}deg)`}}><b>{obj.label}</b>{obj.type==='aisle'&&<small>{obj.w}m x {obj.h}m</small>}</div>)}</section>
      <aside className="props"><h4>{t(lang,'properties')}</h4>{selected?<><b>{selected.label}</b><span>{selected.type}</span><label>X<input type="number" value={selected.x} onChange={e=>updateSelected({x:Number(e.target.value)})}/></label><label>Y<input type="number" value={selected.y} onChange={e=>updateSelected({y:Number(e.target.value)})}/></label><label>Width<input type="number" value={selected.w} onChange={e=>updateSelected({w:Number(e.target.value)})}/></label><label>Depth<input type="number" value={selected.h} onChange={e=>updateSelected({h:Number(e.target.value)})}/></label><label>Rotation<input type="number" value={selected.rotation||0} onChange={e=>updateSelected({rotation:Number(e.target.value)})}/></label><button className="btn primary">Öneriyi uygula</button><button className="btn danger" onClick={deleteSelected}>Sil</button></>:<p>Bir modül, koridor veya obje seç.</p>}</aside></div>
  </div>;
}

function Planogram2D({ lang, planogram, products, setPlanogram }) {
  function addProduct(aid, mid, shelfNo){ const p=products[Math.floor(Math.random()*products.length)]; if(!p) return; setPlanogram(prev=>{const next=structuredClone(prev); const a=next.aisles.find(x=>x.aisle_id===aid); const m=a?.modules.find(x=>x.module_id===mid); const s=m?.shelves.find(x=>x.shelf_no===shelfNo); if(s) s.products.push({...p, aisle_id:aid, module_id:mid, shelf_no:shelfNo}); return next;}); }
  function incFacing(aid,mid,shelfNo,sku,delta){ setPlanogram(prev=>{const next=structuredClone(prev); const p=next.aisles.find(a=>a.aisle_id===aid)?.modules.find(m=>m.module_id===mid)?.shelves.find(s=>s.shelf_no===shelfNo)?.products.find(x=>x.sku===sku); if(p) p.facing_count=clamp((p.facing_count||1)+delta,1,12); return next;}); }
  return <div className="page"><PageHero overline="2D PLANOGRAM" title={t(lang,'planogram2d')} subtitle="Koridor, modül, raf ve ürün yerleşimini okunabilir biçimde yönet." tabs={[['3d','3D View'],['2d','2D Plan'],['heat','Heatmap']]} active="2d" onTab={()=>{}}/><section className="plan2d"><div className="plan-toolbar"><b>{(planogram.aisles||[]).length} koridor</b><b>{useMetrics(planogram,products).shelves} raf</b><button className="btn light">+ Koridor</button></div>{(planogram.aisles||[]).map(a=><div className="corridor-row" key={a.aisle_id}><div className="corridor-head"><h3>Koridor {a.aisle_id}</h3><span>{a.modules?.length||0} modül</span><button className="btn light">+ Modül ekle</button></div><div className="modules-row">{(a.modules||[]).map(m=><div className="module-card" key={m.module_id}><header><b>{a.aisle_id} - {m.side}-Modül {m.module_id}</b><em>{m.module_type}</em></header>{(m.shelves||[]).map(s=><div className="shelf-card" key={s.shelf_no}><div className="shelf-top"><b>Raf {s.shelf_no}</b><span>{s.allowed_storage_type}</span></div><div className="products-line">{(s.products||[]).map(p=><div className="prod-chip" key={`${p.sku}-${Math.random()}`} title={p.product_name}><span>{p.product_name}</span><small>F:{p.facing_count||1}</small><button onClick={()=>incFacing(a.aisle_id,m.module_id,s.shelf_no,p.sku,1)}>+</button><button onClick={()=>incFacing(a.aisle_id,m.module_id,s.shelf_no,p.sku,-1)}>-</button></div>)}<button className="empty-slot" onClick={()=>addProduct(a.aisle_id,m.module_id,s.shelf_no)}>Boş raf · ürün ekle</button></div></div>)}</div>)}</div></div>)}</section></div>;
}
function ProductPlacement({ products }) { return <div className="page"><PageHero overline="PLACEMENT STUDIO" title="Ürün yerleşim stüdyosu" subtitle="Facing, depth, refill cost ve ürün bloklarını admin ekranında yönet."/><div className="placement-grid"><section className="visual-shelf"><h3>Görsel Raf</h3>{[1,2,3,4,5].map(r=><div className="visual-row" key={r}>{products.slice(0,10).map((p,i)=><div className="visual-product" key={`${p.sku}-${i}`} style={{height:30+(i%3)*8}}>{p.brand?.slice(0,2)}</div>)}</div>)}</section><section className="product-table"><h3>SKU Kontrol</h3><table><thead><tr><th>SKU</th><th>Ürün</th><th>Marka</th><th>Storage</th><th>Facing</th><th>Refill/day</th></tr></thead><tbody>{products.map(p=><tr key={p.sku}><td>{p.sku}</td><td>{p.product_name}</td><td>{p.brand}</td><td>{p.storage_type}</td><td>{p.facing_count||1}</td><td>{((p.sales_qty_7d||0)/7/Math.max((p.facing_count||1)*6,1)).toFixed(2)}</td></tr>)}</tbody></table></section></div></div>; }
function ProductLibrary({ products }) { const [q,setQ]=useState(''); const filtered=products.filter(p=>`${p.sku} ${p.product_name} ${p.brand} ${p.category_l2}`.toLowerCase().includes(q.toLowerCase())); return <div className="page"><PageHero overline="PRODUCT LIBRARY" title="Ürün kütüphanesi" subtitle="SKU, barkod, ölçü, storage ve refill risk datasını yönet."/><input className="big-search" value={q} onChange={e=>setQ(e.target.value)} placeholder="SKU / ürün / marka ara"/><div className="library-grid">{filtered.map(p=><div className="library-card" key={p.sku}><div className="sku-thumb"/><b>{p.product_name}</b><span>{p.sku} · {p.brand}</span><em>{p.storage_type}</em><small>{p.width_cm}×{p.depth_cm}×{p.height_cm} cm · Sales 7d: {p.sales_qty_7d}</small></div>)}</div></div>; }
function FixtureLibrary() { const fixtures=[['Yeni Nesil Çelik Raf','100×60×250','AMBIENT'],['Algida Dolabı','200×90×210','FROZEN'],['Yatay Dolap','150×80×110','CHILLED'],['Soğuk Oda','20 m²','CHILLED'],['Donuk Oda','18 m²','FROZEN']]; return <div className="page"><PageHero overline="FIXTURE LIBRARY" title="Fixture kütüphanesi" subtitle="Depo bazlı fixture kapasitesi ve modül tiplerini yönet."/><div className="library-grid">{fixtures.map(f=><div className="library-card" key={f[0]}><b>{f[0]}</b><span>{f[1]}</span><em>{f[2]}</em><button className="btn light">Detay</button></div>)}</div></div>; }
function Analytics({ lang, planogram, products }) { const m=useMetrics(planogram,products); const cards=[['Toplam Raf',m.shelves],['Yerleşen SKU',products.length],['Raf Genişlik Kullanımı',`${m.fillPct}%`],['Raf Hacim Kullanımı','18%'],['Kapasite Hacmi','118.21 m³'],['Soğuk Zincir',`${m.chilledPct}%`],['Refill Risk','Orta'],['Cold Chain','Sağlıklı']]; return <div className="page"><PageHero overline="ANALYTICS" title={t(lang,'analytics')} subtitle="Alan, hacim, doluluk, fixture ve cold chain metrikleri."/><div className="analytics-grid">{cards.map(c=><Metric key={c[0]} label={c[0]} value={c[1]} sub="live calculation"/>)}</div><section className="glass-card"><ul><li>Kolon/duvar ürün hacmini değil, zemin erişimini ve ölü alanı etkiler.</li><li>Dolap/oda fixture kapasitesi safety fill oranıyla ayrı takip edilir.</li><li>Refill cost ürün satış hızı ve shelf capacity ile hesaplanır.</li></ul></section></div>; }
function Rules({ lang }) { const rules=[['Marka yan yana','Brand adjacency prevents visual fragmentation.'],['Soğuk zincir izolasyonu','Chilled and frozen products stay isolated.'],['Ağır ürün sona','Heavy products are placed near the end of picking.'],['Hızlı SKU facing','High velocity SKUs receive more facing/depth.'],['Refill iş gücü azalt','Reduce refill visits and labor minutes.']]; return <div className="page"><PageHero overline="RULE ENGINE" title={t(lang,'rules')} subtitle="Simple words, clear rules, no technical clutter."/><div className="rule-grid">{rules.map(r=><div className="rule-card" key={r[0]}><h3>{r[0]}</h3><p>{r[1]}</p><button className="btn light">{t(lang,'apply')}</button></div>)}</div></div>; }
function Reports({ lang }) { return <div className="page"><PageHero overline="REPORTS" title={t(lang,'reportTitle')} subtitle="Risk, capacity, refill cost ve uygulama durumunu karar odaklı göster."/><section className="glass-card"><h3>Top Risk Stores</h3><table><tbody>{['Anka','Güven FR','Acıbadem'].map((x,i)=><tr key={x}><td>{i+1}</td><td>{x}</td><td>{i===0?'Cold capacity':'Refill risk'}</td><td><button className="btn light">Detay</button></td></tr>)}</tbody></table></section></div>; }
function Placeholder({ title }) { return <div className="page"><PageHero overline="PLONAGRAM OS" title={title} subtitle="Bu modül canlı veri modeliyle aynı tasarım sistemine bağlandı."/><section className="glass-card"><p>Bir sonraki sprintte backend iş kuralı ve yetki akışına bağlanacak.</p></section></div>; }

export default function App() {
  const [loading,setLoading]=useState(true); const [lang,setLang]=useState('TR'); const [view,setView]=useState('command'); const [store,setStore]=useState('Anka (İstanbul)'); const [status,setStatus]=useState(''); const [products,setProducts]=useState(sampleProducts()); const [planogram,setPlanogram]=useState(()=>seedPlan(createDefaultLayout(), sampleProducts()));
  useEffect(()=>{ const timer=setTimeout(()=>setLoading(false),1200); api.getHealth().catch(()=>{}); return ()=>clearTimeout(timer); },[]);
  async function onUploadCsv(file){ if(!file) return; try{ setStatus('CSV yükleniyor...'); const res=await api.uploadProductsCsv(file); const list=res.products||[]; if(list.length) setProducts(list); setStatus(`${list.length||0} SKU yüklendi.`); }catch(e){ setStatus(`Backend CSV yüklenemedi, local parse deneniyor: ${e.message}`); const text=await file.text(); const [head,...rows]=text.split(/\r?\n/).filter(Boolean); const cols=head.split(',').map(x=>x.trim()); const parsed=rows.slice(0,500).map(r=>{const vals=r.split(','); const o={}; cols.forEach((c,i)=>o[c]=vals[i]); return {sku:o.sku||o.SKU||o.barcode, product_name:o.product_name||o.name||o['Product Name']||'Product', brand:o.brand||o.brand_name||'Brand', storage_type:o.storage_type||'AMBIENT', width_cm:Number(o.width_cm||8), height_cm:Number(o.height_cm||15), depth_cm:Number(o.depth_cm||8), sales_qty_7d:Number(o.sales_qty_7d||0)};}); setProducts(parsed); }
  }
  async function onUploadLayout(file){ if(!file) return; try{ if(file.name.toLowerCase().endsWith('.json')){ const json=JSON.parse(await file.text()); setPlanogram(json.planogram||json.layout||json); setStatus('JSON layout yüklendi.'); return; } const res=await api.parseLayoutFile(file, store); if(res.layout){ setPlanogram(res.layout); setStatus(res.message||'Layout yüklendi.'); } }catch(e){ setStatus(`Layout yükleme hatası: ${e.message}`); } }
  async function onGenerate(){ try{ setStatus('Planogram üretiliyor...'); const res=await api.generatePlanogramLite({ products, layout: planogram, mode:'HYBRID' }); setPlanogram(res.planogram||res.layout||planogram); setStatus(`Plan üretildi: ${res.summary?.placed_products||0} ürün yerleşti.`); }catch(e){ setPlanogram(seedPlan(createDefaultLayout(), products)); setStatus(`Backend plan üretimi başarısız, lokal demo plan aktif: ${e.message}`); } }
  function onSave(){ localStorage.setItem('plonagram_layout', JSON.stringify(planogram)); setStatus('Layout kaydedildi.'); }
  function onExport(){ const blob=new Blob([JSON.stringify({ planogram, products },null,2)],{type:'application/json'}); const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download='plonagram_export.json'; a.click(); URL.revokeObjectURL(url); }
  if(loading) return <LoadingSplash/>;
  let content; if(view==='command') content=<CommandCenter lang={lang} setView={setView} planogram={planogram} products={products}/>; else if(view==='live3d') content=<Live3D lang={lang} planogram={planogram} products={products}/>; else if(view==='architect') content=<LayoutArchitect lang={lang} planogram={planogram} setPlanogram={setPlanogram} onSave={onSave}/>; else if(view==='planogram') content=<Planogram2D lang={lang} planogram={planogram} products={products} setPlanogram={setPlanogram}/>; else if(view==='placement') content=<ProductPlacement products={products}/>; else if(view==='products') content=<ProductLibrary products={products}/>; else if(view==='fixtures') content=<FixtureLibrary/>; else if(view==='rules') content=<Rules lang={lang}/>; else if(view==='reports') content=<Reports lang={lang}/>; else if(view==='delta') content=<Placeholder title="Delta Planogram"/>; else if(view==='tasks') content=<Placeholder title="Görev Yönetimi"/>; else content=<Placeholder title="Admin"/>;
  return <Shell lang={lang} setLang={setLang} view={view} setView={setView} store={store} setStore={setStore} onUploadCsv={onUploadCsv} onUploadLayout={onUploadLayout} onGenerate={onGenerate} status={status}>{content}<button className="floating-export" onClick={onExport}>↓ {t(lang,'export')}</button></Shell>;
}
