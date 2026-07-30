const TR = 'tr-TR';

export function num(v, fallback = 0) {
  const n = Number(String(v ?? '').replace(',', '.').replace('%', '').trim());
  return Number.isFinite(n) ? n : fallback;
}

export function getAny(row = {}, names = [], fallback = '') {
  const lower = Object.fromEntries(Object.keys(row || {}).map((k) => [String(k).toLowerCase().trim(), k]));
  for (const name of names) {
    const found = lower[String(name).toLowerCase().trim()];
    if (found !== undefined && row[found] !== undefined && row[found] !== null && row[found] !== '') return row[found];
  }
  return fallback;
}

export function imageFromProduct(p = {}) {
  return getAny(p, [
    'image_url', 'imageUrl', 'Product Image URL', 'product_image_url', 'catalog_image_url', 'pim_image_url', 'photo_url'
  ], '');
}

export function normalizeSalesValue(rawSales, row = {}) {
  let sales = num(rawSales, NaN);
  const pctOrders = num(getAny(row, ['% Orders', 'percent_orders', 'orders_pct', 'order_share'], 0), 0);
  const pctStops = num(getAny(row, ['% Stops', 'percent_stops', 'stops_pct'], 0), 0);
  const rank = num(getAny(row, ['Rank', 'rank'], 0), 0);
  const abc = String(getAny(row, ['ABC', 'abc', 'abc_class'], '')).toUpperCase();

  // ABC raporundaki % Orders alanı çoğu zaman yüzde noktasıdır: 0.984 => çok yüksek, 0.070 => anlamlı satış.
  // Direkt günlük adet değil; bu yüzden operasyon skoru üretmek için ölçeklenir.
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

export function storageFromProduct(p = {}) {
  const raw = String(getAny(p, ['storage', 'storage_type', 'Storage Type', 'allowed_storage_type'], '')).toUpperCase();
  const hay = `${getAny(p, ['product_name', 'Product Name', 'name'], '')} ${getAny(p, ['category', 'category_l1', 'Category L1', 'frontend_category_local'], '')} ${getAny(p, ['subcategory', 'category_l2', 'Category L2', 'frontend_subcategory_local'], '')} ${getAny(p, ['brand', 'brand_name'], '')}`.toLocaleUpperCase(TR);

  // v1.5: Ürün barkodu/CSV storage alanı hatalı gelse bile operasyonel fixture gerçeğini koru.
  // Patates, muz, mandalina gibi dışarı/raf üzerinde duran ürünler random AMBIENT rafa değil MEYVE SEBZE RAFI'na gider.
  if (['PATATES', 'SOĞAN', 'SOGAN', 'MUZ', 'BANANA', 'MANDALINA', 'PORTAKAL', 'ELMA', 'ARMUT', 'AVOKADO'].some((x) => hay.includes(x))) return 'AMBIENT';
  if (['MAYDANOZ', 'MARUL', 'ROKA', 'DEREOTU', 'NANE', 'FESLEĞEN', 'FESLEGEN'].some((x) => hay.includes(x))) return 'CHILLED';

  if (raw.includes('FROZEN') || raw.includes('-18') || hay.includes('DONUK') || hay.includes('DONDURMA') || hay.includes('ICE CREAM') || hay.includes('ALGIDA')) return 'FROZEN';
  if (raw.includes('CHILLED') || raw.includes('COLD') || raw.includes('+4') || hay.includes('SOĞUK') || hay.includes('SOGUK') || hay.includes('SÜT') || hay.includes('SUT') || hay.includes('YOĞURT') || hay.includes('YOGURT') || hay.includes('PEYNİR')) return 'CHILLED';
  return 'AMBIENT';
}

export function isProduce(p = {}) {
  const hay = `${p.name || p.product_name || ''} ${p.category || ''} ${p.subcategory || ''} ${p.brand || ''}`.toLocaleUpperCase(TR);
  return ['MEYVE', 'SEBZE', 'FRUIT', 'VEGETABLE', 'PATATES', 'SOĞAN', 'SOGAN', 'MUZ', 'BANANA', 'MANDALINA', 'PORTAKAL', 'ELMA', 'ARMUT', 'MAYDANOZ', 'DOMATES', 'SALATALIK'].some((x) => hay.includes(x));
}

export function isAmbientProduce(p = {}) {
  const hay = `${p.name || p.product_name || ''} ${p.category || ''} ${p.subcategory || ''} ${p.brand || ''}`.toLocaleUpperCase(TR);
  return ['PATATES', 'SOĞAN', 'SOGAN', 'MUZ', 'BANANA', 'MANDALINA', 'PORTAKAL', 'ELMA', 'ARMUT', 'AVOKADO', 'LIMON', 'LİMON'].some((x) => hay.includes(x));
}

export function isChilledProduce(p = {}) {
  const hay = `${p.name || p.product_name || ''} ${p.category || ''} ${p.subcategory || ''} ${p.brand || ''}`.toLocaleUpperCase(TR);
  return ['MAYDANOZ', 'MARUL', 'ROKA', 'DEREOTU', 'NANE', 'FESLEĞEN', 'FESLEGEN', 'SALATALIK', 'DOMATES', 'ÇİLEK', 'CILEK'].some((x) => hay.includes(x));
}

export function isOdorNonFood(p = {}) {
  const hay = `${p.name || p.product_name || ''} ${p.category || ''} ${p.subcategory || ''} ${p.brand || ''}`.toLocaleUpperCase(TR);
  return ['DOMESTOS', 'DETERJAN', 'TEMİZ', 'TEMIZ', 'ÇAMAŞIR', 'CAMASIR', 'YUMUŞATICI', 'YUMUSATICI', 'SHAMPOO', 'ŞAMPUAN', 'ÇÖP', 'COP', 'GARBAGE', 'BLEACH', 'CLEAN'].some((x) => hay.includes(x));
}

export function isHeavyOrBulky(p = {}) {
  const hay = `${p.name || p.product_name || ''} ${p.category || ''} ${p.subcategory || ''}`.toLocaleUpperCase(TR);
  return Number(p.weight_kg || p.weight || 0) >= 3 || ['WATER', 'SU ', ' 5 L', '5L', '6 X', '10 L', 'KUM', 'MAMA', 'YAĞ', 'YAG'].some((x) => hay.includes(x));
}

export function estimateEmoji(p = {}) {
  const hay = `${p.name || p.product_name || ''} ${p.category || ''} ${p.subcategory || ''}`.toLocaleLowerCase(TR);
  if (p.storage === 'FROZEN') return hay.includes('dondurma') || hay.includes('algida') ? '🍦' : '❄️';
  if (p.storage === 'CHILLED') return hay.includes('süt') ? '🥛' : '🧊';
  if (hay.includes('muz')) return '🍌';
  if (hay.includes('patates')) return '🥔';
  if (hay.includes('çikolata') || hay.includes('chocolate') || hay.includes('gofret')) return '🍫';
  if (hay.includes('bisküvi') || hay.includes('biscuit') || hay.includes('burçak')) return '🍪';
  if (hay.includes('cola') || hay.includes('kola') || hay.includes('beverage')) return '🥤';
  return '▣';
}

export function normalizeProduct(raw = {}, idx = 0) {
  const storage = storageFromProduct(raw);
  const name = String(getAny(raw, ['name', 'product_name', 'Product Name', 'product_name_local', 'pim_product_name_local'], getAny(raw, ['sku', 'SKU'], `Product ${idx + 1}`))).trim();
  const sku = String(getAny(raw, ['sku', 'SKU', 'barcode', 'Barcodes', 'product_barcodes'], `SKU-${idx + 1}`)).trim() || `SKU-${idx + 1}`;
  const brand = String(getAny(raw, ['brand', 'Brand', 'brand_name'], name.split(' ')[0] || 'UNKNOWN')).trim() || 'UNKNOWN';
  const category = String(getAny(raw, ['category', 'category_l1', 'Category L1', 'frontend_category_local'], 'Genel')).trim() || 'Genel';
  const subcategory = String(getAny(raw, ['subcategory', 'category_l2', 'Category L2', 'frontend_subcategory_local'], 'Genel')).trim() || 'Genel';
  const sales = normalizeSalesValue(getAny(raw, ['sales', 'sales_qty_7d', 'sales_7d', 'Sales 7D', '% Orders', 'percent_orders'], 0), raw);
  const width = Math.max(1, num(getAny(raw, ['width', 'width_cm', 'Width', 'product_width_in_cm'], 8), 8));
  const height = Math.max(1, num(getAny(raw, ['height', 'height_cm', 'Height', 'product_height_in_cm'], 16), 16));
  const productDepth = Math.max(1, num(getAny(raw, ['product_depth_cm', 'depth_cm', 'product_length_in_cm', 'length_cm'], 10), 10));
  const imageUrl = imageFromProduct(raw);
  const image = imageUrl || getAny(raw, ['image'], '') || estimateEmoji({ name, category, subcategory, storage });
  const rawDepthUnits = num(getAny(raw, ['merch_depth', 'depth', 'depth_units'], 0), 0);
  const facing = Math.max(1, Math.min(10, Math.round(num(getAny(raw, ['facing', 'facing_count'], 0), 0) || (sales >= 700 ? 6 : sales >= 250 ? 5 : sales >= 120 ? 4 : sales >= 60 ? 3 : sales >= 20 ? 2 : 1))));
  const depth = Math.max(1, Math.min(12, Math.round(rawDepthUnits || (sales >= 700 ? 8 : sales >= 250 ? 6 : sales >= 120 ? 5 : sales >= 60 ? 4 : sales >= 20 ? 3 : 2))));
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
    aisle: raw.aisle || raw.aisle_id || (storage === 'FROZEN' ? 'FROZEN_ROOM' : storage === 'CHILLED' ? 'CHILLED_ROOM' : 'A'),
    module: Number(raw.module || raw.module_id || 1),
    shelf: Number(raw.shelf || raw.shelf_no || 1),
  };
}

