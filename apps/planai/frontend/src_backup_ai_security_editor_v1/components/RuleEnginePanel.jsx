import React, { useMemo, useState } from "react";

const MODES = [
  ["DARKSTORE_AI", "Darkstore AI"],
  ["HYBRID", "Hibrit"],
  ["SALES", "ABC / Satış"],
  ["PICKING", "Picking"],
  ["CATEGORY", "Kategori"],
  ["BRAND", "Marka blok"],
];

const RULE_TYPES = ["Kategori", "Alt kategori", "Marka", "SKU"];
const ZONES = ["Kuru zone", "Soğuk +4", "Donuk -18", "Pallet / Ağır"];
const SIDES = ["Fark etmez", "L", "R"];
const PRIORITIES = ["Normal", "Yüksek", "Kritik", "Sales"];
const BEHAVIORS = ["Zone içine yerleştir", "Yakına grupla", "Alt rafa indir", "Göz hizasına al", "Sona bırak"];

function Pill({ children }) {
  return <span className="pe-stat-pill">{children}</span>;
}

export default function RuleEnginePanel({
  rule,
  setRule,
  onGenerate,
  generating,
  advancedRules = [],
  onAdvancedRulesChange,
  scoreWeights = {},
  onScoreWeightsChange,
  pickingFlow = [],
  onPickingFlowChange,
  uploadStats,
  lastSummary,
  onApplyRulesNow,
}) {
  const [ruleType, setRuleType] = useState("Marka");
  const [value, setValue] = useState("");
  const [zone, setZone] = useState("Kuru zone");
  const [side, setSide] = useState("Fark etmez");
  const [priority, setPriority] = useState("Normal");
  const [behavior, setBehavior] = useState("Zone içine yerleştir");
  const [showScore, setShowScore] = useState(true);
  const [showRules, setShowRules] = useState(true);

  const summaryText = useMemo(() => {
    const loaded = uploadStats?.loaded ?? 0;
    const placed = lastSummary?.placed_products ?? "-";
    const unplaced = lastSummary?.unplaced_products ?? "-";
    return { loaded, placed, unplaced };
  }, [uploadStats, lastSummary]);

  function addRule() {
    if (!String(value || "").trim()) return;
    const newRule = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      type: ruleType,
      value: value.trim(),
      zone,
      side,
      priority,
      behavior,
      created_at: new Date().toISOString(),
    };
    onAdvancedRulesChange?.([...(advancedRules || []), newRule]);
    setValue("");
  }

  function deleteRule(id) {
    onAdvancedRulesChange?.((advancedRules || []).filter((r) => r.id !== id));
  }

  function resetWeights() {
    onScoreWeightsChange?.({ sales: 1.35, picking: 1.2, ergonomics: 1, refill: 0.85, risk: 1.15, fixture: 1.4 });
  }

  function setWeight(key, value) {
    onScoreWeightsChange?.({ ...scoreWeights, [key]: Number(value) });
  }

  function setFlow(index, value) {
    const next = [...(pickingFlow || [])];
    next[index] = value;
    onPickingFlowChange?.(next);
  }

  return (
    <section className="pe-ai-panel premium-rule-panel">
      <div className="pe-ai-head">
        <div>
          <div className="pe-kicker">AI Optimization Center</div>
          <h2>Operasyonel Planogram Motoru</h2>
          <p>Yüklenen SKU, yerleşen/yerleşmeyen ürün, ileri kural setleri ve skor motoru tek merkezden yönetilir.</p>
        </div>
        <div className="pe-rule-actions">
          <button className="pe-primary" onClick={onGenerate} disabled={generating}>{generating ? "Üretiliyor..." : "⚡ Planogram üret"}</button>
          <button onClick={onApplyRulesNow}>Kuralları şimdi uygula</button>
        </div>
      </div>

      <div className="pe-ai-grid">
        <div className="pe-card compact">
          <h3>Dosya durumu</h3>
          <div className="pe-stat-row">
            <Pill>{summaryText.loaded} SKU yüklendi</Pill>
            <Pill>{summaryText.placed} yerleşti</Pill>
            <Pill>{summaryText.unplaced} yerleşmedi</Pill>
          </div>
          <small>{uploadStats?.file || "Dosya yok"}</small>
        </div>

        <div className="pe-card compact">
          <h3>Optimizasyon modu</h3>
          <select value={rule} onChange={(e) => setRule(e.target.value)}>
            {MODES.map(([id, label]) => <option value={id} key={id}>{label}</option>)}
          </select>
        </div>

        <div className="pe-card compact">
          <div className="pe-card-title"><h3>Skor Motoru</h3><button onClick={() => setShowScore(!showScore)}>{showScore ? "Gizle" : "Göster"}</button></div>
          {showScore && Object.entries(scoreWeights || {}).map(([key, val]) => (
            <label className="pe-weight" key={key}>
              <span>{key}</span><b>{Number(val).toFixed(2)}</b>
              <input type="range" min="0" max="2" step="0.05" value={val} onChange={(e) => setWeight(key, e.target.value)} />
            </label>
          ))}
          {showScore && <button onClick={resetWeights}>Varsayılana dön</button>}
        </div>

        <div className="pe-card compact">
          <h3>Admin Toplama Akışı</h3>
          <div className="flow-grid">
            {[0,1,2,3].map((i) => (
              <select key={i} value={pickingFlow?.[i] || ""} onChange={(e) => setFlow(i, e.target.value)}>
                <option value="AMBIENT">Kuru</option>
                <option value="CHILLED">Soğuk</option>
                <option value="FROZEN">Donuk</option>
                <option value="HEAVY_LAST">Ağır ürün en son</option>
              </select>
            ))}
          </div>
        </div>
      </div>

      <div className="pe-card rule-builder">
        <div className="pe-card-title"><h3>İleri Seviye Planogram Kural Setleri</h3><button onClick={() => setShowRules(!showRules)}>{showRules ? "Gizle" : "Göster"}</button></div>
        {showRules && (
          <>
            <div className="rule-form-grid">
              <label>Kural tipi<select value={ruleType} onChange={(e) => setRuleType(e.target.value)}>{RULE_TYPES.map((x) => <option key={x}>{x}</option>)}</select></label>
              <label>Değer<input value={value} onChange={(e) => setValue(e.target.value)} placeholder="Örn: Ülker / Water / MRK..." /></label>
              <label>Hedef zone<select value={zone} onChange={(e) => setZone(e.target.value)}>{ZONES.map((x) => <option key={x}>{x}</option>)}</select></label>
              <label>Taraf<select value={side} onChange={(e) => setSide(e.target.value)}>{SIDES.map((x) => <option key={x}>{x}</option>)}</select></label>
              <label>Öncelik<select value={priority} onChange={(e) => setPriority(e.target.value)}>{PRIORITIES.map((x) => <option key={x}>{x}</option>)}</select></label>
              <label>Davranış<select value={behavior} onChange={(e) => setBehavior(e.target.value)}>{BEHAVIORS.map((x) => <option key={x}>{x}</option>)}</select></label>
              <button className="pe-primary" onClick={addRule}>Kural ekle ve uygula</button>
            </div>

            <div className="rule-table">
              <div className="rule-row head"><span>Tip</span><span>Değer</span><span>Zone</span><span>Taraf</span><span>Öncelik</span><span>Davranış</span><span></span></div>
              {!advancedRules.length && <div className="empty-rule">Henüz özel kural yok. Eklediğinde anında mevcut plana uygulanır.</div>}
              {advancedRules.map((r) => (
                <div className="rule-row" key={r.id}>
                  <span>{r.type}</span><b>{r.value}</b><span>{r.zone}</span><span>{r.side}</span><span>{r.priority}</span><span>{r.behavior}</span>
                  <button onClick={() => deleteRule(r.id)}>Sil</button>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
