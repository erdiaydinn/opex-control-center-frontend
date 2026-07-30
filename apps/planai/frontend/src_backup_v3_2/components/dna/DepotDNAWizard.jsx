import React, { useState } from "react";
import "./DepotDNAWizard.css";

export default function DepotDNAWizard({ store, initialDNA, onSave }) {
  const [dna, setDna] = useState(initialDNA || {});
  const physical = dna.physical || {};
  const operations = dna.operations || {};
  const fixture = dna.fixture_defaults || {};

  function patch(section, key, value) {
    setDna((prev) => ({ ...prev, [section]: { ...(prev[section] || {}), [key]: value } }));
  }

  return (
    <div className="dna-card">
      <div className="dna-head">
        <span>DEPOT DNA</span>
        <h2>{store?.store_name || "Depo Profili"}</h2>
        <p>Bu bilgiler AI yerleşim, rota, kapasite ve benchmark motorunun depo bazlı karar almasını sağlar.</p>
      </div>

      <div className="dna-grid">
        <label>Kat sayısı<input type="number" value={physical.floors ?? 1} onChange={(e) => patch("physical", "floors", Number(e.target.value))} /></label>
        <label>Alt kat var mı?
          <select value={physical.has_basement ? "yes" : "no"} onChange={(e) => patch("physical", "has_basement", e.target.value === "yes")}>
            <option value="no">Hayır</option><option value="yes">Evet</option>
          </select>
        </label>
        <label>Toplam m²<input type="number" value={physical.total_area_m2 ?? ""} onChange={(e) => patch("physical", "total_area_m2", Number(e.target.value))} /></label>
        <label>Ortalama koridor cm<input type="number" value={physical.avg_aisle_width_cm ?? 120} onChange={(e) => patch("physical", "avg_aisle_width_cm", Number(e.target.value))} /></label>

        <label>Günlük sipariş<input type="number" value={operations.avg_daily_orders ?? ""} onChange={(e) => patch("operations", "avg_daily_orders", Number(e.target.value))} /></label>
        <label>Peak picker<input type="number" value={operations.peak_picker_count ?? ""} onChange={(e) => patch("operations", "peak_picker_count", Number(e.target.value))} /></label>
        <label>Mal kabul saatleri<input value={operations.receiving_hours ?? ""} onChange={(e) => patch("operations", "receiving_hours", e.target.value)} placeholder="Örn. 08:00-16:00" /></label>
        <label>16 sonrası mal kabul istenir mi?
          <select value={operations.receiving_after_16_preferred ? "yes" : "no"} onChange={(e) => patch("operations", "receiving_after_16_preferred", e.target.value === "yes")}>
            <option value="no">Hayır, istemeyiz</option><option value="yes">Evet, olabilir</option>
          </select>
        </label>

        <label>Ana raf eni cm<input type="number" value={fixture.main_rack_width_cm ?? 93} onChange={(e) => patch("fixture_defaults", "main_rack_width_cm", Number(e.target.value))} /></label>
        <label>Ana raf derinlik cm<input type="number" value={fixture.main_rack_depth_cm ?? 43} onChange={(e) => patch("fixture_defaults", "main_rack_depth_cm", Number(e.target.value))} /></label>
        <label>Ana raf yükseklik cm<input type="number" value={fixture.main_rack_height_cm ?? 200} onChange={(e) => patch("fixture_defaults", "main_rack_height_cm", Number(e.target.value))} /></label>
        <label>Raf kat sayısı<input type="number" value={fixture.main_rack_levels ?? 6} onChange={(e) => patch("fixture_defaults", "main_rack_levels", Number(e.target.value))} /></label>
      </div>

      <button className="dna-save" onClick={() => onSave?.(dna)}>Depot DNA Kaydet</button>
    </div>
  );
}