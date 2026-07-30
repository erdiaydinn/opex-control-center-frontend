// Plonagram AI Darkstore utility + orientation-aware optimizer

export const DEFAULT_PRODUCTS = [
  { sku: "ULKER_BIS", product_name: "Ülker Bisküvi", brand: "Ülker", category_l1: "Snack", category_l2: "Biscuit", storage_type: "AMBIENT", width_cm: 12, height_cm: 18, depth_cm: 3, case_width_cm: 40, case_height_cm: 25, case_depth_cm: 30, case_pack_qty: 24, sales_qty_7d: 180, percent_stops: 10, orientation: "horizontal" },
  { sku: "WATER_5L", product_name: "Su 5L", brand: "Water", category_l1: "Beverage", category_l2: "Water", storage_type: "AMBIENT", width_cm: 16, height_cm: 36, depth_cm: 16, case_pack_qty: 4, sales_qty_7d: 220, percent_stops: 15, weight_kg: 5, orientation: "vertical" },
  { sku: "CHICKEN", product_name: "Tavuk Göğüs", brand: "Generic", category_l1: "Meat", category_l2: "Chicken", storage_type: "CHILLED", width_cm: 18, height_cm: 4, depth_cm: 14, case_pack_qty: 8, sales_qty_7d: 120, percent_stops: 6, orientation: "horizontal" },
  { sku: "ICE", product_name: "Algida Dondurma", brand: "Algida", category_l1: "Frozen", category_l2: "Ice Cream", storage_type: "FROZEN", width_cm: 14, height_cm: 12, depth_cm: 8, case_pack_qty: 8, sales_qty_7d: 90, percent_stops: 4, orientation: "horizontal" },
];

export const RULES = {
  DARKSTORE_AI: "DARKSTORE_AI",
  HYBRID: "HYBRID",
  SALES: "SALES",
  ABC: "ABC",
  PICKING: "PICKING",
  CATEGORY: "CATEGORY",
  BRAND: "BRAND",
  BRAND_BLOCK: "BRAND_BLOCK",
  COLD_CHAIN: "COLD_CHAIN",
  HEAVY_LAST: "HEAVY_LAST",
};

export function clone(obj) {
  return JSON.parse(JSON.stringify(obj || {}));
}

export function n(v, d = 0) {
  const parsed = Number(String(v ?? "").replace(",", ".").trim());
  return Number.isFinite(parsed) ? parsed : d;
}

function first(...vals) {
  return vals.find((v) => v !== undefined && v !== null && String(v).trim() !== "") ?? "";
}

function inferStorage(raw = {}) {
  const txt = `${raw.product_name || ""} ${raw.name || ""} ${raw.category_l1 || ""} ${raw.category_l2 || ""} ${raw.frontend_category_local || ""} ${raw.frontend_subcategory_local || ""}`.toLowerCase();
  const explicit = String(raw.storage_type || raw["Storage Type"] || "").trim().toUpperCase();
  if (explicit) {
    if (["CHILLED", "COLD", "+4", "SOGUK", "SOĞUK"].includes(explicit)) return "CHILLED";
    if (["FROZEN", "-18", "DONUK"].includes(explicit)) return "FROZEN";
    if (["AMBIENT", "KURU", "DRY"].includes(explicit)) return "AMBIENT";
    return explicit;
  }
  if (/dondurma|ice cream|frozen|donuk|-18|algida/.test(txt)) return "FROZEN";
  if (/tavuk|et |süt|yoğurt|peynir|şarküteri|chilled|soğuk|\+4/.test(txt)) return "CHILLED";
  if (/pide|ramazan|fırın|firin|bakery/.test(txt)) return "AMBIENT";
  return "AMBIENT";
}

