import React, { useMemo, useState } from "react";
import "../styles/plonagram-v19.css";

function makeShelf(index, module) {
  return {
    shelf_no: index + 1,
    width_cm: module.width_cm,
    depth_cm: module.depth_cm,
    height_cm: Math.floor(module.height_cm / Math.max(module.shelf_count || 1, 1)),
    max_weight_kg: module.allowed_storage_type === "AMBIENT" ? 45 : module.allowed_storage_type === "CHILLED" ? 60 : 70,
    products: [],
  };
}

function makeModule(aisleId, side, index, preset = {}) {
  const module = {
    module_id: `${aisleId}-${side}-${String(index + 1).padStart(2, "0")}`,
    fixture_type: preset.fixture_type || "regular_shelf",
    width_cm: Number(preset.width_cm || 100),
    depth_cm: Number(preset.depth_cm || 50),
    height_cm: Number(preset.height_cm || 210),
    shelf_count: Number(preset.shelf_count || 6),
    allowed_storage_type: preset.allowed_storage_type || "AMBIENT",
  };
  module.shelves = Array.from({ length: module.shelf_count }, (_, i) => makeShelf(i, module));
  return module;
}

function makeAisle({ aisleId, leftCount, rightCount, leftPreset, rightPreset }) {
  return {
    aisle_id: aisleId,
    type: "double_sided",
    position: { x: 0, y: 0, rotation: 0 },
    walkway_width_cm: 120,
    faces: {
      L: {
        label: `${aisleId} Sol`,
        modules: Array.from({ length: Number(leftCount || 0) }, (_, i) => makeModule(aisleId, "L", i, leftPreset)),
      },
      R: {
        label: `${aisleId} Sağ`,
        modules: Array.from({ length: Number(rightCount || 0) }, (_, i) => makeModule(aisleId, "R", i, rightPreset)),
      },
    },
  };
}

