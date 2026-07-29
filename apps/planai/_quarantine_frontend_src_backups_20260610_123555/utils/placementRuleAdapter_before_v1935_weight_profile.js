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

export function applyPlacementRulesBeforePlan(products = [], placementRules = []) {
  const activeRules = (placementRules || []).filter((r) => r && r.active !== false);

  if (!activeRules.length) return products || [];

  return (products || []).map((product) => {
    let next = { ...product };
    const applied = [];

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

      // Hard storage gerçeğini ezmiyoruz.
      // Kural sadece satış önceliği, facing ve açıklama tarafında etkili olur.
      const currentSales = safeNumber(next.sales || next.sales_qty_7d || next.sales_7d, 0);
      next.sales = currentSales + weight * 12;
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

    if (applied.length) {
      next.applied_rules = applied;
      next.placement_reason = [
        next.placement_reason,
        `Kural motoru: ${applied.map((r) => `${r.type}:${r.value}->${r.target_zone}`).join(', ')}`,
      ].filter(Boolean).join(' | ');
    }

    return next;
  });
}
