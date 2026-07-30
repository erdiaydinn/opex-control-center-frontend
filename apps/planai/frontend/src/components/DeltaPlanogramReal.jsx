function skuOf(p = {}) {
  return String(p.sku || p.SKU || p.barcode || p.Barcodes || "").trim();
}

function oldLocationOf(p = {}) {
  return (
    p.location_raw ||
    p.current_location ||
    p.currentLocation ||
    p.Location ||
    p.original_location ||
    p.old_location ||
    ""
  );
}

function secondaryLocationOf(p = {}) {
  return p.secondary_location || p["Secondary Location"] || "";
}

function newLocationOf(p = {}) {
  const aisle = p.aisle || p.aisle_id || "";
  const moduleNo = p.module || p.module_id || "";
  const shelfNo = p.shelf || p.shelf_no || "";

  return [aisle, moduleNo ? `M${moduleNo}` : "", shelfNo ? `R${shelfNo}` : ""]
    .filter(Boolean)
    .join("-");
}

function normalizeLocation(v = "") {
  return String(v || "")
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "")
    .replace(/_/g, "-");
}

function buildDeltaRows(products = []) {
  return (products || []).map((p) => {
    const oldLoc = oldLocationOf(p);
    const secondaryLoc = secondaryLocationOf(p);
    const newLoc = newLocationOf(p);
    const oldNorm = normalizeLocation(oldLoc);
    const newNorm = normalizeLocation(newLoc);

    let action = "KONTROL";
    if (!oldNorm && newNorm) action = "YENİ YERLEŞİM";
    else if (oldNorm && newNorm && oldNorm === newNorm) action = "YERİNDE KAL";
    else if (oldNorm && newNorm && oldNorm !== newNorm) action = "TAŞI";
    else action = "LOKASYON EKSİK";

    const facing = p.facing || p.facing_count || "";
    const depth = p.depth || "";

    return {
      action,
      sku: skuOf(p),
      name: p.name || p.product_name || p.productName || p["Product Name"] || "-",
      brand: p.brand || p.brand_name || "-",
      storage: p.storage || p.storage_type || p.storage_class || "-",
      family: p.food_family || "-",
      oldLoc: oldLoc || "-",
      secondaryLoc: secondaryLoc || "-",
      newLoc: newLoc || "-",
      facing,
      depth,
      reason: p.placement_reason || p.reason || "Yeni planogram önerisi",
    };
  });
}

function downloadCsv(rows = []) {
  const headers = [
    "Aksiyon",
    "SKU",
    "Ürün",
    "Marka",
    "Storage",
    "Food Family",
    "Eski ABC Lokasyon",
    "Secondary Location",
    "Yeni Lokasyon",
    "Facing",
    "Depth",
    "Sebep",
  ];

  const csv = [
    headers.join(","),
    ...rows.map((r) => [
      r.action,
      r.sku,
      r.name,
      r.brand,
      r.storage,
      r.family,
      r.oldLoc,
      r.secondaryLoc,
      r.newLoc,
      r.facing,
      r.depth,
      r.reason,
    ].map((v) => `"${String(v ?? "").replaceAll('"', '""')}"`).join(",")),
  ].join("\n");

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "delta_planogram_actions.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function DeltaPlanogramReal({ products = [], unplacedProducts = [], setActive }) {
  const rows = buildDeltaRows(products);
  const actionRows = rows.filter((r) => r.action !== "YERİNDE KAL");
  const moveRows = rows.filter((r) => r.action === "TAŞI");
  const newRows = rows.filter((r) => r.action === "YENİ YERLEŞİM");

  return (
    <main className="page">
      <section className="card pad" style={{ marginBottom: 18 }}>
        <div className="section-eyebrow">DELTA PLANOGRAM</div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
          <div>
            <h1 style={{ margin: "8px 0 6px" }}>ABC lokasyonundan yeni plana geçiş listesi</h1>
            <p className="muted">
              Eski konum ABC dosyasındaki Location / Secondary Location alanından, yeni konum engine’in önerdiği aisle-module-shelf bilgisinden gelir.
            </p>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button className="btn primary" onClick={() => downloadCsv(actionRows)}>CSV indir</button>
            <button className="btn ghost" onClick={() => setActive("planogram")}>Planograma dön</button>
          </div>
        </div>
      </section>

      <section className="grid cols-4" style={{ marginBottom: 18 }}>
        <div className="card pad">
          <div className="muted">Toplam yerleşen</div>
          <div style={{ fontSize: 28, fontWeight: 900 }}>{products.length.toLocaleString("tr-TR")}</div>
        </div>
        <div className="card pad">
          <div className="muted">Taşınacak</div>
          <div style={{ fontSize: 28, fontWeight: 900 }}>{moveRows.length.toLocaleString("tr-TR")}</div>
        </div>
        <div className="card pad">
          <div className="muted">Yeni yerleşim</div>
          <div style={{ fontSize: 28, fontWeight: 900 }}>{newRows.length.toLocaleString("tr-TR")}</div>
        </div>
        <div className="card pad">
          <div className="muted">Atanamayan</div>
          <div style={{ fontSize: 28, fontWeight: 900 }}>{unplacedProducts.length.toLocaleString("tr-TR")}</div>
        </div>
      </section>

      <section className="card pad">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <h3 style={{ margin: 0 }}>Saha aksiyon listesi</h3>
          <span className="muted">{actionRows.length.toLocaleString("tr-TR")} aksiyon</span>
        </div>

        <div style={{ overflowX: "auto", marginTop: 14 }}>
          <table className="data-table" style={{ minWidth: 1180 }}>
            <thead>
              <tr>
                <th>Aksiyon</th>
                <th>SKU</th>
                <th>Ürün</th>
                <th>Storage</th>
                <th>Food Family</th>
                <th>Eski ABC Lokasyon</th>
                <th>Secondary</th>
                <th>Yeni Lokasyon</th>
                <th>Facing</th>
                <th>Depth</th>
                <th>Neden</th>
              </tr>
            </thead>
            <tbody>
              {actionRows.slice(0, 800).map((r, idx) => (
                <tr key={`${r.sku}-${idx}`}>
                  <td><b>{r.action}</b></td>
                  <td>{r.sku}</td>
                  <td>{r.name}</td>
                  <td>{r.storage}</td>
                  <td>{r.family}</td>
                  <td>{r.oldLoc}</td>
                  <td>{r.secondaryLoc}</td>
                  <td>{r.newLoc}</td>
                  <td>{r.facing}</td>
                  <td>{r.depth}</td>
                  <td>{r.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!actionRows.length && (
          <p className="muted" style={{ marginTop: 14 }}>
            Delta aksiyonu bulunamadı. Bu genelde ürünlerde ABC Location alanı taşınmıyorsa veya yeni plan henüz üretilmediyse olur.
          </p>
        )}
      </section>
    </main>
  );
}
