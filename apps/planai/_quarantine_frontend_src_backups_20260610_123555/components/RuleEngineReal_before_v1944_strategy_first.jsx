import React, { useMemo, useState } from 'react';
import { DEFAULT_OPTIMIZATION_WEIGHTS } from '../utils/placementRuleAdapter.js';

const RULE_TYPES = [
  { value: 'brand', label: 'Marka', hint: 'Ülker, Eti, Algida, Coca-Cola gibi' },
  { value: 'category', label: 'Kategori', hint: 'Atıştırmalık, içecek, temizlik gibi' },
  { value: 'subcategory', label: 'Alt kategori', hint: 'Bisküvi, su, yoğurt gibi' },
  { value: 'storage', label: 'Storage', hint: 'AMBIENT, CHILLED, FROZEN' },
  { value: 'sku', label: 'SKU', hint: 'Tek ürün kuralı' },
];

const TARGET_ZONES = [
  { value: 'AMBIENT', label: 'Kuru raf', tone: 'green' },
  { value: 'CHILLED', label: '+4 dolap', tone: 'cyan' },
  { value: 'FROZEN', label: '-18 / Donuk', tone: 'purple' },
  { value: 'PRODUCE', label: 'Meyve sebze', tone: 'green' },
  { value: 'LOWER_SHELF', label: 'Alt raf', tone: 'gray' },
  { value: 'EYE_LEVEL', label: 'Göz hizası', tone: 'pink' },
  { value: 'END_OF_AISLE', label: 'Koridor sonu', tone: 'amber' },
];

const BEHAVIORS = [
  { value: 'prefer_zone', label: 'Öncelik ver', desc: 'Uygunsa hedef alanı tercih eder.' },
  { value: 'force_zone', label: 'Sıkı uygula', desc: 'Hard rule bozulmadan hedefi zorlar.' },
  { value: 'keep_together', label: 'Beraber tut', desc: 'Benzer ürünleri yakınlaştırır.' },
  { value: 'separate_from', label: 'Ayır', desc: 'Koku, hijyen veya kategori ayrımı için kullanılır.' },
  { value: 'increase_facing', label: 'Önyüz artır', desc: 'Satış etkisine göre önyüzü artırır.' },
  { value: 'reduce_facing', label: 'Önyüz azalt', desc: 'Alan tüketimini azaltır.' },
];

const WEIGHT_CONTROLS = [
  { key: 'sales_weight', title: 'Satış etkisi', desc: 'Hızlı satan ürünlerin önceliğini belirler.' },
  { key: 'category_weight', title: 'Kategori etkisi', desc: 'Aynı kategori ürünlerini bloklamayı güçlendirir.' },
  { key: 'brand_block_weight', title: 'Marka blok etkisi', desc: 'Markaları toplam satışa göre bloklara ayırır.' },
  { key: 'basket_affinity_weight', title: 'Sepet birlikteliği', desc: 'Beraber alınan ürünleri yakın tutar.' },
  { key: 'refill_cost_weight', title: 'Refill maliyeti', desc: 'Hızlı dönen ürünlerde derinlik kararını etkiler.' },
  { key: 'picker_route_weight', title: 'Picker rota etkisi', desc: 'Toplama kolaylığını öne alır.' },
  { key: 'cold_chain_weight', title: 'Soğuk zincir etkisi', desc: '+4 ve -18 storage doğruluğunu korur.' },
  { key: 'capacity_weight', title: 'Kapasite etkisi', desc: 'Raf ve dolap kapasite kullanımını dengeler.' },
  { key: 'shelf_fill_weight', title: 'Raf doluluk etkisi', desc: 'Raf dolmadan yeni rafa geçmeyi azaltır.' },
];

