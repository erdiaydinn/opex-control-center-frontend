import React from "react";
import ProductTile3D from "./ProductTile3D.jsx";

export default function ShelfProductTiles({ products = [], x = 0, y = 0, onSelect }) {
  const tileW = 46;
  const gap = 6;

  return (
    <g transform={`translate(${x}, ${y})`}>
      <defs>
        <linearGradient id="fallbackProductGradient" x1="0" x2="1">
          <stop offset="0%" stopColor="#FFF7FB" />
          <stop offset="100%" stopColor="#F3F6FA" />
        </linearGradient>
      </defs>

      {products.map((product, idx) => (
        <ProductTile3D
          key={`${product.sku || idx}-${idx}`}
          product={product}
          x={idx * (tileW + gap)}
          y={0}
          width={tileW}
          height={58}
          onSelect={onSelect}
        />
      ))}
    </g>
  );
}