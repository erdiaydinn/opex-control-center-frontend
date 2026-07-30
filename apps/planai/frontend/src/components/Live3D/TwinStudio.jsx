import React, { useMemo, useState } from "react";
import TwinScene from "./TwinScene";
import TwinRightPanel from "./TwinRightPanel";
import TwinFallback2D from "./TwinFallback2D";
import "../../styles/twin.css";

export default function TwinStudio({ planogram }) {
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [cameraPreset, setCameraPreset] = useState("overview");
  const selectedSku = selectedProduct?.sku;
  const stats = useMemo(() => {
    let shelves = 0, products = 0;
    for (const a of planogram?.aisles || []) for (const m of a.modules || []) { shelves += (m.shelves || []).length; for (const s of m.shelves || []) products += (s.products || []).length; }
    return { aisles: planogram?.aisles?.length || 0, shelves, products };
  }, [planogram]);
  function handleSearch(q) {
    const needle = String(q || "").toLowerCase();
    if (!needle) return;
    for (const a of planogram?.aisles || []) for (const m of a.modules || []) for (const s of m.shelves || []) {
      const p = (s.products || []).find((x) => `${x.sku} ${x.product_name}`.toLowerCase().includes(needle));
      if (p) { setSelectedProduct(p); setCameraPreset("overview"); return; }
    }
  }
  if (!planogram?.aisles?.length) return <TwinFallback2D planogram={planogram} error="Planogram/Store DNA yok. Önce layout üret veya yükle." />;
  return <div className="twin-studio">
    <header className="twin-topbar"><div><span className="eyebrow">PLONAGRAM OS</span><h2>True Twin Studio</h2></div><div className="twin-stat-row"><b>{stats.aisles}</b><span>Koridor</span><b>{stats.shelves}</b><span>Raf</span><b>{stats.products}</b><span>Ürün tile</span></div></header>
    <main className="twin-body"><section className="twin-canvas-shell"><TwinScene planogram={planogram} selectedSku={selectedSku} onSelectProduct={setSelectedProduct} cameraPreset={cameraPreset} /></section><TwinRightPanel selectedProduct={selectedProduct} cameraPreset={cameraPreset} setCameraPreset={setCameraPreset} onSearch={handleSearch} /></main>
  </div>;
}
