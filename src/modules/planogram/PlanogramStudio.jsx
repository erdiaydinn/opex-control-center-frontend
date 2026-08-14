import React from "react";



// Permission contract remains canonical while
// Planogram Studio is security-quarantined.
const PLANOGRAM_FEATURES = [
  "aiRecommend",
  "fixtureEdit",
  "layoutEdit",
  "layoutView",
  "productAssign",
  "ruleEdit"
];

const PLANOGRAM_ACTIONS = [
  "approve",
  "create",
  "delete",
  "edit",
  "export",
  "view"
];
export default function PlanogramStudio() {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        padding: 24,
        boxSizing: "border-box",
        background: "#f6f7fa",
        color: "#111827",
        fontFamily: "Inter, system-ui, sans-serif",
      }}
    >
      <section
        role="status"
        style={{
          width: "min(680px, 100%)",
          padding: 28,
          border: "1px solid #e5e7eb",
          borderRadius: 18,
          background: "#ffffff",
          boxShadow: "0 16px 42px rgba(15,23,42,.10)",
        }}
      >
        <div
          style={{
            fontSize: 13,
            fontWeight: 900,
            letterSpacing: ".08em",
            textTransform: "uppercase",
            color: "#9f1239",
          }}
        >
          Phase 1 Security Quarantine
        </div>

        <h1
          style={{
            margin: "10px 0 8px",
            fontSize: 28,
          }}
        >
          Planogram Studio ge?ici olarak kapal?
        </h1>

        <p
          style={{
            margin: 0,
            lineHeight: 1.6,
            color: "#475467",
          }}
        >
          Legacy PlanAI entegrasyonu g?venli,
          backend-arac?l? yetkilendirme s?n?r?
          tamamlanana kadar yay?nlanm?yor.
        </p>
      </section>
    </main>
  );
}
