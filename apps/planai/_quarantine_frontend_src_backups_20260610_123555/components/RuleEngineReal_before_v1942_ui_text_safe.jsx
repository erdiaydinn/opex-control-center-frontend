import React, { useMemo, useState } from 'react';
import { DEFAULT_OPTIMIZATION_WEIGHTS } from '../utils/placementRuleAdapter.js';

const RULE_TYPES = [
  { value: 'brand', label: 'Marka', hint: '\u00DClker, Eti, Algida, Coca-Cola gibi' },
  { value: 'category', label: 'Kategori', hint: 'At\u0131\u015Ft\u0131rmal\u0131k, i\u00E7ecek, temizlik gibi' },
  { value: 'subcategory', label: 'Alt kategori', hint: 'Bisk\u00FCvi, su, yo\u011Furt gibi' },
  { value: 'storage', label: 'Storage', hint: 'AMBIENT, CHILLED, FROZEN' },
  { value: 'sku', label: 'SKU', hint: 'Tek \u00FCr\u00FCn kural\u0131' },
];

const TARGET_ZONES = [
  { value: 'AMBIENT', label: 'Kuru raf', tone: 'green' },
  { value: 'CHILLED', label: '+4 dolap', tone: 'cyan' },
  { value: 'FROZEN', label: '-18 / Donuk', tone: 'purple' },
  { value: 'PRODUCE', label: 'Meyve sebze', tone: 'green' },
  { value: 'LOWER_SHELF', label: 'Alt raf', tone: 'gray' },
  { value: 'EYE_LEVEL', label: 'G\u00F6z hizas\u0131', tone: 'pink' },
  { value: 'END_OF_AISLE', label: 'Koridor sonu', tone: 'amber' },
];

const BEHAVIORS = [
  { value: 'prefer_zone', label: '\u00D6ncelik ver', desc: 'Uygunsa hedef alan\u0131 tercih eder.' },
  { value: 'force_zone', label: 'S\u0131k\u0131 uygula', desc: 'Hard rule bozulmadan hedefi zorlar.' },
  { value: 'keep_together', label: 'Beraber tut', desc: 'Benzer \u00FCr\u00FCnleri yak\u0131nla\u015Ft\u0131r\u0131r.' },
  { value: 'separate_from', label: 'Ay\u0131r', desc: 'Koku, hijyen veya kategori ayr\u0131m\u0131 i\u00E7in kullan\u0131l\u0131r.' },
  { value: 'increase_facing', label: '\u00D6ny\u00FCz art\u0131r', desc: 'Sat\u0131\u015F etkisine g\u00F6re \u00F6ny\u00FCz\u00FC art\u0131r\u0131r.' },
  { value: 'reduce_facing', label: '\u00D6ny\u00FCz azalt', desc: 'Alan t\u00FCketimini azalt\u0131r.' },
];

const WEIGHT_CONTROLS = [
  { key: 'sales_weight', title: 'Sat\u0131\u015F etkisi', desc: 'H\u0131zl\u0131 satan \u00FCr\u00FCnlerin \u00F6nceli\u011Fini belirler.' },
  { key: 'category_weight', title: 'Kategori etkisi', desc: 'Ayn\u0131 kategori \u00FCr\u00FCnlerini bloklamay\u0131 g\u00FC\u00E7lendirir.' },
  { key: 'brand_block_weight', title: 'Marka blok etkisi', desc: 'Markalar\u0131 toplam sat\u0131\u015Fa g\u00F6re bloklara ay\u0131r\u0131r.' },
  { key: 'basket_affinity_weight', title: 'Sepet birlikteli\u011Fi', desc: 'Beraber al\u0131nan \u00FCr\u00FCnleri yak\u0131n tutar.' },
  { key: 'refill_cost_weight', title: 'Refill maliyeti', desc: 'H\u0131zl\u0131 d\u00F6nen \u00FCr\u00FCnlerde derinlik karar\u0131n\u0131 etkiler.' },
  { key: 'picker_route_weight', title: 'Picker rota etkisi', desc: 'Toplama kolayl\u0131\u011F\u0131n\u0131 \u00F6ne al\u0131r.' },
  { key: 'cold_chain_weight', title: 'So\u011Fuk zincir etkisi', desc: '+4 ve -18 storage do\u011Frulu\u011Funu korur.' },
  { key: 'capacity_weight', title: 'Kapasite etkisi', desc: 'Raf ve dolap kapasite kullan\u0131m\u0131n\u0131 dengeler.' },
  { key: 'shelf_fill_weight', title: 'Raf doluluk etkisi', desc: 'Raf dolmadan yeni rafa ge\u00E7meyi azalt\u0131r.' },
];

