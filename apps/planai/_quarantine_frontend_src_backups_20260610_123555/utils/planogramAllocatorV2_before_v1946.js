const TR = "tr-TR";

const TARGET_FILL_RATIO = 0.84;
const HARD_FILL_RATIO = 0.90;
const PICKER_HAND_CLEARANCE_CM = 10;

export function num(v, fallback = 0) {
  const n = Number(String(v ?? "").replace(",", ".").replace("%", "").trim());
  return Number.isFinite(n) ? n : fallback;
}

export function getAny(row = {}, names = [], fallback = "") {
  const lower = Object.fromEntries(
    Object.keys(row || {}).map((k) => [String(k).toLowerCase().trim(), k])
  );

  for (const name of names) {
    const found = lower[String(name).toLowerCase().trim()];
    if (found !== undefined && row[found] !== undefined && row[found] !== null && row[found] !== "") {
      return row[found];
    }
  }

  return fallback;
}

function upperText(obj = {}) {
  return [
    obj.sku,
    obj.SKU,
    obj.name,
    obj.product_name,
    obj.productName,
    obj["Product Name"],
    obj.brand,
    obj.brand_name,
    obj.category,
    obj.category_l1,
    obj.category_l2,
    obj["Category L1"],
    obj["Category L2"],
    obj.subcategory,
    obj.frontend_category_local,
    obj.frontend_subcategory_local,
    obj.storage,
    obj.storage_type,
    obj.storage_class,
    obj.storage_truth,
    obj.catalog_storage_type,
    obj.master_storage_type,
    obj["Storage Type"],
  ].filter(Boolean).join(" ").toUpperCase();
}

function objectText(o = {}) {
  return [
    o.id,
    o.label,
    o.name,
    o.title,
    o.type,
    o.zone,
    o.fixture_type,
    o.fixture_class,
    o.storage,
    o.storage_type,
    o.storage_class,
  ].filter(Boolean).join(" ").toUpperCase();
}

export function imageFromProduct(p = {}) {
  return getAny(
    p,
    ["image_url", "imageUrl", "Product Image URL", "product_image_url", "catalog_image_url", "pim_image_url", "photo_url", "image"],
    ""
  );
}

function normalizeStorageValue(v) {
  const raw = String(v || "").trim().toUpperCase();
  if (!raw || raw === "NULL" || raw === "NAN" || raw === "UNKNOWN") return "";

  if (raw.includes("FROZEN") || raw.includes("DONUK") || raw.includes("-18") || raw.includes("ICE_CREAM")) return "FROZEN";
  if (raw.includes("CHILLED") || raw.includes("SOGUK") || raw.includes("SOĞUK") || raw.includes("+4")) return "CHILLED";
  if (raw.includes("AMBIENT")) return "AMBIENT";

  return "";
}

function catalogStorageTruth(p = {}) {
  const catalogRaw =
    p.catalog_storage_type ||
    p.catalog_storage_class ||
    p.catalog_storage ||
    p.master_storage_type ||
    p.master_storage_class ||
    p.master_storage ||
    p.canonical_storage_type ||
    p.source_catalog_storage_type ||
    p.storage_truth ||
    p.catalog?.storage_type ||
    p.catalog?.storage_class ||
    p.master_product?.storage_type ||
    p.master_product?.storage_class ||
    "";

  const catalog = normalizeStorageValue(catalogRaw);
  if (catalog) return { value: catalog, source: "catalog" };

  const abc = normalizeStorageValue(p["Storage Type"] || p.abc_storage_type || p.abcStorageType || "");
  if (abc) return { value: abc, source: "abc_fallback" };

  return { value: "", source: "name_fallback" };
}

