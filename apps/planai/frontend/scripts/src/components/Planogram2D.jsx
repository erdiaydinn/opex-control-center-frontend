import React, { useMemo, useState } from "react";
import { computeMetrics } from "../utils/planogram";

function ProductThumb({ p, onClick }) {
  return (
    <button className="p2-product" onClick={onClick} title={p.product_name || p.sku}>
      {p.image_url ? <img src={p.image_url} alt="" /> : <span>📦</span>}
      <small>Ön {p.facing_count || p.facing || 1}</small>
    </button>
  );
}

function ShelfCard({ aisle, module, shelf, onShelfOpen, onShelfSize, onRule, onDeleteShelf }) {
  const util = Math.round(((shelf.used_width_cm || 0) / Math.max(shelf.shelf_width_cm || 100, 1)) * 100);
  const selected = { aisle_id: aisle.aisle_id, module_id: module.module_id, shelf_no: shelf.shelf_no, shelf };
  return (
    <div className="p2-shelf">
      <div className="p2-shelf-head">
        <b>Raf {shelf.shelf_no}</b>
        <span>{shelf.allowed_storage_type || "AMBIENT"} · {util}% · {Math.round(shelf.used_width_cm || 0)}/{shelf.shelf_width_cm || 100}cm</span>
      </div>
      <div className="p2-shelf-actions">
        <button onClick={() => onShelfOpen?.(selected)}>Raf düzenle</button>
        <button onClick={() => onShelfSize?.(aisle.aisle_id, module.module_id, shelf.shelf_no)}>Raf ölçü</button>
        <button onClick={() => onRule?.("shelf", aisle.aisle_id, module.module_id, shelf.shelf_no)}>Raf kuralı</button>
        <button className="danger" onClick={() => onDeleteShelf?.(aisle.aisle_id, module.module_id, shelf.shelf_no)}>Raf sil</button>
      </div>
      <div className="p2-products" onDoubleClick={() => onShelfOpen?.(selected)}>
        {(shelf.products || []).map((p, i) => <ProductThumb key={`${p.sku}-${i}`} p={p} onClick={() => onShelfOpen?.(selected)} />)}
        {!(shelf.products || []).length && <button className="p2-empty" onClick={() => onShelfOpen?.(selected)}>Boş raf · ürün ekle</button>}
      </div>
    </div>
  );
}

function ModuleCard({ aisle, module, onShelfOpen, onAddShelf, onModuleSize, onShelfSize, onRule, onPrintModule, onDeleteModule, onDeleteShelf }) {
  const shelves = module.shelves || [];
  const used = shelves.reduce((s, x) => s + Number(x.used_width_cm || 0), 0);
  const cap = shelves.reduce((s, x) => s + Number(x.shelf_width_cm || 100), 0);
  const util = Math.round((used / Math.max(cap, 1)) * 100);
  return (
    <article className="p2-module">
      <div className="p2-module-head">
        <div><h3>{aisle.aisle_id} · {module.side || ""}-Modül {module.module_id}</h3><small>{module.module_width_cm || 100}×{module.module_depth_cm || 50}×{module.module_height_cm || 210}cm · {module.module_type}</small></div>
        <b>{util}%</b>
      </div>
      <div className="p2-module-actions">
        <button onClick={() => onAddShelf?.(aisle.aisle_id, module.module_id)}>+ Raf</button>
        <button onClick={() => onModuleSize?.(aisle.aisle_id, module.module_id)}>Modül ölçü</button>
        <button onClick={() => onRule?.("module", aisle.aisle_id, module.module_id)}>Modül kuralı</button>
        <button onClick={() => onPrintModule?.(aisle, module)}>Yazdır</button>
        <button className="danger" onClick={() => onDeleteModule?.(aisle.aisle_id, module.module_id)}>Modül sil</button>
      </div>
      <div className="p2-shelves">
        {shelves.map((s) => <ShelfCard key={s.shelf_no} aisle={aisle} module={module} shelf={s} onShelfOpen={onShelfOpen} onShelfSize={onShelfSize} onRule={onRule} onDeleteShelf={onDeleteShelf} />)}
      </div>
    </article>
  );
}

export default function Planogram2D({ plan, onShelfOpen, onAddModule, onAddShelf, onModuleSize, onShelfSize, onRule, onPrintModule, onAddAisle, onDeleteAisle, onDeleteModule, onDeleteShelf }) {
  const [selectedAisle, setSelectedAisle] = useState("ALL");
  const metrics = useMemo(() => computeMetrics(plan), [plan]);
  const aisles = plan?.aisles || [];
  const visible = selectedAisle === "ALL" ? aisles : aisles.filter((a) => String(a.aisle_id) === selectedAisle);
  return (
    <section className="p2-shell">
      <div className="p2-toolbar">
        <div><h2>Operasyonel 2D Studio</h2><p>Koridor/modül seç, toplu kural ata, raf düzenle, modül/raf sil.</p></div>
        <div className="p2-toolbar-actions">
          <select value={selectedAisle} onChange={(e) => setSelectedAisle(e.target.value)}><option value="ALL">Tüm koridorlar</option>{aisles.map((a) => <option key={a.aisle_id} value={a.aisle_id}>Koridor {a.aisle_id}</option>)}</select>
          <button onClick={onAddAisle}>+ Koridor</button>
          {selectedAisle !== "ALL" && <button onClick={() => onAddModule?.(selectedAisle)}>+ Seçili koridora modül</button>}
          {selectedAisle !== "ALL" && <button className="danger" onClick={() => onDeleteAisle?.(selectedAisle)}>Koridor sil</button>}
        </div>
      </div>
      <div className="p2-stats"><span>{aisles.length} koridor</span><span>{metrics.total_shelves} raf</span><span>{metrics.total_products} ürün yerleşti</span><span>{metrics.width_utilization_pct}% doluluk</span></div>
      {visible.map((aisle) => (
        <div className="p2-aisle" key={aisle.aisle_id}>
          <div className="p2-aisle-head"><div><h2>Koridor {aisle.aisle_id}</h2><p>{(aisle.modules || []).length} modül</p></div><button onClick={() => onAddModule?.(aisle.aisle_id)}>+ Modül ekle</button></div>
          <div className="p2-module-grid">{(aisle.modules || []).map((m) => <ModuleCard key={m.module_id} aisle={aisle} module={m} onShelfOpen={onShelfOpen} onAddShelf={onAddShelf} onModuleSize={onModuleSize} onShelfSize={onShelfSize} onRule={onRule} onPrintModule={onPrintModule} onDeleteModule={onDeleteModule} onDeleteShelf={onDeleteShelf} />)}</div>
        </div>
      ))}
    </section>
  );
}
