export default function LoadingScreen() {
  const steps = ['Reading Store DNA', 'Mapping Fixtures', 'Building SKU Graph', 'Calculating Refill Risk', 'EA Intelligence Core Online'];
  return (
    <div className="loading-screen">
      <div className="loading-core">
        <div className="loading-logo">
          <svg width="170" height="170" viewBox="0 0 64 64" fill="none">
            <path d="M17 8 32 2l15 8v22L32 40 17 32V8Z M17 8 32 16v24M47 10 32 16M17 32l15-8 15 8M32 24h14l-14 16v18l-15-8V32M32 40 47 32v14L32 58" stroke="#10131A" strokeWidth="2.4" strokeLinejoin="round" />
            <path d="M32 40 47 32v14" stroke="#DF1067" strokeWidth="2.6" strokeLinejoin="round" />
          </svg>
        </div>
        <div>
          <div className="loading-word">PLONAGRAM</div>
          <div className="loading-sub">WAREHOUSE INTELLIGENCE CORE</div>
        </div>
        <div className="loading-steps">
          {steps.map((s) => <div key={s} className="loading-step">{s}</div>)}
        </div>
        <div className="loading-ring" />
      </div>
    </div>
  );
}
