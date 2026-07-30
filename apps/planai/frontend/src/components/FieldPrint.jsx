import { faceCount, shelfUsedWidth } from "../utils/planogram";

function productCardHtml(p) {
  const img = p.image_url ? `<img src="${p.image_url}"/>` : `<div class="noimg">${p.storage_type === "FROZEN" ? "❄" : p.storage_type === "CHILLED" ? "🥶" : "📦"}</div>`;
  return `<div class="product-card">${img}<b>${p.product_name || ""}</b><span>${p.sku || ""}</span><strong>Ön yüz: ${faceCount(p)}</strong></div>`;
}

export function printModule(aisle, module) {
  const html = `
  <html><head><title>${aisle.aisle_id} Modül ${module.module_id}</title><style>
    body{font-family:Arial,sans-serif;margin:0;color:#111827} .page{padding:22px;page-break-after:always} h1{margin:0 0 6px;font-size:26px}.sub{color:#64748b;margin-bottom:18px}.shelf{border:2px solid #0f172a;border-radius:12px;margin:14px 0;padding:12px}.shelf-head{display:flex;justify-content:space-between;font-weight:800;margin-bottom:10px}.products{display:flex;gap:8px;align-items:stretch;overflow:hidden}.product-card{width:120px;border:1px solid #cbd5e1;border-radius:10px;padding:8px;text-align:center;display:flex;flex-direction:column;gap:4px;min-height:150px}.product-card img{height:70px;object-fit:contain}.product-card b{font-size:11px}.product-card span{font-size:10px;color:#64748b}.product-card strong{font-size:12px}.noimg{height:70px;display:grid;place-items:center;font-size:28px;background:#f1f5f9;border-radius:8px}.list{width:100%;border-collapse:collapse}.list th,.list td{border:1px solid #cbd5e1;padding:8px;font-size:12px}.list th{background:#0f172a;color:white;text-align:left}.badge{display:inline-block;background:#fce7f3;color:#9d174d;border-radius:999px;padding:4px 10px;font-weight:800}@media print{button{display:none}}
  </style></head><body>
    <div class="page"><h1>Koridor ${aisle.aisle_id} / Modül ${module.module_id}</h1><div class="sub">Görsel raf dizilimi · ${module.module_width_cm || "?"}cm modül</div>${[...(module.shelves || [])].reverse().map((s) => `<div class="shelf"><div class="shelf-head"><span>Raf ${s.shelf_no} · ${s.allowed_storage_type}</span><span>${Math.round(shelfUsedWidth(s))}/${s.shelf_width_cm}cm</span></div><div class="products">${(s.products || []).map(productCardHtml).join("") || "<em>Boş raf</em>"}</div></div>`).join("")}</div>
    <div class="page"><h1>Ürün Yerleşim Listesi</h1><div class="sub">Saha personeli için kontrol listesi</div><table class="list"><thead><tr><th>Raf</th><th>Sıra</th><th>Ürün</th><th>SKU</th><th>Marka</th><th>Facing</th><th>Ölçü</th></tr></thead><tbody>${[...(module.shelves || [])].reverse().flatMap((s) => (s.products || []).map((p, i) => `<tr><td>Raf ${s.shelf_no}</td><td>${i + 1}</td><td>${p.product_name || ""}</td><td>${p.sku || ""}</td><td>${p.brand || ""}</td><td><span class="badge">${faceCount(p)}</span></td><td>${p.width_cm || "?"}×${p.height_cm || "?"}×${p.depth_cm || "?"}</td></tr>`)).join("")}</tbody></table></div>
    <script>window.onload=()=>setTimeout(()=>window.print(),300)</script>
  </body></html>`;
  const win = window.open("", "_blank", "width=1200,height=900");
  win.document.write(html); win.document.close();
}

export function printShelf(selected) {
  const s = selected.shelf;
  const fakeAisle = { aisle_id: selected.aisle_id };
  const fakeModule = { module_id: selected.module_id, module_width_cm: s.shelf_width_cm, shelves: [s] };
  printModule(fakeAisle, fakeModule);
}