const BRAND_TARGETS = [
  '#1 marka -> A koridor sa\u011F blok',
  '#2 marka -> A koridor sol blok',
  '#3 marka -> B koridor sa\u011F blok',
  '#4 marka -> B koridor sol blok',
  '#5 marka -> C koridor sa\u011F blok',
  '#6 marka -> C koridor sol blok',
];

function emptyDraft() {
  return {
    type: 'brand',
    value: '',
    target_zone: 'AMBIENT',
    behavior: 'prefer_zone',
    priority: 'normal',
    weight: 7,
    active: true,
  };
}

function salesOf(p = {}) {
  const n = Number(p.sales || p.sales_qty_7d || p.sales_7d || p.sales_qty_30d || p.daily_sales || 0);
  return Number.isFinite(n) ? n : 0;
}

function brandOf(p = {}) {
  return String(p.brand || p.brand_name || p.supplier || '').trim() || 'Markas\u0131z';
}

function norm(value) {
  return String(value || '').toUpperCase().replaceAll('İ', 'I').replaceAll('Ş', 'S').replaceAll('Ğ', 'G').replaceAll('Ü', 'U').replaceAll('Ö', 'O').replaceAll('Ç', 'C').trim();
}

function fieldOf(product, type) {
  const map = {
    brand: [product.brand, product.brand_name],
    category: [product.category, product.category_l1, product.category_l2],
    subcategory: [product.subcategory, product.category_l2, product.category_l3],
    storage: [product.storage, product.storage_type, product.storage_class],
    sku: [product.sku, product.SKU, product.barcode, product.Barcodes],
  };
  return (map[type] || []).filter(Boolean).join(' ');
}

function ruleMatches(product, draft) {
  const q = norm(draft.value);
  if (!q) return false;
  const selected = norm(fieldOf(product, draft.type));
  if (selected) return selected.includes(q);
  return norm(Object.values(product || {}).join(' ')).includes(q);
}

function ruleLabel(rule) {
  if (rule.behavior === 'hybrid_brand_block' || rule.value === 'HYBRID_BRAND_BLOCK') {
    return 'Hibrit marka blok modu';
  }
  const type = RULE_TYPES.find((x) => x.value === rule.type)?.label || rule.type;
  const target = TARGET_ZONES.find((x) => x.value === rule.target_zone)?.label || rule.target_zone;
  const behavior = BEHAVIORS.find((x) => x.value === rule.behavior)?.label || rule.behavior;
  return `${type}: ${rule.value || '-'} -> ${target} / ${behavior}`;
}

function Pill({ children, tone = 'gray' }) {
  return <span className={`rle-pill ${tone}`}>{children}</span>;
}