function inferOrientation(raw = {}) {
  const txt = `${raw.product_name || ""} ${raw.category_l2 || ""} ${raw.category_l1 || ""}`.toLowerCase();
  if (raw.orientation) return String(raw.orientation).toLowerCase();
  if (/bisküvi|biskuvi|biscuit|çikolata|chocolate|bar|gofret|wafer|makarna|pasta/.test(txt)) return "horizontal";
  if (/su|water|cola|içecek|beverage|süt|milk|şişe|bottle/.test(txt)) return "vertical";
  return "horizontal";
}

export function normalizeProduct(raw = {}) {
  const product_name = String(first(raw.product_name, raw["Product Name"], raw.name, raw["Ürün Adı"], "Unnamed Product"));
  const width = Math.max(1, n(first(raw.width_cm, raw.product_width_in_cm, raw.Width, raw.En), 10));
  const height = Math.max(1, n(first(raw.height_cm, raw.product_height_in_cm, raw.Height, raw.Boy), 15));
  const depth = Math.max(1, n(first(raw.depth_cm, raw.product_depth_in_cm, raw.Depth, raw.Derinlik), 8));
  const orientation = inferOrientation({ ...raw, product_name });
  return {
    ...raw,
    sku: String(first(raw.sku, raw.SKU, raw.product_sku, raw.barcode, raw.Barcode, `SKU-${Math.random().toString(36).slice(2, 9)}`)),
    product_name,
    brand: String(first(raw.brand, raw.Brand, raw.brand_name, String(product_name).split(" ")[0], "Unknown")),
    category_l1: String(first(raw.category_l1, raw.category, raw.frontend_category_local, raw.pim_cat_l1, "Uncategorized")),
    category_l2: String(first(raw.category_l2, raw.subcategory, raw.frontend_subcategory_local, raw.pim_cat_l2, "General")),
    storage_type: inferStorage(raw),
    width_cm: width,
    height_cm: height,
    depth_cm: depth,
    case_width_cm: n(first(raw.case_width_cm, raw.case_w_cm, raw.koli_width_cm), width * Math.max(1, n(raw.case_pack_qty, 1))),
    case_height_cm: n(first(raw.case_height_cm, raw.case_h_cm, raw.koli_height_cm), height),
    case_depth_cm: n(first(raw.case_depth_cm, raw.case_d_cm, raw.koli_depth_cm), depth),
    weight_kg: n(first(raw.weight_kg, raw.product_weight_value), 0.2),
    case_pack_qty: n(first(raw.case_pack_qty, raw["Case Pack"]), 1),
    sales_qty_7d: n(first(raw.sales_qty_7d, raw.sales_7d, raw.orders_7d, raw.sales), 0),
    percent_stops: n(first(raw.percent_stops, raw["% Stops"], raw.stops_7d, raw.stop_count), 0),
    image_url: String(first(raw.image_url, raw.product_image_url, raw.catalog_image_url, raw.pim_image_url, "")),
    orientation,
    orientation_mix: raw.orientation_mix || null,
    facing_count: Math.max(1, n(first(raw.facing_count, raw.facing), 1)),
  };
}

function splitCSVLine(line, delimiter) {
  const out = [];
  let cur = "";
  let q = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (q && line[i + 1] === '"') { cur += '"'; i++; }
      else q = !q;
      continue;
    }
    if (ch === delimiter && !q) { out.push(cur.trim()); cur = ""; continue; }
    cur += ch;
  }
  out.push(cur.trim());
  return out;
}

export function parseCSV(text) {
  const lines = String(text || "").replace(/^\ufeff/, "").split(/\r?\n/).filter((x) => x.trim());
  if (!lines.length) return [];
  const delimiter = (lines[0].match(/;/g) || []).length > (lines[0].match(/,/g) || []).length ? ";" : ",";
  const headers = splitCSVLine(lines[0], delimiter);
  return lines.slice(1).map((line) => {
    const values = splitCSVLine(line, delimiter);
    const row = {};
    headers.forEach((h, i) => { row[h] = values[i] ?? ""; });
    return normalizeProduct(row);
  });
}

