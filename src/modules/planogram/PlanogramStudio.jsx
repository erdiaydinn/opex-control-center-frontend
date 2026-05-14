import React from "react";

const PLANAI_URL =
  import.meta.env.VITE_PLANAI_LEGACY_URL || "http://localhost:5174";

export default function PlanogramStudio() {
  return (
    <main style={{ width: "100vw", height: "100vh", background: "#050814" }}>
      <iframe
        title="Planogram Studio"
        src={PLANAI_URL}
        style={{
          width: "100%",
          height: "100%",
          border: "0",
          display: "block",
          background: "#050814",
        }}
      />
    </main>
  );
}
