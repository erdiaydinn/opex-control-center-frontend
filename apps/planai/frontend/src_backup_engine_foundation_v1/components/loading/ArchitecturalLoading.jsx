import React from "react";
import PlonagramArchitecturalMark from "../Brand/PlonagramArchitecturalMark";
import "./ArchitecturalLoading.css";

export default function ArchitecturalLoading({ mode = "boot" }) {
  return (
    <div className="pl-arch-loading" data-mode={mode}>
      <div className="pl-arch-bg" />
      <main className="pl-arch-lockup">
        <PlonagramArchitecturalMark className="pl-arch-mark" />
        <div className="pl-arch-word">PLONAGRAM</div>
        <div className="pl-arch-sub">WAREHOUSE INTELLIGENCE</div>
      </main>
      <div className="pl-arch-bottom">
        <PlonagramArchitecturalMark className="pl-arch-mini" />
        <div className="pl-arch-spinner" />
      </div>
    </div>
  );
}