function shelfOrderFor(p) {
  if (isHeavyOrBulky(p)) return [1, 2, 3, 4, 5, 6, 7, 8];
  if (Number(p.sales || 0) >= 80) return [2, 3, 4, 1, 5, 6, 7, 8];
  return [4, 5, 3, 6, 2, 1, 7, 8];
}

function targetAreas(p, objects) {
  const ids = new Set((objects || []).map((o) => String(o.id)));
  const addExisting = (arr) => arr.filter((x) => ids.has(x));
  const name = `${p.name} ${p.brand} ${p.category} ${p.subcategory}`.toLocaleUpperCase(TR);
  const rank = Number(p.rank || 999999);
  const abc = String(p.abc || p.ABC || '').toUpperCase();
  const score = Number(p.sales || 0);

  if (p.storage === 'FROZEN') return addExisting(name.includes('ALGIDA') || name.includes('MAGNUM') || name.includes('DONDURMA') ? ['ALGIDA_1', 'FROZEN_ROOM'] : ['FROZEN_ROOM', 'ALGIDA_1']);
  if (p.storage === 'CHILLED') return addExisting(isProduce(p) ? ['CHILLED_ROOM', 'HORIZONTAL_FRIDGE'] : ['CHILLED_ROOM', 'HORIZONTAL_FRIDGE']);
  if (isProduce(p)) return addExisting(['PRODUCE_SHELF', 'D', 'E', 'G', 'STEEL_RACK']);
  if (isOdorNonFood(p)) return addExisting(['I', 'H', 'STEEL_RACK', 'G']);
  if (isHeavyOrBulky(p)) return addExisting(['STEEL_RACK', 'G', 'H', 'I', 'F', 'E']);

  // v1.5: A/B/C artık boş kalmaz. A kalite ve hızlı ürünler ön koridorlara dengeli yayılır.
  if (abc === 'A' || rank <= 900 || score >= 55) return addExisting(['A', 'B', 'C', 'D', 'E', 'F']);
  if (abc === 'B' || rank <= 2500 || score >= 18) return addExisting(['D', 'E', 'F', 'G', 'B', 'C', 'H', 'I']);
  return addExisting(['H', 'I', 'G', 'F', 'E', 'C', 'B', 'STEEL_RACK']);
}

