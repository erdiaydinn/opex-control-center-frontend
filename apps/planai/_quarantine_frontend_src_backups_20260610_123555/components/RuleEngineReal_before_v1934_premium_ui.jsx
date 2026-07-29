import React, { useMemo, useState } from 'react';

const RULE_TYPES = [
  { value: 'brand', label: 'Marka' },
  { value: 'category', label: 'Kategori' },
  { value: 'subcategory', label: 'Alt kategori' },
  { value: 'storage', label: 'Storage' },
  { value: 'sku', label: 'SKU' },
];

const TARGET_ZONES = [
  { value: 'AMBIENT', label: 'Kuru raf / Ambient' },
  { value: 'CHILLED', label: '+4 dolap / Soğuk' },
  { value: 'FROZEN', label: '-18 / Donuk' },
  { value: 'PRODUCE', label: 'Meyve sebze rafı' },
  { value: 'LOWER_SHELF', label: 'Alt raf' },
  { value: 'EYE_LEVEL', label: 'Göz hizası' },
  { value: 'END_OF_AISLE', label: 'Koridor sonu' },
];

const BEHAVIORS = [
  { value: 'prefer_zone', label: 'Öncelikli zone’a yerleştir' },
  { value: 'force_zone', label: 'Mümkünse sadece bu zone’da tut' },
  { value: 'keep_together', label: 'Beraber dursun' },
  { value: 'separate_from', label: 'Ayrı dursun' },
  { value: 'increase_facing', label: 'Facing artır' },
  { value: 'reduce_facing', label: 'Facing azalt' },
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

function ruleLabel(rule) {
  return `${rule.type}: ${rule.value || '-'} → ${rule.target_zone} / ${rule.behavior}`;
}

export default function RuleEngineReal({
  placementRules = [],
  setPlacementRules,
  onGenerate,
  products = [],
  unplacedProducts = [],
}) {
  const [draft, setDraft] = useState(emptyDraft());
  const allProducts = useMemo(() => [...(products || []), ...(unplacedProducts || [])], [products, unplacedProducts]);

  const matchedCount = useMemo(() => {
    const q = String(draft.value || '').trim().toUpperCase();
    if (!q) return 0;

    return allProducts.filter((p) => {
      const hay = [
        p.sku, p.SKU, p.name, p.product_name, p.brand, p.brand_name,
        p.category, p.category_l1, p.category_l2, p.storage, p.storage_type,
      ].filter(Boolean).join(' ').toUpperCase();

      return hay.includes(q);
    }).length;
  }, [allProducts, draft.value]);

  function addRule() {
    const value = String(draft.value || '').trim();

    if (!value) {
      alert('Kural değeri boş olamaz.');
      return;
    }

    setPlacementRules((prev = []) => [
      {
        ...draft,
        value,
        id: `RULE-${Date.now()}`,
        created_at: new Date().toISOString(),
      },
      ...prev,
    ]);

    setDraft(emptyDraft());
  }

  function removeRule(id) {
    setPlacementRules((prev = []) => prev.filter((r) => r.id !== id));
  }

  function toggleRule(id) {
    setPlacementRules((prev = []) =>
      prev.map((r) => r.id === id ? { ...r, active: !r.active } : r)
    );
  }

  async function applyAndGenerate() {
    if (typeof onGenerate === 'function') {
      await onGenerate();
    }
  }

  const templates = [
    { type: 'brand', value: 'Algida', target_zone: 'FROZEN', behavior: 'force_zone', priority: 'critical', weight: 10 },
    { type: 'storage', value: 'CHILLED', target_zone: 'CHILLED', behavior: 'force_zone', priority: 'critical', weight: 10 },
    { type: 'brand', value: 'Milagro', target_zone: 'PRODUCE', behavior: 'prefer_zone', priority: 'high', weight: 8 },
    { type: 'category', value: 'Cleaning', target_zone: 'END_OF_AISLE', behavior: 'separate_from', priority: 'normal', weight: 7 },
    { type: 'brand', value: 'Ülker', target_zone: 'AMBIENT', behavior: 'prefer_zone', priority: 'normal', weight: 7 },
    { type: 'brand', value: 'Coca-Cola', target_zone: 'EYE_LEVEL', behavior: 'increase_facing', priority: 'high', weight: 8 },
  ];

  return (
    <main className="page">
      <div className="section-eyebrow">AI OPTIMIZATION CENTER</div>
      <h1 style={{ fontSize: 42, margin: '8px 0' }}>Kural ve Ağırlık Motoru</h1>
      <p className="page-sub">
        Kurallar artık ekranda kalır, localStorage’a yazılır ve plan üretiminden önce ürün havuzuna uygulanır.
      </p>

      <div className="grid cols-2">
        <section className="card pad">
          <h2>Operasyonel Planogram Kuralı</h2>

          <div className="form-grid">
            <label>
              Kural tipi
              <select value={draft.type} onChange={(e) => setDraft((d) => ({ ...d, type: e.target.value }))}>
                {RULE_TYPES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
              </select>
            </label>

            <label>
              Değer
              <input
                value={draft.value}
                onChange={(e) => setDraft((d) => ({ ...d, value: e.target.value }))}
                placeholder="Örn: Ülker, Algida, Milagro, CHILLED"
              />
            </label>

            <label>
              Hedef
              <select value={draft.target_zone} onChange={(e) => setDraft((d) => ({ ...d, target_zone: e.target.value }))}>
                {TARGET_ZONES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
              </select>
            </label>

            <label>
              Davranış
              <select value={draft.behavior} onChange={(e) => setDraft((d) => ({ ...d, behavior: e.target.value }))}>
                {BEHAVIORS.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
              </select>
            </label>

            <label>
              Öncelik
              <select value={draft.priority} onChange={(e) => setDraft((d) => ({ ...d, priority: e.target.value }))}>
                <option value="low">Düşük</option>
                <option value="normal">Normal</option>
                <option value="high">Yüksek</option>
                <option value="critical">Kritik</option>
              </select>
            </label>

            <label>
              Ağırlık: {draft.weight}
              <input
                type="range"
                min="1"
                max="10"
                value={draft.weight}
                onChange={(e) => setDraft((d) => ({ ...d, weight: Number(e.target.value) }))}
              />
            </label>
          </div>

          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 16 }}>
            <button className="btn primary" onClick={addRule}>Kural ekle</button>
            <button className="btn ghost" onClick={applyAndGenerate}>Uygula ve planı yeniden üret</button>
            <span className="muted" style={{ alignSelf: 'center' }}>
              Yaklaşık {matchedCount.toLocaleString('tr-TR')} SKU eşleşiyor.
            </span>
          </div>
        </section>

        <section className="card pad">
          <h2>Ağırlık Motoru</h2>
          <p className="muted">
            Storage hard rule ezilmez. Kural motoru soft öncelik, facing ve karar açıklamasını etkiler.
          </p>

          <div className="list">
            <div className="list-row"><b>Aktif kural</b><span>{placementRules.filter((r) => r.active !== false).length}</span></div>
            <div className="list-row"><b>Pasif kural</b><span>{placementRules.filter((r) => r.active === false).length}</span></div>
            <div className="list-row"><b>Hard rule</b><span>Storage / fixture uyumu</span></div>
            <div className="list-row"><b>Soft rule</b><span>Marka, kategori, affinity, facing</span></div>
          </div>
        </section>
      </div>

      <section className="grid cols-2" style={{ marginTop: 18 }}>
        <div className="card pad">
          <h2>Aktif kurallar</h2>

          {!placementRules.length && (
            <p className="muted">Henüz kural yok. Kural ekleyip “Uygula ve planı yeniden üret” dediğinde plan tekrar hesaplanır.</p>
          )}

          <div className="list">
            {placementRules.map((rule) => (
              <div className="list-row" key={rule.id}>
                <div>
                  <b>{ruleLabel(rule)}</b>
                  <div className="muted">
                    Öncelik: {rule.priority} · Ağırlık: {rule.weight} · {rule.active === false ? 'Pasif' : 'Aktif'}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn ghost" onClick={() => toggleRule(rule.id)}>
                    {rule.active === false ? 'Aktif et' : 'Pasifleştir'}
                  </button>
                  <button className="btn ghost" onClick={() => removeRule(rule.id)}>Sil</button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card pad">
          <h2>Hazır kural şablonları</h2>
          <div className="list">
            {templates.map((template, idx) => (
              <div className="list-row" key={idx}>
                <b>{ruleLabel(template)}</b>
                <button
                  className="btn ghost"
                  onClick={() => setPlacementRules((prev = []) => [
                    { ...template, id: `RULE-${Date.now()}-${idx}`, active: true, created_at: new Date().toISOString() },
                    ...prev,
                  ])}
                >
                  Uygula
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
