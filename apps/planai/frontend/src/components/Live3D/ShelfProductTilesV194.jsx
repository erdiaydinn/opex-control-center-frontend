import React from "react";
import ProductTile3DV194 from "./ProductTile3DV194";
import "./ShelfProductTilesV194.css";

export default function ShelfProductTilesV194({ products = [], max = 18, onSelectProduct }) {
  const visible = products.slice(0, max);
  const overflow = Math.max(0, products.length - visible.length);
  return (
    <div className="shelf194">
      {visible.map((p, idx) => (
        <ProductTile3DV194 key={`${p.sku || p.barcode || idx}-${idx}`} product={p} compact onSelect={onSelectProduct} />
      ))}
      {overflow > 0 && <div className="shelf194-more">+{overflow}</div>}
    </div>
  );
}
