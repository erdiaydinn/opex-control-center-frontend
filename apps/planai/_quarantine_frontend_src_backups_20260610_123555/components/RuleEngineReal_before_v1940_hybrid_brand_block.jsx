import React, { useMemo, useState } from 'react';
import { DEFAULT_OPTIMIZATION_WEIGHTS } from '../utils/placementRuleAdapter.js';

const RULE_TYPES = [
  { value: 'brand', label: 'Marka', hint: 'Ülker, Algida, Coca-Cola gibi' },
  { value: 'category', label: 'Kategori', hint: 'Beverages, Cleaning, Snacks gibi' },
  { value: 'subcategory', label: 'Alt kategori', hint: 'Water, Chocolate, Dairy gibi' },
  { value: 'storage', label: 'Storage', hint: 'AMBIENT, CHILLED, FROZEN' },
  { value: 'sku', label: 'SKU', hint: 'MRK.00506 gibi tek ürün' },
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
  { value: 'prefer_zone', label: 'Öncelik ver', desc: 'Uygunsa hedef bölgeyi tercih eder.' },
  { value: 'force_zone', label: 'Sıkı uygula', desc: 'Storage hard rule bozulmadan hedefi zorlar.' },
  { value: 'keep_together', label: 'Beraber tut', desc: 'Benzer/ilişkili ürünleri yakınlaştırır.' },
  { value: 'separate_from', label: 'Ayır', desc: 'Koku, hijyen veya kategori ayrımı için kullanılır.' },
  { value: 'increase_facing', label: 'Facing artır', desc: 'Ön yüz önceliği yükseltir.' },
  { value: 'reduce_facing', label: 'Facing azalt', desc: 'Alan tüketimini düşürür.' },
];


const WEIGHT_CONTROLS = [
  {
    key: 'sales_weight',
    title: 'Sat?? etkisi',
    desc: 'H?zl? satan ?r?nlerin daha g??l? ?ncelik almas?n? sa?lar.',
  },
  {
    key: 'category_weight',
    title: 'Kategori etkisi',
    desc: 'Ayn? kategori ?r?nlerinin daha d?zenli bloklanmas?n? sa?lar.',
  },
  {
    key: 'brand_block_weight',
    title: 'Marka blok etkisi',
    desc: 'Ayn? marka ?r?nlerini m?mk?n oldu?unca yak?n tutar.',
  },
  {
    key: 'basket_affinity_weight',
    title: 'Sepet birlikteli?i',
    desc: 'Birlikte al?nan ?r?nleri yak?nla?t?r?r.',
  },
  {
    key: 'refill_cost_weight',
    title: 'Refill maliyeti',
    desc: 'H?zl? d?nen ?r?nlerde derinlik ve eri?im karar?n? g??lendirir.',
  },
  {
    key: 'picker_route_weight',
    title: 'Picker rota etkisi',
    desc: 'A??r/b?y?k ?r?nlerde toplama kolayl???n? art?r?r.',
  },
  {
    key: 'cold_chain_weight',
    title: 'So?uk zincir etkisi',
    desc: '+4 ve -18 ?r?nlerde storage do?rulu?unu en y?ksek ?ncelikte tutar.',
  },
  {
    key: 'capacity_weight',
    title: 'Kapasite etkisi',
    desc: 'Raf/dolap kapasite kullan?m?n? dengeler.',
  },
  {
    key: 'shelf_fill_weight',
    title: 'Raf doluluk etkisi',
    desc: 'Raf? gereksiz erken terk etmeyi azalt?r.',
  },
];

function WeightSlider({ item, value, onChange }) {
  return (
    <div className="rle-weight-row">
      <div>
        <b>{item.title}</b>
        <small>{item.desc}</small>
      </div>
      <div className="rle-weight-control">
        <input
          type="range"
          min="1"
          max="10"
          value={value}
          onChange={(e) => onChange(item.key, Number(e.target.value))}
        />
        <span>{value}</span>
      </div>
    </div>
  );
}

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

function norm(value) {
  return String(value || '')
    .toUpperCase()
    .replaceAll('İ', 'I')
    .replaceAll('Ş', 'S')
    .replaceAll('Ğ', 'G')
    .replaceAll('Ü', 'U')
    .replaceAll('Ö', 'O')
    .replaceAll('Ç', 'C')
    .trim();
}