export function normalizeSalesValue(rawSales, row = {}) {
  let sales = num(rawSales, NaN);
  const pctOrders = num(getAny(row, ["% Orders", "percent_orders", "orders_pct", "order_share"], 0), 0);
  const pctStops = num(getAny(row, ["% Stops", "percent_stops", "stops_pct"], 0), 0);
  const rank = num(getAny(row, ["Rank", "rank"], 0), 0);
  const abc = String(getAny(row, ["ABC", "abc", "abc_class"], "")).toUpperCase();

  if (!Number.isFinite(sales) || sales <= 0 || String(rawSales).includes("%")) {
    if (pctOrders > 0) sales = pctOrders <= 1.5 ? pctOrders * 1100 : pctOrders * 11;
    else if (pctStops > 0) sales = pctStops <= 1.5 ? pctStops * 650 : pctStops * 6.5;
  }

  if (!Number.isFinite(sales) || sales <= 0) {
    if (rank > 0) sales = Math.max(1, 420 - rank * 0.055);
    else sales = abc === "A" ? 90 : abc === "B" ? 35 : abc === "C" ? 12 : 1;
  }

  if (abc === "A") sales = Math.max(sales, rank > 0 ? Math.max(55, 260 - rank * 0.025) : 55);
  if (abc === "B") sales = Math.max(sales, 18);

  return Math.max(0, Number((sales || 0).toFixed(3)));
}

export function isExcludedPlanogramProduct(p = {}) {
  const h = upperText(p);

  return (
    h.includes("SHOPPING BAG") ||
    h.includes("ALIŞVERİŞ POŞET") ||
    h.includes("ALISVERIS POSET") ||
    h.includes("POŞET") ||
    h.includes("POSET") ||
    h.includes("CARRIER BAG") ||
    h.includes("MARKET BAG") ||
    h.includes("DISPOSABLE BAG") ||
    h.includes("EVERYDAY") ||
    h.includes("COFFEE MACHINE") ||
    h.includes("KAHVE MAKINESI") ||
    h.includes("KAHVE MAKİNESİ") ||
    h.includes("EQUIPMENT") ||
    h.includes("LA LORRAINE") ||
    h.includes("BAGUETTE") ||
    h.includes("BAGEL") ||
    h.includes("SIMIT") ||
    h.includes("SİMİT") ||
    h.includes("RAMAZAN PIDESI") ||
    h.includes("RAMAZAN PİDESİ") ||
    h.includes("PIDE") ||
    h.includes("PİDE") ||
    h.includes("BAKERY") ||
    h.includes("FIRIN") ||
    h.includes("EKMEK") ||
    h.includes("BREAD")
  );
}

export function isRealProduce(p = {}) {
  const h = upperText(p);

  const produceSignal =
    h.includes("PRODUCE") ||
    h.includes("FRUIT") ||
    h.includes("VEGETABLE") ||
    h.includes("MEYVE") ||
    h.includes("SEBZE") ||
    h.includes("FRESH") ||
    h.includes("BANANA") ||
    h.includes("MUZ") ||
    h.includes("APPLE") ||
    h.includes("ELMA") ||
    h.includes("POTATO") ||
    h.includes("PATATES") ||
    h.includes("ONION") ||
    h.includes("SOGAN") ||
    h.includes("SOĞAN") ||
    h.includes("TOMATO") ||
    h.includes("DOMATES") ||
    h.includes("CUCUMBER") ||
    h.includes("SALATALIK") ||
    h.includes("LETTUCE") ||
    h.includes("MARUL") ||
    h.includes("DILL") ||
    h.includes("DEREOTU") ||
    h.includes("PARSLEY") ||
    h.includes("MAYDANOZ") ||
    h.includes("MUSHROOM") ||
    h.includes("MANTAR") ||
    h.includes("PUMPKIN") ||
    h.includes("KABAK") ||
    h.includes("MINT") ||
    h.includes("NANE") ||
    h.includes("GINGER") ||
    h.includes("ZENCEFIL") ||
    h.includes("AVOCADO") ||
    h.includes("AVOKADO");

  const fakeProduce =
    h.includes("JUICE") ||
    h.includes("DRINK") ||
    h.includes("BEVERAGE") ||
    h.includes("LEMONADE") ||
    h.includes("ICE TEA") ||
    h.includes("WATER") ||
    h.includes("BOTTLE") ||
    h.includes("FROZEN") ||
    h.includes("DONUK") ||
    h.includes("SUPERFRESH") ||
    h.includes("FEAST") ||
    h.includes("NOODLE") ||
    h.includes("CHIPS") ||
    h.includes("CIPS") ||
    h.includes("CAKE") ||
    h.includes("KEK") ||
    h.includes("YOGURT") ||
    h.includes("SNACK") ||
    h.includes("BABY") ||
    h.includes("CHOCOLATE");

  return produceSignal && !fakeProduce;
}

