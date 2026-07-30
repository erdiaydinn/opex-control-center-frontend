export function normalizeRuleText(value) {
  return String(value || '')
    .trim()
    .toUpperCase()
    .replaceAll('İ', 'I')
    .replaceAll('Ş', 'S')
    .replaceAll('Ğ', 'G')
    .replaceAll('Ü', 'U')
    .replaceAll('Ö', 'O')
    .replaceAll('Ç', 'C');
}

export const DEFAULT_OPTIMIZATION_WEIGHTS = {
  sales_weight: 8,
  category_weight: 6,
  brand_block_weight: 7,
  basket_affinity_weight: 7,
  refill_cost_weight: 8,
  picker_route_weight: 6,
  cold_chain_weight: 10,
  capacity_weight: 8,
  shelf_fill_weight: 8,
};

function productHaystack(product = {}) {
  return normalizeRuleText([
    product.sku,
    product.SKU,
    product.barcode,
    product.Barcodes,
    product.name,
    product.product_name,
    product.productName,
    product.brand,
    product.brand_name,
    product.category,
    product.category_l1,
    product.category_l2,
    product.subcategory,
    product.storage,
    product.storage_type,
    product.storage_class,
    product.food_family,
  ].filter(Boolean).join(' '));
}

function matchesRule(product = {}, rule = {}) {
  const value = normalizeRuleText(rule.value);
  if (!value) return false;

  const type = String(rule.type || '').toLowerCase();

  const fields = {
    brand: [product.brand, product.brand_name],
    category: [product.category, product.category_l1, product['Category L1']],
    subcategory: [product.subcategory, product.category_l2, product['Category L2']],
    storage: [product.storage, product.storage_type, product.storage_class],
    sku: [product.sku, product.SKU, product.barcode, product.Barcodes],
  };

  const selected = fields[type];

  if (selected) {
    return normalizeRuleText(selected.filter(Boolean).join(' ')).includes(value);
  }

  return productHaystack(product).includes(value);
}

function safeNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function getWeight(weights = {}, key) {
  const merged = { ...DEFAULT_OPTIMIZATION_WEIGHTS, ...(weights || {}) };
  return Math.max(1, Math.min(10, safeNumber(merged[key], DEFAULT_OPTIMIZATION_WEIGHTS[key] || 5)));
}

function categorySignal(product = {}) {
  return String(product.category || product.category_l1 || product.category_l2 || '').trim() ? 1 : 0;
}

function brandSignal(product = {}) {
  return String(product.brand || product.brand_name || '').trim() ? 1 : 0;
}

function affinitySignal(product = {}) {
  return safeNumber(product.basket_affinity_score, 0) > 0 ? 1 : 0;
}

function coldChainSignal(product = {}) {
  const st = normalizeRuleText(product.storage || product.storage_type || product.storage_class);
  return st.includes('CHILLED') || st.includes('FROZEN') ? 1 : 0;
}

function refillSignal(product = {}) {
  const sales = safeNumber(product.sales || product.sales_qty_7d || product.sales_7d, 0);
  const depth = safeNumber(product.depth, 1);
  return sales >= 80 && depth <= 3 ? 1 : 0;
}

function bulkyPenalty(product = {}) {
  const text = productHaystack(product);
  return (
    text.includes('DAMACANA') ||
    text.includes('CARBOY') ||
    text.includes('19 L') ||
    text.includes('5 L') ||
    text.includes('PAPER TOWEL') ||
    text.includes('TOILET PAPER')
  ) ? 1 : 0;
}

export function applyPlacementRulesBeforePlan(products = [], placementRules = [], optimizationWeights = {}) {
  const activeRules = (placementRules || []).filter((r) => r && r.active !== false);

  return (products || []).map((product) => {
    let next = { ...product };
    const applied = [];

    const baseSales = safeNumber(next.sales || next.sales_qty_7d || next.sales_7d, 0);

    const weightedScore =
      baseSales * (getWeight(optimizationWeights, 'sales_weight') / 8) +
      categorySignal(next) * getWeight(optimizationWeights, 'category_weight') * 4 +
      brandSignal(next) * getWeight(optimizationWeights, 'brand_block_weight') * 3 +
      affinitySignal(next) * getWeight(optimizationWeights, 'basket_affinity_weight') * 8 +
      refillSignal(next) * getWeight(optimizationWeights, 'refill_cost_weight') * 6 +
      coldChainSignal(next) * getWeight(optimizationWeights, 'cold_chain_weight') * 5 -
      bulkyPenalty(next) * Math.max(0, 11 - getWeight(optimizationWeights, 'picker_route_weight')) * 3;

    next.sales = Math.max(baseSales, weightedScore);
    next.optimization_weight_score = Number(weightedScore.toFixed(2));
    next.optimization_weights_applied = optimizationWeights;

    for (const rule of activeRules) {
      if (!matchesRule(next, rule)) continue;

      const weight = Math.max(1, Math.min(10, safeNumber(rule.weight, 5)));
      const behavior = String(rule.behavior || '').toLowerCase();
      const target = String(rule.target_zone || '').toUpperCase();

      applied.push({
        id: rule.id,
        type: rule.type,
        value: rule.value,
        behavior,
        target_zone: target,
        weight,
      });

      next.sales = safeNumber(next.sales, 0) + weight * 12;
      next.rule_score_boost = safeNumber(next.rule_score_boost, 0) + weight * 12;

      if (behavior === 'increase_facing') {
        const facing = safeNumber(next.facing || next.facing_count, 1);
        next.facing = Math.min(4, facing + 1);
        next.facing_count = next.facing;
      }

      if (behavior === 'reduce_facing') {
        const facing = safeNumber(next.facing || next.facing_count, 1);
        next.facing = Math.max(1, facing - 1);
        next.facing_count = next.facing;
      }

      if (behavior === 'prefer_zone' || behavior === 'force_zone') {
        next.preferred_rule_zone = target;
      }

      if (behavior === 'keep_together') {
        next.keep_together_rule = rule.value;
      }

      if (behavior === 'separate_from') {
        next.separate_from_rule = rule.value;
      }
    }

    const weightNote = `Ağırlık profili: satış ${getWeight(optimizationWeights, 'sales_weight')}, kategori ${getWeight(optimizationWeights, 'category_weight')}, picker ${getWeight(optimizationWeights, 'picker_route_weight')}, soğuk zincir ${getWeight(optimizationWeights, 'cold_chain_weight')}`;

    if (applied.length) {
      next.applied_rules = applied;
      next.placement_reason = [
        next.placement_reason,
        weightNote,
        `Kural motoru: ${applied.map((r) => `${r.type}:${r.value}->${r.target_zone}`).join(', ')}`,
      ].filter(Boolean).join(' | ');
    } else {
      next.placement_reason = [
        next.placement_reason,
        weightNote,
      ].filter(Boolean).join(' | ');
    }

    return next;
  });
}
