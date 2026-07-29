export const STRATEGY_MODES = {
  CATEGORY_SALES: "CATEGORY_SALES",
  ABC_DIRECT: "ABC_DIRECT",
  HYBRID_CATEGORY_ABC_SALES: "HYBRID_CATEGORY_ABC_SALES",
  HYBRID_BRAND_SALES: "HYBRID_BRAND_SALES",
};

export const DEFAULT_OPTIMIZATION_WEIGHTS = {
  sales_weight: 8,
  category_weight: 8,
  brand_block_weight: 6,
  abc_location_weight: 7,
  basket_affinity_weight: 5,
  refill_cost_weight: 7,
  picker_route_weight: 6,
  cold_chain_weight: 10,
  capacity_weight: 9,
  shelf_fill_weight: 8,
};

export const DEFAULT_STRATEGY_PROFILE = {
  mode: STRATEGY_MODES.CATEGORY_SALES,
  label: "Kategori içinde satış sıralı",
  weights_enabled: false,
  rules_enabled: true,
  editable_weights_roles: ["admin"],
  weights: DEFAULT_OPTIMIZATION_WEIGHTS,
};

const BRAND_BLOCK_TARGETS = [
  { rank: 1, aisle: "A", side: "SAĞ", code: "A_RIGHT" },
  { rank: 2, aisle: "A", side: "SOL", code: "A_LEFT" },
  { rank: 3, aisle: "B", side: "SAĞ", code: "B_RIGHT" },
  { rank: 4, aisle: "B", side: "SOL", code: "B_LEFT" },
  { rank: 5, aisle: "C", side: "SAĞ", code: "C_RIGHT" },
  { rank: 6, aisle: "C", side: "SOL", code: "C_LEFT" },
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

function loadStrategyProfile(fallback = DEFAULT_STRATEGY_PROFILE) {
  try {
    const raw = localStorage.getItem("plonagram_strategy_profile");
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return {
      ...DEFAULT_STRATEGY_PROFILE,
      ...(parsed || {}),
      weights: {
        ...DEFAULT_OPTIMIZATION_WEIGHTS,
        ...((parsed || {}).weights || {}),
      },
    };
  } catch {
    return fallback;
  }
}

function getCurrentRole() {
  try {
    return String(localStorage.getItem("plonagram_user_role") || "admin").toLowerCase();
  } catch {
    return "admin";
  }
}

function canEditWeights(strategyProfile) {
  const role = getCurrentRole();
  const allowed = strategyProfile?.editable_weights_roles || ["admin"];
  return allowed.map((x) => String(x).toLowerCase()).includes(role);
}

function skuOf(p = {}) {
  return String(p.sku || p.SKU || p.barcode || p.Barcodes || p.product_code || "").trim();
}

function brandOf(p = {}) {
  return String(p.brand || p.brand_name || p.supplier || "MARKASIZ").trim();
}

function categoryOf(p = {}) {
  return String(p.category || p.category_l1 || p.category_l2 || p.category_l3 || "KATEGORİSİZ").trim();
}

function salesOf(p = {}) {
  return safeNumber(
    p.sales_qty_7d ??
      p.sales_7d ??
      p.sales_qty_30d ??
      p.daily_sales ??
      p.sales ??
      0,
    0
  );
}

function abcLocationOf(p = {}) {
  return String(
    p.abc_location ||
      p.location ||
      p.Location ||
      p.secondary_location ||
      p["Secondary Location"] ||
      p.old_location ||
      ""
  ).trim();
}

function storageOf(p = {}) {
  const raw = normalizeRuleText(p.storage || p.storage_type || p.storage_class || "AMBIENT");
  if (raw.includes("FROZEN") || raw.includes("-18")) return "FROZEN";
  if (raw.includes("CHILLED") || raw.includes("+4")) return "CHILLED";
  return "AMBIENT";
}

function productText(p = {}) {
  return normalizeRuleText([
    p.sku,
    p.SKU,
    p.name,
    p.product_name,
    p.productName,
    p.brand,
    p.brand_name,
    p.category,
    p.category_l1,
    p.category_l2,
    p.category_l3,
    p.storage,
    p.storage_type,
    p.food_family,
    p.merch_group,
  ].filter(Boolean).join(" "));
}

function isProduce(p = {}) {
  const h = productText(p);
  return (
    h.includes("MEYVE") ||
    h.includes("SEBZE") ||
    h.includes("PRODUCE") ||
    h.includes("BANANA") ||
    h.includes("MUZ") ||
    h.includes("PATATES") ||
    h.includes("POTATO") ||
    h.includes("SOGAN") ||
    h.includes("SOĞAN") ||
    h.includes("DOMATES") ||
    h.includes("TOMATO") ||
    h.includes("LETTUCE") ||
    h.includes("MARUL")
  );
}

function domainOf(p = {}) {
  const storage = storageOf(p);
  if (storage === "AMBIENT" && isProduce(p)) return "PRODUCE";
  return storage;
}

function domainOrder(p = {}) {
  const d = domainOf(p);
  if (d === "AMBIENT") return 1;
  if (d === "PRODUCE") return 2;
  if (d === "CHILLED") return 3;
  if (d === "FROZEN") return 4;
  return 9;
}

function matchesRule(product = {}, rule = {}) {
  const q = normalizeRuleText(rule.value);
  if (!q) return false;

  const type = String(rule.type || "").toLowerCase();
  const fields = {
    brand: [product.brand, product.brand_name],
    category: [product.category, product.category_l1, product.category_l2, product.category_l3],
    subcategory: [product.subcategory, product.category_l2, product.category_l3],
    storage: [product.storage, product.storage_type, product.storage_class],
    sku: [product.sku, product.SKU, product.barcode, product.Barcodes],
  };

  const selected = fields[type];
  if (selected) return normalizeRuleText(selected.filter(Boolean).join(" ")).includes(q);

  return productText(product).includes(q);
}

function buildBrandRank(products = []) {
  const byDomainBrand = new Map();

  for (const p of products) {
    const domain = domainOf(p);
    const brand = brandOf(p);
    const key = `${domain}__${brand}`;

    if (!byDomainBrand.has(key)) {
      byDomainBrand.set(key, { domain, brand, totalSales: 0, skuCount: 0, products: [] });
    }

    const rec = byDomainBrand.get(key);
    rec.totalSales += salesOf(p);
    rec.skuCount += 1;
    rec.products.push(p);
  }

  const byDomain = new Map();

  for (const rec of byDomainBrand.values()) {
    if (!byDomain.has(rec.domain)) byDomain.set(rec.domain, []);
    byDomain.get(rec.domain).push(rec);
  }

  const out = new Map();

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

        out.set(sku, {
          domain: brandRec.domain,
          brand: brandRec.brand,
          brandRank,
          brandTotalSales: brandRec.totalSales,
          skuRankInBrand: skuIdx + 1,
          target,
        });
      });
    });
  }

  return out;
}

