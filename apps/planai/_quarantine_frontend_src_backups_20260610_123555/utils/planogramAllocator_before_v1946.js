const TR = 'tr-TR';

export function num(v, fallback = 0) {
  const n = Number(String(v ?? '').replace(',', '.').replace('%', '').trim());
  return Number.isFinite(n) ? n : fallback;
}

export function getAny(row = {}, names = [], fallback = '') {
  const lower = Object.fromEntries(
    Object.keys(row || {}).map((k) => [String(k).toLowerCase().trim(), k])
  );

  for (const name of names) {
    const found = lower[String(name).toLowerCase().trim()];
    if (
      found !== undefined &&
      row[found] !== undefined &&
      row[found] !== null &&
      row[found] !== ''
    ) {
      return row[found];
    }
  }

  return fallback;
}

export function imageFromProduct(p = {}) {
  return getAny(
    p,
    [
      'image_url',
      'imageUrl',
      'Product Image URL',
      'product_image_url',
      'catalog_image_url',
      'pim_image_url',
      'photo_url',
    ],
    ''
  );
}

function haystack(p = {}) {
  return [
    p.sku,
    p.SKU,
    p.name,
    p.product_name,
    p.productName,
    p['Product Name'],
    p.brand,
    p.brand_name,
    p.category,
    p.category_l1,
    p.category_l2,
    p['Category L1'],
    p['Category L2'],
    p.frontend_category_local,
    p.frontend_subcategory_local,
    p.subcategory,
    p.storage,
    p.storage_type,
    p.storage_class,
    p.storage_type_hint,
  ]
    .filter(Boolean)
    .join(' ')
    .toLocaleUpperCase(TR);
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
    o.fixture_pool,
    o.storage,
    o.storage_type,
    o.storage_class,
  ]
    .filter(Boolean)
    .join(' ')
    .toLocaleUpperCase(TR);
}

export function normalizeSalesValue(rawSales, row = {}) {
  let sales = num(rawSales, NaN);
  const pctOrders = num(getAny(row, ['% Orders', 'percent_orders', 'orders_pct', 'order_share'], 0), 0);
  const pctStops = num(getAny(row, ['% Stops', 'percent_stops', 'stops_pct'], 0), 0);
  const rank = num(getAny(row, ['Rank', 'rank'], 0), 0);
  const abc = String(getAny(row, ['ABC', 'abc', 'abc_class'], '')).toUpperCase();

  if (!Number.isFinite(sales) || sales <= 0 || String(rawSales).includes('%')) {
    if (pctOrders > 0) sales = pctOrders <= 1.5 ? pctOrders * 1100 : pctOrders * 11;
    else if (pctStops > 0) sales = pctStops <= 1.5 ? pctStops * 650 : pctStops * 6.5;
  }

  if (!Number.isFinite(sales) || sales <= 0) {
    if (rank > 0) sales = Math.max(1, 420 - rank * 0.055);
    else sales = abc === 'A' ? 90 : abc === 'B' ? 35 : abc === 'C' ? 12 : 1;
  }

  if (abc === 'A') sales = Math.max(sales, rank > 0 ? Math.max(55, 260 - rank * 0.025) : 55);
  if (abc === 'B') sales = Math.max(sales, 18);

  return Math.max(0, Number((sales || 0).toFixed(3)));
}


function productTextV1919(p = {}) {
  return [
    p.sku,
    p.SKU,
    p.name,
    p.product_name,
    p.productName,
    p["Product Name"],
    p.brand,
    p.brand_name,
    p.category,
    p.category_l1,
    p.category_l2,
    p["Category L1"],
    p["Category L2"],
    p.frontend_category_local,
    p.frontend_subcategory_local,
    p.subcategory,
    p.storage,
    p.storage_type,
    p.storage_class,
    p.storage_type_hint,
    p["Storage Type"],
  ].filter(Boolean).join(" ").toUpperCase();
}

function explicitStorageV1919(p = {}) {
  return String(
    p.storage ||
    p.storage_type ||
    p.storage_class ||
    p.storage_type_hint ||
    p["Storage Type"] ||
    ""
  ).toUpperCase();
}

function shelfStableCheeseV1919(p = {}) {
  const h = productTextV1919(p);
  return (
    h.includes("MAC & CHEESE") ||
    h.includes("MAC AND CHEESE") ||
    h.includes("QUICK MAC") ||
    h.includes("CHEESE CRACKER") ||
    h.includes("CHEESE STICK") ||
    h.includes("CRACKER") ||
    h.includes("NOODLE") ||
    h.includes("SNACK")
  );
}

function petProductV1919(p = {}) {
  const h = productTextV1919(p);
  return (
    h.includes("WANPY") ||
    h.includes("DREAMIES") ||
    h.includes("CAT TREAT") ||
    h.includes("CAT FOOD") ||
    h.includes("DOG FOOD") ||
    h.includes("PET FOOD") ||
    h.includes("KEDI") ||
    h.includes("KED?") ||
    h.includes("KOPEK") ||
    h.includes("K?PEK") ||
    h.includes("MAMA")
  );
}