export default function StoreDnaBuilderV19({ initialLayout, onSave }) {
  const [storeCode, setStoreCode] = useState(initialLayout?.store_code || "FULYA");
  const [aisles, setAisles] = useState(initialLayout?.aisles || []);
  const [draft, setDraft] = useState({
    aisleId: "A",
    leftCount: 3,
    rightCount: 6,
    leftPreset: { width_cm: 100, depth_cm: 50, height_cm: 210, shelf_count: 7, fixture_type: "regular_shelf", allowed_storage_type: "AMBIENT" },
    rightPreset: { width_cm: 120, depth_cm: 60, height_cm: 250, shelf_count: 6, fixture_type: "hdr_shelf", allowed_storage_type: "AMBIENT" },
  });

  const layout = useMemo(() => ({ schema_version: "layout.v2", store_code: storeCode, aisles, objects: [] }), [storeCode, aisles]);

  function addAisle() {
    const next = makeAisle(draft);
    setAisles((old) => [...old.filter((a) => a.aisle_id !== draft.aisleId), next]);
  }

  function updateModule(aisleId, side, moduleId, patch) {
    setAisles((old) => old.map((a) => {
      if (a.aisle_id !== aisleId) return a;
      const face = a.faces[side];
      const modules = face.modules.map((m) => {
        if (m.module_id !== moduleId) return m;
        const next = { ...m, ...patch };
        if (patch.shelf_count || patch.width_cm || patch.depth_cm || patch.height_cm || patch.allowed_storage_type) {
          next.shelves = Array.from({ length: Number(next.shelf_count || next.shelves?.length || 1) }, (_, i) => ({
            ...(next.shelves?.[i] || {}),
            ...makeShelf(i, next),
          }));
        }
        return next;
      });
      return { ...a, faces: { ...a.faces, [side]: { ...face, modules } } };
    }));
  }

  return (
    <section className="v19-page">
      <div className="v19-page-head">
        <div>
          <div className="v19-eyebrow">SPATIAL CORE</div>
          <h1>Store DNA Builder</h1>
          <p>Koridor → sağ/sol yüz → modül → raf. 2D, 3D ve engine aynı schema’yı kullanır.</p>
        </div>
        <button className="v19-primary" onClick={() => onSave?.(layout)}>Layout V2 Kaydet</button>
      </div>

      <div className="v19-card">
        <div className="v19-card-head"><h3>Hızlı koridor oluştur</h3><span className="v19-pill">Farklı sağ/sol destekli</span></div>
        <div className="v19-builder-grid">
          <label>Depo kodu<input value={storeCode} onChange={(e) => setStoreCode(e.target.value)} /></label>
          <label>Koridor<input value={draft.aisleId} onChange={(e) => setDraft({ ...draft, aisleId: e.target.value.toUpperCase() })} /></label>
          <label>Sol modül<input type="number" value={draft.leftCount} onChange={(e) => setDraft({ ...draft, leftCount: e.target.value })} /></label>
          <label>Sağ modül<input type="number" value={draft.rightCount} onChange={(e) => setDraft({ ...draft, rightCount: e.target.value })} /></label>
          <label>Sol raf sayısı<input type="number" value={draft.leftPreset.shelf_count} onChange={(e) => setDraft({ ...draft, leftPreset: { ...draft.leftPreset, shelf_count: e.target.value } })} /></label>
          <label>Sağ raf sayısı<input type="number" value={draft.rightPreset.shelf_count} onChange={(e) => setDraft({ ...draft, rightPreset: { ...draft.rightPreset, shelf_count: e.target.value } })} /></label>
          <label>Sol ölçü W×D×H<input value={`${draft.leftPreset.width_cm}x${draft.leftPreset.depth_cm}x${draft.leftPreset.height_cm}`} onChange={() => {}} readOnly /></label>
          <label>Sağ ölçü W×D×H<input value={`${draft.rightPreset.width_cm}x${draft.rightPreset.depth_cm}x${draft.rightPreset.height_cm}`} onChange={() => {}} readOnly /></label>
        </div>
        <button className="v19-secondary" onClick={addAisle}>Koridoru ekle/güncelle</button>
      </div>

      <div className="v19-card">
        <div className="v19-card-head"><h3>Oluşan depo gerçekliği</h3><span className="v19-pill">layout.v2</span></div>
        {aisles.map((a) => (
          <div key={a.aisle_id} className="v19-aisle-editor">
            <h3>Koridor {a.aisle_id}</h3>
            {["L", "R"].map((side) => (
              <div key={side}>
                <h4>{side === "L" ? "Sol yüz" : "Sağ yüz"} • {a.faces[side].modules.length} modül</h4>
                <div className="v19-module-grid">
                  {a.faces[side].modules.map((m) => (
                    <div className="v19-module-card" key={m.module_id}>
                      <b>{m.module_id}</b>
                      <label>Genişlik<input type="number" value={m.width_cm} onChange={(e) => updateModule(a.aisle_id, side, m.module_id, { width_cm: Number(e.target.value) })} /></label>
                      <label>Derinlik<input type="number" value={m.depth_cm} onChange={(e) => updateModule(a.aisle_id, side, m.module_id, { depth_cm: Number(e.target.value) })} /></label>
                      <label>Yükseklik<input type="number" value={m.height_cm} onChange={(e) => updateModule(a.aisle_id, side, m.module_id, { height_cm: Number(e.target.value) })} /></label>
                      <label>Raf sayısı<input type="number" value={m.shelves.length} onChange={(e) => updateModule(a.aisle_id, side, m.module_id, { shelf_count: Number(e.target.value) })} /></label>
                      <small>{m.fixture_type} • {m.allowed_storage_type}</small>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ))}
        {aisles.length === 0 && <div className="v19-empty">Henüz koridor yok. A koridorunu oluştur.</div>}
      </div>
    </section>
  );
}