function isPetProduct(p = {}) {
  const h = upperText(p);
  return h.includes("WANPY") || h.includes("DREAMIES") || h.includes("CAT TREAT") || h.includes("CAT FOOD") || h.includes("DOG FOOD") || h.includes("PET FOOD") || h.includes("KEDI") || h.includes("KEDİ") || h.includes("MAMA");
}

function isShelfStableCheese(p = {}) {
  const h = upperText(p);
  return h.includes("MAC & CHEESE") || h.includes("MAC AND CHEESE") || h.includes("QUICK MAC") || h.includes("CHEESE CRACKER") || h.includes("CHEESE STICK") || h.includes("CRACKER") || h.includes("NOODLE") || h.includes("SNACK");
}

function isChemicalProduct(p = {}) {
  const h = upperText(p);
  return h.includes("CIF") || h.includes("DOMESTOS") || h.includes("OMO") || h.includes("YUMO") || h.includes("FINISH") || h.includes("FAIRY") || h.includes("PRIL") || h.includes("DETERJAN") || h.includes("DETERGENT") || h.includes("DISHWASH") || h.includes("LAUNDRY") || h.includes("SOFTENER") || h.includes("BLEACH") || h.includes("CLEANER") || h.includes("OIL REMOVER") || h.includes("SHAMPOO");
}

function isPaperProduct(p = {}) {
  const h = upperText(p);
  return h.includes("TOILET PAPER") || h.includes("PAPER TOWEL") || h.includes("NAPKIN") || h.includes("TISSUE") || h.includes("GARBAGE BAG") || h.includes("KOROPLAST") || h.includes("BAMBOO") || h.includes("SOLO") || h.includes("SELPAK") || h.includes("CONDOM") || h.includes("KONDOM") || h.includes("OKEY");
}

function isBulkyProduct(p = {}) {
  const h = upperText(p);
  return Number(p.weight_kg || p.weight || 0) >= 3 || h.includes("CARBOY") || h.includes("DAMACANA") || h.includes("19 L") || h.includes("19L") || h.includes("12 X") || h.includes("6 X") || h.includes("5 L") || h.includes("5L") || h.includes("10 L") || h.includes("10L") || isPaperProduct(p);
}

function strongChilledSignal(p = {}) {
  const h = upperText(p);
  if (isPetProduct(p)) return false;
  if (isShelfStableCheese(p)) return false;

  return h.includes("YOGURT") || h.includes("AYRAN") || h.includes("KEFIR") || h.includes("PEYNIR") || h.includes("CHEESE") || h.includes("BUTTER") || h.includes("EGG") || h.includes("YUMURTA") || h.includes("CHICKEN") || h.includes("TAVUK") || h.includes("MEAT") || h.includes("BEEF") || h.includes("NAMET") || h.includes("BANVIT") || h.includes("SALAMI") || h.includes("SAUSAGE") || h.includes("CREAM");
}

export function productDomain(p = {}) {
  if (isExcludedPlanogramProduct(p)) return "EXCLUDED";
  if (isRealProduce(p)) return "PRODUCE";

  const truth = catalogStorageTruth(p);
  if (truth.value) return truth.value;

  const h = upperText(p);
  if (h.includes("FROZEN") || h.includes("DONUK") || h.includes("DONDURMA") || h.includes("ICE CREAM") || h.includes("ALGIDA") || h.includes("MAGNUM")) return "FROZEN";

  if (isPetProduct(p)) return "AMBIENT";
  if (isShelfStableCheese(p)) return "AMBIENT";
  if (strongChilledSignal(p)) return "CHILLED";

  return "AMBIENT";
}

export function storageFromProduct(p = {}) {
  const d = productDomain(p);
  if (d === "PRODUCE") return "AMBIENT";
  if (d === "FROZEN") return "FROZEN";
  if (d === "CHILLED") return "CHILLED";
  return "AMBIENT";
}

export function isOdorNonFood(p = {}) {
  return isChemicalProduct(p);
}

export function isHeavyOrBulky(p = {}) {
  return isBulkyProduct(p);
}

