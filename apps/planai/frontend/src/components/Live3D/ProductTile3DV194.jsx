import React, { useMemo, useState } from "react";

function initials(name = "") {
  return String(name || "SKU").split(/\s+/).filter(Boolean).slice(0, 2).map((x) => x[0]).join("").toUpperCase();
}

function categoryClass(product) {
  const raw = `${product.category_l1 || ""} ${product.category_l2 || ""} ${product.storage_type || ""}`.toLowerCase();
  if (raw.includes("frozen") || raw.includes("donuk") || raw.includes("ice")) return "frozen";
  if (raw.includes("chilled") || raw.includes("soğuk") || raw.includes("süt")) return "chilled";
  if (raw.includes("beverage") || raw.includes("water")) return "beverage";
  return "ambient";
}

export default function ProductTile3DV194({ product, compact = false, onSelect }) {
  const [imgError, setImgError] = useState(false);
  const image = product?.image_url || product?.visual?.image_url || product?.product_image_url;
  const cls = useMemo(() => categoryClass(product || {}), [product]);
  const title = product?.product_name || product?.ProductName || product?.sku || "Product";

  return (
    <button className={`tile194 tile194-${cls} ${compact ? "tile194-compact" : ""}`} onClick={() => onSelect?.(product)} title={title}>
      {image && !imgError ? (
        <img src={image} alt="" onError={() => setImgError(true)} />
      ) : (
        <span className="tile194-fallback">{initials(title)}</span>
      )}
      <span className="tile194-hover">{title}</span>
    </button>
  );
}
