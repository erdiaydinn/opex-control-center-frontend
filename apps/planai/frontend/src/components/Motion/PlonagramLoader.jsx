
import React, { useEffect, useState } from "react";

export default function PlonagramLoader({ onDone }) {
  const [step, setStep] = useState(0);
  const steps = [
    "Store DNA okunuyor",
    "Fixture graph kuruluyor",
    "SKU node'ları bağlanıyor",
    "3D scene hazırlanıyor",
    "EA Intelligence Core online",
  ];

  useEffect(() => {
    const tick = setInterval(() => setStep((s) => Math.min(s + 1, steps.length - 1)), 460);
    const done = setTimeout(() => onDone?.(), 2850);
    return () => {
      clearInterval(tick);
      clearTimeout(done);
    };
  }, [onDone]);

  return (
    <div className="pl-loader">
      <div className="pl-loader-bg" />
      <div className="pl-loader-card">
        <svg className="pl-loader-mark" viewBox="0 0 180 180" aria-label="Plonagram logo animation">
          <path d="M52 138V38l38-22 38 22v41L90 101v60L52 138Z" />
          <path d="M90 16v85l38 22V79" />
          <path d="M52 38l38 23 38-23" />
          <path className="hot" d="M90 101l38-22 30 18v41l-30 18-38-22" />
        </svg>
        <h1>PLONAGRAM</h1>
        <p>WAREHOUSE INTELLIGENCE</p>
        <div className="pl-loader-progress"><i style={{ width: `${22 + step * 19}%` }} /></div>
        <div className="pl-loader-steps">
          {steps.map((label, i) => <span key={label} className={i <= step ? "on" : ""}>{label}</span>)}
        </div>
      </div>
    </div>
  );
}
