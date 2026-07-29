const baseProduct = (sku, name, brand, storage, category, width_cm = 8) => ({
  sku,
  name,
  product_name: name,
  brand,
  storage,
  storage_type: storage,
  category,
  category_l1: category,
  width_cm,
  height_cm: 20,
  depth_cm: 10,
  weight_kg: 0.5,
  facing: 1,
  facing_count: 1,
  sales_qty_7d: 20,
  image_url: '',
});

export const productsSeed = [
  baseProduct('SEED-001', 'Beypazarı Coala 6 x 200 ml', 'Beypazarı', 'AMBIENT', 'İçecek', 18),
  baseProduct('SEED-002', 'Beypazarı Maden Suyu 6 x 200 ml', 'Beypazarı', 'AMBIENT', 'İçecek', 18),
  baseProduct('SEED-003', 'Sütaş Ayran 1 L', 'Sütaş', 'CHILLED', 'Süt Ürünleri', 9),
  baseProduct('SEED-004', 'SuperFresh Mini Baguette', 'SuperFresh', 'FROZEN', 'Donuk', 12),
  baseProduct('SEED-005', 'Eti Burçak', 'Eti', 'AMBIENT', 'Atıştırmalık', 8),
  baseProduct('SEED-006', 'Finish Bulaşık Tableti', 'Finish', 'AMBIENT', 'Temizlik', 10),
];

export const products = productsSeed;

export const stores = [
  { code: 'ANKA', name: 'Anka Dark Store', city: 'Ankara', region: 'İç Anadolu', type: 'dark_store' },
  { code: 'ACIBADEM', name: 'Acıbadem Dark Store', city: 'İstanbul', region: 'Marmara', type: 'dark_store' },
  { code: 'GUVEN_FR', name: 'Güven Fulfillment', city: 'İstanbul', region: 'Marmara', type: 'fulfillment' },
];

export const initialObjects = [
  {
    id: 'A1',
    label: 'A1 Ambient raf koridoru',
    type: 'corridor',
    zone: 'AMBIENT',
    storage_type: 'AMBIENT',
    fixture_type: 'steel_rack',
    x: 8, y: 10, w: 28, d: 8, h: 2.1,
    modules: 6, shelves: 36, shelf_count: 6,
    width_cm: 600, depth_cm: 50, height_cm: 210,
  },
  {
    id: 'C1',
    label: 'C1 Soğuk raf koridoru',
    type: 'corridor',
    zone: 'CHILLED',
    storage_type: 'CHILLED',
    fixture_type: 'horizontal_fridge',
    x: 42, y: 10, w: 28, d: 8, h: 2.1,
    modules: 6, shelves: 30, shelf_count: 5,
    width_cm: 600, depth_cm: 55, height_cm: 210,
  },
  {
    id: 'F1',
    label: 'F1 Donuk raf koridoru',
    type: 'corridor',
    zone: 'FROZEN',
    storage_type: 'FROZEN',
    fixture_type: 'martek_frozen_minus18',
    x: 8, y: 28, w: 28, d: 8, h: 2.1,
    modules: 6, shelves: 24, shelf_count: 4,
    width_cm: 600, depth_cm: 60, height_cm: 210,
  },
  {
    id: 'COLUMN-01',
    label: 'Kolon 01',
    type: 'column',
    zone: 'STRUCTURE',
    x: 78, y: 12, w: 3, d: 3, h: 3,
    modules: 0, shelves: 0,
  },
];

export const objectCatalog = [
  { type: 'steel_rack', label: 'Standart raf modülü', zone: 'AMBIENT', w: 14, d: 6, h: 2.1, modules: 1, shelves: 6 },
  { type: 'chilled_rack', label: 'Soğuk raf modülü', zone: 'CHILLED', w: 14, d: 6, h: 2.1, modules: 1, shelves: 5, fixture_type: 'horizontal_fridge' },
  { type: 'frozen_rack', label: 'Donuk raf modülü', zone: 'FROZEN', w: 14, d: 6, h: 2.1, modules: 1, shelves: 5, fixture_type: 'martek_frozen_minus18' },
  { type: 'workbench', label: 'Hazırlık tezgâhı', zone: 'OPERATIONS', w: 12, d: 8, h: 1.1, modules: 0, shelves: 0 },
  { type: 'column', label: 'Kolon', zone: 'STRUCTURE', w: 3, d: 3, h: 2.8, modules: 0, shelves: 0 },
  { type: 'wall', label: 'Duvar', zone: 'STRUCTURE', w: 20, d: 1, h: 3, modules: 0, shelves: 0 },
];

export const fixtures = [
  { id: 'FIX-AMBIENT', name: 'Standart raf', class: 'AMBIENT', stores: ['ANKA', 'ACIBADEM'] },
  { id: 'FIX-CHILLED', name: 'Soğuk raf', class: 'CHILLED', stores: ['ANKA', 'ACIBADEM'] },
  { id: 'FIX-FROZEN', name: 'Donuk raf', class: 'FROZEN', stores: ['ANKA'] },
];

export const insights = [
  { title: 'Soğuk zincir kapasitesi izleniyor', impact: 'Kritik', tone: 'danger' },
  { title: 'Beypazarı çoklu paket profili doğrulanmalı', impact: 'Kontrol', tone: 'warning' },
  { title: '3D twin canonical fixture verisini kullanıyor', impact: 'Stabil', tone: 'success' },
];

export const storeMetrics = [
  { label: 'Yerleşen SKU', value: '1.016', tone: 'success' },
  { label: 'Açıkta SKU', value: '14', tone: 'warning' },
  { label: 'Kural ihlali', value: '0', tone: 'success' },
];

export const metrics = storeMetrics;

export const initialTasks = [
  {
    id: 'T-001',
    store: 'ANKA',
    title: 'CHILLED kapasitesi için fixture revizyonu',
    owner: 'Store Manager',
    priority: 'High',
    deadline: 'Bugün',
    status: 'Open',
    response: '',
  },
];

export function buildPlanogramFromObjects(objects = []) {
  return {
    store_code: 'ANKA',
    aisles: objects
      .filter((item) => item?.type === 'corridor' || Number(item?.modules) > 0)
      .map((item, index) => ({
        aisle_id: item.id || 'A' + (index + 1),
        zone_type: item.zone || item.storage_type || 'AMBIENT',
        modules: Array.from({ length: Math.max(1, Number(item.modules) || 1) }, (_, moduleIndex) => ({
          module_id: String(moduleIndex + 1),
          shelves: Array.from({ length: Math.max(1, Number(item.shelf_count || item.shelves) / Math.max(1, Number(item.modules) || 1) || 1) }, (_, shelfIndex) => ({
            shelf_no: shelfIndex + 1,
            products: [],
          })),
        })),
      })),
  };
}