function foodFamily(p = {}) {
  if (productDomain(p) === "PRODUCE") return "PRODUCE";
  if (isChemicalProduct(p)) return "CHEMICAL";
  if (isPetProduct(p)) return "PET";
  if (isPaperProduct(p)) return "PAPER";
  if (isBulkyProduct(p)) return "BULKY";
  return "FOOD";
}

function familyCompatible(a, b) {
  if (!a || !b) return true;
  if (a === b) return true;
  if (a === "CHEMICAL" || b === "CHEMICAL") return false;
  if (a === "PET" || b === "PET") return false;
  if (a === "PAPER" || b === "PAPER") return false;
  if (a === "BULKY" || b === "BULKY") return false;
  return a === "FOOD" && b === "FOOD";
}

function safeFrontWidth(p = {}, rawWidth = 8) {
  const h = upperText(p);
  let w = Number(rawWidth || 8);

  if (w > 120) w = w / 10;
  if (w > 80 && !isBulkyProduct(p)) w = w / 10;

  if (h.includes("CARBOY") || h.includes("DAMACANA") || h.includes("19 L") || h.includes("19L")) return Math.max(32, Math.min(40, w));
  if (h.includes("12 X") || h.includes("6 X") || h.includes("5 L") || h.includes("5L")) return Math.max(22, Math.min(32, w));
  if (isPaperProduct(p)) return Math.max(20, Math.min(30, w));
  if (!isBulkyProduct(p) && w > 28) return 10;

  return Math.max(4, Math.min(28, w));
}

function slotDomain(o = {}) {
  const h = objectText(o);

  if (h.includes("MEYVE") || h.includes("SEBZE") || h.includes("PRODUCE") || h.includes("FRESH")) return "PRODUCE";
  if (h.includes("FROZEN") || h.includes("DONUK") || h.includes("-18") || h.includes("ALGIDA") || h.includes("ICE_CREAM")) return "FROZEN";
  if (h.includes("CHILLED") || h.includes("SOGUK") || h.includes("SOĞUK") || h.includes("+4") || h.includes("MARTEK")) return "CHILLED";

  return "AMBIENT";
}

function isCompatible(p = {}, slot = {}) {
  const pd = productDomain(p);
  const sd = slot.domain;

  if (pd === "EXCLUDED") return false;
  if (sd === "PRODUCE") return pd === "PRODUCE";
  if (sd === "CHILLED") return pd === "CHILLED";
  if (sd === "FROZEN") return pd === "FROZEN";
  if (sd === "AMBIENT") return pd === "AMBIENT";
  return false;
}

function maxFrontFacing(p = {}) {
  const sales = Number(p.sales || 0);
  const width = Number(p.width || 8);

  if (isBulkyProduct(p) || width >= 18) return 1;
  if (productDomain(p) === "PRODUCE") return sales >= 250 ? 2 : 1;
  if (sales >= 250) return 3;
  if (sales >= 60) return 2;
  return 1;
}

function depthForDemand(p = {}, facing = 1) {
  const sales = Number(p.sales || 0);
  if (sales >= 700) return 10;
  if (sales >= 250) return 8;
  if (sales >= 120) return 6;
  if (sales >= 60) return 4;
  if (sales >= 20) return 3;
  return 2;
}

function shelfFrontLimit(width = 100) {
  return Math.max(50, Math.min(width * HARD_FILL_RATIO, width - PICKER_HAND_CLEARANCE_CM));
}

function targetSkuCount(slot = {}) {
  const w = Number(slot.width || 100);

  if (slot.foodFamily === "BULKY") return Math.max(2, Math.min(4, Math.floor(w / 30)));
  if (slot.foodFamily === "PAPER") return Math.max(3, Math.min(5, Math.floor(w / 24)));
  if (slot.foodFamily === "CHEMICAL" || slot.foodFamily === "PET") return Math.max(4, Math.min(7, Math.floor(w / 18)));
  if (slot.domain === "PRODUCE") return Math.max(6, Math.min(10, Math.floor(w / 16)));
  if (slot.domain === "CHILLED") return Math.max(7, Math.min(12, Math.floor(w / 14)));
  if (slot.domain === "FROZEN") return Math.max(5, Math.min(8, Math.floor(w / 22)));

  return Math.max(6, Math.min(10, Math.floor(w / 16)));
}

