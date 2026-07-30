import React from 'react';

﻿function productImage(p = {}) {
  const url =
    p.image_url ||
    p.imageUrl ||
    p["Product Image URL"] ||
    p.product_image_url ||
    p.image;

  return /^https?:\/\//i.test(String(url || "")) ? url : "";
}

function skuOf(p = {}) {
  return String(p.sku || p.SKU || p.barcode || p.Barcodes || "").trim();
}

function productLocation(p = {}) {
  const aisle = p.aisle || p.aisle_id || "";
  const moduleNo = p.module || p.module_id || "";
  const shelfNo = p.shelf || p.shelf_no || "";

  return {
    aisle: String(aisle || "-"),
    module: String(moduleNo || "-"),
    shelf: String(shelfNo || "-"),
    label: [aisle, moduleNo ? `M${moduleNo}` : "", shelfNo ? `R${shelfNo}` : ""]
      .filter(Boolean)
      .join("-") || "-",
  };
}

function rowsFromProducts(products = []) {
  return (products || []).map((p) => {
    const loc = productLocation(p);

    return {
      raw: p,
      aisle: loc.aisle,
      module: loc.module,
      shelf: loc.shelf,
      location: loc.label,
      sku: skuOf(p),
      name: p.name || p.product_name || p.productName || p["Product Name"] || "-",
      brand: p.brand || p.brand_name || "-",
      category: p.category || p.category_l1 || p["Category L1"] || "-",
      storage: p.storage || p.storage_type || p.storage_class || "-",
      family: p.food_family || "-",
      facing: p.facing || p.facing_count || "-",
      depth: p.depth || "-",
      reason: p.placement_reason || "-",
      img: productImage(p),
    };
  });
}

