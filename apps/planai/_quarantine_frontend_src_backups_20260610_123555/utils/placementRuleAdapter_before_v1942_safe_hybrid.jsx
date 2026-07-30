export const DEFAULT_OPTIMIZATION_WEIGHTS = {
  sales_weight: 8,
  category_weight: 6,
  brand_block_weight: 9,
  basket_affinity_weight: 7,
  refill_cost_weight: 8,
  picker_route_weight: 6,
  cold_chain_weight: 10,
  capacity_weight: 8,
  shelf_fill_weight: 8,
};

const BRAND_BLOCK_TARGETS = [
  { rank: 1, aisle: "A", side: "SAĞ", code: "A_RIGHT" },
  { rank: 2, aisle: "A", side: "SOL", code: "A_LEFT" },
  { rank: 3, aisle: "B", side: "SAĞ", code: "B_RIGHT" },
  { rank: 4, aisle: "B", side: "SOL", code: "B_LEFT" },
  { rank: 5, aisle: "C", side: "SAĞ", code: "C_RIGHT" },
  { rank: 6, aisle: "C", side: "SOL", code: "C_LEFT" },
  { rank: 7, aisle: "D", side: "SAĞ", code: "D_RIGHT" },
  { rank: 8, aisle: "D", side: "SOL", code: "D_LEFT" },
];

export function normalizeRuleText(value) {
  return String(value || "")
    .trim()
    .toUpperCase()
    .replaceAll("İ", "I")
    .replaceAll("Ş", "S")
    .replaceAll("Ğ", "G")
    .replaceAll("Ü", "U")
    .replaceAll("Ö", "O")
    .replaceAll("Ç", "C");
}

function safeNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function getWeight(weights = {}, key) {
  const merged = { ...DEFAULT_OPTIMIZATION_WEIGHTS, ...(weights || {}) };
  return Math.max(1, Math.min(10, safeNumber(merged[key], DEFAULT_OPTIMIZATION_WEIGHTS[key] || 5)));
}

function skuOf(product = {}) {
  return String(product.sku || product.SKU || product.barcode || product.Barcodes || product.product_code || "").trim();
}

function brandOf(product = {}) {
  return String(product.brand || product.brand_name || product.supplier || "MARKASIZ").trim();
}

function salesOf(product = {}) {
  return safeNumber(
    product.sales_qty_7d ??
    product.sales_7d ??
    product.sales_qty_30d ??
    product.daily_sales ??
    product.sales ??
    0,
    0
  );
}

function storageOf(product = {}) {
  const raw = normalizeRuleText(product.storage || product.storage_type || product.storage_class || "AMBIENT");
  if (raw.includes("FROZEN") || raw.includes("-18")) return "FROZEN";
  if (raw.includes("CHILLED") || raw.includes("+4")) return "CHILLED";
  return "AMBIENT";
}

function productText(product = {}) {
  return normalizeRuleText([
    product.sku,
    product.SKU,
    product.name,
    product.product_name,
    product.productName,
    product.brand,
    product.brand_name,
    product.category,
    product.category_l1,
    product.category_l2,
    product.category_l3,
    product.storage,
    product.storage_type,
    product.food_family,
    product.merch_group,
  ].filter(Boolean).join(" "));
}

function isProduce(product = {}) {
  const h = productText(product);
  return (
    h.includes("MEYVE") ||
    h.includes("SEBZE") ||
    h.includes("PRODUCE") ||
    h.includes("BANANA") ||
    h.includes("MUZ") ||
    h.includes("PATATES") ||
    h.includes("POTATO") ||
    h.includes("SOĞAN") ||
    h.includes("SOGAN") ||
    h.includes("DOMATES") ||
    h.includes("TOMATO") ||
    h.includes("LETTUCE") ||
    h.includes("MARUL")
  );
}

function domainOf(product = {}) {
  const st = storageOf(product);
  if (st === "AMBIENT" && isProduce(product)) return "PRODUCE";
  return st;
}