function maxSkuCount(slot = {}) {
  if (slot.foodFamily === "BULKY") return targetSkuCount(slot);
  if (slot.foodFamily === "PAPER") return targetSkuCount(slot);
  return targetSkuCount(slot) + 1;
}

function fillRatio(slot = {}) {
  return Number(slot.used || 0) / Math.max(Number(slot.frontLimit || slot.usableWidth || 1), 1);
}

function densityScore(slot = {}) {
  const r = fillRatio(slot);

  if (slot.count > 0 && r < TARGET_FILL_RATIO) return -100 + r;
  if (slot.count === 0) return 0;
  return 10 + r;
}

function skuKeyForAffinity(p = {}) {
  return String(p.sku || p.SKU || p.barcode || p.name || "").trim();
}

function affinityScoreForSlot(product = {}, slot = {}, affinityMap = {}) {
  const sku = skuKeyForAffinity(product);
  const partners = affinityMap?.[sku] || [];
  if (!partners.length || !slot?.skus) return 0;

  let score = 0;
  for (const partner of partners) {
    const partnerSku = String(partner.sku || "").trim();
    if (partnerSku && slot.skus.has(partnerSku)) score += Number(partner.score || 0);
  }

  return score;
}

export function estimateEmoji(p = {}) {
  return "▣";
}

export function normalizeProduct(raw = {}, idx = 0) {
  const name = String(
    getAny(raw, ["name", "product_name", "Product Name", "product_name_local", "pim_product_name_local"], getAny(raw, ["sku", "SKU"], `Product ${idx + 1}`))
  ).trim();

  const sku = String(getAny(raw, ["sku", "SKU", "barcode", "Barcodes", "product_barcodes"], `SKU-${idx + 1}`)).trim() || `SKU-${idx + 1}`;
  const brand = String(getAny(raw, ["brand", "Brand", "brand_name"], name.split(" ")[0] || "UNKNOWN")).trim() || "UNKNOWN";
  const category = String(getAny(raw, ["category", "category_l1", "Category L1", "frontend_category_local"], "Genel")).trim() || "Genel";
  const subcategory = String(getAny(raw, ["subcategory", "category_l2", "Category L2", "frontend_subcategory_local"], "Genel")).trim() || "Genel";
  const sales = normalizeSalesValue(getAny(raw, ["sales", "sales_qty_7d", "sales_7d", "Sales 7D", "% Orders", "percent_orders"], 0), raw);
  const baseWidth = Math.max(1, num(getAny(raw, ["width", "width_cm", "Width", "product_width_in_cm"], 8), 8));
  const width = safeFrontWidth({ ...raw, name, category, subcategory, brand }, baseWidth);
  const storageTruth = catalogStorageTruth({ ...raw, name, category, subcategory, brand });
  const storage = storageFromProduct({ ...raw, name, product_name: name, category, subcategory, brand });
  const domain = productDomain({ ...raw, name, category, subcategory, brand, storage });
  const family = foodFamily({ ...raw, name, category, subcategory, brand, storage });
  const imageUrl = imageFromProduct(raw);
  const rawDepthUnits = num(getAny(raw, ["merch_depth", "depth", "depth_units"], 0), 0);

  const facing = Math.max(
    1,
    Math.min(
      maxFrontFacing({ ...raw, name, category, subcategory, brand, storage, sales, width }),
      Math.round(num(getAny(raw, ["facing", "facing_count"], 0), 0) || (sales >= 250 ? 3 : sales >= 60 ? 2 : 1))
    )
  );

  const depth = Math.max(1, Math.min(12, Math.round(rawDepthUnits || depthForDemand({ sales }, facing))));

  return {
    ...raw,
    sku,
    name,
    product_name: name,
    brand,
    category,
    category_l1: raw.category_l1 || raw["Category L1"] || category,
    category_l2: raw.category_l2 || raw["Category L2"] || subcategory,
    subcategory,
    storage,
    storage_type: storage,
    storage_class: storage,
    storage_source: storageTruth.source,
    product_domain: domain,
    food_family: family,
    sales,
    sales_label: sales >= 100 ? Math.round(sales).toLocaleString(TR) : sales.toFixed(1),
    facing,
    facing_count: facing,
    depth,
    width,
    width_cm: width,
    product_depth_cm: Math.max(1, num(getAny(raw, ["product_depth_cm", "depth_cm", "product_length_in_cm", "length_cm"], 10), 10)),
    height: Math.max(1, num(getAny(raw, ["height", "height_cm", "Height", "product_height_in_cm"], 16), 16)),
    weight_kg: Math.max(0.01, num(getAny(raw, ["weight_kg", "Weight", "product_weight_value"], 0.2), 0.2)),
    abc: getAny(raw, ["ABC", "abc", "abc_class"], ""),
    rank: num(getAny(raw, ["Rank", "rank"], 0), 0),
    location_raw: getAny(raw, ["Location", "current_location"], raw.location_raw || ""),
    secondary_location: getAny(raw, ["Secondary Location", "secondary_location"], raw.secondary_location || ""),
    image_url: imageUrl,
    image: imageUrl || getAny(raw, ["image"], "") || estimateEmoji({ name, category, subcategory, storage }),
    risk: sales >= 250 ? "Yüksek" : sales >= 80 ? "Orta" : "Düşük",
  };
}

