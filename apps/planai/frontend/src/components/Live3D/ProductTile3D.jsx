import React, { useMemo, useState } from "react";

/**
 * ProductTile3D
 * 
 * Principle:
 * - Default 3D twin does NOT print product names as floating labels.
 * - It renders product face/image tiles.
 * - Names appear only on hover/selection through a compact info card.
 */
export default function ProductTile3D({
  product,
  x = 0,
  y = 0,
  width = 48,
  height = 58,
  onSelect,
}) {
  const [hover, setHover] = useState(false);

  const hasImage = Boolean(product?.image_url);
  const initials = useMemo(() => {
    const brand = product?.brand || product?.category_l2 || product?.product_name || "SKU";
    return String(brand).slice(0, 2).toUpperCase();
  }, [product]);

  return (
    <g
      transform={`translate(${x}, ${y})`}
      className="product-tile3d"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={() => onSelect?.(product)}
      role="button"
      tabIndex={0}
    >
      <rect
        width={width}
        height={height}
        rx="7"
        fill={hasImage ? "#ffffff" : "url(#fallbackProductGradient)"}
        stroke={hover ? "#DF1067" : "rgba(16,19,26,.16)"}
        strokeWidth={hover ? "2" : "1"}
      />

      {hasImage ? (
        <image
          href={product.image_url}
          x="3"
          y="3"
          width={width - 6}
          height={height - 6}
          preserveAspectRatio="xMidYMid meet"
          clipPath="inset(0 round 6px)"
        />
      ) : (
        <>
          <rect x="8" y="8" width={width - 16} height={height - 16} rx="6" fill="rgba(255,255,255,.38)" />
          <text
            x={width / 2}
            y={height / 2 + 5}
            textAnchor="middle"
            fontSize="13"
            fontWeight="800"
            fill="#10131A"
          >
            {initials}
          </text>
        </>
      )}

      {hover && (
        <g transform={`translate(${Math.min(width + 8, 62)}, -4)`}>
          <rect width="210" height="72" rx="12" fill="#10131A" opacity=".94" />
          <text x="12" y="20" fontSize="11" fill="#fff" fontWeight="800">
            {String(product?.product_name || "Product").slice(0, 28)}
          </text>
          <text x="12" y="39" fontSize="10" fill="#D5DAE5">
            SKU: {product?.sku || "-"} · {product?.storage_type || "-"}
          </text>
          <text x="12" y="56" fontSize="10" fill="#D5DAE5">
            Facing: {product?.facing_count || product?.facing || 1} · Orders: {product?.order_share_pct || 0}%
          </text>
        </g>
      )}
    </g>
  );
}