function hybridBrandRuleIsActive(rules = []) {
  return (rules || []).some((r) => {
    if (!r || r.active === false) return false;
    return (
      r.behavior === "hybrid_brand_block" ||
      r.value === "HYBRID_BRAND_BLOCK" ||
      r.type === "hybrid_brand_block"
    );
  });
}

function buildHybridBrandIndex(products = []) {
  const domainBrandMap = new Map();

  for (const p of products || []) {
    const domain = domainOf(p);
    const brand = brandOf(p);
    const key = `${domain}__${brand}`;

    if (!domainBrandMap.has(key)) {
      domainBrandMap.set(key, {
        domain,
        brand,
        totalSales: 0,
        skuCount: 0,
        products: [],
      });
    }

    const rec = domainBrandMap.get(key);
    rec.totalSales += salesOf(p);
    rec.skuCount += 1;
    rec.products.push(p);
  }

  const byDomain = new Map();

  for (const rec of domainBrandMap.values()) {
    if (!byDomain.has(rec.domain)) byDomain.set(rec.domain, []);
    byDomain.get(rec.domain).push(rec);
  }

  const index = new Map();

  for (const [, brands] of byDomain.entries()) {
    const rankedBrands = brands.sort((a, b) => {
      return b.totalSales - a.totalSales || b.skuCount - a.skuCount || a.brand.localeCompare(b.brand, "tr");
    });

    rankedBrands.forEach((brandRec, brandIdx) => {
      const brandRank = brandIdx + 1;
      const target = BRAND_BLOCK_TARGETS[(brandRank - 1) % BRAND_BLOCK_TARGETS.length];

      const rankedSku = [...brandRec.products].sort((a, b) => {
        return salesOf(b) - salesOf(a) || skuOf(a).localeCompare(skuOf(b), "tr");
      });

      rankedSku.forEach((p, skuIdx) => {
        const sku = skuOf(p);
        if (!sku) return;

        index.set(sku, {
          domain: brandRec.domain,
          brand: brandRec.brand,
          brandRank,
          brandTotalSales: brandRec.totalSales,
          brandSkuCount: brandRec.skuCount,
          skuRankInBrand: skuIdx + 1,
          target,
        });
      });
    });
  }

  return index;
}

function matchesRule(product = {}, rule = {}) {
  const value = normalizeRuleText(rule.value);
  if (!value) return false;

  const type = String(rule.type || "").toLowerCase();

  const fields = {
    brand: [product.brand, product.brand_name],
    category: [product.category, product.category_l1, product.category_l2],
    subcategory: [product.subcategory, product.category_l2, product.category_l3],
    storage: [product.storage, product.storage_type, product.storage_class],
    sku: [product.sku, product.SKU, product.barcode, product.Barcodes],
  };

  const selected = fields[type];

  if (selected) {
    return normalizeRuleText(selected.filter(Boolean).join(" ")).includes(value);
  }

  return productText(product).includes(value);
}

function applyManualRules(product, activeRules = []) {
  let next = { ...product };
  const applied = [];

  for (const rule of activeRules) {
    if (!rule || rule.active === false) continue;
    if (rule.behavior === "hybrid_brand_block" || rule.value === "HYBRID_BRAND_BLOCK") continue;
    if (!matchesRule(next, rule)) continue;

    const ruleWeight = Math.max(1, Math.min(10, safeNumber(rule.weight, 5)));
    const behavior = String(rule.behavior || "").toLowerCase();
    const target = String(rule.target_zone || "").toUpperCase();

    applied.push({
      id: rule.id,
      type: rule.type,
      value: rule.value,
      behavior,
      target_zone: target,
      weight: ruleWeight,
    });

    next.rule_score_boost = safeNumber(next.rule_score_boost, 0) + ruleWeight * 12;

    if (behavior === "increase_facing") {
      const facing = safeNumber(next.facing || next.facing_count, 1);
      next.facing = Math.min(4, facing + 1);
      next.facing_count = next.facing;
    }

    if (behavior === "reduce_facing") {
      const facing = safeNumber(next.facing || next.facing_count, 1);
      next.facing = Math.max(1, facing - 1);
      next.facing_count = next.facing;
    }

    if (behavior === "prefer_zone" || behavior === "force_zone") {
      next.preferred_rule_zone = target;
    }

    if (behavior === "keep_together") {
      next.keep_together_rule = rule.value;
    }

    if (behavior === "separate_from") {
      next.separate_from_rule = rule.value;
    }
  }

  if (applied.length) {
    next.applied_rules = [...(next.applied_rules || []), ...applied];
  }

  return next;
}

