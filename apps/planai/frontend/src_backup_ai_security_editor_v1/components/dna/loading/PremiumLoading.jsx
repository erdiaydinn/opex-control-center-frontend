import React, { useEffect, useState } from "react";
import "./PremiumLoading.css";

function PlonagramLineLogo() {
  return (
    <svg className="pl-load-logo" viewBox="0 0 120 120" aria-hidden="true">
      <path className="pl-load-line base" d="M38 24 L70 8 L96 24 L96 56 L70 72 L54 64 L54 92 L38 108 L22 100 L22 40 Z" />
      <path className="pl-load-line base" d="M38 24 L38 84 L54 92" />
      <path className="pl-load-line base" d="M22 40 L38 48 L70 32 L96 24" />
      <path className="pl-load-line base" d="M70 8 L70 32 L70 72" />
      <path className="pl-load-line base" d="M54 64 L70 56 L70 32" />
      <path className="pl-load-line accent" d="M70 56 L96 40" />
    </svg>
  );
}

export default function PremiumLoading({ mode = "boot" }) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setProgress((p) => Math.min(100, p + 2)), 28);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="pl-load-screen">
      <div className="pl-load-bg" />
      <div className="pl-load-center">
        <PlonagramLineLogo />
        <div className="pl-load-word">P L O N A G R A M</div>
        <div className="pl-load-sub">WAREHOUSE INTELLIGENCE</div>
      </div>
      <div className="pl-load-footer">
        <PlonagramLineLogo />
        <div className="pl-load-spinner" style={{ "--p": `${progress}%` }} />
      </div>
    </div>
  );
}
