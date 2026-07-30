import React, { useEffect, useMemo, useState } from 'react';
import {
  DEFAULT_OPTIMIZATION_WEIGHTS,
  DEFAULT_STRATEGY_PROFILE,
  STRATEGY_MODES,
} from '../utils/placementRuleAdapter.js';

// =====================================================================
// TEK KURAL & AĞIRLIK MOTORU
// Komuta Merkezi (embedded), tam sayfa (full) ve Optimum Plan onay
// modalı (modal) AYNI bileşeni ve AYNI paylaşılan state'i kullanır.
// Kural motoru UI'ı yalnızca burada tanımlıdır; kopya panel yoktur.
// =====================================================================

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

// Komuta Merkezi (embedded) ve modal özetinde daha kısa ağırlık listesi.
const WEIGHT_CONTROLS_COMPACT = [
  ['sales_weight', 'Satış etkisi'],
  ['category_weight', 'Kategori etkisi'],
  ['brand_block_weight', 'Marka blok etkisi'],
  ['refill_cost_weight', 'Refill maliyeti'],
  ['picker_route_weight', 'Picker rota etkisi'],
  ['cold_chain_weight', 'Soğuk zincir etkisi'],
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

const BEHAVIORS = [
  ['prefer_block', 'Blok tercih et'],
  ['increase_facing', 'Önyüz artır'],
  ['reduce_facing', 'Önyüz azalt'],
];

const BEHAVIOR_LABELS = Object.fromEntries(BEHAVIORS);

function roleOf() {
  try {
    return String(localStorage.getItem('plonagram_user_role') || 'admin').toLowerCase();
  } catch {
    return 'admin';
  }
}

function canEditWeights(profile) {
  const role = roleOf();
  return (profile?.editable_weights_roles || ['admin']).map((x) => String(x).toLowerCase()).includes(role);
}

function emptyRule() {
  return {
    type: 'brand',
    value: '',
    target_aisle: 'A',
    target_side: 'SAĞ',
    behavior: 'prefer_block',
    priority: 7,
  };
}

// ---------------------------------------------------------------------
// KURAL ŞEMA KÖPRÜSÜ
// Canonical alanlar: target_aisle / target_side / behavior / priority.
// adapter iki şemayı da tolere ettiği için kural KAYDEDİLİRKEN canonical
// + alias alanların ikisini birden basıyoruz. Böylece:
//   - yeni RuleWeightEngine tek (canonical) şemaya oturur,
//   - applyPlacementRulesBeforePlan canonical YA DA alias okusa da çalışır,
//   - eski localStorage kuralları (zone/side/priority) kırılmaz.
// ---------------------------------------------------------------------
function normalizeRuleForRead(r = {}) {
  const target_aisle = r.target_aisle ?? r.aisle ?? r.zone ?? r.targetZone ?? '';
  const target_side = r.target_side ?? r.side ?? r.targetSide ?? '';
  const behavior = r.behavior ?? r.action ?? 'prefer_block';
  const priority = r.priority ?? r.weight ?? 7;
  return { ...r, target_aisle, target_side, behavior, priority };
}

function buildRuleRecord(draft) {
  const value = String(draft.value || '').trim();
  const target_aisle = draft.target_aisle || '';
  const target_side = draft.target_side || '';
  const behavior = draft.behavior || 'prefer_block';
  const priority = Number(draft.priority ?? 7);
  return {
    id: `RULE-${Date.now()}`,
    type: draft.type || 'brand',
    value,
    // canonical
    target_aisle,
    target_side,
    behavior,
    priority,
    // alias (adapter / eski şema toleransı)
    aisle: target_aisle,
    zone: target_aisle,
    side: target_side,
    action: behavior,
    weight: priority,
    created_at: new Date().toISOString(),
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

// Hard rule özetleri her modda aynı metinle gösterilir (tek kaynak).
const HARD_RULES = [
  ['storage_raw', 'storage_raw: Raf → raf · Dolap → +4 dolap · Donuk → -18 freezer'],
  ['case_pack_qty', 'case_pack_qty: kırık koli değil, tam koli katı'],
];

export default function RuleWeightEngine({
  mode = 'full',
  placementRules = [],
  setPlacementRules,
  optimizationWeights = DEFAULT_OPTIMIZATION_WEIGHTS,
  setOptimizationWeights,
  strategyProfile = DEFAULT_STRATEGY_PROFILE,
  setStrategyProfile,
  products = [],
  unplacedProducts = [],
  storeDna,
  readiness,
  notify,
  // embedded modunda "Optimum plan ayarlarını aç" → App modal'ı açar
  onOpenPlanModal,
  // modal modunda "Ayarlarla optimum plan üret" → App planı çalıştırır
  onRun,
  onClose,
}) {
  const [draft, setDraft] = useState(emptyRule());

  const allProducts = useMemo(
    () => [...(products || []), ...(unplacedProducts || [])],
    [products, unplacedProducts],
  );

  const rules = useMemo(() => (placementRules || []).map(normalizeRuleForRead), [placementRules]);

  const selectedStrategy = STRATEGIES.find((x) => x.mode === strategyProfile?.mode) || STRATEGIES[0];
  const weightsAllowed = selectedStrategy.weights && canEditWeights(strategyProfile);

  const strategyConfirmed = useMemo(() => {
    try {
      return localStorage.getItem('plonagram_strategy_confirmed') === '1';
    } catch {
      return false;
    }
  }, [strategyProfile]);

  // Strateji profilini ağırlık + etiketle senkron tut (tek kaynak localStorage).
  useEffect(() => {
    const next = {
      ...strategyProfile,
      weights_enabled: Boolean(selectedStrategy.weights),
      label: selectedStrategy.title,
      weights: {
        ...DEFAULT_OPTIMIZATION_WEIGHTS,
        ...(strategyProfile?.weights || {}),
        ...(optimizationWeights || {}),
      },
    };
    try {
      localStorage.setItem('plonagram_strategy_profile', JSON.stringify(next));
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategyProfile?.mode, optimizationWeights]);

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

  // ---- readiness sinyalleri (özet kartları) ----
  const candidateCount = allProducts.length;
  const catalogReady = candidateCount > 0;
  const storeDnaReady = Boolean(storeDna || readiness?.store_dna || readiness?.dna);
  const abcReady = allProducts.some((p) => p.abc || p.abc_class || p.ABC);
  const casePackReady = allProducts.filter((p) => Number(p.case_pack_qty || p.casePackQty || 0) > 0).length;

  // ---- actions ----
  function chooseStrategy(modeValue) {
    const item = STRATEGIES.find((x) => x.mode === modeValue) || STRATEGIES[0];
    setStrategyProfile?.((prev = DEFAULT_STRATEGY_PROFILE) => ({
      ...prev,
      mode: item.mode,
      label: item.title,
      weights_enabled: item.weights,
    }));
    try {
      localStorage.setItem('plonagram_strategy_confirmed', '1');
    } catch {}
  }

  function updateWeight(key, value) {
    if (typeof setOptimizationWeights !== 'function') return;
    if (mode === 'full' && !weightsAllowed) return;
    setOptimizationWeights((prev = DEFAULT_OPTIMIZATION_WEIGHTS) => ({
      ...DEFAULT_OPTIMIZATION_WEIGHTS,
      ...(prev || {}),
      [key]: Number(value),
    }));
  }

  function addRule() {
    const value = String(draft.value || '').trim();
    if (!value) {
      notify?.('Kural değeri boş olamaz.');
      return;
    }
    const record = buildRuleRecord({ ...draft, value });
    setPlacementRules?.((prev = []) => [record, ...(prev || [])]);
    setDraft(emptyRule());
    notify?.('Kural motora eklendi. Optimum plan üretirken uygulanacak.');
  }

  function removeRule(id) {
    setPlacementRules?.((prev = []) => (prev || []).filter((r) => r.id !== id));
  }

  // Ağırlık satırlarını render eden ortak yardımcı.
  function renderWeightRows(controls, { compact = false } = {}) {
    return controls.map(([key, label]) => {
      const val = optimizationWeights?.[key] ?? DEFAULT_OPTIMIZATION_WEIGHTS[key] ?? 5;
      const disabled = mode === 'full' ? !weightsAllowed : mode === 'modal';
      return (
        <div className="rle-weight-row" key={key}>
          <div>
            <b>{label}{compact ? `: ${val}` : ''}</b>
            {!compact && <small>Hibrit strateji karar etkisi</small>}
          </div>
          <div className="rle-weight-control">
            <input
              type="range"
              min="1"
              max="10"
              step="1"
              disabled={disabled}
              value={val}
              onChange={(e) => updateWeight(key, e.target.value)}
            />
            {!compact && <span>{val}</span>}
          </div>
        </div>
      );
    });
  }

  // Kural ekleme formu (embedded + full ortak).
  function renderRuleBuilder() {
    return (
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
              {BEHAVIORS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>

          <label>
            <span>Öncelik: {draft.priority}/10</span>
            <input type="range" min="1" max="10" value={draft.priority} onChange={(e) => setDraft((d) => ({ ...d, priority: Number(e.target.value) }))} />
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
    );
  }

  // Strateji kartları (embedded + full ortak).
  function renderStrategyCards() {
    return (
      <div className="rle-strategy-grid">
        {STRATEGIES.map((s) => (
          <button
            key={s.mode}
            className={`rle-strategy-card ${strategyProfile?.mode === s.mode ? 'active' : ''}`}
            onClick={() => chooseStrategy(s.mode)}
            type="button"
          >
            <b>{s.title}</b>
            <span>{s.desc}</span>
            <small>{s.weights ? 'Ağırlık motoru: yetkili kullanıcı' : 'Ağırlık motoru yok'}</small>
          </button>
        ))}
      </div>
    );
  }

  function renderActiveRules() {
    return (
      <section className="rle-rules-card">
        <div className="rle-card-head">
          <div><h2>Aktif yerleşim kuralları</h2><p>Marka/kategori tercihleri burada görünür.</p></div>
        </div>
        {!rules.length ? (
          <div className="rle-empty">Henüz kural yok. Gerekirse marka veya kategori bazlı tercih ekle.</div>
        ) : (
          <div className="rle-rule-list">
            {rules.map((r) => (
              <div className="rle-rule-row" key={r.id}>
                <div>
                  <b>{r.type}: {r.value}</b>
                  <small>Hedef: {r.target_aisle || '-'} {r.target_side || ''} · Davranış: {BEHAVIOR_LABELS[r.behavior] || r.behavior} · Öncelik: {r.priority}/10</small>
                </div>
                <div className="rle-rule-actions">
                  <button className="btn ghost" onClick={() => removeRule(r.id)}>Sil</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    );
  }

  function renderHardRuleList() {
    return (
      <div className="rle-hardrules">
        {HARD_RULES.map(([key, label]) => (
          <div className="rle-hardrule" key={key}><b>Hard rule</b><span className="muted">{label}</span></div>
        ))}
      </div>
    );
  }

  // ===================================================================
  // MODE: EMBEDDED  (Komuta Merkezi içi gerçek motor — kopya değil)
  // ===================================================================
  if (mode === 'embedded') {
    return (
      <div className="card pad rle-embedded" style={{ marginTop: 20 }}>
        <div className="section-eyebrow">KURAL VE AĞIRLIK MOTORU</div>
        <div className="rle-embedded-head">
          <div>
            <h2 style={{ margin: '6px 0' }}>Kural ve Ağırlık Motoru</h2>
            <p className="muted" style={{ maxWidth: 860 }}>
              Komuta Merkezi sadece özet ekranı değil; planı hangi strateji, kural ve ağırlıkla üreteceğini buradan yönetir. Ayrı sekmede aratmaz.
            </p>
          </div>
          <button className="btn primary" onClick={onOpenPlanModal}>Optimum plan ayarlarını aç</button>
        </div>

        <div className="rle-kpi-grid" style={{ marginTop: 14 }}>
          <div className="rle-kpi"><span>Catalog / SKU</span><b>{catalogReady ? candidateCount : 'Eksik'}</b><small>Aday havuz</small></div>
          <div className="rle-kpi"><span>Store DNA</span><b>{storeDnaReady ? 'Hazır' : 'Eksik'}</b><small>Depo gerçekliği</small></div>
          <div className="rle-kpi"><span>ABC sinyali</span><b>{abcReady ? 'Var' : 'Yok'}</b><small>Satış/ABC</small></div>
          <div className="rle-kpi"><span>Koli bilgisi</span><b>{casePackReady ? `${casePackReady} SKU` : 'Eksik'}</b><small>case_pack_qty</small></div>
        </div>

        <div className="rle-card-head" style={{ marginTop: 16 }}>
          <div><h3 style={{ margin: 0 }}>Strateji seçimi</h3><p className="muted">Hard kurallar hiçbir stratejide ezilmez.</p></div>
        </div>
        {renderStrategyCards()}

        <div className="rle-layout" style={{ marginTop: 16 }}>
          {renderRuleBuilder()}

          <div className="rle-templates">
            <h3 style={{ marginTop: 0 }}>Ağırlık motoru</h3>
            <p className="muted">{selectedStrategy.weights ? (weightsAllowed ? 'Hibrit modda düzenlenebilir.' : 'Sadece görüntüleme.') : 'Bu strateji ağırlık kullanmaz.'}</p>
            <div className="rle-weight-grid">{renderWeightRows(WEIGHT_CONTROLS_COMPACT, { compact: true })}</div>
            <div className="mini-metric" style={{ marginTop: 10 }}>
              <b>{selectedStrategy.title}</b>
              <span>Aktif strateji</span>
            </div>
          </div>
        </div>

        {renderHardRuleList()}
        {renderActiveRules()}
      </div>
    );
  }

  // ===================================================================
  // MODE: MODAL  (Optimum Plan onayı — aynı state'ten okur, salt-özet)
  // ===================================================================
  if (mode === 'modal') {
    return (
      <div className="rle-modal-body">
        <div className="rle-modal-head">
          <div>
            <div className="section-eyebrow">OPTIMUM PLAN ENGINE</div>
            <h2 style={{ margin: '8px 0', fontSize: 30 }}>Plan üretim ayarları</h2>
            <p className="muted">Plan üretmeden önce strateji, aktif kurallar ve ağırlıklar burada onaylanır. Kullanıcı artık ayrı Kural Motoru ekranı aramaz.</p>
          </div>
          {onClose && <button className="btn ghost" onClick={onClose}>Kapat</button>}
        </div>

        <div className="rle-kpi-grid" style={{ marginTop: 14 }}>
          <div className="rle-kpi"><span>Aday SKU</span><b>{candidateCount}</b><small>{catalogReady ? 'Hazır' : 'Eksik'}</small></div>
          <div className="rle-kpi"><span>Aktif kural</span><b>{rules.length}</b><small>Yerleşim tercihi</small></div>
          <div className="rle-kpi"><span>Store DNA</span><b>{storeDnaReady ? 'Hazır' : 'Eksik'}</b><small>Depo gerçekliği</small></div>
          <div className="rle-kpi"><span>ABC sinyali</span><b>{abcReady ? 'Var' : 'Yok'}</b><small>Satış/ABC</small></div>
        </div>

        <div className="rle-layout" style={{ marginTop: 16 }}>
          <div className="rle-builder">
            <div className="rle-card-head"><div><h3 style={{ marginTop: 0 }}>Strateji</h3></div></div>
            <div className="mini-metric"><b>{selectedStrategy.title}</b><span>{selectedStrategy.desc}</span></div>
            {renderHardRuleList()}
            <div className="rle-modal-rules">
              {!rules.length
                ? <div className="muted">Aktif kural yok. Plan saf strateji ile çalışır.</div>
                : rules.slice(0, 6).map((r) => (
                    <div className="rle-modal-rule" key={r.id}>
                      <b>{r.type}: {r.value}</b>
                      <small>{r.target_aisle || '-'} {r.target_side || ''} · {BEHAVIOR_LABELS[r.behavior] || r.behavior} · {r.priority}/10</small>
                    </div>
                  ))}
            </div>
          </div>

          <div className="rle-templates">
            <h3 style={{ marginTop: 0 }}>Ağırlık özeti</h3>
            <div className="rle-weight-grid">{renderWeightRows(WEIGHT_CONTROLS_COMPACT, { compact: true })}</div>
          </div>
        </div>

        <div className="rle-modal-actions">
          {onClose && <button className="btn ghost" onClick={onClose}>Vazgeç</button>}
          <button className="btn primary" onClick={onRun}>Ayarlarla optimum plan üret</button>
        </div>
      </div>
    );
  }

  // ===================================================================
  // MODE: FULL  (Gelişmiş Motor Ayarları sayfası)
  // ===================================================================
  return (
    <main className="page rle-page">
      <section className="rle-hero">
        <div>
          <div className="section-eyebrow">PLANOGRAM STRATEJİSİ</div>
          <h1>Gelişmiş Motor Ayarları</h1>
          <p>
            Önce strateji belirlenir, sonra SKU yüklenir ve planogram üretilir.
            Ağırlık motoru sadece hibrit stratejilerde ve yetkili kullanıcılar için aktiftir.
          </p>
        </div>
        <div className="rle-hero-actions">
          <button
            className="btn primary"
            onClick={onOpenPlanModal}
            disabled={!strategyConfirmed}
            title={strategyConfirmed ? 'Seçili stratejiyle plan üret' : 'Önce aşağıdan bir strateji seç'}
          >
            Optimum plan ayarlarını aç
          </button>
          {!strategyConfirmed && (
            <small className="rle-hero-hint">Önce aşağıdaki kartlardan bir strateji seç.</small>
          )}
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
        {renderStrategyCards()}
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
          <div className="rle-weight-grid">{renderWeightRows(WEIGHT_CONTROLS)}</div>
        </section>
      )}

      <section className="rle-layout">
        {renderRuleBuilder()}

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

      {renderHardRuleList()}
      {renderActiveRules()}
    </main>
  );
}