function getProductField(product, type) {
  const map = {
    brand: [product.brand, product.brand_name],
    category: [product.category, product.category_l1, product['Category L1']],
    subcategory: [product.subcategory, product.category_l2, product['Category L2']],
    storage: [product.storage, product.storage_type, product.storage_class],
    sku: [product.sku, product.SKU, product.barcode, product.Barcodes],
  };

  return (map[type] || []).filter(Boolean).join(' ');
}

function ruleMatches(product, draft) {
  const q = norm(draft.value);
  if (!q) return false;

  const selected = norm(getProductField(product, draft.type));
  if (selected) return selected.includes(q);

  const all = norm([
    product.sku,
    product.SKU,
    product.name,
    product.product_name,
    product.brand,
    product.brand_name,
    product.category,
    product.category_l1,
    product.category_l2,
    product.storage,
    product.storage_type,
  ].filter(Boolean).join(' '));

  return all.includes(q);
}

function ruleLabel(rule) {
  const type = RULE_TYPES.find((x) => x.value === rule.type)?.label || rule.type;
  const target = TARGET_ZONES.find((x) => x.value === rule.target_zone)?.label || rule.target_zone;
  const behavior = BEHAVIORS.find((x) => x.value === rule.behavior)?.label || rule.behavior;

  return `${type}: ${rule.value || '-'} → ${target} / ${behavior}`;
}