function applyManualRules(product, activeRules = []) {
  let next = { ...product };
  const applied = [];

  for (const rule of activeRules) {
    if (!rule || rule.active === false) continue;
    if (!matchesRule(next, rule)) continue;

    const behavior = String(rule.behavior || "prefer_block").toLowerCase();
    const targetAisle = String(rule.target_aisle || "").trim();
    const targetSide = String(rule.target_side || "").trim();

    applied.push({
      id: rule.id,
      type: rule.type,
      value: rule.value,
      behavior,
      target_aisle: targetAisle,
      target_side: targetSide,
      weight: safeNumber(rule.weight, 7),
    });

    if (targetAisle) next.preferred_aisle = targetAisle;
    if (targetSide) next.preferred_side = targetSide;

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
  }

  if (applied.length) {
    next.applied_rules = [...(next.applied_rules || []), ...applied];
    next.placement_reason = [
      next.placement_reason,
      `Manuel kural: ${applied.map((r) => `${r.type}:${r.value} -> ${r.target_aisle || "-"} ${r.target_side || ""}`).join(", ")}`,
    ].filter(Boolean).join(" | ");
  }

  return next;
}

function strategySortValue(product = {}, brandIndex, strategyProfile) {
  const mode = strategyProfile.mode;

  if (mode === STRATEGY_MODES.CATEGORY_SALES) {
    return {
      a: domainOrder(product),
      b: categoryOf(product),
      c: -salesOf(product),
      d: brandOf(product),
    };
  }

  if (mode === STRATEGY_MODES.ABC_DIRECT) {
    return {
      a: domainOrder(product),
      b: abcLocationOf(product) || "ZZZ",
      c: categoryOf(product),
      d: -salesOf(product),
    };
  }

  if (mode === STRATEGY_MODES.HYBRID_BRAND_SALES) {
    const hb = brandIndex.get(skuOf(product));
    return {
      a: domainOrder(product),
      b: hb?.brandRank ?? 9999,
      c: hb?.skuRankInBrand ?? 9999,
      d: -salesOf(product),
    };
  }

  return {
    a: domainOrder(product),
    b: categoryOf(product),
    c: abcLocationOf(product) || "ZZZ",
    d: -salesOf(product),
  };
}

