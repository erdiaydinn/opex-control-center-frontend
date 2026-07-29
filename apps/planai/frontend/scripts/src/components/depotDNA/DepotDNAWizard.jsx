import React, { useEffect, useState } from "react";
import { plonagramApi } from "../../services/plonagramApi";
import "./DepotDNAWizard.css";

const clone = (x) => JSON.parse(JSON.stringify(x || {}));

export default function DepotDNAWizard({ storeCode, onSaved }) {
  const [dna, setDna] = useState(null);
  const [status, setStatus] = useState("Yükleniyor...");

  useEffect(() => {
    if (!storeCode) return;
    setStatus("Yükleniyor...");
    plonagramApi.getDepotDNA(storeCode)
      .then((r) => { setDna(r.dna); setStatus(r.exists ? "Kayıtlı profil yüklendi." : "Yeni depo profili oluşturulacak."); })
      .catch((e) => setStatus(e.message));
  }, [storeCode]);

  function set(path, value) {
    setDna((prev) => {
      const next = clone(prev);
      let cur = next;
      path.slice(0, -1).forEach((k) => { cur[k] ||= {}; cur = cur[k]; });
      cur[path[path.length - 1]] = value;
      return next;
    });
  }

  async function save() {
    const res = await plonagramApi.saveDepotDNA(storeCode, dna);
    setDna(res.dna);
    setStatus("Depo DNA kaydedildi.");
    onSaved?.(res.dna);
  }

  if (!dna) return <div className="dna-card">{status}</div>;
  const p = dna.physical || {};
  const o = dna.operations || {};
  const f = dna.fixture_defaults || {};
  const c = dna.cold_rooms || {};
  const inv = dna.object_inventory || {};

  return (
    <section className="dna-card">
      <div className="dna-head">
        <div>
          <p className="dna-kicker">DEPOT DNA</p>
          <h2>Depo Fizik & Operasyon Profili</h2>
          <span>{status}</span>
        </div>
        <button onClick={save}>Kaydet</button>
      </div>

      <div className="dna-grid">
        <div className="dna-section">
          <h3>Fiziksel yapı</h3>
          <label>Kat sayısı<input type="number" value={p.floors ?? 1} onChange={(e)=>set(["physical","floors"], Number(e.target.value))}/></label>
          <label className="check"><input type="checkbox" checked={!!p.has_basement} onChange={(e)=>set(["physical","has_basement"], e.target.checked)}/> Alt kat var</label>
          <label>Toplam alan m²<input type="number" value={p.total_area_m2 ?? ""} onChange={(e)=>set(["physical","total_area_m2"], Number(e.target.value || 0))}/></label>
          <label>Picking alanı m²<input type="number" value={p.picking_area_m2 ?? ""} onChange={(e)=>set(["physical","picking_area_m2"], Number(e.target.value || 0))}/></label>
          <label>Ortalama koridor cm<input type="number" value={p.avg_aisle_width_cm ?? 120} onChange={(e)=>set(["physical","avg_aisle_width_cm"], Number(e.target.value))}/></label>
        </div>

        <div className="dna-section">
          <h3>Raf / fixture</h3>
          <label>Ana raf tipi
            <select value={f.main_rack_type || "steel_rack"} onChange={(e)=>set(["fixture_defaults","main_rack_type"], e.target.value)}>
              <option value="steel_rack">Çelik Raf 93×43×200</option>
              <option value="steel_rack_new_gen">Yeni Nesil 100×60×250</option>
              <option value="hdr_heavy_rack">HDR 90×60×250</option>
            </select>
          </label>
          <label className="check"><input type="checkbox" checked={!!f.has_new_gen_steel_rack} onChange={(e)=>set(["fixture_defaults","has_new_gen_steel_rack"], e.target.checked)}/> Yeni nesil çelik raf var</label>
          <label>Standart raf adedi<input type="number" value={inv.steel_rack_count ?? 0} onChange={(e)=>set(["object_inventory","steel_rack_count"], Number(e.target.value))}/></label>
          <label>Yeni nesil raf adedi<input type="number" value={inv.steel_rack_new_gen_count ?? 0} onChange={(e)=>set(["object_inventory","steel_rack_new_gen_count"], Number(e.target.value))}/></label>
          <label>HDR adedi<input type="number" value={inv.hdr_heavy_rack_count ?? 0} onChange={(e)=>set(["object_inventory","hdr_heavy_rack_count"], Number(e.target.value))}/></label>
        </div>

        <div className="dna-section">
          <h3>Soğuk oda / donuk oda</h3>
          <label className="check"><input type="checkbox" checked={!!c.has_chilled_room} onChange={(e)=>set(["cold_rooms","has_chilled_room"], e.target.checked)}/> +4 soğuk oda var</label>
          <label>+4 oda m²<input type="number" value={c.chilled_room_area_m2 ?? 0} onChange={(e)=>set(["cold_rooms","chilled_room_area_m2"], Number(e.target.value))}/></label>
          <label>+4 oda iç tipi
            <select value={c.chilled_room_storage_type || "mixed"} onChange={(e)=>set(["cold_rooms","chilled_room_storage_type"], e.target.value)}>
              <option value="rack">Raf</option><option value="pallet">Palet</option><option value="crate">Kasa/Krat</option><option value="mixed">Karışık</option>
            </select>
          </label>
          <label className="check"><input type="checkbox" checked={!!c.has_frozen_room} onChange={(e)=>set(["cold_rooms","has_frozen_room"], e.target.checked)}/> -18 donuk oda var</label>
          <label>-18 oda m²<input type="number" value={c.frozen_room_area_m2 ?? 0} onChange={(e)=>set(["cold_rooms","frozen_room_area_m2"], Number(e.target.value))}/></label>
          <label>-18 oda iç tipi
            <select value={c.frozen_room_storage_type || "mixed"} onChange={(e)=>set(["cold_rooms","frozen_room_storage_type"], e.target.value)}>
              <option value="rack">Raf</option><option value="pallet">Palet</option><option value="crate">Kasa/Krat</option><option value="mixed">Karışık</option>
            </select>
          </label>
        </div>

        <div className="dna-section">
          <h3>Operasyon</h3>
          <label>Günlük sipariş ort.<input type="number" value={o.avg_daily_orders ?? ""} onChange={(e)=>set(["operations","avg_daily_orders"], Number(e.target.value || 0))}/></label>
          <label>Peak picker<input type="number" value={o.peak_picker_count ?? ""} onChange={(e)=>set(["operations","peak_picker_count"], Number(e.target.value || 0))}/></label>
          <label>Mal kabul saatleri<input value={o.receiving_hours || ""} onChange={(e)=>set(["operations","receiving_hours"], e.target.value)} placeholder="Örn: 09:00-16:00"/></label>
          <label className="check"><input type="checkbox" checked={!!o.receiving_after_16_risk} onChange={(e)=>set(["operations","receiving_after_16_risk"], e.target.checked)}/> 16 sonrası mal kabul riskli</label>
          <label className="check"><input type="checkbox" checked={!!o.frozen_pick_last} onChange={(e)=>set(["operations","frozen_pick_last"], e.target.checked)}/> Donuk ürün rota sonunda</label>
        </div>
      </div>
    </section>
  );
}