const BRAND_TARGETS = [
  '#1 marka -> A koridor sağ blok',
  '#2 marka -> A koridor sol blok',
  '#3 marka -> B koridor sağ blok',
  '#4 marka -> B koridor sol blok',
  '#5 marka -> C koridor sağ blok',
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
  return String(p.brand || p.brand_name || p.supplier || '').trim() || 'Markasız';
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
      alert('Kural değeri boş olamaz.');
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
    { title: 'Algida sadece donukta', desc: 'Algida ürünlerini -18 / Algida alanına zorlar.', rule: { type: 'brand', value: 'Algida', target_zone: 'FROZEN', behavior: 'force_zone', priority: 'critical', weight: 10 } },
    { title: '+4 ürün soğukta kalsın', desc: 'Chilled ürünleri ambient rafa düşürmez.', rule: { type: 'storage', value: 'CHILLED', target_zone: 'CHILLED', behavior: 'force_zone', priority: 'critical', weight: 10 } },
    { title: 'Milagro meyve sebze', desc: 'Milagro produce ürünlerini meyve-sebze alanına iter.', rule: { type: 'brand', value: 'Milagro', target_zone: 'PRODUCE', behavior: 'prefer_zone', priority: 'high', weight: 8 } },
    { title: 'Temizlik ayrıştır', desc: 'Kimyasal/temizlik ürünlerini gıdadan uzaklaştırır.', rule: { type: 'category', value: 'Cleaning', target_zone: 'END_OF_AISLE', behavior: 'separate_from', priority: 'high', weight: 8 } },
    { title: 'Coca-Cola göz hizası', desc: 'Hızlı içeceklerde görünürlüğü artırır.', rule: { type: 'brand', value: 'Coca-Cola', target_zone: 'EYE_LEVEL', behavior: 'increase_facing', priority: 'high', weight: 8 } },
  ];

  return (
    <main className="page rle-page">
      <section className="rle-hero">
        <div>
          <div className="section-eyebrow">AI OPTIMIZATION CENTER</div>
          <h1>Kural ve Ağırlık Motoru</h1>
          <p>
            Hibrit planogramda önce hard rule korunur; sonra marka toplam satışı, kategori, sepet birlikteliği,
            picker rota, refill ve kapasite birlikte okunur. Marka içinde SKU sıralaması satışa göre yapılır.
          </p>
        </div>
        <div className="rle-hero-actions">
          <button className="btn primary" onClick={applyAndGenerate}>Kurallarla planı üret</button>
          <button className="btn ghost" onClick={() => setPlacementRules([])}>Tüm kuralları temizle</button>
        </div>
      </section>

      <section className="rle-kpi-grid">
        <div className="rle-kpi"><span>Aktif kural</span><b>{activeRules.length}</b><small>Plan üretiminde uygulanır</small></div>
        <div className="rle-kpi"><span>Pasif kural</span><b>{passiveRules.length}</b><small>Kayıtlı ama çalışmaz</small></div>
        <div className="rle-kpi"><span>Ürün havuzu</span><b>{allProducts.length.toLocaleString('tr-TR')}</b><small>Yerleşen + atanamayan</small></div>
        <div className="rle-kpi"><span>Hibrit mod</span><b>{hybridActive ? 'Açık' : 'Kapalı'}</b><small>Marka bloklu sıralama</small></div>
      </section>

      <section className="rle-weight-panel">
        <div className="rle-card-head">
          <div>
            <h2>Hibrit marka blok modu</h2>
            <p>En yüksek toplam satışa sahip marka ilk bloğu alır. Marka bloğunun içinde SKU’lar satışa göre dizilir.</p>
          </div>
          <button className={hybridActive ? 'btn primary' : 'btn ghost'} onClick={toggleHybridBrandBlock}>
            {hybridActive ? 'Hibrit mod açık' : 'Hibrit modu aç'}
          </button>
        </div>

        <div className="rle-hybrid-grid">
          <div className="rle-hybrid-card">
            <h3>Blok rotası</h3>
            {BRAND_TARGETS.map((x) => <div className="rle-mini-row" key={x}>{x}</div>)}
          </div>
          <div className="rle-hybrid-card">
            <h3>Depodaki en güçlü markalar</h3>
            {topBrands.slice(0, 8).map((b, idx) => (
              <div className="rle-mini-row" key={b.brand}>
                <b>#{idx + 1} {b.brand}</b>
                <span>{Math.round(b.sales).toLocaleString('tr-TR')} satış · {b.sku} SKU</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="rle-weight-panel">
        <div className="rle-card-head">
          <div>
            <h2>Optimizasyon ağırlık profili</h2>
            <p>Satış, kategori, marka blok, sepet birlikteliği, picker rota, refill ve soğuk zincir etkisini yönetir.</p>
          </div>
          <div className="rle-hero-actions">
            <button className="btn ghost" onClick={resetOptimizationWeights}>Varsayılana dön</button>
            <button className="btn primary" onClick={applyAndGenerate}>Ağırlıklarla planı üret</button>
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
              <h2>Kural oluştur</h2>
              <p>Marka, kategori, storage veya SKU bazlı manuel kural ekle.</p>
            </div>
            <Pill tone={selectedTarget?.tone}>{selectedTarget?.label}</Pill>
          </div>

          <div className="rle-form">
            <label><span>Kural tipi</span><select value={draft.type} onChange={(e) => setDraft((d) => ({ ...d, type: e.target.value }))}>{RULE_TYPES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}</select><small>{selectedType?.hint}</small></label>
            <label><span>Değer</span><input value={draft.value} onChange={(e) => setDraft((d) => ({ ...d, value: e.target.value }))} placeholder="Örn: Algida, Ülker, CHILLED..." /><small>{matchedProducts.length.toLocaleString('tr-TR')} SKU eşleşiyor</small></label>
            <label><span>Hedef alan</span><select value={draft.target_zone} onChange={(e) => setDraft((d) => ({ ...d, target_zone: e.target.value }))}>{TARGET_ZONES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}</select><small>Hard storage kuralı bozulmaz.</small></label>
            <label><span>Davranış</span><select value={draft.behavior} onChange={(e) => setDraft((d) => ({ ...d, behavior: e.target.value }))}>{BEHAVIORS.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}</select><small>{selectedBehavior?.desc}</small></label>
            <label><span>Öncelik</span><select value={draft.priority} onChange={(e) => setDraft((d) => ({ ...d, priority: e.target.value }))}><option value="low">Düşük</option><option value="normal">Normal</option><option value="high">Yüksek</option><option value="critical">Kritik</option></select><small>Çakışan kurallarda karar notuna yansır.</small></label>
            <label><span>Ağırlık: {draft.weight}/10</span><input type="range" min="1" max="10" value={draft.weight} onChange={(e) => setDraft((d) => ({ ...d, weight: Number(e.target.value) }))} /><small>Yüksek ağırlık önceliği artırır.</small></label>
          </div>

          {suggestions.length > 0 && (
            <div className="rle-suggestions">
              <b>Hızlı seçim</b>
              <div>{suggestions.map((s) => <button key={s.value} onClick={() => setDraft((d) => ({ ...d, value: s.value }))}>{s.value} <span>{s.count}</span></button>)}</div>
            </div>
          )}

          <div className="rle-preview">
            <div><b>Karar önizlemesi</b><p><strong>{draft.value || 'Seçili değer'}</strong> için {selectedBehavior?.label.toLowerCase()} uygulanır. Hedef: <strong>{selectedTarget?.label}</strong>. Etkilenen ürün: <strong>{matchedProducts.length}</strong>.</p></div>
            <button className="btn primary" onClick={addRule}>Kuralı kaydet</button>
          </div>
        </div>

        <div className="rle-templates">
          <h2>Hazır kural şablonları</h2>
          <p>Tek tıkla en sık kullanılan operasyon kurallarını ekle.</p>
          <div className="rle-template-list">
            {templates.map((t) => <button key={t.title} className="rle-template" onClick={() => applyTemplate(t.rule)}><span>{t.title}</span><small>{t.desc}</small></button>)}
          </div>
        </div>
      </section>

      <section className="rle-rules-card">
        <div className="rle-card-head">
          <div><h2>Aktif kural listesi</h2><p>Bu liste localStorage’da kalır. Plan üretiminden önce ürün havuzuna uygulanır.</p></div>
          <button className="btn ghost" onClick={applyAndGenerate}>Uygula ve yeniden üret</button>
        </div>

        {!placementRules.length ? (
          <div className="rle-empty">Henüz kural yok. Hibrit modu aç veya manuel kural oluştur.</div>
        ) : (
          <div className="rle-rule-list">
            {placementRules.map((rule) => {
              const target = TARGET_ZONES.find((z) => z.value === rule.target_zone);
              return (
                <div className={`rle-rule-row ${rule.active === false ? 'inactive' : ''}`} key={rule.id}>
                  <div><b>{ruleLabel(rule)}</b><small>Öncelik: {rule.priority} · Ağırlık: {rule.weight}/10 · {rule.active === false ? 'Pasif' : 'Aktif'}</small></div>
                  <div className="rle-rule-actions">
                    <Pill tone={target?.tone}>{target?.label || rule.target_zone}</Pill>
                    <button className="btn ghost" onClick={() => toggleRule(rule.id)}>{rule.active === false ? 'Aktif et' : 'Pasifleştir'}</button>
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