export function makeShelves(count, storageType = "AMBIENT", width = 100, height = 35, depth = 50, maxWeight = 45) {
  return Array.from({ length: count }, (_, i) => ({
    shelf_no: i + 1,
    shelf_width_cm: width,
    shelf_height_cm: height,
    shelf_depth_cm: depth,
    max_weight_kg: maxWeight,
    zone_type: i === 0 ? "bottom" : i === count - 1 ? "top" : i >= Math.floor(count / 2) ? "eye" : "mid",
    allowed_storage_type: storageType,
    products: [],
    used_width_cm: 0,
    used_volume_cm3: 0,
    used_weight_kg: 0,
  }));
}

export function generateDefaultLayout(storeCode = "ACIBADEM") {
  const ids = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"];

  const makeDefaultModules = (count = 10, storage = "AMBIENT") =>
    Array.from({ length: count }, (_, m) => ({
      module_id: m + 1,
      side: m < 5 ? "L" : "R",
      module_side: m < 5 ? "L" : "R",
      module_type: "regular_shelf",
      module_width_cm: 100,
      module_depth_cm: 50,
      module_height_cm: 210,
      layout_orientation: "vertical",
      layout_rotation: 0,
      shelves: makeShelves(6, storage, 100, 35, 50, storage === "AMBIENT" ? 45 : 60),
    }));

  const aisles = ids.map((id, i) => ({
    aisle_id: id,
    row: Math.floor(i / 2) + 1,
    position: i % 2,
    direction: "LTR",
    aisle_type: "double_sided",
    left_modules: 5,
    right_modules: 5,
    module_count: 10,
    walkway_width_m: 1.2,
    distance_to_dispatch: i + 1,
    // Artık A/B birbirinin raf tarafı değil; her harf kendi picker koridorudur.
    layout_position: { grid_x: (i % 2) * 11, grid_y: Math.floor(i / 2) * 5, rotation: 0 },
    modules: makeDefaultModules(10, "AMBIENT"),
  }));

  aisles.push({
    aisle_id: "MARTEK+4",
    zone_type: "COLD_ZONE",
    fixture_type: "four_door_cooler",
    aisle_type: "single_sided",
    left_modules: 5,
    right_modules: 0,
    module_count: 5,
    walkway_width_m: 1.2,
    layout_position: { grid_x: 23, grid_y: 0, rotation: 0 },
    modules: Array.from({ length: 5 }, (_, m) => ({
      module_id: m + 1,
      side: "L",
      module_side: "L",
      module_type: "fridge",
      module_width_cm: 150,
      module_depth_cm: 60,
      module_height_cm: 210,
      layout_orientation: "vertical",
      layout_rotation: 0,
      shelves: makeShelves(6, "CHILLED", 150, 35, 55, 60),
    })),
  });

  aisles.push({
    aisle_id: "MARTEK-18",
    zone_type: "FROZEN_ZONE",
    fixture_type: "horizontal_freezer",
    aisle_type: "single_sided",
    left_modules: 4,
    right_modules: 0,
    module_count: 4,
    walkway_width_m: 1.2,
    layout_position: { grid_x: 23, grid_y: 5, rotation: 0 },
    modules: Array.from({ length: 4 }, (_, m) => ({
      module_id: m + 1,
      side: "L",
      module_side: "L",
      module_type: "horizontal_freezer",
      module_width_cm: 158,
      module_depth_cm: 60,
      module_height_cm: 90,
      layout_orientation: "vertical",
      layout_rotation: 0,
      shelves: makeShelves(3, "FROZEN", 158, 40, 60, 70),
    })),
  });

  return {
    store_code: storeCode,
    route_strategy: "AI_DARKSTORE_FLOW",
    language: "tr",
    layout_objects: [
      { id: "dispatch-1", type: "dispatch", x: 0, y: -3, w: 4, h: 2, rotation: 0, label: "DISPATCH" },
      { id: "wall-n", type: "wall", x: 0, y: -5, w: 32, h: .25, rotation: 0, label: "DUVAR" },
      { id: "wall-s", type: "wall", x: 0, y: 24, w: 32, h: .25, rotation: 0, label: "DUVAR" },
      { id: "wall-e", type: "wall", x: 27, y: 8, w: .25, h: 30, rotation: 0, label: "DUVAR" },
      { id: "wall-w", type: "wall", x: -18, y: 8, w: .25, h: 30, rotation: 0, label: "DUVAR" },
    ],
    aisles,
  };
}

