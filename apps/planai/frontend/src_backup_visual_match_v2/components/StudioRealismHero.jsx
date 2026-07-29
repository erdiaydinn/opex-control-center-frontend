import React from "react";
import MarketDigitalTwinVisual from "./visuals/MarketDigitalTwinVisual";

export default function StudioRealismHero({ onOpenStudio, onGenerate }) {
  return (
    <section className="os-realism-hero">
      <div className="os-realism-copy">
        <div className="os-chip">AI-supported Darkstore Operating Intelligence</div>
        <h1>PLONAGRAM <span>Digital Twin</span></h1>
        <p>Gerçek market/darkstore yapısına göre raf, dolap, dispatch, transpalet ve picker rotasını aynı operasyon zekâsında birleştirir.</p>
        <div className="os-realism-actions">
          <button onClick={onGenerate}>✦ Generate Planogram</button>
          <button className="ghost" onClick={onOpenStudio}>Open 3D Studio →</button>
        </div>
      </div>
      <div className="os-realism-visual">
        <MarketDigitalTwinVisual variant="hero" />
      </div>
    </section>
  );
}