function WeightSlider({ item, value, onChange }) {
  return (
    <div className="rle-weight-row">
      <div>
        <b>{item.title}</b>
        <small>{item.desc}</small>
      </div>
      <div className="rle-weight-control">
        <input type="range" min="1" max="10" value={value} onChange={(e) => onChange(item.key, Number(e.target.value))} />
        <span>{value}</span>
      </div>
    </div>
  );
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
  const [draft, setDraft] = useState(emptyDraft());
  const allProducts = useMemo(() => [...(products || []), ...(unplacedProducts || [])], [products, unplacedProducts]);

  const hybridActive = placementRules.some((r) => r.active !== false && (r.behavior === 'hybrid_brand_block' || r.value === 'HYBRID_BRAND_BLOCK'));

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

  const matchedProducts = useMemo(() => {
    if (!draft.value) return [];
    return allProducts.filter((p) => ruleMatches(p, draft));
  }, [allProducts, draft]);

  const suggestions = useMemo(() => {
    const values = new Map();
    for (const p of allProducts) {
      const raw = fieldOf(p, draft.type);
      if (!raw) continue;
      String(raw).split(',').map((x) => x.trim()).filter(Boolean).slice(0, 3).forEach((x) => values.set(x, (values.get(x) || 0) + 1));
    }
    return [...values.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12).map(([value, count]) => ({ value, count }));
  }, [allProducts, draft.type]);

  const activeRules = placementRules.filter((r) => r.active !== false);
  const passiveRules = placementRules.filter((r) => r.active === false);

  function updateOptimizationWeight(key, value) {
    if (typeof setOptimizationWeights !== 'function') return;
    setOptimizationWeights((prev = DEFAULT_OPTIMIZATION_WEIGHTS) => ({
      ...DEFAULT_OPTIMIZATION_WEIGHTS,
      ...(prev || {}),
      [key]: value,
    }));
  }

  function resetOptimizationWeights() {
    if (typeof setOptimizationWeights === 'function') {
      setOptimizationWeights(DEFAULT_OPTIMIZATION_WEIGHTS);
    }
  }

  function addRule() {
    const value = String(draft.value || '').trim();
    if (!value) {
      alert('Kural de\u011Feri bo\u015F olamaz.');
      return;
    }

    setPlacementRules((prev = []) => [
      { ...draft, value, id: `RULE-${Date.now()}`, created_at: new Date().toISOString() },
      ...prev,
    ]);
    setDraft(emptyDraft());
  }

  function toggleHybridBrandBlock() {
    if (hybridActive) {
      setPlacementRules((prev = []) => prev.filter((r) => !(r.behavior === 'hybrid_brand_block' || r.value === 'HYBRID_BRAND_BLOCK')));
      return;
    }

    setPlacementRules((prev = []) => [
      {
        id: 'SYSTEM-HYBRID-BRAND-BLOCK',
        type: 'hybrid_brand_block',
        value: 'HYBRID_BRAND_BLOCK',
        target_zone: 'BRAND_BLOCK',
        behavior: 'hybrid_brand_block',
        priority: 'critical',
        weight: 10,
        active: true,
        created_at: new Date().toISOString(),
      },
      ...prev,
    ]);
  }

  function applyTemplate(template) {
    setPlacementRules((prev = []) => [{ ...template, id: `RULE-${Date.now()}`, active: true, created_at: new Date().toISOString() }, ...prev]);
  }

  function removeRule(id) {
    setPlacementRules((prev = []) => prev.filter((r) => r.id !== id));
  }

  function toggleRule(id) {
    setPlacementRules((prev = []) => prev.map((r) => (r.id === id ? { ...r, active: !r.active } : r)));
  }

  async function applyAndGenerate() {
    if (typeof onGenerate === 'function') await onGenerate();
  }

  const selectedType = RULE_TYPES.find((x) => x.value === draft.type);
  const selectedTarget = TARGET_ZONES.find((x) => x.value === draft.target_zone);
  const selectedBehavior = BEHAVIORS.find((x) => x.value === draft.behavior);

  const templates = [
    { title: 'Algida sadece donukta', desc: 'Algida \u00FCr\u00FCnlerini -18 / Algida alan\u0131na zorlar.', rule: { type: 'brand', value: 'Algida', target_zone: 'FROZEN', behavior: 'force_zone', priority: 'critical', weight: 10 } },
    { title: '+4 \u00FCr\u00FCn so\u011Fukta kals\u0131n', desc: 'Chilled \u00FCr\u00FCnleri ambient rafa d\u00FC\u015F\u00FCrmez.', rule: { type: 'storage', value: 'CHILLED', target_zone: 'CHILLED', behavior: 'force_zone', priority: 'critical', weight: 10 } },
    { title: 'Milagro meyve sebze', desc: 'Milagro produce \u00FCr\u00FCnlerini meyve-sebze alan\u0131na iter.', rule: { type: 'brand', value: 'Milagro', target_zone: 'PRODUCE', behavior: 'prefer_zone', priority: 'high', weight: 8 } },
    { title: 'Temizlik ayr\u0131\u015Ft\u0131r', desc: 'Kimyasal/temizlik \u00FCr\u00FCnlerini g\u0131dadan uzakla\u015Ft\u0131r\u0131r.', rule: { type: 'category', value: 'Cleaning', target_zone: 'END_OF_AISLE', behavior: 'separate_from', priority: 'high', weight: 8 } },
    { title: 'Coca-Cola g\u00F6z hizas\u0131', desc: 'H\u0131zl\u0131 i\u00E7eceklerde g\u00F6r\u00FCn\u00FCrl\u00FC\u011F\u00FC art\u0131r\u0131r.', rule: { type: 'brand', value: 'Coca-Cola', target_zone: 'EYE_LEVEL', behavior: 'increase_facing', priority: 'high', weight: 8 } },
  ];

  return (
    <main className="page rle-page">
      <section className="rle-hero">
        <div>
          <div className="section-eyebrow">AI OPTIMIZATION CENTER</div>
          <h1>Kural ve A\u011F\u0131rl\u0131k Motoru</h1>
          <p>
            Hibrit planogramda \u00F6nce hard rule korunur; sonra marka toplam sat\u0131\u015F\u0131, kategori, sepet birlikteli\u011Fi,
            picker rota, refill ve kapasite birlikte okunur. Marka i\u00E7inde SKU s\u0131ralamas\u0131 sat\u0131\u015Fa g\u00F6re yap\u0131l\u0131r.
          </p>
        </div>
        <div className="rle-hero-actions">
          <button className="btn primary" onClick={applyAndGenerate}>Kurallarla plan\u0131 \u00FCret</button>
          <button className="btn ghost" onClick={() => setPlacementRules([])}>T\u00FCm kurallar\u0131 temizle</button>
        </div>
      </section>

      <section className="rle-kpi-grid">
        <div className="rle-kpi"><span>Aktif kural</span><b>{activeRules.length}</b><small>Plan \u00FCretiminde uygulan\u0131r</small></div>
        <div className="rle-kpi"><span>Pasif kural</span><b>{passiveRules.length}</b><small>Kay\u0131tl\u0131 ama \u00E7al\u0131\u015Fmaz</small></div>
        <div className="rle-kpi"><span>\u00DCr\u00FCn havuzu</span><b>{allProducts.length.toLocaleString('tr-TR')}</b><small>Yerle\u015Fen + atanamayan</small></div>
        <div className="rle-kpi"><span>Hibrit mod</span><b>{hybridActive ? 'A\u00E7\u0131k' : 'Kapal\u0131'}</b><small>Marka bloklu s\u0131ralama</small></div>
      </section>

      <section className="rle-weight-panel">
        <div className="rle-card-head">
          <div>
            <h2>Hibrit marka blok modu</h2>
            <p>En y\u00FCksek toplam sat\u0131\u015Fa sahip marka ilk blo\u011Fu al\u0131r. Marka blo\u011Funun i\u00E7inde SKU’lar sat\u0131\u015Fa g\u00F6re dizilir.</p>
          </div>
          <button className={hybridActive ? 'btn primary' : 'btn ghost'} onClick={toggleHybridBrandBlock}>
            {hybridActive ? 'Hibrit mod a\u00E7\u0131k' : 'Hibrit modu a\u00E7'}
          </button>
        </div>

        <div className="rle-hybrid-grid">
          <div className="rle-hybrid-card">
            <h3>Blok rotas\u0131</h3>
            {BRAND_TARGETS.map((x) => <div className="rle-mini-row" key={x}>{x}</div>)}
          </div>
          <div className="rle-hybrid-card">
            <h3>Depodaki en g\u00FC\u00E7l\u00FC markalar</h3>
            {topBrands.slice(0, 8).map((b, idx) => (
              <div className="rle-mini-row" key={b.brand}>
                <b>#{idx + 1} {b.brand}</b>
                <span>{Math.round(b.sales).toLocaleString('tr-TR')} sat\u0131\u015F · {b.sku} SKU</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="rle-weight-panel">
        <div className="rle-card-head">
          <div>
            <h2>Optimizasyon a\u011F\u0131rl\u0131k profili</h2>
            <p>Sat\u0131\u015F, kategori, marka blok, sepet birlikteli\u011Fi, picker rota, refill ve so\u011Fuk zincir etkisini y\u00F6netir.</p>
          </div>
          <div className="rle-hero-actions">
            <button className="btn ghost" onClick={resetOptimizationWeights}>Varsay\u0131lana d\u00F6n</button>
            <button className="btn primary" onClick={applyAndGenerate}>A\u011F\u0131rl\u0131klarla plan\u0131 \u00FCret</button>
          </div>
        </div>

        <div className="rle-weight-grid">
          {WEIGHT_CONTROLS.map((item) => (
            <WeightSlider
              key={item.key}
              item={item}
              value={optimizationWeights?.[item.key] ?? DEFAULT_OPTIMIZATION_WEIGHTS[item.key]}
              onChange={updateOptimizationWeight}
            />
          ))}
        </div>
      </section>

      <section className="rle-layout">
        <div className="rle-builder">
          <div className="rle-card-head">
            <div>
              <h2>Kural olu\u015Ftur</h2>
              <p>Marka, kategori, storage veya SKU bazl\u0131 manuel kural ekle.</p>
            </div>
            <Pill tone={selectedTarget?.tone}>{selectedTarget?.label}</Pill>
          </div>

          <div className="rle-form">
            <label><span>Kural tipi</span><select value={draft.type} onChange={(e) => setDraft((d) => ({ ...d, type: e.target.value }))}>{RULE_TYPES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}</select><small>{selectedType?.hint}</small></label>
            <label><span>De\u011Fer</span><input value={draft.value} onChange={(e) => setDraft((d) => ({ ...d, value: e.target.value }))} placeholder="\u00D6rn: Algida, \u00DClker, CHILLED..." /><small>{matchedProducts.length.toLocaleString('tr-TR')} SKU e\u015Fle\u015Fiyor</small></label>
            <label><span>Hedef alan</span><select value={draft.target_zone} onChange={(e) => setDraft((d) => ({ ...d, target_zone: e.target.value }))}>{TARGET_ZONES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}</select><small>Hard storage kural\u0131 bozulmaz.</small></label>
            <label><span>Davran\u0131\u015F</span><select value={draft.behavior} onChange={(e) => setDraft((d) => ({ ...d, behavior: e.target.value }))}>{BEHAVIORS.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}</select><small>{selectedBehavior?.desc}</small></label>
            <label><span>\u00D6ncelik</span><select value={draft.priority} onChange={(e) => setDraft((d) => ({ ...d, priority: e.target.value }))}><option value="low">D\u00FC\u015F\u00FCk</option><option value="normal">Normal</option><option value="high">Y\u00FCksek</option><option value="critical">Kritik</option></select><small>\u00C7ak\u0131\u015Fan kurallarda karar notuna yans\u0131r.</small></label>
            <label><span>A\u011F\u0131rl\u0131k: {draft.weight}/10</span><input type="range" min="1" max="10" value={draft.weight} onChange={(e) => setDraft((d) => ({ ...d, weight: Number(e.target.value) }))} /><small>Y\u00FCksek a\u011F\u0131rl\u0131k \u00F6nceli\u011Fi art\u0131r\u0131r.</small></label>
          </div>

          {suggestions.length > 0 && (
            <div className="rle-suggestions">
              <b>H\u0131zl\u0131 se\u00E7im</b>
              <div>{suggestions.map((s) => <button key={s.value} onClick={() => setDraft((d) => ({ ...d, value: s.value }))}>{s.value} <span>{s.count}</span></button>)}</div>
            </div>
          )}

          <div className="rle-preview">
            <div><b>Karar \u00F6nizlemesi</b><p><strong>{draft.value || 'Se\u00E7ili de\u011Fer'}</strong> i\u00E7in {selectedBehavior?.label.toLowerCase()} uygulan\u0131r. Hedef: <strong>{selectedTarget?.label}</strong>. Etkilenen \u00FCr\u00FCn: <strong>{matchedProducts.length}</strong>.</p></div>
            <button className="btn primary" onClick={addRule}>Kural\u0131 kaydet</button>
          </div>
        </div>

        <div className="rle-templates">
          <h2>Haz\u0131r kural \u015Fablonlar\u0131</h2>
          <p>Tek t\u0131kla en s\u0131k kullan\u0131lan operasyon kurallar\u0131n\u0131 ekle.</p>
          <div className="rle-template-list">
            {templates.map((t) => <button key={t.title} className="rle-template" onClick={() => applyTemplate(t.rule)}><span>{t.title}</span><small>{t.desc}</small></button>)}
          </div>
        </div>
      </section>

      <section className="rle-rules-card">
        <div className="rle-card-head">
          <div><h2>Aktif kural listesi</h2><p>Bu liste localStorage’da kal\u0131r. Plan \u00FCretiminden \u00F6nce \u00FCr\u00FCn havuzuna uygulan\u0131r.</p></div>
          <button className="btn ghost" onClick={applyAndGenerate}>Uygula ve yeniden \u00FCret</button>
        </div>

        {!placementRules.length ? (
          <div className="rle-empty">Hen\u00FCz kural yok. Hibrit modu a\u00E7 veya manuel kural olu\u015Ftur.</div>
        ) : (
          <div className="rle-rule-list">
            {placementRules.map((rule) => {
              const target = TARGET_ZONES.find((z) => z.value === rule.target_zone);
              return (
                <div className={`rle-rule-row ${rule.active === false ? 'inactive' : ''}`} key={rule.id}>
                  <div><b>{ruleLabel(rule)}</b><small>\u00D6ncelik: {rule.priority} · A\u011F\u0131rl\u0131k: {rule.weight}/10 · {rule.active === false ? 'Pasif' : 'Aktif'}</small></div>
                  <div className="rle-rule-actions">
                    <Pill tone={target?.tone}>{target?.label || rule.target_zone}</Pill>
                    <button className="btn ghost" onClick={() => toggleRule(rule.id)}>{rule.active === false ? 'Aktif et' : 'Pasifle\u015Ftir'}</button>
                    <button className="btn ghost" onClick={() => removeRule(rule.id)}>Sil</button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
