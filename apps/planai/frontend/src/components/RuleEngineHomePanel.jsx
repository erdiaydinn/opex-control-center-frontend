import React from "react";
import "../styles/catalog-rule-engine.css";

const DEFAULT_RULES = {
  mode: "HYBRID",
  hard_rules: {
    storage: true,
    fixture: true,
    food_non_food_split: true,
    shelf_category_lock: true,
    brand_cluster: true,
  },
  scoring_config: {
    sales: 1.35,
    picking: 1.2,
    fixture: 1.4,
    brand_cluster: 1.25,
    coverage: 1.1,
  },
};

export default function RuleEngineHomePanel({ value, onChange, onOpenFullRuleEngine }) {
  const rules = { ...DEFAULT_RULES, ...(value || {}) };
  const hard = { ...DEFAULT_RULES.hard_rules, ...(rules.hard_rules || {}) };

  function patch(next) {
    const merged = { ...rules, ...next, hard_rules: { ...hard, ...(next.hard_rules || {}) } };
    onChange?.(merged);
    localStorage.setItem("plonagram.ruleEngine", JSON.stringify(merged));
  }

  return (
    <section className="rule-home-card">
      <div className="rule-home-head">
        <div>
          <p className="eyebrow">Rule Engine</p>
          <h3>Kural Motoru</h3>
          <p>Storage, fixture, gıda/gıda dışı, kategori ve marka blokları burada görünür olmalı.</p>
        </div>
        <button type="button" className="plona-secondary-btn" onClick={onOpenFullRuleEngine}>
          Detaylı Kural Motoru
        </button>
      </div>

      <div className="rule-mode-row">
        {["HYBRID", "ABC", "CATEGORY", "BRAND", "PICKING", "REFILL"].map((mode) => (
          <button
            key={mode}
            type="button"
            className={rules.mode === mode ? "rule-chip active" : "rule-chip"}
            onClick={() => patch({ mode })}
          >
            {mode}
          </button>
        ))}
      </div>

      <div className="rule-toggle-grid">
        <label><input type="checkbox" checked={hard.storage} onChange={(e) => patch({ hard_rules: { storage: e.target.checked } })} /> Storage hard match</label>
        <label><input type="checkbox" checked={hard.fixture} onChange={(e) => patch({ hard_rules: { fixture: e.target.checked } })} /> Raf / Dolap / Donuk hard match</label>
        <label><input type="checkbox" checked={hard.food_non_food_split} onChange={(e) => patch({ hard_rules: { food_non_food_split: e.target.checked } })} /> Gıda - Gıda dışı ayır</label>
        <label><input type="checkbox" checked={hard.shelf_category_lock} onChange={(e) => patch({ hard_rules: { shelf_category_lock: e.target.checked } })} /> Aynı rafta kategori karıştırma</label>
        <label><input type="checkbox" checked={hard.brand_cluster} onChange={(e) => patch({ hard_rules: { brand_cluster: e.target.checked } })} /> Marka bloklarını koru</label>
      </div>

      <div className="rule-mini-status">
        <span>Aktif mod: <b>{rules.mode}</b></span>
        <span>Motor: catalog-first / fixture-first</span>
      </div>
    </section>
  );
}
