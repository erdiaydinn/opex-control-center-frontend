import React, { useEffect, useMemo, useState } from 'react';
import {
  DEFAULT_OPTIMIZATION_WEIGHTS,
  DEFAULT_STRATEGY_PROFILE,
  STRATEGY_MODES,
} from '../utils/placementRuleAdapter.js';

const STRATEGIES = [
  {
    mode: STRATEGY_MODES.CATEGORY_SALES,
    title: 'Kategori içinde satış sıralı',
    desc: 'Kategori blokları korunur. Her kategori içinde en hızlı satan SKU öne gelir.',
    weights: false,
  },
  {
    mode: STRATEGY_MODES.ABC_DIRECT,
    title: 'ABC direkt',
    desc: 'ABC dosyasındaki eski lokasyon ana referanstır. Delta daha kontrollü çıkar.',
    weights: false,
  },
  {
    mode: STRATEGY_MODES.HYBRID_CATEGORY_ABC_SALES,
    title: 'Hibrit: kategori + ABC + satış',
    desc: 'Kategori, ABC lokasyonu ve satış birlikte değerlendirilir.',
    weights: true,
  },
  {
    mode: STRATEGY_MODES.HYBRID_BRAND_SALES,
    title: 'Hibrit: marka blok + satış',
    desc: 'En güçlü markalar blok alır. Marka içinde SKU sırası satışa göre yapılır.',
    weights: true,
  },
];

const WEIGHT_CONTROLS = [
  ['sales_weight', 'Satış etkisi'],
  ['category_weight', 'Kategori etkisi'],
  ['brand_block_weight', 'Marka blok etkisi'],
  ['abc_location_weight', 'ABC eski lokasyon etkisi'],
  ['basket_affinity_weight', 'Sepet birlikteliği'],
  ['refill_cost_weight', 'Refill maliyeti'],
  ['picker_route_weight', 'Picker rota etkisi'],
  ['cold_chain_weight', 'Soğuk zincir etkisi'],
  ['capacity_weight', 'Kapasite etkisi'],
  ['shelf_fill_weight', 'Raf doluluk etkisi'],
];

const RULE_TYPES = [
  ['brand', 'Marka'],
  ['category', 'Kategori'],
  ['subcategory', 'Alt kategori'],
  ['storage', 'Storage'],
  ['sku', 'SKU'],
];

const AISLES = ['', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];
const SIDES = ['', 'SAĞ', 'SOL'];

function roleOf() {
  try {
    return String(localStorage.getItem('plonagram_user_role') || 'admin').toLowerCase();
  } catch {
    return 'admin';
  }
}

function canEditWeights(profile) {
  const role = roleOf();
  return (profile.editable_weights_roles || ['admin']).map((x) => String(x).toLowerCase()).includes(role);
}

function readProfile() {
  try {
    const raw = localStorage.getItem('plonagram_strategy_profile');
    if (!raw) return DEFAULT_STRATEGY_PROFILE;
    return {
      ...DEFAULT_STRATEGY_PROFILE,
      ...JSON.parse(raw),
    };
  } catch {
    return DEFAULT_STRATEGY_PROFILE;
  }
}

function emptyRule() {
  return {
    type: 'brand',
    value: '',
    target_aisle: 'A',
    target_side: 'SAĞ',
    behavior: 'prefer_block',
    weight: 7,
    active: true,
  };
}

function salesOf(p = {}) {
  const n = Number(p.sales_qty_7d || p.sales_7d || p.sales_qty_30d || p.daily_sales || p.sales || 0);
  return Number.isFinite(n) ? n : 0;
}

function brandOf(p = {}) {
  return String(p.brand || p.brand_name || p.supplier || 'Markasız').trim();
}