export function facingWidth(product, orientationOverride = null) {
  const p = normalizeProduct(product);
  const orientation = orientationOverride || p.orientation || "horizontal";
  const unitWidth = orientation === "vertical" ? p.depth_cm : p.width_cm;
  return Math.max(1, unitWidth);
}

export function productWidth(product) {
  const p = normalizeProduct(product);
  return Math.round(facingWidth(p) * Math.max(1, n(p.facing_count ?? p.facing, 1)) * 10) / 10;
}

export function faceCount(product) {
  return Math.max(1, n(product?.facing_count ?? product?.facing, 1));
}

export function productVolume(product) {
  const p = normalizeProduct(product);
  return Math.round(p.width_cm * p.height_cm * p.depth_cm * faceCount(p));
}

export function recalcShelf(shelf) {
  const products = shelf.products || [];
  shelf.used_width_cm = Math.round(products.reduce((s, p) => s + productWidth(p), 0) * 10) / 10;
  shelf.used = shelf.used_width_cm;
  shelf.capacity_volume_cm3 = Math.round(n(shelf.shelf_width_cm, 100) * n(shelf.shelf_height_cm, 35) * n(shelf.shelf_depth_cm, 50));
  shelf.used_volume_cm3 = Math.round(products.reduce((s, p) => s + productVolume(p), 0));
  shelf.used_weight_kg = Math.round(products.reduce((s, p) => s + n(p.weight_kg, .2) * faceCount(p), 0) * 100) / 100;
  return shelf;
}

export function shelfUsedWidth(shelf) {
  return recalcShelf({ ...shelf }).used_width_cm || 0;
}

export function shelfUtil(shelf) {
  return Math.round((shelfUsedWidth(shelf) / Math.max(1, n(shelf?.shelf_width_cm, 100))) * 100);
}

export function shelfVolUtil(shelf) {
  const s = recalcShelf({ ...shelf });
  return Math.round((n(s.used_volume_cm3, 0) / Math.max(1, n(s.capacity_volume_cm3, 1))) * 100);
}

export function findShelf(plan, aisleId, moduleId, shelfNo) {
  for (const aisle of plan?.aisles || []) {
    if (String(aisle.aisle_id) !== String(aisleId)) continue;
    for (const module of aisle.modules || []) {
      if (String(module.module_id) !== String(moduleId)) continue;
      for (const shelf of module.shelves || []) {
        if (String(shelf.shelf_no) === String(shelfNo)) return { aisle, module, shelf };
      }
    }
  }
  return null;
}

function storageOrder(s) {
  const x = String(s || "AMBIENT").toUpperCase();
  if (x === "AMBIENT") return 1;
  if (x === "CHILLED") return 2;
  if (x === "FROZEN") return 3;
  return 9;
}

function scoreProduct(p, mode = "DARKSTORE_AI", weights = {}) {
  const w = { sales: 1.35, picking: 1.2, ergonomics: 1, refill: .85, risk: 1.15, fixture: 1.4, ...weights };
  const sales = n(p.sales_qty_7d, 0);
  const stops = n(p.percent_stops, 0);
  const heavyPenalty = n(p.weight_kg, 0) >= 3 ? 35 : 0;
  const coldBonus = p.storage_type === "CHILLED" || p.storage_type === "FROZEN" ? 12 : 0;
  if (["SALES", "ABC"].includes(String(mode).toUpperCase())) return sales * 100 + stops;
  if (String(mode).toUpperCase().includes("PICK")) return stops * 120 + sales;
  return sales * w.sales + stops * 20 * w.picking + coldBonus - heavyPenalty * w.ergonomics;
}