function Pill({ children, tone = 'gray' }) {
  return <span className={`rle-pill ${tone}`}>{children}</span>;
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

  const matchedProducts = useMemo(() => {
    if (!draft.value) return [];
    return allProducts.filter((p) => ruleMatches(p, draft));
  }, [allProducts, draft]);

  const suggestions = useMemo(() => {
    const values = new Map();

    for (const p of allProducts) {
      const raw = getProductField(p, draft.type);
      if (!raw) continue;

      String(raw)
        .split(',')
        .map((x) => x.trim())
        .filter(Boolean)
        .slice(0, 3)
        .forEach((x) => values.set(x, (values.get(x) || 0) + 1));
    }

    return [...values.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12)
      .map(([value, count]) => ({ value, count }));
  }, [allProducts, draft.type]);

  const activeRules = placementRules.filter((r) => r.active !== false);

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
  const passiveRules = placementRules.filter((r) => r.active === false);

  function setDraftField(key, value) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function addRule() {
    const value = String(draft.value || '').trim();

    if (!value) {
      alert('Kural değeri boş. Örnek: Ülker, Algida, CHILLED, MRK.00506');
      return;
    }

    const nextRule = {
      ...draft,
      value,
      id: `RULE-${Date.now()}`,
      created_at: new Date().toISOString(),
    };

    setPlacementRules((prev = []) => [nextRule, ...prev]);
    setDraft(emptyDraft());
  }

  function applyTemplate(template) {
    setPlacementRules((prev = []) => [
      {
        ...template,
        id: `RULE-${Date.now()}`,
        active: true,
        created_at: new Date().toISOString(),
      },
      ...prev,
    ]);
  }

  function removeRule(id) {
    setPlacementRules((prev = []) => prev.filter((r) => r.id !== id));
  }

  function toggleRule(id) {
    setPlacementRules((prev = []) =>
      prev.map((r) => (r.id === id ? { ...r, active: !r.active } : r))
    );
  }

  async function applyAndGenerate() {
    if (typeof onGenerate === 'function') {
      await onGenerate();
    }
  }

  const selectedType = RULE_TYPES.find((x) => x.value === draft.type);
  const selectedTarget = TARGET_ZONES.find((x) => x.value === draft.target_zone);
  const selectedBehavior = BEHAVIORS.find((x) => x.value === draft.behavior);

  const templates = [
    {
      title: 'Algida sadece donukta',
      desc: 'Algida ürünlerini -18 / Algida alanına zorlar.',
      rule: { type: 'brand', value: 'Algida', target_zone: 'FROZEN', behavior: 'force_zone', priority: 'critical', weight: 10 },
    },
    {
      title: '+4 ürün soğukta kalsın',
      desc: 'Chilled ürünleri ambient rafa düşürmez.',
      rule: { type: 'storage', value: 'CHILLED', target_zone: 'CHILLED', behavior: 'force_zone', priority: 'critical', weight: 10 },
    },
    {
      title: 'Milagro meyve sebze',
      desc: 'Milagro produce ürünlerini meyve-sebze alanına iter.',
      rule: { type: 'brand', value: 'Milagro', target_zone: 'PRODUCE', behavior: 'prefer_zone', priority: 'high', weight: 8 },
    },
    {
      title: 'Temizlik ayrıştır',
      desc: 'Kimyasal/temizlik ürünlerini gıdadan uzaklaştırır.',
      rule: { type: 'category', value: 'Cleaning', target_zone: 'END_OF_AISLE', behavior: 'separate_from', priority: 'high', weight: 8 },
    },
    {
      title: 'Coca-Cola göz hizası',
      desc: 'Hızlı içeceklerde görünürlük etkisini artırır.',
      rule: { type: 'brand', value: 'Coca-Cola', target_zone: 'EYE_LEVEL', behavior: 'increase_facing', priority: 'high', weight: 8 },
    },
    {
      title: 'Ülker kuru rafta',
      desc: 'Ülker ambient ürünlerini kuru raf tarafına iter.',
      rule: { type: 'brand', value: 'Ülker', target_zone: 'AMBIENT', behavior: 'prefer_zone', priority: 'normal', weight: 7 },
    },
  ];

  return (
    <main className="page rle-page">
      <section className="rle-hero">
        <div>
          <div className="section-eyebrow">AI OPTIMIZATION CENTER</div>
          <h1>Kural ve Ağırlık Motoru</h1>
          <p>
            Kural ekle, etkisini gör, planı yeniden üret. Storage hard rule ezilmez; kural motoru
            yerleşim önceliği, facing, yakınlık ve karar açıklamasını etkiler.
          </p>
        </div>

        <div className="rle-hero-actions">
          <button className="btn primary" onClick={applyAndGenerate}>Kurallarla planı üret</button>
          <button className="btn ghost" onClick={() => setPlacementRules([])}>Tüm kuralları temizle</button>
        </div>
      </section>

      <section className="rle-kpi-grid">
        <div className="rle-kpi">
          <span>Aktif kural</span>
          <b>{activeRules.length}</b>
          <small>Plan üretiminde uygulanır</small>
        </div>
        <div className="rle-kpi">
          <span>Pasif kural</span>
          <b>{passiveRules.length}</b>
          <small>Kayıtlı ama çalışmaz</small>
        </div>
        <div className="rle-kpi">
          <span>Ürün havuzu</span>
          <b>{allProducts.length.toLocaleString('tr-TR')}</b>
          <small>Yerleşen + atanamayan</small>
        </div>
        <div className="rle-kpi">
          <span>Taslak eşleşme</span>
          <b>{matchedProducts.length.toLocaleString('tr-TR')}</b>
          <small>Şu anki değerle</small>
        </div>
      </section>

      <section className="rle-weight-panel">
        <div className="rle-card-head">
          <div>
            <h2>Optimizasyon a??rl?k profili</h2>
            <p>Bu ayarlar sat??, kategori, marka, sepet birlikteli?i, picker rota, refill ve so?uk zincir etkisini y?netir.</p>
          </div>
          <div className="rle-hero-actions">
            <button className="btn ghost" onClick={resetOptimizationWeights}>Varsay?lana d?n</button>
            <button className="btn primary" onClick={applyAndGenerate}>A??rl?klarla plan? ?ret</button>
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
              <p>Bir kural tipi seç, değer gir, hedefi ve davranışı belirle.</p>
            </div>
            <Pill tone={selectedTarget?.tone}>{selectedTarget?.label}</Pill>
          </div>

          <div className="rle-form">
            <label>
              <span>Kural tipi</span>
              <select value={draft.type} onChange={(e) => setDraftField('type', e.target.value)}>
                {RULE_TYPES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
              </select>
              <small>{selectedType?.hint}</small>
            </label>

            <label>
              <span>Değer</span>
              <input
                value={draft.value}
                onChange={(e) => setDraftField('value', e.target.value)}
                placeholder="Örn: Algida, Ülker, CHILLED..."
              />
              <small>{matchedProducts.length.toLocaleString('tr-TR')} SKU eşleşiyor</small>
            </label>

            <label>
              <span>Hedef alan</span>
              <select value={draft.target_zone} onChange={(e) => setDraftField('target_zone', e.target.value)}>
                {TARGET_ZONES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
              </select>
              <small>Hard storage kuralı bozulmaz.</small>
            </label>

            <label>
              <span>Davranış</span>
              <select value={draft.behavior} onChange={(e) => setDraftField('behavior', e.target.value)}>
                {BEHAVIORS.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
              </select>
              <small>{selectedBehavior?.desc}</small>
            </label>

            <label>
              <span>Öncelik</span>
              <select value={draft.priority} onChange={(e) => setDraftField('priority', e.target.value)}>
                <option value="low">Düşük</option>
                <option value="normal">Normal</option>
                <option value="high">Yüksek</option>
                <option value="critical">Kritik</option>
              </select>
              <small>Çakışan kurallarda karar notuna yansır.</small>
            </label>

            <label>
              <span>Ağırlık: {draft.weight}/10</span>
              <input
                type="range"
                min="1"
                max="10"
                value={draft.weight}
                onChange={(e) => setDraftField('weight', Number(e.target.value))}
              />
              <small>Yüksek ağırlık ürün önceliğini artırır.</small>
            </label>
          </div>

          {suggestions.length > 0 && (
            <div className="rle-suggestions">
              <b>Hızlı seçim</b>
              <div>
                {suggestions.map((s) => (
                  <button key={s.value} onClick={() => setDraftField('value', s.value)}>
                    {s.value} <span>{s.count}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="rle-preview">
            <div>
              <b>Karar önizlemesi</b>
              <p>
                <strong>{draft.value || 'Seçili değer'}</strong> için {selectedBehavior?.label.toLowerCase()} uygulanır.
                Hedef: <strong>{selectedTarget?.label}</strong>. Etkilenen ürün: <strong>{matchedProducts.length}</strong>.
              </p>
            </div>
            <button className="btn primary" onClick={addRule}>Kuralı kaydet</button>
          </div>
        </div>

        <div className="rle-templates">
          <h2>Hazır kural şablonları</h2>
          <p>Tek tıkla sahada en sık kullanılan operasyon kurallarını ekle.</p>

          <div className="rle-template-list">
            {templates.map((t) => (
              <button key={t.title} className="rle-template" onClick={() => applyTemplate(t.rule)}>
                <span>{t.title}</span>
                <small>{t.desc}</small>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="rle-rules-card">
        <div className="rle-card-head">
          <div>
            <h2>Aktif kural listesi</h2>
            <p>Bu liste localStorage’da kalır. Plan üretiminden önce ürün havuzuna uygulanır.</p>
          </div>
          <button className="btn ghost" onClick={applyAndGenerate}>Uygula ve yeniden üret</button>
        </div>

        {!placementRules.length ? (
          <div className="rle-empty">
            Henüz kural yok. Soldan kural oluştur veya sağdaki şablonlardan birini uygula.
          </div>
        ) : (
          <div className="rle-rule-list">
            {placementRules.map((rule) => {
              const target = TARGET_ZONES.find((z) => z.value === rule.target_zone);

              return (
                <div className={`rle-rule-row ${rule.active === false ? 'inactive' : ''}`} key={rule.id}>
                  <div>
                    <b>{ruleLabel(rule)}</b>
                    <small>
                      Öncelik: {rule.priority} · Ağırlık: {rule.weight}/10 · {rule.active === false ? 'Pasif' : 'Aktif'}
                    </small>
                  </div>

                  <div className="rle-rule-actions">
                    <Pill tone={target?.tone}>{target?.label || rule.target_zone}</Pill>
                    <button className="btn ghost" onClick={() => toggleRule(rule.id)}>
                      {rule.active === false ? 'Aktif et' : 'Pasifleştir'}
                    </button>
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