export default function RuleEngineReal({
  placementRules = [],
  setPlacementRules,
  optimizationWeights = DEFAULT_OPTIMIZATION_WEIGHTS,
  setOptimizationWeights,
  onGenerate,
  products = [],
  unplacedProducts = [],
}) {
  const [strategyProfile, setStrategyProfile] = useState(readProfile);
  const [draft, setDraft] = useState(emptyRule());

  const allProducts = useMemo(() => [...(products || []), ...(unplacedProducts || [])], [products, unplacedProducts]);
  const selectedStrategy = STRATEGIES.find((x) => x.mode === strategyProfile.mode) || STRATEGIES[0];
  const weightsAllowed = selectedStrategy.weights && canEditWeights(strategyProfile);

  useEffect(() => {
    const next = {
      ...strategyProfile,
      weights_enabled: Boolean(selectedStrategy.weights),
      label: selectedStrategy.title,
      weights: {
        ...DEFAULT_OPTIMIZATION_WEIGHTS,
        ...(strategyProfile.weights || {}),
        ...(optimizationWeights || {}),
      },
    };
    localStorage.setItem('plonagram_strategy_profile', JSON.stringify(next));
  }, [strategyProfile, selectedStrategy, optimizationWeights]);

  const topBrands = useMemo(() => {
    const map = new Map();

    for (const p of allProducts) {
      const brand = brandOf(p);
      const rec = map.get(brand) || { brand, sales: 0, sku: 0 };
      rec.sales += salesOf(p);
      rec.sku += 1;
      map.set(brand, rec);
    }

    return [...map.values()].sort((a, b) => b.sales - a.sales || b.sku - a.sku).slice(0, 10);
  }, [allProducts]);

  function chooseStrategy(mode) {
    const item = STRATEGIES.find((x) => x.mode === mode) || STRATEGIES[0];

    setStrategyProfile((prev) => ({
      ...prev,
      mode: item.mode,
      label: item.title,
      weights_enabled: item.weights,
    }));
  }

  function updateWeight(key, value) {
    if (!weightsAllowed || typeof setOptimizationWeights !== 'function') return;

    setOptimizationWeights((prev = DEFAULT_OPTIMIZATION_WEIGHTS) => ({
      ...DEFAULT_OPTIMIZATION_WEIGHTS,
      ...(prev || {}),
      [key]: value,
    }));

    setStrategyProfile((prev) => ({
      ...prev,
      weights: {
        ...DEFAULT_OPTIMIZATION_WEIGHTS,
        ...(prev.weights || {}),
        [key]: value,
      },
    }));
  }

  function addRule() {
    const value = String(draft.value || '').trim();
    if (!value) {
      alert('Kural değeri boş olamaz.');
      return;
    }

    const rule = {
      ...draft,
      value,
      id: `RULE-${Date.now()}`,
      created_at: new Date().toISOString(),
    };

    if (typeof setPlacementRules === 'function') {
      setPlacementRules((prev = []) => [rule, ...prev]);
    }

    setDraft(emptyRule());
  }

  function removeRule(id) {
    if (typeof setPlacementRules === 'function') {
      setPlacementRules((prev = []) => prev.filter((r) => r.id !== id));
    }
  }

  async function generate() {
    localStorage.setItem('plonagram_strategy_profile', JSON.stringify({
      ...strategyProfile,
      label: selectedStrategy.title,
      weights_enabled: Boolean(selectedStrategy.weights),
      weights: {
        ...DEFAULT_OPTIMIZATION_WEIGHTS,
        ...(strategyProfile.weights || {}),
        ...(optimizationWeights || {}),
      },
    }));

    if (typeof onGenerate === 'function') await onGenerate();
  }

  return (
    <main className="page rle-page">
      <section className="rle-hero">
        <div>
          <div className="section-eyebrow">PLANOGRAM STRATEJİSİ</div>
          <h1>Planogram Stratejisi</h1>
          <p>
            Önce strateji belirlenir, sonra SKU yüklenir ve planogram üretilir.
            Ağırlık motoru sadece hibrit stratejilerde ve yetkili kullanıcılar için aktiftir.
          </p>
        </div>
        <div className="rle-hero-actions">
          <button className="btn primary" onClick={generate}>Stratejiyle plan üret</button>
        </div>
      </section>

      <section className="rle-kpi-grid">
        <div className="rle-kpi"><span>Seçili strateji</span><b>{selectedStrategy.title}</b><small>Üretimde uygulanır</small></div>
        <div className="rle-kpi"><span>Ağırlık motoru</span><b>{selectedStrategy.weights ? 'Hibrit' : 'Kapalı'}</b><small>Sadece hibrit modda</small></div>
        <div className="rle-kpi"><span>Yetki</span><b>{weightsAllowed ? 'Düzenler' : 'Görüntüler'}</b><small>Rol: {roleOf()}</small></div>
        <div className="rle-kpi"><span>Ürün havuzu</span><b>{allProducts.length.toLocaleString('tr-TR')}</b><small>Yerleşen + atanamayan</small></div>
      </section>

      <section className="rle-weight-panel">
        <div className="rle-card-head">
          <div>
            <h2>Strateji seçimi</h2>
            <p>Strateji SKU yüklemeden önce belirlenmelidir. Hard kurallar hiçbir stratejide ezilmez.</p>
          </div>
        </div>

        <div className="rle-strategy-grid">
          {STRATEGIES.map((s) => (
            <button
              key={s.mode}
              className={`rle-strategy-card ${strategyProfile.mode === s.mode ? 'active' : ''}`}
              onClick={() => chooseStrategy(s.mode)}
            >
              <b>{s.title}</b>
              <span>{s.desc}</span>
              <small>{s.weights ? 'Ağırlık motoru: yetkili kullanıcı' : 'Ağırlık motoru yok'}</small>
            </button>
          ))}
        </div>
      </section>

      {selectedStrategy.weights && (
        <section className="rle-weight-panel">
          <div className="rle-card-head">
            <div>
              <h2>Hibrit ağırlık motoru</h2>
              <p>Bu alan sadece Admin veya Admin tarafından yetkilendirilen kullanıcılar için düzenlenebilir.</p>
            </div>
            {!weightsAllowed && <span className="rle-lock">Sadece görüntüleme</span>}
          </div>

          <div className="rle-weight-grid">
            {WEIGHT_CONTROLS.map(([key, label]) => (
              <div className="rle-weight-row" key={key}>
                <div><b>{label}</b><small>Hibrit strateji karar etkisi</small></div>
                <div className="rle-weight-control">
                  <input
                    type="range"
                    min="1"
                    max="10"
                    disabled={!weightsAllowed}
                    value={optimizationWeights?.[key] ?? DEFAULT_OPTIMIZATION_WEIGHTS[key]}
                    onChange={(e) => updateWeight(key, Number(e.target.value))}
                  />
                  <span>{optimizationWeights?.[key] ?? DEFAULT_OPTIMIZATION_WEIGHTS[key]}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="rle-layout">
        <div className="rle-builder">
          <div className="rle-card-head">
            <div>
              <h2>Marka / kategori yerleşim kuralı</h2>
              <p>Bu kurallar her stratejide çalışır; fakat storage, gıda güvenliği ve kapasite hard rule’larını bozamaz.</p>
            </div>
          </div>

          <div className="rle-form">
            <label>
              <span>Kural tipi</span>
              <select value={draft.type} onChange={(e) => setDraft((d) => ({ ...d, type: e.target.value }))}>
                {RULE_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>

            <label>
              <span>Değer</span>
              <input value={draft.value} onChange={(e) => setDraft((d) => ({ ...d, value: e.target.value }))} placeholder="Örn: Ülker, Eti, Coca-Cola..." />
            </label>

            <label>
              <span>Hedef reyon</span>
              <select value={draft.target_aisle} onChange={(e) => setDraft((d) => ({ ...d, target_aisle: e.target.value }))}>
                {AISLES.map((x) => <option key={x || 'none'} value={x}>{x || 'Seçme'}</option>)}
              </select>
            </label>

            <label>
              <span>Hedef taraf</span>
              <select value={draft.target_side} onChange={(e) => setDraft((d) => ({ ...d, target_side: e.target.value }))}>
                {SIDES.map((x) => <option key={x || 'none'} value={x}>{x || 'Seçme'}</option>)}
              </select>
            </label>

            <label>
              <span>Davranış</span>
              <select value={draft.behavior} onChange={(e) => setDraft((d) => ({ ...d, behavior: e.target.value }))}>
                <option value="prefer_block">Blok tercih et</option>
                <option value="increase_facing">Önyüz artır</option>
                <option value="reduce_facing">Önyüz azalt</option>
              </select>
            </label>

            <label>
              <span>Ağırlık: {draft.weight}/10</span>
              <input type="range" min="1" max="10" value={draft.weight} onChange={(e) => setDraft((d) => ({ ...d, weight: Number(e.target.value) }))} />
            </label>
          </div>

          <div className="rle-preview">
            <div>
              <b>Örnek karar</b>
              <p>{draft.value || 'Seçili marka'} için {draft.target_aisle || '-'} reyonu {draft.target_side || ''} tarafı tercih edilir. Hard rule bozulmaz.</p>
            </div>
            <button className="btn primary" onClick={addRule}>Kuralı kaydet</button>
          </div>
        </div>

        <div className="rle-templates">
          <h2>Depodaki güçlü markalar</h2>
          <p>Bu liste strateji seçimine yardımcı olur.</p>
          <div className="rle-template-list">
            {topBrands.map((b, i) => (
              <button key={b.brand} className="rle-template" onClick={() => setDraft((d) => ({ ...d, type: 'brand', value: b.brand }))}>
                <span>#{i + 1} {b.brand}</span>
                <small>{Math.round(b.sales).toLocaleString('tr-TR')} satış · {b.sku} SKU</small>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="rle-rules-card">
        <div className="rle-card-head">
          <div><h2>Aktif yerleşim kuralları</h2><p>Admin tarafından belirlenen marka/kategori tercihleri burada görünür.</p></div>
        </div>

        {!placementRules.length ? (
          <div className="rle-empty">Henüz kural yok. Gerekirse marka veya kategori bazlı tercih ekle.</div>
        ) : (
          <div className="rle-rule-list">
            {placementRules.map((r) => (
              <div className="rle-rule-row" key={r.id}>
                <div>
                  <b>{r.type}: {r.value}</b>
                  <small>Hedef: {r.target_aisle || '-'} {r.target_side || ''} · Davranış: {r.behavior} · Ağırlık: {r.weight}/10</small>
                </div>
                <div className="rle-rule-actions">
                  <button className="btn ghost" onClick={() => removeRule(r.id)}>Sil</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