export function applyPlacementRulesBeforePlan(products = [], placementRules = [], optimizationWeights = {}) {
  const activeRules = (placementRules || []).filter((r) => r && r.active !== false);
  const hybridActive = hybridBrandRuleIsActive(activeRules);
  const hybridIndex = hybridActive ? buildHybridBrandIndex(products) : new Map();

  return (products || []).map((product, originalIndex) => {
    let next = { ...product, original_input_index: originalIndex };

    const baseSales = salesOf(next);
    const domain = domainOf(next);

    const baseScore =
      baseSales * (getWeight(optimizationWeights, "sales_weight") / 8) +
      (brandOf(next) !== "MARKASIZ" ? getWeight(optimizationWeights, "brand_block_weight") * 3 : 0) +
      (next.category || next.category_l1 || next.category_l2 ? getWeight(optimizationWeights, "category_weight") * 4 : 0) +
      (domain === "CHILLED" || domain === "FROZEN" ? getWeight(optimizationWeights, "cold_chain_weight") * 5 : 0);

    next.optimization_weight_score = Number(baseScore.toFixed(2));
    next.optimization_weights_applied = optimizationWeights;
    next.planogram_domain = domain;

    const hb = hybridIndex.get(skuOf(next));

    if (hb) {
      const brandWeight = getWeight(optimizationWeights, "brand_block_weight");

      next.hybrid_brand_block = true;
      next.brand_block_rank = hb.brandRank;
      next.brand_total_sales = Number(hb.brandTotalSales.toFixed(2));
      next.brand_block_target_aisle = hb.target.aisle;
      next.brand_block_target_side = hb.target.side;
      next.brand_block_target_code = hb.target.code;
      next.sku_rank_in_brand = hb.skuRankInBrand;

      next.preferred_aisle = hb.target.aisle;
      next.preferred_side = hb.target.side;
      next.preferred_brand_block = hb.target.code;

      /*
        Bilerek satış değerini devasa şişirmiyoruz.
        Önceki sürüm bu yüzden 3000+ ürünü atanamayanda bırakıyordu.
        Gerçek A sağ / A sol yerleşimi allocator slot scorer'a bağlanmalı.
      */
      next.hybrid_priority_score =
        Math.max(0, 1000 - hb.brandRank) * brandWeight +
        Math.max(0, 1000 - hb.skuRankInBrand) / 10;

      next.applied_rules = [
        ...(next.applied_rules || []),
        {
          id: "HYBRID_BRAND_BLOCK",
          type: "hybrid",
          value: hb.brand,
          behavior: "hybrid_brand_block",
          target_zone: `${hb.target.aisle}_${hb.target.side}`,
          weight: brandWeight,
        },
      ];

      next.placement_reason = [
        next.placement_reason,
        `Hibrit marka blok: ${hb.brand} marka satış sırası #${hb.brandRank} -> ${hb.target.aisle} ${hb.target.side}; marka içi SKU sırası #${hb.skuRankInBrand}`,
      ].filter(Boolean).join(" | ");
    }

    next = applyManualRules(next, activeRules);

    next.placement_reason = [
      next.placement_reason,
      `Ağırlık profili: satış ${getWeight(optimizationWeights, "sales_weight")}, kategori ${getWeight(optimizationWeights, "category_weight")}, marka blok ${getWeight(optimizationWeights, "brand_block_weight")}, picker ${getWeight(optimizationWeights, "picker_route_weight")}, soğuk zincir ${getWeight(optimizationWeights, "cold_chain_weight")}`,
    ].filter(Boolean).join(" | ");

    return next;
  });
}
