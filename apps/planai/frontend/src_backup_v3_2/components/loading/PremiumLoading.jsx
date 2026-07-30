import React from 'react';
import './PremiumLoading.css';

export default function PremiumLoading() {
  const steps = [
    'Reading Store DNA',
    'Mapping Fixtures',
    'Building SKU Graph',
    'Calculating Refill Risk',
    'EA Intelligence Core Online',
  ];

  return (
    <div className="plonagram-loading-screen">
      <div className="plonagram-loading-warehouse" />
      <div className="plonagram-loading-lockup">
        <svg className="plonagram-loading-mark" viewBox="0 0 180 180" role="img" aria-label="PLONAGRAM loading mark">
          <path className="plonagram-loading-line" d="M58 45 L90 27 L122 45 L122 82 L93 99 L93 134 L60 153 L60 116 L33 101 L33 63 Z" />
          <path className="plonagram-loading-line" d="M58 45 L58 116 L92 135 L92 99 L122 82" />
          <path className="plonagram-loading-line" d="M33 63 L60 80 L90 62 L122 45" />
          <path className="plonagram-loading-line" d="M60 80 L60 153" />
          <path className="plonagram-loading-accent" d="M92 99 L122 82 L122 53" />
        </svg>

        <div className="plonagram-loading-title">PLONAGRAM</div>
        <div className="plonagram-loading-subtitle">WAREHOUSE INTELLIGENCE</div>

        <div className="plonagram-loading-steps">
          {steps.map((step, index) => (
            <span key={step} style={{ animationDelay: `${index * 0.18}s` }}>{step}</span>
          ))}
        </div>
      </div>

      <div className="plonagram-loading-bottom">
        <svg className="plonagram-loading-mini" viewBox="0 0 180 180" aria-hidden="true">
          <path className="plonagram-loading-line mini" d="M58 45 L90 27 L122 45 L122 82 L93 99 L93 134 L60 153 L60 116 L33 101 L33 63 Z" />
          <path className="plonagram-loading-line mini" d="M33 63 L60 80 L90 62 L122 45" />
          <path className="plonagram-loading-accent mini" d="M92 99 L122 82" />
        </svg>
        <div className="plonagram-loading-ring" />
      </div>
    </div>
  );
}
