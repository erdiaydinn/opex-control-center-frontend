import React from "react";
import { summarizeTwinPayload } from "../../services/plonagramV194Api";

export default function V194PipelineStatusCard({ twinPayload }) {
  const s = summarizeTwinPayload(twinPayload || {});
  return (
    <div style={{ background: "#fff", border: "1px solid rgba(16,19,26,.08)", borderRadius: 22, padding: 18, boxShadow: "0 14px 36px rgba(16,19,26,.08)" }}>
      <div style={{ color: "#df1067", fontWeight: 900, fontSize: 11, letterSpacing: ".14em" }}>VISUAL TWIN READYNESS</div>
      <h3 style={{ margin: "8px 0 12px", fontSize: 20 }}>V1.9.4 Pipeline Durumu</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10 }}>
        <Box label="Sellable" value={s.sellable} />
        <Box label="Excluded" value={s.excluded} />
        <Box label="Review" value={s.review} />
        <Box label="Image" value={`${s.imageCoveragePct}%`} />
      </div>
    </div>
  );
}

function Box({ label, value }) {
  return <div style={{ background: "#f7f4ef", borderRadius: 14, padding: 12 }}><strong>{value}</strong><span style={{ display: "block", color: "#657085", fontSize: 12 }}>{label}</span></div>;
}