export function compareByRule(ruleId = "DARKSTORE_AI", weights = {}) {
  return (a, b) => {
    const pa = normalizeProduct(a), pb = normalizeProduct(b);
    const mode = String(ruleId || "").toUpperCase();
    if (mode === "CATEGORY") {
      return `${pa.category_l1}|${pa.category_l2}|${pa.brand}`.localeCompare(`${pb.category_l1}|${pb.category_l2}|${pb.brand}`) || scoreProduct(pb, "SALES") - scoreProduct(pa, "SALES");
    }
    if (mode === "BRAND" || mode === "BRAND_BLOCK") {
      return `${pa.brand}|${pa.category_l2}`.localeCompare(`${pb.brand}|${pb.category_l2}`) || scoreProduct(pb, "SALES") - scoreProduct(pa, "SALES");
    }
    return scoreProduct(pb, mode, weights) - scoreProduct(pa, mode, weights);
  };
}

function facingForProduct(p, mode) {
  // FIRST PASS: all products start with 1 facing to place max SKU coverage.
  return 1;
}

function collectShelves(plan) {
  const out = [];
  for (const aisle of plan?.aisles || []) {
    for (const module of aisle.modules || []) {
      for (const shelf of module.shelves || []) out.push({ aisle, module, shelf });
    }
  }
  return out;
}

function compatible(p, shelf) {
  const st = String(shelf.allowed_storage_type || "AMBIENT").toUpperCase();
  if (p.storage_type !== st) return false;
  if (p.height_cm > n(shelf.shelf_height_cm, 35) * 1.35) return false;
  if (p.depth_cm > n(shelf.shelf_depth_cm, 50) * 1.35) return false;
  return true;
}

export function applyAdvancedRulesToPlan(plan, rules = []) {
  const next = clone(plan);
  if (!Array.isArray(rules) || !rules.length) return next;
  const shelves = collectShelves(next);
  for (const rule of rules) {
    const type = String(rule.type || "").toLowerCase();
    const value = String(rule.value || "").toLowerCase();
    const targetAisle = rule.aisle_id ? String(rule.aisle_id) : null;
    for (const { aisle, shelf } of shelves) {
      if (targetAisle && String(aisle.aisle_id) !== targetAisle) continue;
      if (type === "storage") shelf.allowed_storage_type = String(rule.value || shelf.allowed_storage_type).toUpperCase();
      shelf.assignment_rule = rule;
    }
  }
  return next;
}