function csvEscape(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function downloadCsv(rows = []) {
  const headers = [
    "Koridor",
    "Modül",
    "Raf",
    "Yeni Lokasyon",
    "SKU",
    "Ürün",
    "Marka",
    "Kategori",
    "Storage",
    "Food Family",
    "Facing",
    "Depth",
    "Neden",
  ];

  const csv = [
    headers.join(","),
    ...rows.map((r) => [
      r.aisle,
      r.module,
      r.shelf,
      r.location,
      r.sku,
      r.name,
      r.brand,
      r.category,
      r.storage,
      r.family,
      r.facing,
      r.depth,
      r.reason,
    ].map(csvEscape).join(",")),
  ].join("\n");

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "planogram_export.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function buildPrintHtml(rows = [], mode = "both", title = "Planogram") {
  const showVisual = mode === "visual" || mode === "both";
  const showText = mode === "text" || mode === "both";

  const grouped = rows.reduce((acc, r) => {
    const key = `${r.aisle} / Modül ${r.module} / Raf ${r.shelf}`;
    acc[key] ||= [];
    acc[key].push(r);
    return acc;
  }, {});

  const visualHtml = Object.entries(grouped).map(([key, items]) => `
    <section class="shelf-card">
      <h3>${key}</h3>
      <div class="visual-row">
        ${items.map((r) => `
          <div class="product-card">
            ${r.img ? `<img src="${r.img}" />` : `<div class="no-img">${String(r.name || "?").slice(0, 2)}</div>`}
            <b>${r.name}</b>
            <small>${r.sku}</small>
            <small>${r.storage} · Facing ${r.facing} · Depth ${r.depth}</small>
          </div>
        `).join("")}
      </div>
    </section>
  `).join("");

  const textHtml = `
    <table>
      <thead>
        <tr>
          <th>Lokasyon</th>
          <th>SKU</th>
          <th>Ürün</th>
          <th>Marka</th>
          <th>Storage</th>
          <th>Family</th>
          <th>Facing</th>
          <th>Depth</th>
          <th>Neden</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((r) => `
          <tr>
            <td>${r.location}</td>
            <td>${r.sku}</td>
            <td>${r.name}</td>
            <td>${r.brand}</td>
            <td>${r.storage}</td>
            <td>${r.family}</td>
            <td>${r.facing}</td>
            <td>${r.depth}</td>
            <td>${r.reason}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;

  return `
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>${title}</title>
<style>
  body { font-family: Arial, sans-serif; margin: 24px; color: #111827; }
  h1 { margin: 0 0 8px; font-size: 28px; }
  .meta { color: #64748b; margin-bottom: 24px; }
  table { width: 100%; border-collapse: collapse; font-size: 11px; }
  th { text-align: left; background: #f8fafc; color: #475569; }
  th, td { border-bottom: 1px solid #e5e7eb; padding: 8px; vertical-align: top; }
  .shelf-card { page-break-inside: avoid; border: 1px solid #e5e7eb; border-radius: 14px; padding: 14px; margin-bottom: 16px; }
  .shelf-card h3 { margin: 0 0 12px; font-size: 16px; }
  .visual-row { display: flex; gap: 10px; flex-wrap: wrap; }
  .product-card { width: 120px; min-height: 150px; border: 1px solid #e5e7eb; border-radius: 12px; padding: 8px; display: flex; flex-direction: column; gap: 5px; }
  .product-card img { width: 48px; height: 48px; object-fit: contain; align-self: center; }
  .product-card b { font-size: 10px; line-height: 1.25; }
  .product-card small { color: #64748b; font-size: 9px; line-height: 1.25; }
  .no-img { width: 48px; height: 48px; border-radius: 10px; background: #fce7f3; display:flex; align-items:center; justify-content:center; font-weight:800; align-self:center; }
  @media print {
    body { margin: 14mm; }
    .shelf-card { break-inside: avoid; }
  }
</style>
</head>
<body>
  <h1>${title}</h1>
  <div class="meta">${rows.length.toLocaleString("tr-TR")} ürün · ${new Date().toLocaleString("tr-TR")}</div>
  ${showVisual ? visualHtml : ""}
  ${showText ? textHtml : ""}
</body>
</html>
`;
}

function openPrintWindow(rows, mode, title) {
  const html = buildPrintHtml(rows, mode, title);
  const win = window.open("", "_blank");

  if (!win) {
    alert("Popup engellendi. Tarayıcıdan popup izni verip tekrar dene.");
    return;
  }

  win.document.open();
  win.document.write(html);
  win.document.close();

  setTimeout(() => {
    win.focus();
    win.print();
  }, 500);
}

function downloadHtml(rows, mode, title) {
  const html = buildPrintHtml(rows, mode, title);
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "planogram_print_view.html";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function PlanogramExportPanel({ products = [] }) {
  const [scope, setScope] = React.useState("all");
  const [mode, setMode] = React.useState("both");
  const [aisle, setAisle] = React.useState("");
  const [moduleNo, setModuleNo] = React.useState("");
  const [shelfNo, setShelfNo] = React.useState("");

  const allRows = rowsFromProducts(products);

  const rows = allRows.filter((r) => {
    if (scope === "all") return true;
    if (scope === "aisle") return String(r.aisle).toUpperCase() === String(aisle).trim().toUpperCase();
    if (scope === "module") {
      return (
        String(r.aisle).toUpperCase() === String(aisle).trim().toUpperCase() &&
        String(r.module) === String(moduleNo).trim()
      );
    }
    if (scope === "shelf") {
      return (
        String(r.aisle).toUpperCase() === String(aisle).trim().toUpperCase() &&
        String(r.module) === String(moduleNo).trim() &&
        String(r.shelf) === String(shelfNo).trim()
      );
    }
    return true;
  });

  const title =
    scope === "all"
      ? "Tüm Planogram"
      : scope === "aisle"
        ? `Koridor ${aisle}`
        : scope === "module"
          ? `Koridor ${aisle} / Modül ${moduleNo}`
          : `Koridor ${aisle} / Modül ${moduleNo} / Raf ${shelfNo}`;

  return (
    <section className="card pad planogram-export-panel">
      <div>
        <div className="section-eyebrow">PLANOGRAM ÇIKTI MERKEZİ</div>
        <h3>Yazdır / indir</h3>
        <p className="muted">Tüm planogram, koridor, modül veya raf bazında yazılı ve görselli çıktı al.</p>
      </div>

      <div className="export-grid">
        <label>
          Kapsam
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="all">Tüm planogram</option>
            <option value="aisle">Koridor</option>
            <option value="module">Modül</option>
            <option value="shelf">Raf</option>
          </select>
        </label>

        <label>
          Format
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="both">Yazılı + resimli</option>
            <option value="text">Sadece yazılı</option>
            <option value="visual">Sadece resimli</option>
          </select>
        </label>

        {scope !== "all" && (
          <label>
            Koridor
            <input value={aisle} onChange={(e) => setAisle(e.target.value)} placeholder="A" />
          </label>
        )}

        {(scope === "module" || scope === "shelf") && (
          <label>
            Modül
            <input value={moduleNo} onChange={(e) => setModuleNo(e.target.value)} placeholder="2" />
          </label>
        )}

        {scope === "shelf" && (
          <label>
            Raf
            <input value={shelfNo} onChange={(e) => setShelfNo(e.target.value)} placeholder="1" />
          </label>
        )}
      </div>

      <div className="export-actions">
        <button className="btn primary" onClick={() => openPrintWindow(rows, mode, title)}>
          Yazdır / PDF kaydet
        </button>
        <button className="btn ghost" onClick={() => downloadHtml(rows, mode, title)}>
          HTML indir
        </button>
        <button className="btn ghost" onClick={() => downloadCsv(rows)}>
          CSV indir
        </button>
        <span className="muted">{rows.length.toLocaleString("tr-TR")} ürün seçili</span>
      </div>
    </section>
  );
}
