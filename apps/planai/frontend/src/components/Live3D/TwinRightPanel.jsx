import React from "react";

export default function TwinRightPanel({ selectedProduct, cameraPreset, setCameraPreset, onSearch }) {
  return (
    <aside className="twin-right-panel">
      <section>
        <h3>Kamera</h3>
        <select value={cameraPreset} onChange={(e) => setCameraPreset(e.target.value)}>
          <option value="overview">Genel Bakış</option>
          <option value="top">Üstten Görünüm</option>
          <option value="chilled">+4 Zone</option>
          <option value="frozen">-18 Zone</option>
          <option value="dispatch">Dispatch</option>
        </select>
      </section>
      <section>
        <h3>SKU Ara</h3>
        <input placeholder="SKU / ürün adı" onKeyDown={(e) => e.key === "Enter" && onSearch?.(e.currentTarget.value)} />
      </section>
      <section>
        <h3>Seçili Ürün</h3>
        {selectedProduct ? <div className="selected-product-card">
          {selectedProduct.image_url && <img src={selectedProduct.image_url} alt="" />}
          <b>{selectedProduct.product_name}</b>
          <span>SKU: {selectedProduct.sku}</span><span>Facing: {selectedProduct.facing_count || selectedProduct.facing || 1}</span><span>Storage: {selectedProduct.storage_type}</span>
        </div> : <p>Raf içindeki bir ürüne tıkla.</p>}
      </section>
    </aside>
  );
}