function chemicalProductV1919(p = {}) {
  const h = productTextV1919(p);
  return (
    h.includes("CIF") ||
    h.includes("C?F") ||
    h.includes("DOMESTOS") ||
    h.includes("OMO") ||
    h.includes("PRIL") ||
    h.includes("DETERJAN") ||
    h.includes("DETERGENT") ||
    h.includes("BLEACH") ||
    h.includes("CLEANER") ||
    h.includes("DIRT") ||
    h.includes("OIL REMOVER") ||
    h.includes("SOAP") ||
    h.includes("SABUN") ||
    h.includes("SPRAY") ||
    h.includes("SHAMPOO") ||
    h.includes("?AMPUAN")
  );
}

function paperBulkyProductV1919(p = {}) {
  const h = productTextV1919(p);
  return (
    h.includes("TOILET PAPER") ||
    h.includes("PAPER TOWEL") ||
    h.includes("GARBAGE BAG") ||
    h.includes("KOROPLAST") ||
    h.includes("BAMBOO") ||
    h.includes("SOLO") ||
    h.includes("SELPAK")
  );
}

function bulkyProductV1919(p = {}) {
  const h = productTextV1919(p);
  return (
    Number(p.weight_kg || p.weight || 0) >= 3 ||
    h.includes("CARBOY") ||
    h.includes("DAMACANA") ||
    h.includes("19 L") ||
    h.includes("19L") ||
    h.includes("12 X") ||
    h.includes("6 X") ||
    h.includes("5 L") ||
    h.includes("5L") ||
    h.includes("10 L") ||
    h.includes("10L") ||
    paperBulkyProductV1919(p)
  );
}

function inferredWidthV1919(p = {}) {
  const h = productTextV1919(p);
  const base = Number(p.width || p.width_cm || 8);

  if (h.includes("CARBOY") || h.includes("DAMACANA") || h.includes("19 L") || h.includes("19L")) {
    return Math.max(base, 34);
  }

  if (h.includes("12 X") || h.includes("6 X") || h.includes("5 L") || h.includes("5L")) {
    return Math.max(base, 24);
  }

  if (paperBulkyProductV1919(p)) {
    return Math.max(base, 22);
  }

  return base;
}

function strongChilledV1919(p = {}) {
  const h = productTextV1919(p);

  if (shelfStableCheeseV1919(p)) return false;
  if (petProductV1919(p)) return false;

  return (
    h.includes("MILK") ||
    h.includes("S?T") ||
    h.includes("SUT") ||
    h.includes("YOGURT") ||
    h.includes("YO?URT") ||
    h.includes("AYRAN") ||
    h.includes("KEFIR") ||
    h.includes("KEF?R") ||
    h.includes("DAIRY") ||
    h.includes("PEYNIR") ||
    h.includes("PEYN?R") ||
    h.includes("CHEESE") ||
    h.includes("BUTTER") ||
    h.includes("EGG") ||
    h.includes("YUMURTA") ||
    h.includes("CHICKEN") ||
    h.includes("MEAT")
  );
}

function foodFamilyV1919(p = {}) {
  if (chemicalProductV1919(p)) return "CHEMICAL";
  if (petProductV1919(p)) return "PET";
  if (paperBulkyProductV1919(p)) return "PAPER";
  if (bulkyProductV1919(p)) return "BULKY";
  return "FOOD";
}

function familyCompatibleV1919(a, b) {
  if (!a || !b) return true;
  if (a === b) return true;
  if (a === "CHEMICAL" || b === "CHEMICAL") return false;
  if (a === "PET" || b === "PET") return false;
  if (a === "BULKY" || b === "BULKY") return false;
  if (a === "PAPER" || b === "PAPER") return false;
  return a === "FOOD" && b === "FOOD";
}

export function isExcludedPlanogramProduct(p = {}) {
  const h = haystack(p);

  return (
    h.includes('SHOPPING BAG') ||
    h.includes('ALIŞVERİŞ POŞET') ||
    h.includes('ALISVERIS POSET') ||
    h.includes('POŞET') ||
    h.includes('POSET') ||
    h.includes('CARRIER BAG') ||
    h.includes('MARKET BAG') ||
    h.includes('DISPOSABLE BAG') ||
    h.includes('EVERYDAY') ||
    h.includes('COFFEE MACHINE') ||
    h.includes('KAHVE MAKINESI') ||
    h.includes('KAHVE MAKİNESİ') ||
    h.includes('EQUIPMENT') ||
    h.includes('EKIPMAN') ||
    h.includes('EKİPMAN') ||
    h.includes('LA LORRAINE') ||
    h.includes('BAGUETTE') ||
    h.includes('BAGEL') ||
    h.includes('SİMİT') ||
    h.includes('SIMIT') ||
    h.includes('RAMAZAN PIDESI') ||
    h.includes('RAMAZAN PİDESİ') ||
    h.includes('PIDE') ||
    h.includes('PİDE') ||
    h.includes('BAKERY') ||
    h.includes('FIRIN') ||
    h.includes('EKMEK') ||
    h.includes('BREAD')
  );
}

