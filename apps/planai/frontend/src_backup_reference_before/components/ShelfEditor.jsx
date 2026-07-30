import React, { useMemo, useState } from "react";
import "./ShelfEditor.css";
import FixtureViewerRouter from "./fixture/FixtureViewerRouter";
import { faceCount, normalizeProduct, productWidth, shelfUtil } from "../utils/planogram";

function productMatches(p, q) {
  const s = `${p.product_name || ""} ${p.sku || ""} ${p.brand || ""} ${p.category_l1 || ""} ${p.category_l2 || ""}`.toLowerCase();
  return s.includes(String(q || "").toLowerCase());
}

function detectShelfFixtureType(shelf, selected) {
  const products = shelf?.products || [];
  const raw = [
    selected?.fixture_viewer_type,
    selected?.fixture_need,
    selected?.placed_fixture_type,
    selected?.module?.fixture_viewer_type,
    selected?.module?.fixture_type,
    selected?.module?.module_type,
    shelf?.fixture_viewer_type,
    shelf?.fixture_need,
    shelf?.recommended_zone_type,
    shelf?.allowed_storage_type,
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

  if (raw.includes("freezer") || raw.includes("frozen") || raw.includes("-18") || raw.includes("algida") || raw.includes("superfresh")) {
    return "freezer_door_view";
  }
  if (raw.includes("milagro")) return "milagro_chilled_produce_view";
  if (raw.includes("chilled") || raw.includes("fridge") || raw.includes("+4") || raw.includes("cooler")) {
    return "chilled_door_view";
  }
  if (raw.includes("produce") || raw.includes("meyve") || raw.includes("sebze") || raw.includes("crate")) {
    return "produce_crate_view";
  }
  if (raw.includes("bulk") || raw.includes("pallet") || raw.includes("damacana") || raw.includes("water_rack")) {
    return "bulk_floor_view";
  }
  if (raw.includes("bakery") || raw.includes("fırın") || raw.includes("firin") || raw.includes("la lorraine")) {
    return "bakery_station_view";
  }
  return "regular_shelf_view";
}

export default function ShelfEditor({
  selected,
  plan,
  products = [],
  onClose,
  onFacing,
  onRemove,
  onAddProduct,
  onSortShelf,
  onMoveProduct,
  onPrintShelf,
  onOpenShelfSize,
  onRotateProduct,
  onSetProductOrientation,
}) {
  const [selectedSku, setSelectedSku] = useState(null);
  const [search, setSearch] = useState("");
  const [showAdd, setShowAdd] = useState(false);

  const shelf = selected?.shelf;
  const target = selected;
  const selectedProduct = (shelf?.products || []).find((p) => String(p.sku) === String(selectedSku));
  const fixtureType = detectShelfFixtureType(shelf, selected);

  const available = useMemo(() => {
    const placed = new Set();
    for (const a of plan?.aisles || []) {
      for (const m of a.modules || []) {
        for (const s of m.shelves || []) {
          for (const p of s.products || []) placed.add(String(p.sku));
        }
      }
    }
    return (products || [])
      .map(normalizeProduct)
      .filter((p) => !placed.has(String(p.sku)))
      .filter((p) => !search || productMatches(p, search))
      .slice(0, 80);
  }, [products, plan, search]);

  if (!selected || !shelf) return null;

  return (
    <div className="se-backdrop">
      <div className="se-modal se-modal-fixture">
        <header className="se-head">
          <div>
            <div className="se-kicker">FIXTURE WORKSPACE</div>
            <h2>{selected.aisle_id}00-{String(selected.module_id).padStart(2, "0")}-D{String(shelf.shelf_no).padStart(2, "0")}</h2>
            <p>
              {shelf.allowed_storage_type || "AMBIENT"} · {shelf.shelf_width_cm}×{shelf.shelf_depth_cm}×{shelf.shelf_height_cm} cm ·
              Doluluk %{shelfUtil(shelf)} · {fixtureType}
            </p>
          </div>
          <button onClick={onClose}>Kapat</button>
        </header>

        <section className="se-fixture-stage">
          <FixtureViewerRouter
            fixtureType={fixtureType}
            shelf={shelf}
            module={selected?.module}
            aisle={selected?.aisle}
            products={shelf.products || []}
          />
        </section>

        <section className="se-selection-strip">
          {(shelf.products || []).map((p) => (
            <button
              key={p.sku}
              className={`se-product-chip ${String(selectedSku) === String(p.sku) ? "active" : ""}`}
              onClick={() => setSelectedSku(p.sku)}
              title={`${p.product_name} · ${p.sku}`}
            >
              <span className="se-chip-img">
                {p.image_url ? <img src={p.image_url} alt="" /> : "📦"}
              </span>
              <span className="se-chip-text">
                <b>{p.product_name}</b>
                <small>{p.brand} · {faceCount(p)} ön · {p.orientation || "horizontal"} · {Math.round(productWidth(p))}cm</small>
              </span>
            </button>
          ))}
          {!(shelf.products || []).length && <div className="se-empty">Bu fixture boş. Ürün ekleyebilirsin.</div>}
        </section>

        <section className="se-actions">
          <button onClick={() => onSortShelf?.(target, "DARKSTORE_AI")}>Darkstore AI diz</button>
          <button onClick={() => onSortShelf?.(target, "SALES")}>ABC/Satış diz</button>
          <button onClick={() => onSortShelf?.(target, "PICKING")}>Picking diz</button>
          <button onClick={() => onSortShelf?.(target, "CATEGORY")}>Kategori diz</button>
          <button onClick={() => onSortShelf?.(target, "BRAND")}>Marka diz</button>
          <button className="primary" onClick={() => setShowAdd((v) => !v)}>Boş ürün ata</button>
          <button onClick={() => onPrintShelf?.(target)}>Yazdır</button>
          <button onClick={() => onOpenShelfSize?.(target)}>Raf/Fixture ölçüsü</button>
        </section>

        {selectedProduct && (
          <section className="se-product-panel">
            <div>
              <b>{selectedProduct.product_name}</b>
              <span>{selectedProduct.sku} · {selectedProduct.brand}</span>
            </div>
            <button onClick={() => onFacing?.(selectedProduct.sku, 1)}>Ön yüz artır</button>
            <button onClick={() => onFacing?.(selectedProduct.sku, -1)}>Ön yüz azalt</button>
            <button onClick={() => onMoveProduct?.(target, selectedProduct.sku, "left")}>Sola taşı</button>
            <button onClick={() => onMoveProduct?.(target, selectedProduct.sku, "right")}>Sağa taşı</button>
            <button onClick={() => onRotateProduct?.(target, selectedProduct.sku)}>Yön değiştir</button>
            <button onClick={() => onSetProductOrientation?.(target, selectedProduct.sku, "horizontal")}>Yatay</button>
            <button onClick={() => onSetProductOrientation?.(target, selectedProduct.sku, "vertical")}>Dikey</button>
            <button className="danger" onClick={() => onRemove?.(selectedProduct.sku)}>Fixture’dan kaldır</button>
          </section>
        )}

        {showAdd && (
          <section className="se-add">
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="SKU, marka, ürün, kategori ara..." />
            <div className="se-add-list">
              {available.map((p) => (
                <button key={p.sku} onClick={() => onAddProduct?.(target, p)}>
                  {p.image_url ? <img src={p.image_url} alt="" /> : <span>📦</span>}
                  <b>{p.product_name}</b>
                  <small>{p.brand} · {p.storage_type}</small>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