function moduleShelfWidthCm(o = {}) {
  const direct = Number(o.shelf_width_cm || o.module_width_cm || o.width_cm || 0);
  if (direct > 0) return Math.max(40, Math.min(240, direct));
  if (o.type === 'produce_shelf') return 120;
  if (o.type === 'chilled_room' || o.type === 'frozen_room') return 150;
  if (o.type === 'steel_rack') return 100;
  return 100;
}

function moduleShelfDepthCm(o = {}) {
  const direct = Number(o.shelf_depth_cm || o.module_depth_cm || o.depth_cm || 0);
  if (direct > 0) return Math.max(20, Math.min(120, direct));
  if (o.type === 'produce_shelf') return 60;
  if (o.type === 'chilled_room') return 55;
  if (o.type === 'frozen_room') return 60;
  if (o.type === 'steel_rack') return 60;
  return 50;
}

function productWidthCm(p = {}) {
  return Math.max(4, Number(p.width_cm || p.width || p.product_width_in_cm || 8));
}

function productDepthCm(p = {}) {
  return Math.max(1, Number(p.product_depth_cm || p.depth_cm || p.product_length_in_cm || 10));
}

function maxDepthUnitsFor(slot, p) {
  return Math.max(1, Math.floor(Number(slot.depth || 50) / productDepthCm(p)));
}