function compareStrategy(a, b, brandIndex, strategyProfile) {
  const av = strategySortValue(a, brandIndex, strategyProfile);
  const bv = strategySortValue(b, brandIndex, strategyProfile);

  return (
    av.a - bv.a ||
    String(av.b).localeCompare(String(bv.b), "tr") ||
    Number(av.c) - Number(bv.c) ||
    String(av.d).localeCompare(String(bv.d), "tr")
  );
}

export function applyPlacementRulesBeforePlan(
  products = [],
  placementRules = [],
  optimizationWeights = {},
  strategyProfileArg = null
) {
  const strategyProfile = {
    ...loadStrategyProfile(),
    ...(strategyProfileArg || {}),
  };

  const weights = {
    ...DEFAULT_OPTIMIZATION_WEIGHTS,
    ...(strategyProfile.weights || {}),
    ...(optimizationWeights || {}),
  };

  const activeRules = (placementRules || []).filter((r) => r && r.active !== false);
  const brandIndex = buildBrandRank(products);

  const hydrated = (products || []).map((product, originalIndex) => {
    let next = {
      ...product,
      original_input_index: originalIndex,
      strategy_mode: strategyProfile.mode,
      strategy_label: strategyProfile.label,
      planogram_domain: domainOf(product),
    };

    const hb = brandIndex.get(skuOf(next));

    if (hb) {
      next.brand_block_rank = hb.brandRank;
      next.brand_total_sales = Number(hb.brandTotalSales.toFixed(2));
      next.sku_rank_in_brand = hb.skuRankInBrand;
      next.brand_block_target_aisle = hb.target.aisle;
      next.brand_block_target_side = hb.target.side;
      next.brand_block_target_code = hb.target.code;

      if (strategyProfile.mode === STRATEGY_MODES.HYBRID_BRAND_SALES) {
        next.hybrid_brand_block = true;
        next.preferred_aisle = hb.target.aisle;
        next.preferred_side = hb.target.side;
      }
    }

    if (
      strategyProfile.mode === STRATEGY_MODES.HYBRID_CATEGORY_ABC_SALES ||
      strategyProfile.mode === STRATEGY_MODES.HYBRID_BRAND_SALES
    ) {
      const canUseWeights = strategyProfile.weights_enabled && canEditWeights(strategyProfile);

      next.optimization_weights_applied = canUseWeights ? weights : DEFAULT_OPTIMIZATION_WEIGHTS;
      next.optimization_weight_score =
        salesOf(next) * (safeNumber(weights.sales_weight, 8) / 8) +
        (categoryOf(next) ? safeNumber(weights.category_weight, 8) * 3 : 0) +
        (abcLocationOf(next) ? safeNumber(weights.abc_location_weight, 7) * 2 : 0) +
        (hb ? safeNumber(weights.brand_block_weight, 6) * 2 : 0);
    }

    next = applyManualRules(next, activeRules);

    next.placement_reason = [
      next.placement_reason,
      `Strateji: ${strategyProfile.label}`,
      strategyProfile.mode === STRATEGY_MODES.CATEGORY_SALES
        ? `Kategori içinde satış sıralı: ${categoryOf(next)} / satış ${salesOf(next)}`
        : "",
      strategyProfile.mode === STRATEGY_MODES.ABC_DIRECT
        ? `ABC direkt referans: ${abcLocationOf(next) || "ABC lokasyon yok"}`
        : "",
      strategyProfile.mode === STRATEGY_MODES.HYBRID_BRAND_SALES && hb
        ? `Hibrit marka blok: ${hb.brand} marka sıra #${hb.brandRank}, hedef ${hb.target.aisle} ${hb.target.side}, marka içi SKU sıra #${hb.skuRankInBrand}`
        : "",
    ].filter(Boolean).join(" | ");

    return next;
  });

  return hydrated.sort((a, b) => {
    return compareStrategy(a, b, brandIndex, strategyProfile) || safeNumber(a.original_input_index) - safeNumber(b.original_input_index);
  });
}