function shelfOrderFor(p) {
  if (isBulkyProduct(p)) return [1, 2, 3, 4, 5, 6, 7, 8];
  if (Number(p.sales || 0) >= 80) return [2, 3, 4, 1, 5, 6, 7, 8];
  return [4, 5, 3, 6, 2, 1, 7, 8];
}

function byDomain(objects = [], domain) {
  return (objects || []).filter((o) => slotDomain(o) === domain).map((o) => String(o.id));
}

function targetAreas(p, objects) {
  const ids = new Set((objects || []).map((o) => String(o.id)));
  const has = (x) => ids.has(String(x));
  const abc = String(p.abc || p.ABC || "").toUpperCase();
  const rank = Number(p.rank || 999999);
  const score = Number(p.sales || 0);

  if (productDomain(p) === "PRODUCE") return byDomain(objects, "PRODUCE");
  if (p.storage === "FROZEN") return byDomain(objects, "FROZEN");
  if (p.storage === "CHILLED") return byDomain(objects, "CHILLED");

  if (isBulkyProduct(p)) {
    const preferred = ["STEEL_RACK", "G", "H", "I", "F"].filter(has);
    return preferred.length ? preferred : byDomain(objects, "AMBIENT");
  }

  if (isChemicalProduct(p) || isPetProduct(p) || isPaperProduct(p)) {
    const preferred = ["I", "H", "STEEL_RACK", "G", "F"].filter(has);
    return preferred.length ? preferred : byDomain(objects, "AMBIENT");
  }

  if (abc === "A" || rank <= 900 || score >= 55) return ["A", "B", "C", "D", "E", "F"].filter(has);
  if (abc === "B" || rank <= 2500 || score >= 18) return ["D", "E", "F", "G", "B", "C", "H", "I"].filter(has);

  return ["H", "I", "G", "F", "E", "C", "B", "STEEL_RACK"].filter(has);
}

function shelfWidthForObject(o = {}, domain = "AMBIENT") {
  const explicit = Number(o.shelf_width_cm || o.width_cm || 0);
  if (explicit > 0) return explicit > 250 ? explicit / 10 : explicit;

  if (domain === "PRODUCE") return 120;
  if (domain === "CHILLED") return 100;
  if (domain === "FROZEN") return 100;
  if (String(o.type || "").includes("steel")) return 140;

  return 100;
}

function buildSlots(objects = []) {
  const slots = [];

  for (const o of objects || []) {
    if (!o) continue;

    const isMartek = objectText(o).includes("MARTEK");
    const domain = isMartek ? "CHILLED" : slotDomain(o);
    const zone = domain === "PRODUCE" ? "AMBIENT" : domain;
    const modules = isMartek
      ? Math.max(2, Number(o.modules || 0) || 2)
      : Math.max(1, Math.min(80, Number(o.modules || (domain === "CHILLED" || domain === "FROZEN" ? 1 : 0))));

    const shelvesTotal = isMartek
      ? Math.max(10, Number(o.shelves || 0) || 10)
      : Math.max(1, Math.min(800, Number(o.shelves || (domain === "CHILLED" || domain === "FROZEN" ? 5 : modules * 6))));

    const shelvesPerModule = Math.max(1, Math.ceil(shelvesTotal / modules));
    const width = shelfWidthForObject(o, domain);
    const frontLimit = shelfFrontLimit(width);

    for (let m = 1; m <= modules; m += 1) {
      for (let s = 1; s <= shelvesPerModule; s += 1) {
        slots.push({
          areaId: String(o.id),
          areaLabel: o.label || o.id,
          zone,
          domain,
          module: m,
          shelf: s,
          width,
          usableWidth: width,
          frontLimit,
          used: 0,
          count: 0,
          maxCount: 999,
          foodFamily: null,
          skus: new Set(),
        });
      }
    }
  }

  return slots;
}

