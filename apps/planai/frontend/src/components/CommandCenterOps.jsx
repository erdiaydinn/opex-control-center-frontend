export default function CommandCenterOps({
  store,
  objects = [],
  products = [],
  unplacedProducts = [],
  tasks = [],
  readiness,
  storeDna,
  setActive,
  onGenerate,
}) {
  const placed = products.length;
  const unplaced = unplacedProducts.length;
  const total = placed + unplaced;

  const usableObjects = (objects || []).filter((o) => Number(o.modules || 0) > 0 || Number(o.shelves || 0) > 0);

  const avgUtil = usableObjects.length
    ? Math.round(usableObjects.reduce((s, o) => s + Number(o.utilization || 0), 0) / usableObjects.length)
    : 0;

  const isCold = (o) => {
    const h = [o.id, o.label, o.name, o.zone, o.type, o.fixture_type, o.storage, o.storage_type]
      .filter(Boolean)
      .join(" ")
      .toUpperCase();

    return h.includes("CHILLED") || h.includes("+4") || h.includes("SOĞUK") || h.includes("SOGUK") || h.includes("MARTEK");
  };

  const isFrozen = (o) => {
    const h = [o.id, o.label, o.name, o.zone, o.type, o.fixture_type, o.storage, o.storage_type]
      .filter(Boolean)
      .join(" ")
      .toUpperCase();

    return h.includes("FROZEN") || h.includes("-18") || h.includes("DONUK") || h.includes("ALGIDA");
  };

  const avgFor = (fn) => {
    const list = usableObjects.filter(fn);
    return list.length ? Math.round(list.reduce((s, o) => s + Number(o.utilization || 0), 0) / list.length) : 0;
  };

  const locationOf = (p) =>
    p.location_raw ||
    p.current_location ||
    p.Location ||
    p.original_location ||
    "";

  const newLocationOf = (p) =>
    [
      p.aisle || p.aisle_id,
      p.module || p.module_id,
      p.shelf || p.shelf_no,
    ].filter(Boolean).join("-");

  const normalizeLoc = (v) => String(v || "").trim().toUpperCase().replace(/\s+/g, "");

  const deltaCount = products.filter((p) => {
    const oldLoc = normalizeLoc(locationOf(p));
    const newLoc = normalizeLoc(newLocationOf(p));
    return oldLoc && newLoc && oldLoc !== newLoc;
  }).length;

  const openTasks = tasks.filter((t) => String(t.status || "").toLowerCase() !== "done").length;

  const score = Math.max(
    0,
    Math.min(
      100,
      Math.round(
        40 +
        (total ? (placed / Math.max(total, 1)) * 25 : 0) +
        Math.min(avgUtil, 100) * 0.2 -
        Math.min(unplaced / 100, 20)
      )
    )
  );

  const kpis = [
    { label: "Planogram Skoru", value: `${score}/100`, note: "Gerçek ürün + fixture state" },
    { label: "Alan Kullanımı", value: `${avgUtil}%`, note: `${usableObjects.length} fixture/koridor` },
    { label: "Yerleşen SKU", value: placed.toLocaleString("tr-TR"), note: "Aktif plan" },
    { label: "Atanamayan SKU", value: unplaced.toLocaleString("tr-TR"), note: "Aksiyon bekliyor" },
    { label: "+4 Kapasite", value: `${avgFor(isCold)}%`, note: "Chilled / Martek / yatay dolap" },
    { label: "-18 Kapasite", value: `${avgFor(isFrozen)}%`, note: "Donuk oda / Algida" },
    { label: "Delta Aksiyonu", value: deltaCount.toLocaleString("tr-TR"), note: "ABC lokasyonuna göre" },
    { label: "Açık Görev", value: openTasks.toLocaleString("tr-TR"), note: "Saha uygulama" },
  ];

  const readinessLabel = storeDna || readiness ? "Hazır / doğrulanıyor" : "Kurulum eksik";

  return (
    <main className="page">
      <section className="card pad" style={{ marginBottom: 18 }}>
        <div className="section-eyebrow">PLONAGRAM OS KOMUTA MERKEZİ</div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 18, alignItems: "center", flexWrap: "wrap" }}>
          <div>
            <h1 style={{ margin: "8px 0 6px" }}>{store || "Depo"} operasyon özeti</h1>
            <p className="muted" style={{ maxWidth: 760 }}>
              Bu ekran artık statik görsel değil; aktif SKU, fixture kullanımı, atanamayan ürün ve ABC bazlı delta aksiyonlarından beslenir.
            </p>
          </div>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button className="btn primary" onClick={onGenerate}>Optimum plan üret</button>
            <button className="btn ghost" onClick={() => setActive("planogram")}>Planogramı aç</button>
            <button className="btn ghost" onClick={() => setActive("delta")}>Delta aksiyonları</button>
          </div>
        </div>
      </section>

      <section className="grid cols-4" style={{ marginBottom: 18 }}>
        {kpis.map((kpi) => (
          <div key={kpi.label} className="card pad">
            <div className="muted" style={{ fontWeight: 800, fontSize: 12 }}>{kpi.label}</div>
            <div style={{ fontSize: 28, fontWeight: 900, marginTop: 8 }}>{kpi.value}</div>
            <div className="muted" style={{ marginTop: 6 }}>{kpi.note}</div>
          </div>
        ))}
      </section>

      <section className="grid cols-2">
        <div className="card pad">
          <div className="section-eyebrow">PLANOGRAM HAZIRLIK</div>
          <h3>{readinessLabel}</h3>
          <p className="muted">
            Store DNA, ABC, catalog ve layout tamamlanmadan engine süs veriyle değil gerçek depo verisiyle çalışmalı.
          </p>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 14 }}>
            <button className="btn ghost" onClick={() => setActive("storeDna")}>Depo kurulumuna git</button>
            <button className="btn ghost" onClick={() => setActive("fixture")}>Fixture kontrolü</button>
          </div>
        </div>

        <div className="card pad">
          <div className="section-eyebrow">COUNCIL INTELLIGENCE</div>
          <h3>Gerçek aksiyonlar</h3>
          <div className="list">
            <div className="list-row">
              <b>Delta Planogram</b>
              <span className="muted">{deltaCount} ürünün ABC lokasyonu yeni öneriyle farklı.</span>
            </div>
            <div className="list-row">
              <b>Atanamayan SKU</b>
              <span className="muted">{unplaced} ürün için sebep/aksiyon kontrolü gerekiyor.</span>
            </div>
            <div className="list-row">
              <b>Soğuk / donuk kapasite</b>
              <span className="muted">+4: {avgFor(isCold)}% · -18: {avgFor(isFrozen)}%</span>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
