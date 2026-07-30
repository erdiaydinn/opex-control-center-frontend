import React from "react";

export function Card({ children, className = "" }) {
  return <section className={`pe-card ${className}`}>{children}</section>;
}

export function Button({ children, onClick, variant = "secondary", active = false, disabled = false, title }) {
  return <button title={title} disabled={disabled} onClick={onClick} className={`pe-btn pe-btn-${variant} ${active ? "is-active" : ""}`}>{children}</button>;
}

export function Stat({ label, value, hint }) {
  return <div className="pe-stat"><div className="pe-stat-value">{value}</div><div className="pe-stat-label">{label}</div>{hint && <div className="pe-stat-hint">{hint}</div>}</div>;
}

export function EmptyImage({ storage }) {
  return <div className={`pe-product-fallback ${storage || "AMBIENT"}`}>{storage === "FROZEN" ? "❄" : storage === "CHILLED" ? "🥶" : "📦"}</div>;
}

export function ProductImage({ product, className = "" }) {
  if (product?.image_url) return <img src={product.image_url} alt="" className={className || "pe-product-image"} loading="lazy" onError={(e) => { e.currentTarget.style.display = "none"; }} />;
  return <EmptyImage storage={product?.storage_type} />;
}
