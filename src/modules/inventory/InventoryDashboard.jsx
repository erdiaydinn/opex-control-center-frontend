import React, { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft, BarChart3, Boxes, CheckCircle2, ClipboardCheck, Download,
  FileSpreadsheet, MapPin, PackageCheck, Plus, RefreshCw, ScanBarcode,
  Search, ShieldCheck, TriangleAlert, Upload, XCircle
} from "lucide-react";
import "./inventory.css";

const STORAGE_KEY = "opex_inventory_v1";
const demo = {
  products: [
    { sku: "100001", barcode: "8690001000011", name: "Süt 1 L", uom: "ADET", cost: 42.5 },
    { sku: "100002", barcode: "8690001000028", name: "Maden Suyu 6x200 ml", uom: "PAKET", cost: 58 },
    { sku: "100003", barcode: "8690001000035", name: "Pirinç 1 kg", uom: "ADET", cost: 71.9 }
  ],
  locations: ["A01-01-D01", "A01-01-D02", "B02-03-D01"],
  stock: [
    { location: "A01-01-D01", sku: "100001", expected: 24 },
    { location: "A01-01-D01", sku: "100002", expected: 10 },
    { location: "A01-01-D02", sku: "100003", expected: 18 }
  ],
  documents: [],
  audit: []
};

function allowSensitivePilotStorage() {
  return (
    typeof window !== "undefined" &&
    import.meta.env.DEV
  );
}

function purgeSensitiveInventoryStorage() {
  if (typeof window === "undefined") return;

  try {
    window.localStorage.removeItem(
      STORAGE_KEY
    );
  } catch {
    // Browser storage may be unavailable.
  }
}

function loadState() {
  if (!allowSensitivePilotStorage()) {
    purgeSensitiveInventoryStorage();
    return demo;
  }

  try {
    return (
      JSON.parse(
        window.localStorage.getItem(
          STORAGE_KEY
        )
      ) || demo
    );
  } catch {
    return demo;
  }
}

function now() { return new Date().toISOString(); }
function uid(prefix) { return prefix + "-" + Date.now().toString(36).toUpperCase(); }
function csvEscape(value) {
  const text = String(value ?? "");
  return /[",\n]/.test(text) ? '"' + text.replaceAll('"', '""') + '"' : text;
}
function downloadCsv(name, rows) {
  const csv = "\ufeff" + rows.map(row => row.map(csvEscape).join(";")).join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}
function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return [];
  const delimiter = lines[0].includes(";") ? ";" : ",";
  const headers = lines[0].split(delimiter).map(x => x.trim().toLowerCase());
  return lines.slice(1).map(line => {
    const values = line.split(delimiter).map(x => x.trim());
    return headers.reduce((row, header, index) => ({ ...row, [header]: values[index] || "" }), {});
  });
}

