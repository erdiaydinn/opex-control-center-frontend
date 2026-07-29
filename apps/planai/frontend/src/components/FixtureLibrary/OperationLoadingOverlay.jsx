import { useEffect, useMemo, useState } from 'react';
import BrandLogo from './BrandLogo.jsx';

const STEPS = {
  sku: [
    'Reading SKU file',
    'Normalizing barcode and product names',
    'Mapping category / brand graph',
    'Estimating missing dimensions',
    'SKU graph ready'
  ],
  layout: [
    'Reading layout file',
    'Detecting rooms and fixtures',
    'Mapping cold and frozen zones',
    'Building digital twin geometry',
    'Layout state ready'
  ],
  plan: [
    'Reading Store DNA',
    'Mapping Fixtures',
    'Building SKU Graph',
    'Calculating Refill Risk',
    'Council Engine Online'
  ],
  boot: [
    'Reading Store DNA',
    'Mapping Fixtures',
    'Building SKU Graph',
    'Calculating Refill Risk',
    'EA Intelligence Core Online'
  ]
};

const TIPS = [
  'Hızlı satan ürün rafta değil, rotada kazanır: en kısa toplama hattı her zaman para eder.',
  'Facing yalnızca görüntü değildir; refill maliyetini ve picker beklemesini doğrudan değiştirir.',
  'Donuk ürün önce doğru zone ister. Yanlış fixture, iyi algoritmayı bile çöpe çevirir.',
  'Aynı marka blokları göze temiz gelir; aynı zamanda picker hafızasını da güçlendirir.',
  'Boş raf başarı değildir. Doğru doluluk, doğru erişim ve doğru derinlik başarıdır.',
  'Planogram güzel görünmek için değil, siparişi daha hızlı ve daha az hatayla toplatmak için vardır.'
];

export default function OperationLoadingOverlay({ open, mode = 'plan', title, subtitle, progress = 0, onCancel, cancellable = true }) {
  const [tick, setTick] = useState(0);
  const steps = STEPS[mode] || STEPS.plan;
  const pct = Math.max(0, Math.min(100, Number(progress || 0)));
  const activeStep = Math.min(steps.length - 1, Math.floor((pct / 100) * steps.length));
  const tip = useMemo(() => TIPS[tick % TIPS.length], [tick]);

  useEffect(() => {
    if (!open) return undefined;
    const timer = window.setInterval(() => setTick((v) => v + 1), 2600);
    return () => window.clearInterval(timer);
  }, [open]);

  if (!open) return null;

  return (
    <div className="op-loading-backdrop" role="dialog" aria-modal="true">
      <div className="op-loading-card">
        <div className="op-loading-mark real-logo" aria-hidden="true">
          <BrandLogo compact animated />
        </div>
        <div className="section-eyebrow">PLONAGRAM OS</div>
        <h2>{title || 'Warehouse Intelligence Core'}</h2>
        <p className="muted">{subtitle || 'Operasyon verisi okunuyor, dijital ikiz güncelleniyor.'}</p>
        <div className="op-progress"><span style={{ width: `${pct}%` }} /></div>
        <div className="op-steps">
          {steps.map((s, i) => <div key={s} className={i <= activeStep ? 'active' : ''}><i>{i + 1}</i><span>{s}</span></div>)}
        </div>
        <div className="op-tip">
          <b>Planogram Intelligence</b>
          <span>{tip}</span>
        </div>
        {cancellable && <button className="btn ghost danger" onClick={onCancel}>İşlemi iptal et</button>}
      </div>
    </div>
  );
}
