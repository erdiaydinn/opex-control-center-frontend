
import React from "react";

export default function PremiumLoader({ title="İşlem yapılıyor", subtitle="PLONAGRAM OS hazırlanıyor", steps=[], onCancel }) {
  return (
    <div className="po-loader-shell">
      <div className="po-loader-card">
        <div className="po-loader-mark" aria-label="Plonagram loading">
          <span className="po-loader-p po-loader-p1" />
          <span className="po-loader-p po-loader-p2" />
          <span className="po-loader-p po-loader-p3" />
        </div>
        <div className="po-kicker">PLONAGRAM OS</div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
        <div className="po-loader-steps">
          {(steps.length ? steps : ["Reading Store DNA", "Mapping Fixtures", "Building SKU Graph", "EA Intelligence Core Online"]).map((s, i) => (
            <div className="po-loader-step" key={s}><b /> <span>{s}</span><em>{i < 3 ? "active" : "ready"}</em></div>
          ))}
        </div>
        {onCancel && <button className="po-ghost-btn" onClick={onCancel}>İptal et</button>}
      </div>
    </div>
  );
}