function canFitProductInSlot(p, slot, facing) {
  const required = Math.max(3, Number(p.width || 8) * facing);
  return slot.used + required <= slot.frontLimit && slot.count < maxSkuCount(slot);
}

export function buildStorePlan(inputProducts = [], objects = [], options = {}) {
  const normalized = (inputProducts || [])
    .map((p, idx) => normalizeProduct(p, idx))
    .filter((p) => productDomain(p) !== "EXCLUDED");

  const slots = buildSlots(objects);
  const placed = [];
  const unplaced = [];

  const familyOrder = { CHEMICAL: 0, PET: 1, PAPER: 2, BULKY: 3, PRODUCE: 4, FOOD: 5 };
  const domainOrder = { FROZEN: 0, CHILLED: 1, PRODUCE: 2, AMBIENT: 3 };

  const sorted = [...normalized].sort((a, b) => {
    return (
      (domainOrder[productDomain(a)] ?? 9) - (domainOrder[productDomain(b)] ?? 9) ||
      (familyOrder[foodFamily(a)] ?? 9) - (familyOrder[foodFamily(b)] ?? 9) ||
      Number(b.sales || 0) - Number(a.sales || 0) ||
      Number(a.rank || 999999) - Number(b.rank || 999999)
    );
  });

  for (const p of sorted) {
    const targets = targetAreas(p, objects);
    const targetPriority = new Map(targets.map((id, idx) => [String(id), idx]));
    const shelfOrder = shelfOrderFor(p);
    const pFamily = foodFamily(p);
    const facing = Math.max(1, Math.min(maxFrontFacing(p), Number(p.facing || 1)));

    let compatible = slots.filter((s) => {
      const inTarget = !targets.length || targets.includes(s.areaId);
      return inTarget && isCompatible(p, s) && familyCompatible(pFamily, s.foodFamily) && s.count < maxSkuCount(s);
    });

    if (!compatible.length) {
      compatible = slots.filter((s) => isCompatible(p, s) && familyCompatible(pFamily, s.foodFamily) && s.count < maxSkuCount(s));
    }

    const fitting = compatible.filter((s) => canFitProductInSlot(p, s, facing));

    const openUnderfilled = fitting.filter((s) => s.count > 0 && fillRatio(s) < TARGET_FILL_RATIO);

    const candidates = (openUnderfilled.length ? openUnderfilled : fitting).sort((a, b) => {
      const prio =
        (targetPriority.get(String(a.areaId)) ?? 99) -
        (targetPriority.get(String(b.areaId)) ?? 99);

      const affA = affinityScoreForSlot(p, a, options.affinityMap || {});
      const affB = affinityScoreForSlot(p, b, options.affinityMap || {});

      return (
        densityScore(a) - densityScore(b) ||
        prio ||
        (affB > 0 ? -1 : 0) - (affA > 0 ? -1 : 0) ||
        shelfOrder.indexOf(a.shelf) - shelfOrder.indexOf(b.shelf) ||
        a.used - b.used ||
        a.module - b.module ||
        a.shelf - b.shelf
      );
    });

    const slot = candidates[0];

    if (!slot) {
      const domain = productDomain(p);
      const reason =
        domain === "CHILLED"
          ? "NO_CHILLED_FRONT_CAPACITY"
          : domain === "FROZEN"
            ? "NO_FROZEN_FRONT_CAPACITY"
            : domain === "PRODUCE"
              ? "NO_PRODUCE_FRONT_CAPACITY"
              : "NO_PHYSICAL_FRONT_CAPACITY";

      unplaced.push({
        ...p,
        reason,
        reason_code: reason,
        product_domain: domain,
        food_family: pFamily,
        suggested_action:
          domain === "CHILLED"
            ? "+4 sogutucu / MARTEK kapasitesi, product width veya shelf width kontrol edilmeli."
            : domain === "FROZEN"
              ? "-18 donuk alan / Algida dolabı kapasitesi kontrol edilmeli."
              : domain === "PRODUCE"
                ? "Meyve-sebze raf kapasitesi veya ürün havuzu kontrol edilmeli."
                : "Ambient raf kapasitesi, bulky alan veya ürün ölçüleri kontrol edilmeli.",
      });
      continue;
    }

    const required = Math.max(3, Number(p.width || 8) * facing);
    slot.used += required;
    slot.count += 1;
    slot.foodFamily = slot.foodFamily || pFamily;
    slot.skus.add(skuKeyForAffinity(p));

    const affinityScore = affinityScoreForSlot(p, slot, options.affinityMap || {});

    placed.push({
      ...p,
      facing,
      facing_count: facing,
      depth: Math.max(Number(p.depth || 1), depthForDemand(p, facing)),
      depth_strategy: "DEPTH_FIRST_FRONT_FACE_CAPPED",
      aisle: slot.areaId,
      aisle_id: slot.areaId,
      module: slot.module,
      module_id: slot.module,
      shelf: slot.shelf,
      shelf_no: slot.shelf,
      position: slot.count,
      position_order: slot.count,
      product_domain: productDomain(p),
      slot_domain: slot.domain,
      food_family: pFamily,
      basket_affinity_score: affinityScore,
      picker_clearance_cm: PICKER_HAND_CLEARANCE_CM,
      shelf_target_fill_pct: Math.round(TARGET_FILL_RATIO * 100),
      placement_reason:
        affinityScore > 0
          ? `${slot.domain} domain + ${pFamily} family + basket affinity + shelf fill before open new shelf`
          : `${slot.domain} domain + ${pFamily} family + shelf fill before open new shelf + picker clearance`,
    });
  }

  const utilizationByArea = {};

  for (const s of slots) {
    utilizationByArea[s.areaId] ||= { used: 0, cap: 0, count: 0 };
    utilizationByArea[s.areaId].used += Math.min(s.used, s.frontLimit);
    utilizationByArea[s.areaId].cap += s.frontLimit;
    utilizationByArea[s.areaId].count += s.count;
  }

  return { placed, unplaced, utilizationByArea };
}

