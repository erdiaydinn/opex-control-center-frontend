import { getAny, normalizeProduct, normalizeSalesValue, storageFromProduct, imageFromProduct, estimateEmoji } from './planogramAllocatorV2.js';

const readAsText = (file) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result || ''));
  reader.onerror = () => reject(reader.error || new Error('Dosya okunamadı'));
  reader.readAsText(file, 'utf-8');
});

function splitCsvLine(line, delimiter) {
  const out = [];
  let value = '';
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    const next = line[i + 1];
    if (ch === '"' && quoted && next === '"') { value += '"'; i += 1; continue; }
    if (ch === '"') { quoted = !quoted; continue; }
    if (ch === delimiter && !quoted) { out.push(value.trim()); value = ''; continue; }
    value += ch;
  }
  out.push(value.trim());
  return out;
}

function detectDelimiter(headerLine) {
  const candidates = [',', ';', '\t', '|'];
  return candidates.map((d) => ({ d, n: splitCsvLine(headerLine, d).length })).sort((a, b) => b.n - a.n)[0]?.d || ',';
}

function keyOf(row, names, fallback = '') {
  const lower = Object.fromEntries(Object.keys(row).map((k) => [String(k).toLowerCase().trim(), k]));
  for (const name of names) {
    const found = lower[String(name).toLowerCase().trim()];
    if (found !== undefined && row[found] !== undefined && row[found] !== '') return row[found];
  }
  return fallback;
}

function num(v, fallback = 0) {
  const n = Number(String(v ?? '').replace(',', '.').replace('%', '').trim());
  return Number.isFinite(n) ? n : fallback;
}

function storageFrom(row) {
  const raw = String(keyOf(row, ['storage_type', 'storage', 'Storage Type', 'allowed_storage_type'], '')).toUpperCase();
  const hay = `${keyOf(row, ['product_name', 'name', 'product_name_local'], '')} ${keyOf(row, ['category_l1', 'frontend_category_local', 'category'], '')} ${keyOf(row, ['category_l2', 'frontend_subcategory_local', 'subcategory'], '')}`.toLocaleUpperCase('tr-TR');
  if (raw.includes('FROZEN') || raw.includes('-18') || hay.includes('DONUK') || hay.includes('DONDURMA') || hay.includes('ALGIDA')) return 'FROZEN';
  if (raw.includes('CHILLED') || raw.includes('+4') || hay.includes('SOĞUK') || hay.includes('SÜT') || hay.includes('YOĞURT')) return 'CHILLED';
  return 'AMBIENT';
}

function emojiFor(row, storage) {
  const hay = `${keyOf(row, ['product_name', 'name'], '')} ${keyOf(row, ['category_l2', 'subcategory'], '')}`.toLocaleLowerCase('tr-TR');
  if (storage === 'FROZEN') return hay.includes('dondurma') || hay.includes('algida') ? '🍦' : '❄️';
  if (storage === 'CHILLED') return hay.includes('süt') ? '🥛' : '🧊';
  if (hay.includes('muz')) return '🍌';
  if (hay.includes('çikolata') || hay.includes('gofret')) return '🍫';
  if (hay.includes('bisküvi') || hay.includes('burçak')) return '🍪';
  if (hay.includes('cola') || hay.includes('kola')) return '🥤';
  if (hay.includes('patates')) return '🥔';
  return '▣';
}

export async function parseCsvProducts(file) {
  const text = (await readAsText(file)).replace(/^\uFEFF/, '');
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length);
  if (!lines.length) return [];
  const delimiter = detectDelimiter(lines[0]);
  const headers = splitCsvLine(lines[0], delimiter).map((h) => h.trim());
  const rows = lines.slice(1).map((line) => {
    const cells = splitCsvLine(line, delimiter);
    return Object.fromEntries(headers.map((h, i) => [h, cells[i] ?? '']));
  });

  return rows.map((row, idx) => normalizeProduct({
    ...row,
    sku: getAny(row, ['sku', 'SKU', 'barcode', 'Barcodes', 'product_barcodes'], `SKU-UP-${idx + 1}`),
    product_name: getAny(row, ['product_name', 'Product Name', 'name', 'product_name_local', 'pim_product_name_local'], ''),
    brand: getAny(row, ['brand', 'Brand', 'brand_name'], ''),
    category_l1: getAny(row, ['category_l1', 'Category L1', 'frontend_category_local', 'category'], 'Genel'),
    category_l2: getAny(row, ['category_l2', 'Category L2', 'frontend_subcategory_local', 'subcategory'], 'Genel'),
    storage_type: storageFromProduct(row),
    sales: normalizeSalesValue(getAny(row, ['sales_qty_7d', 'sales_7d', 'sales', 'Sales 7D', '% Orders', 'percent_orders'], 0), row),
    image_url: imageFromProduct(row),
    image: imageFromProduct(row) || estimateEmoji(row),
  }, idx));
}

export async function parseJsonLayout(file) {
  const text = await readAsText(file);
  const data = JSON.parse(text);
  if (Array.isArray(data)) return data;
  if (Array.isArray(data.objects)) return data.objects;
  if (Array.isArray(data.layout_objects)) return data.layout_objects;
  if (Array.isArray(data.aisles)) {
    return data.aisles.map((a, i) => ({
      id: String(a.aisle_id || a.id || `A${i + 1}`),
      label: String(a.aisle_id || a.label || `A${i + 1}`),
      type: 'corridor',
      zone: 'AMBIENT',
      x: Number(a.layout_position?.grid_x ?? 10 + (i % 3) * 34),
      y: Number(a.layout_position?.grid_y ?? 20 + Math.floor(i / 3) * 22),
      w: Math.max(8, Number(a.w || 30)),
      d: Math.max(4, Number(a.d || 8)),
      h: Number(a.h || 2.5),
      rotation: Number(a.layout_position?.rotation || 0),
      modules: Number(a.modules?.length || a.left_modules + a.right_modules || 6),
      shelves: Number((a.modules || []).reduce((sum, m) => sum + (m.shelves?.length || 0), 0) || 24),
      utilization: 70,
      changed: 0,
    }));
  }
  throw new Error('JSON layout içinde objects, layout_objects veya aisles bulunamadı.');
}

export function normalizeProductsForBackend(products) {
  return (products || []).map((p, idx) => {
    const x = normalizeProduct(p, idx);
    return {
      sku: x.sku,
      product_name: x.product_name || x.name,
      brand: x.brand,
      category_l1: x.category,
      category_l2: x.subcategory,
      storage_type: x.storage,
      width_cm: x.width,
      height_cm: x.height,
      depth_cm: x.product_depth_cm || 10,
      weight_kg: x.weight_kg || 0.2,
      sales_qty_7d: x.sales || 0,
      percent_stops: x.percent_stops || getAny(x, ['% Stops'], 0),
      image_url: x.image_url || '',
      rank: x.rank || getAny(x, ['Rank'], 0),
      abc: x.abc || getAny(x, ['ABC'], ''),
    };
  });
}
