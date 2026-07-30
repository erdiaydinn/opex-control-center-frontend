export default function BrandLogo({ compact = false, animated = false }) {
  return (
    <div className="logo-wrap">
      <svg className={animated ? 'loading-logo' : 'logo-mark'} viewBox="0 0 120 120" aria-label="PLONAGRAM logo">
        <g fill="none" stroke="#10131A" strokeWidth="5.6" strokeLinejoin="round" strokeLinecap="round" className={animated ? 'draw-line' : ''}>
          <path d="M35 15 L35 94 L56 106 L56 73 L78 86 L100 73 L100 42 L72 27 L56 36 L56 27 Z" />
          <path d="M35 15 L56 27 L78 16 L100 29 L100 42" />
          <path d="M56 36 L78 49 L78 86" />
          <path d="M35 94 L56 73 L56 36" />
        </g>
        <path className={animated ? 'draw-line draw-pink' : ''} d="M80 49 L100 42 L100 73 L78 86" fill="none" stroke="#DF1067" strokeWidth="5.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {!compact && (
        <div className="hide-narrow">
          <div className="logo-word">PLONAGRAM</div>
          <div className="logo-sub">WAREHOUSE INTELLIGENCE</div>
        </div>
      )}
    </div>
  );
}