export function isRealProduce(p = {}) {
  const h = haystack(p);

  const produceSignal =
    h.includes('PRODUCE') ||
    h.includes('FRUIT') ||
    h.includes('VEGETABLE') ||
    h.includes('MEYVE') ||
    h.includes('SEBZE') ||
    h.includes('FRESH') ||
    h.includes('BANANA') ||
    h.includes('MUZ') ||
    h.includes('APPLE') ||
    h.includes('ELMA') ||
    h.includes('POTATO') ||
    h.includes('PATATES') ||
    h.includes('ONION') ||
    h.includes('SOĞAN') ||
    h.includes('SOGAN') ||
    h.includes('TOMATO') ||
    h.includes('DOMATES') ||
    h.includes('CUCUMBER') ||
    h.includes('SALATALIK') ||
    h.includes('LETTUCE') ||
    h.includes('MARUL') ||
    h.includes('DILL') ||
    h.includes('DEREOTU') ||
    h.includes('PARSLEY') ||
    h.includes('MAYDANOZ') ||
    h.includes('MUSHROOM') ||
    h.includes('MANTAR') ||
    h.includes('PUMPKIN') ||
    h.includes('KABAK') ||
    h.includes('MINT') ||
    h.includes('NANE') ||
    h.includes('GINGER') ||
    h.includes('ZENCEFIL') ||
    h.includes('ZENCEFİL') ||
    h.includes('LEMON') ||
    h.includes('LIMON') ||
    h.includes('LİMON') ||
    h.includes('ORANGE') ||
    h.includes('PORTAKAL') ||
    h.includes('MANDALINA');

  const fakeProduce =
    h.includes('CHIPS') ||
    h.includes('CIPS') ||
    h.includes('ÇİPS') ||
    h.includes('CAKE') ||
    h.includes('KEK') ||
    h.includes('YOGURT') ||
    h.includes('YOĞURT') ||
    h.includes('SNACK') ||
    h.includes('BABY') ||
    h.includes('MOISTUR') ||
    h.includes('BATH') ||
    h.includes('SHOWER') ||
    h.includes('WATER') ||
    h.includes('DRINK') ||
    h.includes('JUICE') ||
    h.includes('BOTTLE') ||
    h.includes('CANDY') ||
    h.includes('CHOCOLATE');

  return produceSignal && !fakeProduce;
}


function isNonFoodProduct(p = {}) {
  const h = haystack(p);

  return (
    h.includes('CONDOM') ||
    h.includes('KONDOM') ||
    h.includes('OKEY') ||
    h.includes('PED') ||
    h.includes('DIAPER') ||
    h.includes('BEBEK BEZI') ||
    h.includes('BEBEK BEZ?') ||
    h.includes('DETERJAN') ||
    h.includes('CIF') ||
    h.includes('C?F') ||
    h.includes('DOMESTOS') ||
    h.includes('CIF') ||
    h.includes('C?F') ||
    h.includes('BLEACH') ||
    h.includes('CLEANER') ||
    h.includes('DIRT') ||
    h.includes('OIL REMOVER') ||
    h.includes('SOAP') ||
    h.includes('SABUN') ||
    h.includes('SHAMPOO') ||
    h.includes('?AMPUAN') ||
    h.includes('TOOTHPASTE') ||
    h.includes('D?? MACUNU') ||
    h.includes('DIS MACUNU') ||
    h.includes('MOISTUR') ||
    h.includes('BATH') ||
    h.includes('SHOWER') ||
    h.includes('COSMETIC') ||
    h.includes('KOZMETIK') ||
    h.includes('KOZMET?K') ||
    h.includes('PET FOOD') ||
    h.includes('CAT FOOD') ||
    h.includes('DOG FOOD') ||
    h.includes('KEDI MAMASI') ||
    h.includes('KED? MAMASI') ||
    h.includes('K?PEK MAMASI') ||
    h.includes('KOPEK MAMASI')
  );
}

function productFoodFamily(p = {}) {
  if (isNonFoodProduct(p)) return 'NONFOOD';
  return 'FOOD';
}

function canShareShelfFoodFamily(product = {}, slot = {}) {
  const family = productFoodFamily(product);
  if (!slot.foodFamily) return true;
  return slot.foodFamily === family;
}

export function isOdorNonFood(p = {}) {
  return chemicalProductV1919(p);
}

export function isHeavyOrBulky(p = {}) {
  return bulkyProductV1919(p);
}