export function localGeneratePlanogram(products = [], layout, mode = "DARKSTORE_AI", options = {}) {
  let next = applyAdvancedRulesToPlan(clone(layout || generateDefaultLayout("AUTO")), options.advanced_rules || []);
  const weights = options.score_weights || {};
  const shelves = collectShelves(next);

  for (const { shelf } of shelves) {
    shelf.products = [];
    recalcShelf(shelf);
  }

  const normalized = (products || []).map(normalizeProduct).filter(p => p.sku);
  const sorted = [...normalized].sort((a, b) => {
    const so = storageOrder(a.storage_type) - storageOrder(b.storage_type);
    if (so) return so;
    return compareByRule(mode, weights)(a, b);
  });

  const unplaced = [];
  const placedReasons = [];

  for (const raw of sorted) {
    let placed = false;
    const desired = facingForProduct(raw, mode);
    const candidate = { ...raw, facing: desired, facing_count: desired };
    const width = productWidth(candidate);

    let targetShelves = shelves
      .filter(t => compatible(candidate, t.shelf))
      .filter(t => n(t.shelf.used_width_cm, 0) + width <= n(t.shelf.shelf_width_cm, 100) * 0.96);

    // Advanced rule hint: brand/category assigned shelves first.
    const brandRuleTargets = targetShelves.filter(t => {
      const r = t.shelf.assignment_rule;
      if (!r) return false;
      const type = String(r.type || "").toLowerCase();
      const val = String(r.value || "").toLowerCase();
      if (type === "brand") return String(candidate.brand || "").toLowerCase().includes(val);
      if (type === "category") return String(candidate.category_l1 || "").toLowerCase().includes(val);
      if (type === "subcategory") return String(candidate.category_l2 || "").toLowerCase().includes(val);
      return false;
    });
    if (brandRuleTargets.length) targetShelves = brandRuleTargets;

    targetShelves.sort((a, b) => n(a.shelf.used_width_cm, 0) - n(b.shelf.used_width_cm, 0));

    if (targetShelves.length) {
      const t = targetShelves[0];
      t.shelf.products.push({
        ...candidate,
        aisle_id: t.aisle.aisle_id,
        module_id: t.module.module_id,
        shelf_no: t.shelf.shelf_no,
        position_order: (t.shelf.products || []).length + 1,
      });
      recalcShelf(t.shelf);
      placed = true;
      placedReasons.push({ sku: candidate.sku, reason: "placed_min_facing" });
    }

    if (!placed) unplaced.push({ ...raw, reason: "capacity_or_storage_constraint" });
  }

  // Second pass: boost facing only for high runners if free space exists.
  for (const { shelf } of shelves) {
    shelf.products = [...(shelf.products || [])].sort(compareByRule(mode, weights)).map((p, i) => ({ ...p, position_order: i + 1 }));
    for (const p of shelf.products) {
      const sales = n(p.sales_qty_7d, 0);
      const maxFacing = sales >= 500 ? 5 : sales >= 250 ? 4 : sales >= 100 ? 3 : sales >= 40 ? 2 : 1;
      while (faceCount(p) < maxFacing) {
        const old = faceCount(p);
        p.facing_count = old + 1;
        p.facing = p.facing_count;
        recalcShelf(shelf);
        if (shelf.used_width_cm > n(shelf.shelf_width_cm, 100) * 0.96) {
          p.facing_count = old; p.facing = old; recalcShelf(shelf); break;
        }
      }
    }
    recalcShelf(shelf);
  }

  const metrics = computeMetrics(next);
  return {
    planogram: next,
    summary: {
      total_products: normalized.length,
      placed_products: normalized.length - unplaced.length,
      unplaced_products: unplaced.length,
      capacity_utilization_pct: metrics.width_utilization_pct,
    },
    unplaced_products: unplaced,
    optimized: true,
    local_optimizer: true,
    mode,
    metrics,
    placement_reasoning: placedReasons.slice(0, 500),
  };
}

export function computeMetrics(plan) {
  let totalShelves = 0, totalProducts = 0, capWidth = 0, usedWidth = 0, capVolume = 0, usedVolume = 0;
  for (const { shelf } of collectShelves(plan)) {
    totalShelves++;
    recalcShelf(shelf);
    totalProducts += (shelf.products || []).length;
    capWidth += n(shelf.shelf_width_cm, 100);
    usedWidth += n(shelf.used_width_cm, 0);
    capVolume += n(shelf.capacity_volume_cm3, 0);
    usedVolume += n(shelf.used_volume_cm3, 0);
  }
  return {
    total_shelves: totalShelves,
    total_products: totalProducts,
    width_capacity_cm: Math.round(capWidth),
    width_used_cm: Math.round(usedWidth),
    width_utilization_pct: Math.round((usedWidth / Math.max(1, capWidth)) * 100),
    volume_capacity_cm3: Math.round(capVolume),
    volume_used_cm3: Math.round(usedVolume),
    volume_utilization_pct: Math.round((usedVolume / Math.max(1, capVolume)) * 100),
  };
}