export default function InventoryDashboard() {
  const [data, setData] = useState(loadState);
  const [tab, setTab] = useState("overview");
  const [activeId, setActiveId] = useState("");
  const [scanLocation, setScanLocation] = useState("");
  const [scanCode, setScanCode] = useState("");
  const [qty, setQty] = useState(1);
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");
  const fileRef = useRef(null);

  const active = data.documents.find(d => d.id === activeId) || data.documents[0];
  const lines = active?.lines || [];
  const completed = lines.filter(l => l.counted !== null).length;
  const varianceLines = lines.filter(l => l.counted !== null && l.counted !== l.expected);
  const varianceValue = varianceLines.reduce((sum, l) => sum + Math.abs(l.counted - l.expected) * (l.cost || 0), 0);

  function save(next, message) {
    if (allowSensitivePilotStorage()) {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify(next)
      );
    } else {
      purgeSensitiveInventoryStorage();
    }

    setData(next);
    setNotice(message || "Kaydedildi");

    window.setTimeout(
      () => setNotice(""),
      2400
    );
  }

  function createDocument() {
    const id = uid("CNT");
    const lines = data.stock.map((s, index) => {
      const product = data.products.find(p => p.sku === s.sku) || {};
      return { id: id + "-" + index, ...s, name: product.name || s.sku, barcode: product.barcode || "", cost: Number(product.cost || 0), counted: null, revisions: [] };
    });
    const doc = { id, name: "Genel Sayım " + new Date().toLocaleDateString("tr-TR"), status: "COUNTING", createdAt: now(), lines };
    save({ ...data, documents: [doc, ...data.documents], audit: [{ at: now(), action: "DOCUMENT_CREATED", documentId: id }, ...data.audit] }, "Sayım belgesi oluşturuldu");
    setActiveId(id); setTab("terminal");
  }

  function updateDocument(mutator, action) {
    if (!active) return;
    const documents = data.documents.map(doc => doc.id === active.id ? mutator(doc) : doc);
    save({ ...data, documents, audit: [{ at: now(), action, documentId: active.id }, ...data.audit] });
  }

  function submitScan(event) {
    event.preventDefault();
    if (!active || active.status !== "COUNTING") return setNotice("Aktif sayım belgesi yok");
    if (!data.locations.includes(scanLocation)) return setNotice("Lokasyon bulunamadı");
    const product = data.products.find(p => p.barcode === scanCode || p.sku === scanCode);
    if (!product) return setNotice("Barkod / SKU bulunamadı");
    const found = active.lines.find(l => l.location === scanLocation && l.sku === product.sku);
    updateDocument(doc => {
      let docLines = doc.lines;
      if (found) docLines = docLines.map(line => line.id === found.id ? { ...line, counted: Number(line.counted || 0) + Number(qty) } : line);
      else docLines = [...docLines, { id: uid("LINE"), location: scanLocation, sku: product.sku, barcode: product.barcode, name: product.name, expected: 0, counted: Number(qty), cost: product.cost, unexpected: true, revisions: [] }];
      return { ...doc, lines: docLines };
    }, "SCAN_RECORDED");
    setScanCode(""); setQty(1);
  }

  function changeCount(line, value) {
    const nextValue = value === "" ? null : Math.max(0, Number(value));
    updateDocument(doc => ({ ...doc, lines: doc.lines.map(item => item.id === line.id ? {
      ...item, counted: nextValue, revisions: [...(item.revisions || []), { at: now(), from: item.counted, to: nextValue, source: "PC_CONTROL" }]
    } : item) }), "CONTROL_REVISION");
  }

  function closeCount() {
    if (!active || completed !== lines.length) return setNotice("Tüm satırlar sayılmadan kapatılamaz");
    updateDocument(doc => ({ ...doc, status: varianceLines.length ? "RECONCILIATION" : "APPROVED", countedAt: now() }), "COUNT_COMPLETED");
    setTab("reconcile");
  }

  function approve() {
    updateDocument(doc => ({ ...doc, status: "APPROVED", approvedAt: now() }), "DOCUMENT_APPROVED");
  }

  function importFile(event) {
    const file = event.target.files?.[0]; if (!file) return;
    file.text().then(text => {
      const rows = parseCsv(text);
      const products = rows.filter(r => r.sku).map(r => ({ sku: r.sku, barcode: r.barcode, name: r.name || r.product_name, uom: r.uom || "ADET", cost: Number(r.cost || 0) }));
      const locations = [...new Set(rows.map(r => r.location).filter(Boolean))];
      const stock = rows.filter(r => r.sku && r.location).map(r => ({ sku: r.sku, location: r.location, expected: Number(r.expected || r.qty || 0) }));
      if (!products.length || !stock.length) return setNotice("Şablon kolonları bulunamadı");
      save({ ...data, products, locations, stock }, rows.length + " satır yüklendi");
    });
    event.target.value = "";
  }

  const filtered = lines.filter(l => [l.sku, l.name, l.location, l.barcode].join(" ").toLowerCase().includes(query.toLowerCase()));
  const metrics = [
    ["Aktif belge", data.documents.filter(d => d.status !== "APPROVED").length, ClipboardCheck],
    ["Sayım ilerleme", lines.length ? Math.round(completed / lines.length * 100) + "%" : "—", ScanBarcode],
    ["Farklı SKU", varianceLines.length, TriangleAlert],
    ["Mutlak etki", "₺" + varianceValue.toLocaleString("tr-TR", { maximumFractionDigits: 0 }), BarChart3]
  ];

  return <main className="inv-page">
    <header className="inv-topbar">
      <div className="inv-brand"><Link to="/" aria-label="Geri"><ArrowLeft /></Link><div><small>OPEX CONTROL CENTER</small><strong>Inventory</strong></div></div>
      <div className="inv-actions">
        {notice && <span className="inv-notice">{notice}</span>}
        <input ref={fileRef} type="file" accept=".csv,.txt" hidden onChange={importFile} />
        <button className="secondary" onClick={() => fileRef.current?.click()}><Upload size={17}/> Veri yükle</button>
        <button onClick={createDocument}><Plus size={17}/> Sayım başlat</button>
      </div>
    </header>

    <section className="inv-hero">
      <div><span className="inv-kicker"><ShieldCheck size={15}/> Kör sayım ve denetlenebilir mutabakat</span><h1>Stok gerçeğini<br/>lokasyonda yakala.</h1><p>Terminal sayımı, kontrol sayımı, fark yönetimi ve tutanak tek akışta.</p></div>
      <div className="inv-active-card"><small>SEÇİLİ BELGE</small><strong>{active?.id || "Henüz belge yok"}</strong><span>{active?.name || "Yeni sayım başlatarak ilerleyin"}</span>{active && <em className={"status " + active.status.toLowerCase()}>{active.status}</em>}</div>
    </section>

    <nav className="inv-tabs">
      {[["overview","Genel Bakış"],["terminal","Terminal Sayımı"],["control","PC Kontrol"],["reconcile","Fark & Onay"],["data","Ana Veriler"]].map(([key,label]) => <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>{label}</button>)}
    </nav>

    {tab === "overview" && <section>
      <div className="inv-metrics">{metrics.map(([label,value,Icon]) => <article key={label}><Icon/><small>{label}</small><strong>{value}</strong></article>)}</div>
      <div className="inv-grid two">
        <article className="inv-panel"><div className="panel-title"><div><small>COUNT DOCUMENTS</small><h2>Sayım belgeleri</h2></div><button onClick={createDocument}><Plus size={16}/> Yeni</button></div>
          <div className="doc-list">{data.documents.length ? data.documents.map(doc => <button key={doc.id} onClick={() => {setActiveId(doc.id); setTab("terminal");}}><span><strong>{doc.id}</strong><small>{doc.name}</small></span><em className={"status " + doc.status.toLowerCase()}>{doc.status}</em></button>) : <div className="inv-empty"><Boxes/><strong>İlk sayımı başlatın</strong><span>Snapshot satırları otomatik belgeye dönüşür.</span></div>}</div>
        </article>
        <article className="inv-panel"><div className="panel-title"><div><small>AUDIT TRAIL</small><h2>Son hareketler</h2></div></div><div className="audit-list">{data.audit.slice(0,8).map((a,i) => <div key={i}><span></span><strong>{a.action}</strong><small>{a.documentId} · {new Date(a.at).toLocaleString("tr-TR")}</small></div>)}</div></article>
      </div>
    </section>}

    {tab === "terminal" && <section className="inv-grid terminal-grid">
      <article className="inv-panel scan-panel"><div className="panel-title"><div><small>HANDHELD MODE</small><h2>Kör sayım</h2></div><ScanBarcode size={28}/></div>
        <div className="blind-note"><ShieldCheck/> Sistem adedi sayım personeline gösterilmez.</div>
        <form onSubmit={submitScan}>
          <label>1. Lokasyon okut<input autoFocus value={scanLocation} onChange={e => setScanLocation(e.target.value.toUpperCase())} placeholder="A01-01-D01"/></label>
          <label>2. Barkod / SKU okut<input value={scanCode} onChange={e => setScanCode(e.target.value)} placeholder="Barkodu okutun"/></label>
          <label>3. Miktar<input type="number" min="1" value={qty} onChange={e => setQty(e.target.value)}/></label>
          <button type="submit"><ScanBarcode/> Sayıma ekle</button>
        </form>
        <button className="close-count" onClick={closeCount}><PackageCheck/> Lokasyonları tamamla ve sayımı kapat</button>
      </article>
      <article className="inv-panel"><div className="panel-title"><div><small>PROGRESS</small><h2>Sayım ilerlemesi</h2></div><strong>{completed}/{lines.length}</strong></div>
        <div className="progress"><span style={{width: (lines.length ? completed/lines.length*100 : 0) + "%"}}></span></div>
        <div className="count-feed">{lines.filter(l => l.counted !== null).slice(-10).reverse().map(l => <div key={l.id}><MapPin/><span><strong>{l.location}</strong><small>{l.sku} · {l.name}</small></span><b>{l.counted}</b></div>)}</div>
      </article>
    </section>}

    {tab === "control" && <section className="inv-panel">
      <div className="panel-title"><div><small>FAST CONTROL GRID</small><h2>PC kontrol sayımı</h2></div><div className="searchbox"><Search size={16}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="SKU, ürün, lokasyon ara"/></div></div>
      <div className="table-wrap"><table><thead><tr><th>Lokasyon</th><th>SKU</th><th>Ürün</th><th>Sistem</th><th>Sayım</th><th>Fark</th><th>Etki</th><th>Durum</th></tr></thead><tbody>{filtered.map(l => { const diff = l.counted === null ? null : l.counted-l.expected; return <tr key={l.id} className={diff ? "has-diff" : ""}><td>{l.location}</td><td>{l.sku}</td><td>{l.name}</td><td>{l.expected}</td><td><input type="number" min="0" value={l.counted ?? ""} onChange={e => changeCount(l,e.target.value)}/></td><td>{diff ?? "—"}</td><td>{diff === null ? "—" : "₺"+Math.abs(diff*l.cost).toFixed(0)}</td><td>{l.unexpected ? <span className="pill warn">Beklenmeyen</span> : diff ? <span className="pill danger">Kontrol</span> : <span className="pill ok">Uyumlu</span>}</td></tr>})}</tbody></table></div>
    </section>}

    {tab === "reconcile" && <section className="inv-grid two">
      <article className="inv-panel"><div className="panel-title"><div><small>VARIANCE</small><h2>Fark mutabakatı</h2></div><TriangleAlert/></div>
        <div className="variance-list">{varianceLines.length ? varianceLines.map(l => <div key={l.id}><span><strong>{l.sku} · {l.name}</strong><small>{l.location} · Sistem {l.expected} / Sayım {l.counted}</small></span><b className={l.counted-l.expected > 0 ? "positive" : "negative"}>{l.counted-l.expected > 0 ? "+" : ""}{l.counted-l.expected}</b></div>) : <div className="inv-empty"><CheckCircle2/><strong>Fark bulunmuyor</strong></div>}</div>
      </article>
      <article className="inv-panel approval"><ShieldCheck size={42}/><h2>Sayımı sonuçlandır</h2><p>Onay sonrası belge kilitlenir. Sonraki değişiklik yeni revizyon gerektirir.</p>
        <button disabled={!active || active.status === "COUNTING" || active.status === "APPROVED"} onClick={approve}><CheckCircle2/> Onayla ve kilitle</button>
        <button className="secondary" disabled={!active} onClick={() => active && downloadCsv(active.id+"_tutanak.csv", [["Lokasyon","SKU","Ürün","Sistem","Sayım","Fark"], ...active.lines.map(l => [l.location,l.sku,l.name,l.expected,l.counted,l.counted-l.expected])])}><Download/> Sayım tutanağı indir</button>
      </article>
    </section>}

    {tab === "data" && <section className="inv-grid three">
      {[["Ürünler",data.products.length,FileSpreadsheet],["Lokasyonlar",data.locations.length,MapPin],["Stok satırları",data.stock.length,Boxes]].map(([label,value,Icon]) => <article className="inv-panel master" key={label}><Icon/><small>MASTER DATA</small><strong>{value}</strong><span>{label}</span></article>)}
      <article className="inv-panel upload-help"><Upload/><h2>Tek dosyayla yükle</h2><p>CSV kolonları: <b>sku;barcode;name;uom;cost;location;expected</b></p><button onClick={() => fileRef.current?.click()}>CSV seç</button><button className="secondary" onClick={() => downloadCsv("inventory_sablon.csv", [["sku","barcode","name","uom","cost","location","expected"],["100001","8690001000011","Örnek ürün","ADET","25.5","A01-01-D01","10"]])}><Download/> Şablon indir</button></article>
    </section>}
  </main>;
}
