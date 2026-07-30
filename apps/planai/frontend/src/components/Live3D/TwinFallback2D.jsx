import React from "react";

export default function TwinFallback2D({ planogram, error }) {
  const aisles = planogram?.aisles || [];
  return (
    <div className="twin-fallback">
      <div className="twin-fallback-header">
        <b>3D sahne geçici olarak açılamadı</b>
        <span>{error || "WebGL / scene payload kontrol edilmeli."}</span>
      </div>
      <div className="twin-fallback-grid">
        {aisles.map((a) => <div key={a.aisle_id} className="twin-fallback-aisle"><strong>{a.aisle_id}</strong><span>{a.modules?.length || 0} modül</span></div>)}
      </div>
    </div>
  );
}
