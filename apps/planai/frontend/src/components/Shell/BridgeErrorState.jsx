import React from "react";

export default function BridgeErrorState({ health, onRetry }) {
  return (
    <div className="bridge-error-state">
      <div className="bridge-error-card">
        <div className="bridge-error-eyebrow">Planogram Studio</div>
        <h2>Studio başlatılamadı</h2>
        <p>OPEX portal açık; ancak legacy PlanAI frontend yanıt vermiyor olabilir. Blank screen yerine bu kontrol ekranı gösteriliyor.</p>
        <div className="bridge-error-grid">
          <span>PlanAI Frontend</span><b>{health?.frontend?.ok ? "Online" : "Offline"}</b>
          <span>PlanAI Backend</span><b>{health?.backend?.ok ? "Online" : "Kontrol gerekli"}</b>
        </div>
        <button onClick={onRetry}>Tekrar dene</button>
        <code>Beklenen: localhost:5174 frontend · 127.0.0.1:8001 backend</code>
      </div>
    </div>
  );
}