function catalogStorageTruth(p = {}) {
  const raw =
    p.catalog_storage_type ||
    p.storage_type ||
    p.storage_class ||
    p.storage ||
    "";

  const v = String(raw || "").trim().toUpperCase();

  if (!v || v === "NULL" || v === "NAN" || v === "UNKNOWN") return "";

  if (v.includes("FROZEN") || v.includes("DONUK") || v.includes("-18") || v.includes("ICE_CREAM")) return "FROZEN";
  if (v.includes("CHILLED") || v.includes("SO?UK") || v.includes("SOGUK") || v.includes("+4")) return "CHILLED";
  if (v.includes("AMBIENT")) return "AMBIENT";

  return "";
}

export function productDomain(p = {}) {
  const catalogStorage = catalogStorageTruth(p);

  // Catalog is the only hard source of storage truth.
  if (catalogStorage) {
    if (isExcludedPlanogramProduct(p)) return "EXCLUDED";
    if (isRealProduce(p)) return "PRODUCE";
    return catalogStorage;
  }

  // Fallback only when catalog storage is missing.
  const h = upperText(p);
  const explicit = explicitStorage(p);

  if (isExcludedPlanogramProduct(p)) return "EXCLUDED";
  if (isRealProduce(p)) return "PRODUCE";

  if (
    explicit.includes("FROZEN") ||
    explicit.includes("DONUK") ||
    h.includes("FROZEN") ||
    h.includes("DONUK") ||
    h.includes("DONDURMA") ||
    h.includes("ICE CREAM") ||
    h.includes("ALGIDA") ||
    h.includes("MAGNUM")
  ) {
    return "FROZEN";
  }

  if (isPetProduct(p)) return "AMBIENT";
  if (isShelfStableCheese(p)) return "AMBIENT";

  if (
    explicit.includes("CHILLED") ||
    explicit.includes("SO?UK") ||
    explicit.includes("SOGUK") ||
    strongChilledSignal(p)
  ) {
    return "CHILLED";
  }

  return "AMBIENT";
}

export function storageFromProduct(p = {}) {
  const d = productDomain(p);
  if (d === 'PRODUCE') return 'AMBIENT';
  if (d === 'FROZEN') return 'FROZEN';
  if (d === 'CHILLED') return 'CHILLED';
  return 'AMBIENT';
}

function slotDomain(o = {}) {
  const h = objectText(o);

  if (
    h.includes('MEYVE') ||
    h.includes('SEBZE') ||
    h.includes('PRODUCE') ||
    h.includes('FRESH')
  ) {
    return 'PRODUCE';
  }

  if (
    h.includes('FROZEN') ||
    h.includes('DONUK') ||
    h.includes('-18') ||
    h.includes('ALGIDA') ||
    h.includes('ICE_CREAM')
  ) {
    return 'FROZEN';
  }

  if (
    h.includes('CHILLED') ||
    h.includes('SOĞUK') ||
    h.includes('SOGUK') ||
    h.includes('+4')
  ) {
    return 'CHILLED';
  }

  return 'AMBIENT';
}

function isCompatible(p = {}, slot = {}) {
  const pd = productDomain(p);
  const sd = slot.domain;

  if (pd === 'EXCLUDED') return false;
  if (sd === 'PRODUCE') return pd === 'PRODUCE';
  if (sd === 'CHILLED') return pd === 'CHILLED';
  if (sd === 'FROZEN') return pd === 'FROZEN';
  if (sd === 'AMBIENT') return pd === 'AMBIENT';

  return false;
}

