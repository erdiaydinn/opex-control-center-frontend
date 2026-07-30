import BrandLogo from './BrandLogo.jsx';

export default function LoadingScreen({ lang = 'tr' }) {
  const steps = lang === 'tr'
    ? ['Store DNA okunuyor', 'Fixture haritası kuruluyor', 'SKU grafı hazırlanıyor', 'Refill riski hesaplanıyor', 'EA Intelligence Core çevrimiçi']
    : ['Reading Store DNA', 'Mapping Fixtures', 'Building SKU Graph', 'Calculating Refill Risk', 'EA Intelligence Core Online'];
  return (
    <div className="loading-screen">
      <div className="loading-card">
        <BrandLogo compact animated />
        <div style={{ textAlign: 'center' }}>
          <div className="logo-word" style={{ letterSpacing: '.42em' }}>PLONAGRAM OS</div>
          <div className="logo-sub">WAREHOUSE INTELLIGENCE CORE</div>
        </div>
        <div className="loading-steps">
          {steps.map((s) => <span key={s}>• {s}</span>)}
        </div>
      </div>
    </div>
  );
}