export function updateObjectsFromPlan(objects = [], plan = {}) {
  return (objects || []).map((o) => {
    const m = plan.utilizationByArea?.[String(o.id)];
    const isMartek = objectText(o).includes("MARTEK");

    if (!m) {
      return {
        ...o,
        modules: isMartek ? Math.max(2, Number(o.modules || 0) || 2) : o.modules,
        shelves: isMartek ? Math.max(10, Number(o.shelves || 0) || 10) : o.shelves,
        utilization: 0,
      };
    }

    const utilization = Math.round((m.used / Math.max(m.cap, 1)) * 100);

    return {
      ...o,
      modules: isMartek ? Math.max(2, Number(o.modules || 0) || 2) : o.modules,
      shelves: isMartek ? Math.max(10, Number(o.shelves || 0) || 10) : o.shelves,
      utilization: Math.max(0, Math.min(100, utilization)),
      changed: Math.max(Number(o.changed || 0), Math.round(m.count * 0.05)),
    };
  });
}

export function productsForShelf(products = [], aisle, module, shelf) {
  return (products || []).filter(
    (p) =>
      String(p.aisle || p.aisle_id) === String(aisle) &&
      Number(p.module || p.module_id || 1) === Number(module) &&
      Number(p.shelf || p.shelf_no || 1) === Number(shelf)
  );
}

export function moduleShelfCount(products = [], aisle, module) {
  return Math.max(
    1,
    ...products
      .filter(
        (p) =>
          String(p.aisle || p.aisle_id) === String(aisle) &&
          Number(p.module || p.module_id || 1) === Number(module)
      )
      .map((p) => Number(p.shelf || p.shelf_no || 1))
  );
}