function buildSlots(objects = []) {
  const slots = [];
  for (const o of objects || []) {
    if (!o || !o.modules || !o.shelves) continue;
    const zone = String(o.zone || 'AMBIENT').toUpperCase();
    if (!['AMBIENT', 'CHILLED', 'FROZEN'].includes(zone)) continue;
    const modules = Math.max(1, Math.min(32, Number(o.modules || 1)));
    const shelvesPerModule = Math.max(1, Math.min(10, Math.ceil(Number(o.shelves || modules * 5) / modules)));
    const width = moduleShelfWidthCm(o);
    const depth = moduleShelfDepthCm(o);
    for (let m = 1; m <= modules; m += 1) {
      for (let s = 1; s <= shelvesPerModule; s += 1) {
        slots.push({
          areaId: o.id,
          areaLabel: o.label,
          zone,
          module: m,
          shelf: s,
          width,
          depth,
          used: 0,
          count: 0,
          maxCount: Math.max(1, Math.floor(width / 4)),
        });
      }
    }
  }
  return slots;
}

export function buildStorePlan(inputProducts = [], objects = [], options = {}) {
  const products = (inputProducts || []).map(normalizeProduct);
  const slots = buildSlots(objects);
  const placed = [];
  const unplaced = [];
  const sorted = [...products].sort((a, b) => {
    const zoneOrder = { FROZEN: 0, CHILLED: 1, AMBIENT: 2 };
    return (zoneOrder[a.storage] ?? 9) - (zoneOrder[b.storage] ?? 9) || Number(b.sales || 0) - Number(a.sales || 0) || Number(a.rank || 999999) - Number(b.rank || 999999);
  });
  for (const p0 of sorted) {
    const p = normalizeProduct(p0);
    const targets = targetAreas(p, objects);
    let chosen = null;
    const shelfOrder = shelfOrderFor(p);
    const targetPriority = new Map(targets.map((id, idx) => [String(id), idx]));
    const candidates = slots
      .filter((s) => targets.includes(s.areaId) && s.zone === p.storage && s.count < s.maxCount)
      .sort((a, b) => {
        const ai = String(a.areaId || '');
        const bi = String(b.areaId || '');
        const frontBoostA = options.forceFrontBalance && ['A','B','C'].includes(ai) ? -0.28 : 0;
        const frontBoostB = options.forceFrontBalance && ['A','B','C'].includes(bi) ? -0.28 : 0;
        const occA = a.count / Math.max(a.maxCount, 1);
        const occB = b.count / Math.max(b.maxCount, 1);
        return (occA + frontBoostA) - (occB + frontBoostB)
          || (targetPriority.get(ai) ?? 99) - (targetPriority.get(bi) ?? 99)
          || shelfOrder.indexOf(a.shelf) - shelfOrder.indexOf(b.shelf)
          || a.used - b.used
          || a.module - b.module;
      });
    for (const slot of candidates) {
      const preferredFacing = Math.max(1, Math.min(10, Number(p.facing || 1)));
      const unitWidth = productWidthCm(p);
      const remainingWidth = Math.max(0, slot.width - slot.used);
      const maxFacingByWidth = Math.floor(remainingWidth / unitWidth);
      if (maxFacingByWidth < 1) continue;

      const actualFacing = Math.max(1, Math.min(preferredFacing, maxFacingByWidth, 8));
      const actualDepth = Math.max(1, Math.min(Number(p.depth || 1), maxDepthUnitsFor(slot, p), 20));
      const required = unitWidth * actualFacing;

      if (slot.used + required <= slot.width + 0.001) {
        chosen = { slot, required, actualFacing, actualDepth, preferredFacing };
        break;
      }
    }
    if (!chosen) {
      unplaced.push({
        ...p,
        reason: targets.length ? 'Kapasite veya kural nedeniyle sığmadı' : 'Uygun storage/fixture bulunamadı',
        suggested_action: p.storage === 'FROZEN'
          ? '-18 donuk alan / Algida dolabı kapasitesini artır veya facing düşür.'
          : p.storage === 'CHILLED'
            ? '+4 soğutucu kapasitesini artır veya storage kuralını doğrula.'
            : 'Raf kapasitesini, fixture uygunluğunu veya ürün ölçüsünü kontrol et.',
      });
      continue;
    }
    const { slot, required, actualFacing, actualDepth, preferredFacing } = chosen;
    slot.used += required;
    slot.count += 1;
    placed.push({
      ...p,
      facing: actualFacing,
      depth: actualDepth,
      preferred_facing: preferredFacing,
      width_used_cm: Math.round(required * 10) / 10,
      shelf_width_cm: slot.width,
      shelf_depth_cm: slot.depth,
      aisle: slot.areaId,
      aisle_id: slot.areaId,
      module: slot.module,
      module_id: slot.module,
      shelf: slot.shelf,
      shelf_no: slot.shelf,
      position: slot.count,
      placement_reason: actualFacing < preferredFacing
        ? `${p.storage} fixture + kapasiteye göre facing ${preferredFacing} → ${actualFacing} düşürüldü`
        : `${p.storage} fixture + satış/ABC önceliği + kategori ayrımı`,
    });
  }
  const utilizationByArea = {};
  for (const s of slots) {
    utilizationByArea[s.areaId] ||= { used: 0, cap: 0, count: 0 };
    utilizationByArea[s.areaId].used += Math.min(s.used, s.width);
    utilizationByArea[s.areaId].cap += s.width;
    utilizationByArea[s.areaId].count += s.count;
  }
  return { placed, unplaced, utilizationByArea };
}

export function updateObjectsFromPlan(objects = [], plan = {}) {
  return (objects || []).map((o) => {
    const m = plan.utilizationByArea?.[o.id];
    if (!m) return o;
    return {
      ...o,
      utilization: Math.max(5, Math.min(98, Math.round((m.used / Math.max(m.cap, 1)) * 100))),
      changed: Math.max(Number(o.changed || 0), Math.round(m.count * 0.05)),
    };
  });
}

export function productsForShelf(products = [], aisle, module, shelf) {
  return (products || []).filter((p) => String(p.aisle) === String(aisle) && Number(p.module || 1) === Number(module) && Number(p.shelf || 1) === Number(shelf));
}

export function moduleShelfCount(products = [], aisle, module) {
  return Math.max(1, ...products.filter((p) => String(p.aisle) === String(aisle) && Number(p.module || 1) === Number(module)).map((p) => Number(p.shelf || 1)));
}
