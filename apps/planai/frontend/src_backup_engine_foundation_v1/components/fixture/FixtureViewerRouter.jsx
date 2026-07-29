import React from "react";
import "./FixtureViewer.css";

function n(v, d = 0) {
  const x = Number(v);
  return Number.isFinite(x) ? x : d;
}

function txt(v) {
  return String(v ?? "").trim();
}

function cx(...v) {
  return v.filter(Boolean).join(" ");
}

function name(p) {
  return txt(p.product_name || p.name || p.sku || "Ürün");
}

function brand(p) {
  return txt(p.brand || p.brand_name || "UNKNOWN").split(",")[0];
}

function getType({ fixtureType, shelf, module, products }) {
  const raw = [
    fixtureType,
    shelf?.fixture_viewer_type,
    shelf?.fixture_need,
    shelf?.recommended_zone_type,
    shelf?.allowed_storage_type,
    module?.fixture_viewer_type,
    module?.fixture_type,
    module?.module_type,
    ...products.map((p) => [
      p.fixture_viewer_type,
      p.fixture_need,
      p.placed_fixture_type,
      p.recommended_zone_type,
      p.storage_type,
      p.category_l1,
      p.category_l2,
      p.brand,
      p.product_name,
    ].join(" ")),
  ].join(" ").toLowerCase();

  if (raw.includes("freezer") || raw.includes("frozen") || raw.includes("-18") || raw.includes("algida") || raw.includes("superfresh")) return "freezer_door_view";
  if (raw.includes("milagro")) return "milagro_chilled_produce_view";
  if (raw.includes("chilled") || raw.includes("fridge") || raw.includes("+4") || raw.includes("cooler")) return "chilled_door_view";
  if (raw.includes("produce") || raw.includes("meyve") || raw.includes("sebze") || raw.includes("crate")) return "produce_crate_view";
  if (raw.includes("bulk") || raw.includes("pallet") || raw.includes("damacana") || raw.includes("water_rack")) return "bulk_floor_view";
  if (raw.includes("bakery") || raw.includes("fırın") || raw.includes("firin") || raw.includes("la lorraine")) return "bakery_station_view";
  return "regular_shelf_view";
}

function splitRows(products, maxRows = 6) {
  const sorted = [...products].sort((a, b) => n(a.position_order, 999) - n(b.position_order, 999));
  const rows = Array.from({ length: Math.min(maxRows, Math.max(1, Math.ceil(sorted.length / 8))) }, () => []);
  sorted.forEach((p, i) => rows[i % rows.length].push(p));
  return rows;
}

function Face({ p, cold = false }) {
  const img = txt(p.image_url);
  const facing = n(p.facing_count ?? p.facing, 1);
  const depth = n(p.depth_units, 0);
  return (
    <div className={cx("fx-face", cold && "cold")}>
      <div className="fx-face-img">
        {img ? <img src={img} alt="" /> : <span>{brand(p).slice(0, 2).toUpperCase()}</span>}
      </div>
      <b title={name(p)}>{name(p)}</b>
      <small>{brand(p)}</small>
      <em>{facing}F{depth ? ` · D${depth}` : ""}</em>
    </div>
  );
}

function Header({ type, title, note, temp, products }) {
  const facings = products.reduce((a, p) => a + n(p.facing_count ?? p.facing, 1), 0);
  const stockBehind = products.reduce((a, p) => {
    const total = n(p.total_capacity_units, 0);
    const facing = n(p.facing_count ?? p.facing, 1);
    return a + Math.max(0, total - facing);
  }, 0);
  return (
    <div className="fx-head">
      <div>
        <span>{type}</span>
        <h3>{title}</h3>
        <p>{note}</p>
      </div>
      <div className="fx-metrics">
        {temp && <strong>{temp}</strong>}
        <strong>{products.length} SKU</strong>
        <strong>{facings} facing</strong>
        {stockBehind > 0 && <strong>{stockBehind} stock-behind</strong>}
      </div>
    </div>
  );
}

