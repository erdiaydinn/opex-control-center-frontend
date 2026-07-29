export default function BrandLogo({ compact = false }) {
  return (
    <div className="brand-block">
      <div className="logo-mark" aria-label="PLONAGRAM OS">
        <svg width="46" height="46" viewBox="0 0 64 64" fill="none">
          <path d="M17 8 32 2l15 8v22L32 40 17 32V8Z" stroke="#10131A" strokeWidth="2.8" strokeLinejoin="round" />
          <path d="M17 8 32 16v24M47 10 32 16M17 32l15-8 15 8" stroke="#10131A" strokeWidth="2.3" strokeLinejoin="round" />
          <path d="M32 24h14l-14 16v18l-15-8V32" stroke="#10131A" strokeWidth="2.8" strokeLinejoin="round" />
          <path d="M32 40 47 32v14L32 58" stroke="#DF1067" strokeWidth="2.8" strokeLinejoin="round" />
        </svg>
      </div>
      {!compact && (
        <div className="hide-narrow">
          <div className="logo-word">PLONAGRAM</div>
          <div className="logo-sub">WAREHOUSE INTELLIGENCE</div>
        </div>
      )}
    </div>
  );
}
