// PLONAGRAM Placement Diagnostics
// Frontend-only diagnostic engine. It does not change the planogram; it explains why SKUs did not fit.

export function pdNumber(value, fallback = 0) {
  const parsed = Number(String(value ?? '').replace(',', '.').replace('%', '').trim());
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function pdText(value) {
  return String(value ?? '').trim();
}

export function pdNorm(value) {
  return pdText(value)
    .toLocaleLowerCase('tr-TR')
    .replaceAll('ı', 'i')
    .replaceAll('ğ', 'g')
    .replaceAll('ü', 'u')
    .replaceAll('ş', 's')
    .replaceAll('ö', 'o')
    .replaceAll('ç', 'c');
}

export function inferStorageType(raw = {}) {
  const explicit = pdNorm(raw.storage_type || raw.Storage || raw['Storage Type'] || raw.allowed_storage_type);
  const haystack = pdNorm([
    raw.product_name,
    raw.name,
    raw.product_name_local,
    raw.category_l1,
    raw.category_l2,
    raw.frontend_category_local,
    raw.frontend_subcategory_local,
    raw.brand,
    raw.brand_name,
  ].filter(Boolean).join(' '));

  const text = `${explicit} ${haystack}`;
  if (/frozen|freezer|donuk|-18|dondurma|algida|ice cream/.test(text)) return 'FROZEN';
  if (/chilled|cold|soguk|soğuk|\+4|sut|süt|yogurt|yoğurt|peynir|tavuk|et\b|dairy/.test(text)) return 'CHILLED';
  return 'AMBIENT';
}

export function getProductDimensions(raw = {}) {
  const widthRaw = raw.width_cm ?? raw.product_width_in_cm ?? raw.Width ?? raw.En;
  const heightRaw = raw.height_cm ?? raw.product_height_in_cm ?? raw.Height ?? raw.Boy;
  const depthRaw = raw.depth_cm ?? raw.product_depth_in_cm ?? raw.product_length_in_cm ?? raw.Depth ?? raw.Derinlik;

  const width = pdNumber(widthRaw, 0);
  const height = pdNumber(heightRaw, 0);
  const depth = pdNumber(depthRaw, 0);

  const missingWidth = width <= 0;
  const missingHeight = height <= 0;
  const missingDepth = depth <= 0;

  return {
    width_cm: missingWidth ? 10 : width,
    height_cm: missingHeight ? 15 : height,
    depth_cm: missingDepth ? 8 : depth,
    missing_dimensions: missingWidth || missingHeight || missingDepth,
    missing_dimension_fields: [
      missingWidth ? 'width_cm' : null,
      missingHeight ? 'height_cm' : null,
      missingDepth ? 'depth_cm' : null,
    ].filter(Boolean),
  };
}

export function skuOf(raw = {}) {
  return pdText(raw.sku || raw.SKU || raw.product_sku || raw.barcode || raw.Barcode || raw.product_barcodes || raw.product_name || raw.name);
}

export function collectShelves(planogram = {}) {
  const shelves = [];
  for (const aisle of planogram.aisles || []) {
    for (const module of aisle.modules || []) {
      const moduleType = pdText(module.module_type || module.type || 'regular_shelf');
      const moduleProductAllowed = !/room|zone|dispatch|receiving|column|wall/i.test(moduleType);
      for (const shelf of module.shelves || []) {
        const storage = pdText(shelf.allowed_storage_type || module.allowed_storage_type || 'AMBIENT').toUpperCase();
        const width = pdNumber(shelf.shelf_width_cm, pdNumber(module.module_width_cm, 100));
        const height = pdNumber(shelf.shelf_height_cm, 35);
        const depth = pdNumber(shelf.shelf_depth_cm, pdNumber(module.module_depth_cm, 50));
        const used = pdNumber(shelf.used_width_cm, (shelf.products || []).reduce((sum, p) => {
          const dims = getProductDimensions(p);
          const facing = Math.max(1, pdNumber(p.facing_count ?? p.facing, 1));
          return sum + dims.width_cm * facing * 1.1;
        }, 0));
        shelves.push({
          aisle_id: aisle.aisle_id,
          module_id: module.module_id,
          shelf_no: shelf.shelf_no,
          module_type: moduleType,
          storage,
          width_cm: width,
          height_cm: height,
          depth_cm: depth,
          used_width_cm: used,
          remaining_width_cm: Math.max(0, width - used),
          product_allowed: moduleProductAllowed,
          products_count: (shelf.products || []).length,
        });
      }
    }
  }
  return shelves;
}

export function classifyUnplacedProduct(product = {}, shelves = [], knownReason = '') {
  const sku = skuOf(product);
  const storage = inferStorageType(product);
  const dims = getProductDimensions(product);
  const facing = Math.max(1, pdNumber(product.facing_count ?? product.facing, 1));
  const requiredWidth = dims.width_cm * facing * 1.1;

  const productShelves = shelves.filter((s) => s.product_allowed);
  const storageShelves = productShelves.filter((s) => s.storage === storage);
  const heightOkShelves = storageShelves.filter((s) => dims.height_cm <= s.height_cm);
  const depthOkShelves = heightOkShelves.filter((s) => dims.depth_cm <= s.depth_cm);
  const capacityOkShelves = depthOkShelves.filter((s) => requiredWidth <= s.remaining_width_cm * 0.96);

  let reason = knownReason || '';
  let reasonCode = 'unknown';
  let severity = 'medium';
  let action = 'Ürünü manuel kontrol et; shelf/storage/capacity kısıtlarından hangisine takıldığını doğrula.';

  if (dims.missing_dimensions) {
    reasonCode = 'missing_dimensions';
    reason = `Ürün ölçüsü eksik: ${dims.missing_dimension_fields.join(', ')}`;
    severity = 'high';
    action = 'Master product datasında genişlik/yükseklik/derinlik alanlarını tamamla veya AI tahmini ölçü uygula.';
  } else if (!productShelves.length) {
    reasonCode = 'no_product_fixture';
    reason = 'Layout içinde ürün kabul eden fixture/raf bulunamadı.';
    severity = 'critical';
    action = 'Market rafı / gondol / Algida dolap gibi ürün alabilen fixture modülleri ekle.';
  } else if (!storageShelves.length) {
    reasonCode = 'no_matching_storage_shelf';
    reason = `${storage} storage için uygun raf/dolap yok.`;
    severity = 'high';
    action = `${storage} ürünler için uygun zone/fixture kapasitesi oluştur. Algida ve dolapları dekor değil ürün fixture modülü yap.`;
  } else if (!heightOkShelves.length) {
    reasonCode = 'product_too_tall';
    reason = `Ürün yüksekliği (${dims.height_cm} cm) uygun ${storage} raf yüksekliğini aşıyor.`;
    severity = 'high';
    action = 'Raf yüksekliğini artır veya ürünü daha yüksek modüle taşı.';
  } else if (!depthOkShelves.length) {
    reasonCode = 'product_too_deep';
    reason = `Ürün derinliği (${dims.depth_cm} cm) uygun ${storage} raf derinliğini aşıyor.`;
    severity = 'high';
    action = 'Raf/dolap derinliğini artır veya ürünü dolap/oda içine taşı.';
  } else if (!capacityOkShelves.length) {
    reasonCode = 'insufficient_capacity';
    reason = `Uygun ${storage} raf var ama kalan genişlik yetersiz. Gerekli: ${Math.round(requiredWidth)} cm.`;
    severity = 'medium';
    action = 'Facing azalt, raf sayısını artır, modül genişliğini büyüt veya düşük satışlı SKU’ları arkaya taşı.';
  } else if (knownReason) {
    reasonCode = String(knownReason).replace(/[^a-zA-Z0-9_]/g, '_').toLowerCase();
    reason = knownReason;
  }

  return {
    sku,
    product_name: pdText(product.product_name || product.name || product.product_name_local || 'Unnamed Product'),
    brand: pdText(product.brand || product.brand_name || ''),
    category_l1: pdText(product.category_l1 || product.frontend_category_local || ''),
    category_l2: pdText(product.category_l2 || product.frontend_subcategory_local || ''),
    storage_type: storage,
    width_cm: dims.width_cm,
    height_cm: dims.height_cm,
    depth_cm: dims.depth_cm,
    facing_count: facing,
    required_width_cm: Math.round(requiredWidth),
    reason_code: reasonCode,
    reason,
    severity,
    suggested_action: action,
  };
}

export function buildPlacementDiagnostics({ products = [], planogram = {}, unplacedProducts = [] } = {}) {
  const shelves = collectShelves(planogram);
  const unplacedMap = new Map();
  for (const u of unplacedProducts || []) {
    unplacedMap.set(skuOf(u), u);
  }

  const productBySku = new Map();
  const duplicateSkus = new Map();
  for (const p of products || []) {
    const sku = skuOf(p);
    if (!sku) continue;
    if (productBySku.has(sku)) duplicateSkus.set(sku, (duplicateSkus.get(sku) || 1) + 1);
    else productBySku.set(sku, p);
  }

  const enrichedUnplaced = [];
  for (const u of unplacedProducts || []) {
    const sku = skuOf(u);
    const raw = productBySku.get(sku) || u;
    enrichedUnplaced.push(classifyUnplacedProduct({ ...raw, ...u }, shelves, u.reason || u.constraint_reason || ''));
  }

  // When backend does not return all unplaced SKUs, infer missing ones by comparing placed products in shelves.
  const placedSkus = new Set();
  for (const shelf of (planogram.aisles || []).flatMap((a) => (a.modules || []).flatMap((m) => (m.shelves || [])))) {
    for (const p of shelf.products || []) placedSkus.add(skuOf(p));
  }
  for (const [sku, raw] of productBySku.entries()) {
    if (!placedSkus.has(sku) && !unplacedMap.has(sku)) {
      enrichedUnplaced.push(classifyUnplacedProduct(raw, shelves, 'not_returned_by_engine_but_not_placed'));
    }
  }

  const reasonCounts = enrichedUnplaced.reduce((acc, row) => {
    acc[row.reason_code] = (acc[row.reason_code] || 0) + 1;
    return acc;
  }, {});

  const storageCounts = enrichedUnplaced.reduce((acc, row) => {
    acc[row.storage_type] = (acc[row.storage_type] || 0) + 1;
    return acc;
  }, {});

  const capacityByStorage = shelves.reduce((acc, s) => {
    if (!acc[s.storage]) acc[s.storage] = { shelves: 0, used: 0, capacity: 0, remaining: 0 };
    acc[s.storage].shelves += 1;
    acc[s.storage].used += s.used_width_cm;
    acc[s.storage].capacity += s.width_cm;
    acc[s.storage].remaining += s.remaining_width_cm;
    return acc;
  }, {});

  const productAllowedShelves = shelves.filter((s) => s.product_allowed).length;
  const placedCount = placedSkus.size;
  const totalProducts = productBySku.size || products.length;

  return {
    summary: {
      total_products: totalProducts,
      placed_unique_skus: placedCount,
      unplaced_count: enrichedUnplaced.length,
      duplicate_sku_count: duplicateSkus.size,
      total_shelves: shelves.length,
      product_allowed_shelves: productAllowedShelves,
      placement_rate_pct: Math.round((placedCount / Math.max(1, totalProducts)) * 100),
    },
    reasonCounts,
    storageCounts,
    capacityByStorage,
    shelves,
    duplicateSkus: Array.from(duplicateSkus.entries()).map(([sku, count]) => ({ sku, count })),
    unplaced: enrichedUnplaced,
  };
}

export function toCsv(rows = []) {
  const headers = ['sku','product_name','brand','category_l1','category_l2','storage_type','width_cm','height_cm','depth_cm','facing_count','required_width_cm','reason_code','reason','severity','suggested_action'];
  const escape = (v) => `"${String(v ?? '').replaceAll('"', '""')}"`;
  return [headers.join(','), ...rows.map((r) => headers.map((h) => escape(r[h])).join(','))].join('\n');
}