function Freezer({ products, module }) {
  const rows = splitRows(products, 5);
  return (
    <div className="fx-view fx-freezer">
      <Header type="FREEZER_DOOR" title={module?.door_no ? `Freezer Door ${module.door_no}` : "Freezer Cabinet"} temp="-18°C" products={products} note="Kapak açılmış freezer gerçekliği. Standart raf gibi çizilmez." />
      <div className="fx-freezer-box">
        <div className="fx-open-door"><i /></div>
        <div className="fx-freezer-inner">
          {rows.map((row, i) => (
            <div className="fx-cold-row" key={i}>
              {row.map((p) => <Face key={p.sku} p={p} cold />)}
              <div className="fx-rail">Shelf {i + 1} · depth/backstock</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Chilled({ products, module }) {
  const rows = splitRows(products, 5);
  return (
    <div className="fx-view fx-chilled">
      <Header type="CHILLED_DOOR" title={module?.door_no ? `Chilled Door ${module.door_no}` : "Chilled Cabinet"} temp="+4°C" products={products} note="+4 dolap modülü. Süt, yoğurt, peynir ve hassas ürün gerçekliği." />
      <div className="fx-chilled-box">
        {rows.map((row, i) => <div className="fx-cold-row" key={i}>{row.map((p) => <Face key={p.sku} p={p} cold />)}</div>)}
      </div>
    </div>
  );
}

function Produce({ products, milagro = false }) {
  return (
    <div className={cx("fx-view fx-produce", milagro && "milagro")}>
      <Header type={milagro ? "MILAGRO_CHILLED_PRODUCE" : "PRODUCE_CRATE"} title={milagro ? "Milagro / Chilled Produce" : "Produce Crate Zone"} temp={milagro ? "+4°C" : null} products={products} note={milagro ? "Maydanoz, roka, dereotu gibi ürünler +4 gerçekliğinde." : "Mandalina, patates, soğan gibi ürünler kasa/krat gerçekliğinde."} />
      <div className="fx-crates">
        {products.map((p) => <div className="fx-crate" key={p.sku}><Face p={p} /><small>crate/bin</small></div>)}
      </div>
    </div>
  );
}

function Bulk({ products }) {
  return (
    <div className="fx-view fx-bulk">
      <Header type="BULK_FLOOR" title="Bulk Floor / Pallet Zone" products={products} note="Su koli, kağıt ürünleri ve hacimli ürünler zemin/palet gerçekliğinde." />
      <div className="fx-pallets">
        {products.map((p) => <div className="fx-pallet" key={p.sku}><Face p={p} /><i /><i /><i /></div>)}
      </div>
    </div>
  );
}

function Bakery({ products }) {
  return (
    <div className="fx-view fx-bakery">
      <Header type="BAKERY_STATION" title="Bakery Station" products={products} note="Fırın/La Lorraine ürünleri standart raf değil, istasyon gerçekliğiyle." />
      <div className="fx-bakery-counter">{products.map((p) => <Face key={p.sku} p={p} />)}</div>
    </div>
  );
}

function Regular({ products }) {
  const rows = splitRows(products, 4);
  return (
    <div className="fx-view fx-regular">
      <Header type="REGULAR_SHELF" title="Regular Shelf" products={products} note="Kuru gıda, non-food ve standart raf görünümü." />
      <div className="fx-rack">
        {rows.map((row, i) => <div className="fx-rack-row" key={i}>{row.map((p) => <Face key={p.sku} p={p} />)}</div>)}
      </div>
    </div>
  );
}

export default function FixtureViewerRouter({ fixtureType, shelf, module, aisle, products = [] }) {
  const finalProducts = Array.isArray(products) && products.length ? products : (shelf?.products || []);
  const type = getType({ fixtureType, shelf, module, aisle, products: finalProducts });

  if (type === "freezer_door_view") return <Freezer products={finalProducts} module={module} />;
  if (type === "chilled_door_view") return <Chilled products={finalProducts} module={module} />;
  if (type === "milagro_chilled_produce_view") return <Produce products={finalProducts} milagro />;
  if (type === "produce_crate_view") return <Produce products={finalProducts} />;
  if (type === "bulk_floor_view") return <Bulk products={finalProducts} />;
  if (type === "bakery_station_view") return <Bakery products={finalProducts} />;
  return <Regular products={finalProducts} />;
}
