function upper(value) {
  return String(value || "")
    .toUpperCase()
    .replaceAll("İ", "I")
    .replaceAll("Ş", "S")
    .replaceAll("Ğ", "G")
    .replaceAll("Ü", "U")
    .replaceAll("Ö", "O")
    .replaceAll("Ç", "C");
}

function skuOf(p = {}) {
  return String(p.sku || p.SKU || p.barcode || p.product_code || "").trim();
}

function aisleOf(p = {}) {
  return String(p.aisle_id || p.aisle || p.corridor || p.zone || "").trim();
}

function moduleOf(p = {}) {
  return String(p.module_id || p.module || p.module_no || "").trim();
}

function shelfOf(p = {}) {
  return String(p.shelf_no || p.shelf || p.raf || "").trim();
}

function textOf(p = {}) {
  return upper([
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
    p.frontend_category_local,
    p.frontend_subcategory_local,
    p.storage,
    p.storage_type,
    p.food_family,
    p.merch_group,
  ].filter(Boolean).join(" "));
}

export function foodSafetyFamily(product = {}) {
  const h = textOf(product);

  const chemical =
    h.includes("DOMESTOS") ||
    h.includes("CIF") ||
    h.includes("OMO") ||
    h.includes("PEROS") ||
    h.includes("YUMOS") ||
    h.includes("PRIL") ||
    h.includes("DETERJAN") ||
    h.includes("DETERGENT") ||
    h.includes("CLEANER") ||
    h.includes("CLEANING") ||
    h.includes("BLEACH") ||
    h.includes("WC BLOCK") ||
    h.includes("SOAP") ||
    h.includes("SABUN") ||
    h.includes("LIQUID SOAP") ||
    h.includes("SURFACE") ||
    h.includes("POLISH") ||
    h.includes("SHAMPOO") ||
    h.includes("SPRAY") ||
    h.includes("DIRT") ||
    h.includes("OIL REMOVER");

  if (chemical) return "NON_FOOD_CHEMICAL";

  const nonFoodGeneral =
    h.includes("TOILET PAPER") ||
    h.includes("PAPER TOWEL") ||
    h.includes("NAPKIN") ||
    h.includes("TISSUE") ||
    h.includes("DIAPER") ||
    h.includes("WET WIPE") ||
    h.includes("ISLAK MENDIL") ||
    h.includes("FOLDER") ||
    h.includes("BATTERY") ||
    h.includes("PIL ") ||
    h.includes("CONDOM") ||
    h.includes("TOOTHBRUSH") ||
    h.includes("TOOTHPASTE");

  if (nonFoodGeneral) return "NON_FOOD_GENERAL";

  const pet =
    h.includes("CAT FOOD") ||
    h.includes("DOG FOOD") ||
    h.includes("CAT TREAT") ||
    h.includes("DOG TREAT") ||
    h.includes("WANPY") ||
    h.includes("DREAMIES") ||
    h.includes("KEDI") ||
    h.includes("KOPEK") ||
    h.includes("KÖPEK") ||
    h.includes("MAMA");

  if (pet) return "NON_FOOD_PET";

  return "FOOD";
}

function familyGroup(family) {
  return String(family || "").startsWith("NON_FOOD") ? "NON_FOOD" : "FOOD";
}

function shelfKey(product = {}) {
  return `${aisleOf(product)}__${moduleOf(product)}__${shelfOf(product)}`;
}

function moduleKey(product = {}) {
  return `${aisleOf(product)}__${moduleOf(product)}`;
}

function makeUnplaced(product, reasonDetail) {
  const fam = foodSafetyFamily(product);

  return {
    ...product,
    reason: "FOOD_SAFETY_HARD_ISOLATION",
    reason_code: "FOOD_SAFETY_HARD_ISOLATION",
    suggested_action: reasonDetail,
    food_safety_family: fam,
    food_safety_group: familyGroup(fam),
    placement_reason: [
      product.placement_reason,
      reasonDetail,
    ].filter(Boolean).join(" | "),
  };
}

export function enforceFoodSafetyHardIsolation(products = [], unplacedProducts = []) {
  if (!Array.isArray(products) || products.length === 0) {
    return {
      changed: false,
      products,
      unplacedProducts,
      removed: 0,
      violations: [],
    };
  }

  const enriched = products.map((p) => {
    const fam = foodSafetyFamily(p);
    return {
      ...p,
      food_safety_family: fam,
      food_safety_group: familyGroup(fam),
    };
  });

  const toRemove = new Set();
  const violations = [];

  const shelves = new Map();

  for (const p of enriched) {
    const key = shelfKey(p);
    if (!key || key === "____") continue;
    if (!shelves.has(key)) shelves.set(key, []);
    shelves.get(key).push(p);
  }

  for (const [key, items] of shelves.entries()) {
    const groups = new Set(items.map((p) => p.food_safety_group));

    if (groups.has("FOOD") && groups.has("NON_FOOD")) {
      const foodCount = items.filter((p) => p.food_safety_group === "FOOD").length;
      const nonFoodCount = items.filter((p) => p.food_safety_group === "NON_FOOD").length;

      const removeGroup = nonFoodCount <= foodCount ? "NON_FOOD" : "FOOD";

      for (const p of items) {
        if (p.food_safety_group === removeGroup) {
          toRemove.add(skuOf(p) || `${key}-${p.product_name || p.name}`);
        }
      }

      violations.push({
        type: "SHELF_FOOD_NONFOOD_MIX",
        key,
        removeGroup,
        foodCount,
        nonFoodCount,
      });
    }
  }

  const modules = new Map();

  for (const p of enriched) {
    const key = moduleKey(p);
    if (!key || key === "__") continue;
    if (!modules.has(key)) modules.set(key, []);
    modules.get(key).push(p);
  }

  for (const [key, items] of modules.entries()) {
    const foodCount = items.filter((p) => p.food_safety_group === "FOOD").length;
    const nonFoodCount = items.filter((p) => p.food_safety_group === "NON_FOOD").length;

    if (foodCount && nonFoodCount) {
      const removeGroup = nonFoodCount <= foodCount ? "NON_FOOD" : "FOOD";

      for (const p of items) {
        if (p.food_safety_group === removeGroup) {
          toRemove.add(skuOf(p) || `${key}-${p.product_name || p.name}`);
        }
      }

      violations.push({
        type: "MODULE_FOOD_NONFOOD_MIX",
        key,
        removeGroup,
        foodCount,
        nonFoodCount,
      });
    }
  }

  if (toRemove.size === 0) {
    return {
      changed: false,
      products: enriched,
      unplacedProducts,
      removed: 0,
      violations,
    };
  }

  const existingUnplaced = new Set(
    (unplacedProducts || []).map((p) => skuOf(p)).filter(Boolean)
  );

  const kept = [];
  const moved = [];

  for (const p of enriched) {
    const key = skuOf(p) || `${moduleKey(p)}-${p.product_name || p.name}`;

    if (toRemove.has(key)) {
      if (!existingUnplaced.has(skuOf(p))) {
        moved.push(makeUnplaced(
          p,
          "Gıda / gıda dışı hard izolasyon: aynı raf veya aynı modül kalite ve koku riski nedeniyle engellendi."
        ));
      }
    } else {
      kept.push(p);
    }
  }

  return {
    changed: true,
    products: kept,
    unplacedProducts: [...(unplacedProducts || []), ...moved],
    removed: moved.length,
    violations,
  };
}