function maxFrontFacing(p = {}) {
  const sales = Number(p.sales || 0);
  const width = Number(p.width || 8);

  if (isHeavyOrBulky(p) || width >= 18) return sales >= 250 ? 2 : 1;
  if (productDomain(p) === 'PRODUCE') return sales >= 250 ? 2 : 1;
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

function targetSkuCount(slot = {}) {
  const w = Number(slot.width || 100);

  if (slot.domain === 'PRODUCE') return Math.max(6, Math.min(10, Math.floor(w / 16)));
  if (slot.domain === 'CHILLED') return Math.max(6, Math.min(10, Math.floor(w / 18)));
  if (slot.domain === 'FROZEN') return Math.max(5, Math.min(8, Math.floor(w / 22)));

  return Math.max(6, Math.min(10, Math.floor(w / 16)));
}

function maxSkuCount(slot = {}) {
  return targetSkuCount(slot) + 2;
}

function densityScore(slot = {}) {
  const target = targetSkuCount(slot);
  const count = Number(slot.count || 0);

  if (count > 0 && count < target) return -10 + count / Math.max(target, 1);
  if (count === 0) return 0;
  return 5 + (count - target) / Math.max(target, 1);
}

export function estimateEmoji(p = {}) {
  const h = haystack(p).toLocaleLowerCase(TR);
  if (p.storage === 'FROZEN') return h.includes('dondurma') || h.includes('algida') ? '🍦' : '❄️';
  if (p.storage === 'CHILLED') return h.includes('süt') ? '🥛' : '🧊';
  if (h.includes('muz') || h.includes('banana')) return '🍌';
  if (h.includes('patates') || h.includes('potato')) return '🥔';
  if (h.includes('çikolata') || h.includes('chocolate') || h.includes('gofret')) return '🍫';
  if (h.includes('bisküvi') || h.includes('biscuit') || h.includes('burçak')) return '🍪';
  if (h.includes('cola') || h.includes('kola') || h.includes('beverage')) return '🥤';
  return '▣';
}

export function normalizeProduct(raw = {}, idx = 0) {
  const name = String(
    getAny(
      raw,
      ['name', 'product_name', 'Product Name', 'product_name_local', 'pim_product_name_local'],
      getAny(raw, ['sku', 'SKU'], `Product ${idx + 1}`)
    )
  ).trim();

  const sku = String(
    getAny(raw, ['sku', 'SKU', 'barcode', 'Barcodes', 'product_barcodes'], `SKU-${idx + 1}`)
  ).trim() || `SKU-${idx + 1}`;

  const brand = String(getAny(raw, ['brand', 'Brand', 'brand_name'], name.split(' ')[0] || 'UNKNOWN')).trim() || 'UNKNOWN';
  const category = String(getAny(raw, ['category', 'category_l1', 'Category L1', 'frontend_category_local'], 'Genel')).trim() || 'Genel';
  const subcategory = String(getAny(raw, ['subcategory', 'category_l2', 'Category L2', 'frontend_subcategory_local'], 'Genel')).trim() || 'Genel';
  const sales = normalizeSalesValue(getAny(raw, ['sales', 'sales_qty_7d', 'sales_7d', 'Sales 7D', '% Orders', 'percent_orders'], 0), raw);
  const baseWidth = Math.max(1, num(getAny(raw, ['width', 'width_cm', 'Width', 'product_width_in_cm'], 8), 8));
  const width = Math.max(baseWidth, inferredWidthV1919({ ...raw, name, category, subcategory, brand }));
  const height = Math.max(1, num(getAny(raw, ['height', 'height_cm', 'Height', 'product_height_in_cm'], 16), 16));
  const productDepth = Math.max(1, num(getAny(raw, ['product_depth_cm', 'depth_cm', 'product_length_in_cm', 'length_cm'], 10), 10));
  const storage = storageFromProduct({ ...raw, name, product_name: name, category, subcategory, brand });
  const imageUrl = imageFromProduct(raw);
  const image = imageUrl || getAny(raw, ['image'], '') || estimateEmoji({ name, category, subcategory, storage });
  const rawDepthUnits = num(getAny(raw, ['merch_depth', 'depth', 'depth_units'], 0), 0);
  const facing = Math.max(
    1,
    Math.min(
      maxFrontFacing({ ...raw, name, category, subcategory, brand, storage, sales, width }),
      Math.round(num(getAny(raw, ['facing', 'facing_count'], 0), 0) || (sales >= 250 ? 3 : sales >= 60 ? 2 : 1))
    )
  );
  const depth = Math.max(
    1,
    Math.min(12, Math.round(rawDepthUnits || depthForDemand({ sales }, facing)))
  );

  return {
    ...raw,
    sku,
    name,
    product_name: name,
    brand,
    category,
    subcategory,
    storage,
    storage_type: storage,
    product_domain: productDomain({ ...raw, name, category, subcategory, brand, storage }),
    food_family: productFoodFamily({ ...raw, name, category, subcategory, brand, storage }),
    sales,
    sales_label: sales >= 100 ? Math.round(sales).toLocaleString(TR) : sales.toFixed(1),
    facing,
    depth,
    product_depth_cm: productDepth,
    width,
    height,
    weight_kg: Math.max(0.01, num(getAny(raw, ['weight_kg', 'Weight', 'product_weight_value'], 0.2), 0.2)),
    abc: getAny(raw, ['ABC', 'abc', 'abc_class'], ''),
    rank: num(getAny(raw, ['Rank', 'rank'], 0), 0),
    location_raw: getAny(raw, ['Location', 'current_location'], ''),
    secondary_location: getAny(raw, ['Secondary Location', 'secondary_location'], ''),
    image_url: imageUrl,
    image,
    risk: sales >= 250 ? 'Yüksek' : sales >= 80 ? 'Orta' : 'Düşük',
    color: storage === 'FROZEN' ? '#7b61ff' : storage === 'CHILLED' ? '#18c7df' : '#df1067',
  };
}

function shelfOrderFor(p) {
  if (isHeavyOrBulky(p)) return [1, 2, 3, 4, 5, 6, 7, 8];
  if (Number(p.sales || 0) >= 80) return [2, 3, 4, 1, 5, 6, 7, 8];
  return [4, 5, 3, 6, 2, 1, 7, 8];
}

function targetAreas(p, objects) {
  const ids = new Set((objects || []).map((o) => String(o.id)));
  const has = (x) => ids.has(String(x));
  const h = haystack(p);
  const abc = String(p.abc || p.ABC || '').toUpperCase();
  const rank = Number(p.rank || 999999);
  const score = Number(p.sales || 0);

  if (productDomain(p) === 'PRODUCE') {
    return [...ids].filter((id) => {
      const o = (objects || []).find((x) => String(x.id) === String(id));
      return slotDomain(o) === 'PRODUCE';
    });
  }

  if (p.storage === 'FROZEN') {
    const preferred = h.includes('ALGIDA') || h.includes('MAGNUM') || h.includes('DONDURMA')
      ? ['ALGIDA_1', 'FROZEN_ROOM']
      : ['FROZEN_ROOM', 'ALGIDA_1'];
    return preferred.filter(has);
  }

  if (p.storage === 'CHILLED') {
    return ['CHILLED_ROOM', 'HORIZONTAL_FRIDGE', '+4 SOĞUK', '+4 SOGUK'].filter(has);
  }

  if (isOdorNonFood(p) || isNonFoodProduct(p)) return ['I', 'H', 'STEEL_RACK', 'G', 'F'].filter(has);
  if (isHeavyOrBulky(p)) return ['STEEL_RACK', 'G', 'H', 'I', 'F', 'E'].filter(has);

  if (abc === 'A' || rank <= 900 || score >= 55) return ['A', 'B', 'C', 'D', 'E', 'F'].filter(has);
  if (abc === 'B' || rank <= 2500 || score >= 18) return ['D', 'E', 'F', 'G', 'B', 'C', 'H', 'I'].filter(has);

  return ['H', 'I', 'G', 'F', 'E', 'C', 'B', 'STEEL_RACK'].filter(has);
}

function buildSlots(objects = []) {
  const slots = [];

  for (const o of objects || []) {
    if (!o || !o.modules || !o.shelves) continue;

    const domain = slotDomain(o);
    const zone = domain === 'PRODUCE' ? 'AMBIENT' : domain;
    const modules = Math.max(1, Math.min(40, Number(o.modules || 1)));
    const shelvesPerModule = Math.max(
      1,
      Math.min(12, Math.ceil(Number(o.shelves || modules * 5) / modules))
    );

    const width =
      Number(o.shelf_width_cm || o.width_cm || o.width) ||
      (domain === 'CHILLED' || domain === 'FROZEN'
        ? 180
        : domain === 'PRODUCE'
          ? 120
          : o.type === 'steel_rack'
            ? 140
            : 120);

    for (let m = 1; m <= modules; m += 1) {
      for (let s = 1; s <= shelvesPerModule; s += 1) {
        slots.push({
          areaId: o.id,
          areaLabel: o.label || o.id,
          zone,
          domain,
          module: m,
          shelf: s,
          width,
          usableWidth: width * 0.92,
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
    if (partnerSku && slot.skus.has(partnerSku)) {
      score += Number(partner.score || 0);
    }
  }

  return score;
}


// === V1.9.43 Hybrid Brand Block Slot Scorer ===
// RuleEngine Hybrid Brand Block Slot Scorer ===
// RuleEngine ?r?nlere preferred_aisle / preferred_side / brand_block_rank bas?yor.
// Bu helper'lar art?k bu sinyali ger?ek slot se?iminde kullan?r.
// Hard storage, food-family ve kapasite filtreleri yine daha ?nce ?al???r; yani bu scorer kapasiteyi bozmaz.

function normalizeHybridSide(value = "") {
  const v = String(value || "")
    .trim()
    .toUpperCase()
    .replaceAll("?", "I")
    .replaceAll("?", "G")
    .replaceAll("?", "U")
    .replaceAll("?", "S")
    .replaceAll("?", "O")
    .replaceAll("?", "C");

  if (["R", "RIGHT", "SAG", "SA?"].includes(v)) return "SA?";
  if (["L", "LEFT", "SOL"].includes(v)) return "SOL";
  return "";
}

function buildHybridSideByModule(slots = []) {
  const byAisle = new Map();

  for (const s of slots || []) {
    const aisle = String(s.areaId || s.aisle || s.aisle_id || "").trim();
    const moduleNo = Number(s.module || s.module_id || 0);

    if (!aisle || !Number.isFinite(moduleNo) || moduleNo <= 0) continue;
    if (!byAisle.has(aisle)) byAisle.set(aisle, new Set());
    byAisle.get(aisle).add(moduleNo);
  }

  const out = new Map();

  for (const [aisle, set] of byAisle.entries()) {
    const modules = [...set].sort((a, b) => a - b);
    const midpoint = Math.ceil(modules.length / 2);

    modules.forEach((moduleNo, idx) => {
      const side = idx < midpoint ? "SOL" : "SA?";
      out.set(`${aisle}__${moduleNo}`, side);
    });
  }

  return out;
}

function hybridProductCompare(a = {}, b = {}) {
  const ar = Number(a.brand_block_rank || 999999);
  const br = Number(b.brand_block_rank || 999999);

  const as = Number(a.sku_rank_in_brand || 999999);
  const bs = Number(b.sku_rank_in_brand || 999999);

  const ap = Number(a.hybrid_priority_score || 0);
  const bp = Number(b.hybrid_priority_score || 0);

  return (
    ar - br ||
    as - bs ||
    bp - ap
  );
}

function hybridSlotScore(product = {}, slot = {}, sideByModule = new Map()) {
  let score = 0;

  const preferredAisle = String(product.preferred_aisle || product.brand_block_target_aisle || "").trim();
  const slotAisle = String(slot.areaId || slot.aisle || slot.aisle_id || "").trim();

  if (preferredAisle) {
    score += slotAisle === preferredAisle ? 5000 : -5000;
  }

  const preferredSide = normalizeHybridSide(product.preferred_side || product.brand_block_target_side);
  const explicitSlotSide = normalizeHybridSide(slot.side || slot.module_side || slot.moduleSide);
  const derivedSlotSide = sideByModule.get(`${slotAisle}__${Number(slot.module || slot.module_id || 0)}`) || "";
  const slotSide = explicitSlotSide || derivedSlotSide;

  if (preferredSide) {
    score += slotSide === preferredSide ? 1500 : -1500;
  }

  // Marka blo?u i?indeki y?ksek sat??l? SKU'lar ?nce daha bo? / g?r?n?r slotlar? als?n.
  if (product.hybrid_brand_block || product.brand_block_rank) {
    score += Math.max(0, 1000 - Number(product.brand_block_rank || 999)) * 4;
    score += Math.max(0, 1000 - Number(product.sku_rank_in_brand || 999)) * 0.25;
  }

  return score;
}

function hybridPlacementNote(product = {}, slot = {}, sideByModule = new Map()) {
  if (!(product.hybrid_brand_block || product.brand_block_rank || product.preferred_aisle)) return "";

  const slotAisle = String(slot.areaId || slot.aisle || slot.aisle_id || "").trim();
  const slotSide =
    normalizeHybridSide(slot.side || slot.module_side || slot.moduleSide) ||
    sideByModule.get(`${slotAisle}__${Number(slot.module || slot.module_id || 0)}`) ||
    "";

  const brand = product.brand || product.brand_name || product.supplier || "Marka";
  const rank = product.brand_block_rank ? `#${product.brand_block_rank}` : "-";
  const skuRank = product.sku_rank_in_brand ? `#${product.sku_rank_in_brand}` : "-";
  const target = [product.preferred_aisle || product.brand_block_target_aisle, product.preferred_side || product.brand_block_target_side]
    .filter(Boolean)
    .join(" ");

  return `Hibrit marka blok: ${brand} marka s?ra ${rank}, marka i?i SKU s?ra ${skuRank}, hedef ${target}, se?ilen ${slotAisle} ${slotSide}`.trim();
}

export function buildStorePlan(inputProducts = [], objects = [], options = {}) {
  const normalized = (inputProducts || [])
    .map(normalizeProduct)
    .filter((p) => productDomain(p) !== 'EXCLUDED');

  const slots = buildSlots(objects);
  const sideByModule = buildHybridSideByModule(slots);
  const placed = [];
  const unplaced = [];

  const sorted = [...normalized].sort((a, b) => {
    const domainOrder = { FROZEN: 0, CHILLED: 1, PRODUCE: 2, AMBIENT: 3 };
    return (
      (domainOrder[productDomain(a)] ?? 9) - (domainOrder[productDomain(b)] ?? 9) ||
      hybridProductCompare(a, b) ||
      Number(b.sales || 0) - Number(a.sales || 0) ||
      Number(a.rank || 999999) - Number(b.rank || 999999)
    );
  });

  for (const p of sorted) {
    const targets = targetAreas(p, objects);
    const targetPriority = new Map(targets.map((id, idx) => [String(id), idx]));
    const shelfOrder = shelfOrderFor(p);

    let candidates = slots
      .filter((s) => {
        const inTarget = !targets.length || targets.includes(s.areaId);
        return inTarget && isCompatible(p, s) && canShareShelfFoodFamily(p, s) && s.count < maxSkuCount(s);
      });

    if (!candidates.length) {
      candidates = slots.filter((s) => isCompatible(p, s) && canShareShelfFoodFamily(p, s) && s.count < maxSkuCount(s));
    }

    candidates = candidates.sort((a, b) => {
      const ai = String(a.areaId || '');
      const bi = String(b.areaId || '');

      const hybridPref =
        hybridSlotScore(p, b, sideByModule) - hybridSlotScore(p, a, sideByModule);

      if (hybridPref !== 0) return hybridPref;

      const prio =
        (targetPriority.get(ai) ?? 99) - (targetPriority.get(bi) ?? 99);

      if (prio !== 0) return prio;

      const affA = affinityScoreForSlot(p, a, options.affinityMap || {});
      const affB = affinityScoreForSlot(p, b, options.affinityMap || {});

      return (
        (affB > 0 ? -1 : 0) - (affA > 0 ? -1 : 0) ||
        densityScore(a) - densityScore(b) ||
        shelfOrder.indexOf(a.shelf) - shelfOrder.indexOf(b.shelf) ||
        a.used - b.used ||
        a.module - b.module ||
        a.shelf - b.shelf
      );
    });

    let chosen = null;

    for (const slot of candidates) {
      const facing = Math.max(1, Math.min(maxFrontFacing(p), Number(p.facing || 1)));
      const required = Math.max(3, Number(p.width || 8) * facing);

      if (slot.used + required <= slot.usableWidth && slot.count < maxSkuCount(slot)) {
        chosen = { slot, required, facing };
        break;
      }
    }

    if (!chosen) {
      unplaced.push({
        ...p,
        reason: 'NO_PHYSICAL_FRONT_CAPACITY',
        reason_code: 'NO_PHYSICAL_FRONT_CAPACITY',
        product_domain: productDomain(p),
        suggested_action:
          productDomain(p) === 'PRODUCE'
            ? 'Meyve-sebze raf kapasitesini artır veya ürün havuzunu azalt.'
            : p.storage === 'FROZEN'
              ? '-18 donuk alan / Algida dolabı kapasitesini artır.'
              : p.storage === 'CHILLED'
                ? '+4 soğutucu kapasitesini artır.'
                : 'Ambient raf kapasitesini veya ürün ölçülerini kontrol et.',
      });
      continue;
    }

    const { slot, required, facing } = chosen;
    slot.used += required;
    slot.count += 1;
    slot.foodFamily = slot.foodFamily || foodFamilyV1919(p);
    slot.skus.add(skuKeyForAffinity(p));
    slot.foodFamily = slot.foodFamily || productFoodFamily(p);

    placed.push({
      ...p,
      facing,
      depth: Math.max(Number(p.depth || 1), depthForDemand(p, facing)),
      depth_strategy: 'DEPTH_FIRST_FRONT_FACE_CAPPED',
      aisle: slot.areaId,
      aisle_id: slot.areaId,
      module: slot.module,
      module_id: slot.module,
      shelf: slot.shelf,
      shelf_no: slot.shelf,
      position: slot.count,
      slot_domain: slot.domain,
      hybrid_brand_block: Boolean(p.hybrid_brand_block),
      brand_block_rank: p.brand_block_rank || null,
      sku_rank_in_brand: p.sku_rank_in_brand || null,
      preferred_aisle: p.preferred_aisle || null,
      preferred_side: p.preferred_side || null,
      selected_side: normalizeHybridSide(slot.side || slot.module_side || slot.moduleSide) || sideByModule.get(`${slot.areaId}__${Number(slot.module || 0)}`) || null,
      hybrid_placement_note: hybridPlacementNote(p, slot, sideByModule),
      food_family: foodFamilyV1919(p),
      food_family: productFoodFamily(p),
      basket_affinity_score: affinityScoreForSlot(p, slot, options.affinityMap || {}),
      placement_reason: hybridPlacementNote(p, slot, sideByModule) || (affinityScoreForSlot(p, slot, options.affinityMap || {}) > 0
        ? `${slot.domain} domain + basket affinity yak?nl??? + physical front capacity`
        : `${slot.domain} domain + physical front capacity + depth-first stock`),
    });
  }

  const utilizationByArea = {};

  for (const s of slots) {
    utilizationByArea[s.areaId] ||= { used: 0, cap: 0, count: 0 };
    utilizationByArea[s.areaId].used += Math.min(s.used, s.usableWidth);
    utilizationByArea[s.areaId].cap += s.usableWidth;
    utilizationByArea[s.areaId].count += s.count;
  }

  return { placed, unplaced, utilizationByArea };
}

export function updateObjectsFromPlan(objects = [], plan = {}) {
  return (objects || []).map((o) => {
    const m = plan.utilizationByArea?.[o.id];
    if (!m) return o;

    const utilization = Math.round((m.used / Math.max(m.cap, 1)) * 100);

    return {
      ...o,
      utilization: Math.max(0, Math.min(100, utilization)),
      changed: Math.max(Number(o.changed || 0), Math.round(m.count * 0.05)),
    };
  });
}

export function productsForShelf(products = [], aisle, module, shelf) {
  return (products || []).filter(
    (p) =>
      String(p.aisle) === String(aisle) &&
      Number(p.module || 1) === Number(module) &&
      Number(p.shelf || 1) === Number(shelf)
  );
}

export function moduleShelfCount(products = [], aisle, module) {
  return Math.max(
    1,
    ...products
      .filter((p) => String(p.aisle) === String(aisle) && Number(p.module || 1) === Number(module))
      .map((p) => Number(p.shelf || 1))
  );
}
