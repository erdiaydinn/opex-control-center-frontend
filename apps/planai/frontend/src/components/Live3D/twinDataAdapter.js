import * as THREE from 'three';

const ZONE_COLORS = {
  AMBIENT: '#df1067',
  CHILLED: '#18c7df',
  FROZEN: '#7b61ff',
  DISPATCH: '#17a66a',
  INBOUND: '#f5b900',
  FACILITY: '#657085',
  STRUCTURE: '#10131a',
  SAFETY: '#e84a4a',
  EQUIPMENT: '#64748b',
};

const ZONE_NAMES_TR = {
  AMBIENT: 'Kuru Alan',
  CHILLED: '+4 Soğuk',
  FROZEN: '-18 Donuk',
  DISPATCH: 'Sevkiyat',
  INBOUND: 'Mal Kabul',
  FACILITY: 'Tesis',
  STRUCTURE: 'Yapı',
  SAFETY: 'Güvenlik',
  EQUIPMENT: 'Ekipman',
};

const FLOOR_HEIGHT = 6.2;

export function zoneColor(zone) {
  return ZONE_COLORS[String(zone || 'AMBIENT').toUpperCase()] || '#df1067';
}

export function zoneName(zone) {
  return ZONE_NAMES_TR[String(zone || 'AMBIENT').toUpperCase()] || zone || 'Alan';
}

function deterministicRatio(seedText) {
  const raw = String(seedText || 'PLONAGRAM');
  let hash = 0;
  for (let i = 0; i < raw.length; i += 1) hash = (hash * 31 + raw.charCodeAt(i)) % 997;
  return hash / 997;
}

function getFloor(o) {
  return Number(o?.floor ?? o?.floor_level ?? o?.level ?? 0) || 0;
}

export function objectToWorld(o) {
  const x = (Number(o.x || 0) - 70) * 1.15;
  const z = (Number(o.y || 0) - 50) * 1.1;
  const w = Math.max(2, Number(o.w || 8) * 1.05);
  const d = Math.max(2, Number(o.d || 4) * 1.05);
  const h = Math.max(0.4, Number(o.h || 2.5) * 4);
  const y = h / 2;
  return { x, y, z, w, d, h, rotation: THREE.MathUtils.degToRad(Number(o.rotation || 0)) };
}

function buildFloors(objects) {
  const explicitFloors = new Set((objects || []).map((o) => getFloor(o)));
  explicitFloors.add(0);
  // Gerçek Store DNA'da kat yoksa hayali asma kat ekleme.
  return Array.from(explicitFloors).sort((a, b) => a - b).map((level) => ({
    level,
    name: level === 0 ? 'Zemin Kat' : level === 1 ? 'Asma Kat' : `${level}. Kat`,
    height: level * FLOOR_HEIGHT,
    width: level === 0 ? 170 : 96,
    depth: level === 0 ? 122 : 78,
  }));
}

function buildWorkers() {
  return [
    { id: 'picker-01', name: 'Mehmet', floor: 0, path: [[-44, .5, 10], [-34, .5, 2], [-22, .5, 9], [-14, .5, 2]], activity: 'picking', speed: .032 },
    { id: 'picker-02', name: 'Ayşe', floor: 0, path: [[18, .5, -30], [30, .5, -22], [42, .5, -16], [50, .5, -5]], activity: 'carrying', speed: .026 },
    { id: 'picker-03', name: 'Fatma', floor: 1, path: [[-28, .5, -20], [-16, .5, -15], [-6, .5, -9], [8, .5, -16]], activity: 'picking', speed: .029 },
    { id: 'picker-04', name: 'Ali', floor: 1, path: [[12, .5, 18], [22, .5, 11], [30, .5, 4], [16, .5, -4]], activity: 'walking', speed: .024 },
  ];
}

function buildSyntheticMezzanineFixtures() {
  return [
    {
      id: 'MEZZ-A1', label: 'Asma Kat Raf A1', type: 'steel_rack', zone: 'AMBIENT', floor: 1,
      world: { x: -28, y: 3.1, z: -18, w: 18, d: 5.2, h: 5.4, rotation: 0 },
      color: zoneColor('AMBIENT'), zoneName: zoneName('AMBIENT'), isRack: true, isRoom: false, isColumn: false, utilization: 68, modules: 5, shelves: 5, changed: 8,
    },
    {
      id: 'MEZZ-B1', label: 'Asma Kat +4 Raf', type: 'steel_rack', zone: 'CHILLED', floor: 1,
      world: { x: 10, y: 3.1, z: -16, w: 15, d: 5.2, h: 5.1, rotation: 0 },
      color: zoneColor('CHILLED'), zoneName: zoneName('CHILLED'), isRack: true, isRoom: false, isColumn: false, utilization: 71, modules: 4, shelves: 5, changed: 5,
    },
  ];
}

export function buildTwinModel(objects = [], products = []) {
  const floor = { width: 170, depth: 122 };
  const cleanedObjects = (objects || []).filter(Boolean);
  const byId = Object.fromEntries(cleanedObjects.map((o) => [String(o.id), o]));

  const fixtures = cleanedObjects.map((o) => {
    const world = objectToWorld(o);
    const zone = String(o.zone || 'AMBIENT').toUpperCase();
    const floorLevel = getFloor(o);
    const isRack = ['corridor', 'steel_rack', 'rack_module'].includes(o.type);
    const isRoom = ['chilled_room', 'frozen_room', 'receiving', 'dispatch', 'rest_area', 'wc', 'manager_desk'].includes(o.type);
    const isColumn = o.type === 'column';
    return {
      ...o,
      floor: floorLevel,
      world,
      zone,
      color: zoneColor(zone),
      zoneName: zoneName(zone),
      isRack,
      isRoom,
      isColumn,
      isFixture: !isRack && !isColumn,
      utilization: Number(o.utilization || 0),
      modules: Number(o.modules || 0),
      shelves: Number(o.shelves || 0),
      changed: Number(o.changed || 0),
    };
  });

  const enrichedFixtures = fixtures;

  const rackFixtures = enrichedFixtures.filter((f) => f.isRack);
  const roomFixtures = enrichedFixtures.filter((f) => f.isFixture && !f.isColumn);
  const columns = enrichedFixtures.filter((f) => f.isColumn);

  const productMarkers = (products || []).map((p, idx) => {
    const area = byId[String(p.aisle)] || byId.A || cleanedObjects[0] || { x: 50, y: 50, w: 10, d: 10, floor: 0 };
    const w = objectToWorld(area);
    const lane = ((idx % 7) - 3) * 0.8;
    const depth = ((Math.floor(idx / 7) % 4) - 1.5) * 0.9;
    const floorLevel = getFloor(p.floor !== undefined ? p : area);
    return {
      ...p,
      floor: floorLevel,
      world: [w.x + lane, Math.max(2, w.h + 0.8), w.z + depth],
      areaId: area.id,
      color: p.color || zoneColor(p.storage),
    };
  });

  const route = [
    [-70, 0.35, 42], [-52, 0.35, 30], [-36, 0.35, 16], [-10, 0.35, 10], [12, 0.35, 14], [36, 0.35, 8], [55, 0.35, -2], [62, 0.35, -24]
  ];

  const mezzanineRoute = [[-32, 0.5, -24], [-22, 0.5, -15], [-8, 0.5, -9], [8, 0.5, -14], [22, 0.5, -6]];

  const coldRoute = [
    [38, 0.42, -45], [54, 0.42, -35], [60, 0.42, -12], [50, 0.42, 10], [58, 0.42, 34]
  ];

  const alerts = [
    { id: 'refill-alert', type: 'refill', label: 'Refill gerekli', sub: 'Aisle A • Shelf 12', position: [-42, 2.4, 4], color: '#f5b900', floor: 0 },
    { id: 'congestion-alert', type: 'congestion', label: 'Yoğunluk', sub: 'Aisle D', position: [-25, 2.4, 18], color: '#e84a4a', floor: 0 },
    { id: 'cold-alert', type: 'cold', label: 'Soğuk zincir', sub: '+4 / -18 normal', position: [54, 2.4, -18], color: '#18c7df', floor: 0 },
    { id: 'mezz-alert', type: 'mezzanine', label: 'Asma kat kontrol', sub: 'Üst platform raf doluluğu %71', position: [8, 2.4, -14], color: '#7b61ff', floor: 1 },
  ];

  const floors = buildFloors(enrichedFixtures);
  const stairs = floors.length > 1 ? [{ id: 'stairs-main', position: [-20, 0, 10], label: 'Merdiven / Kat geçişi' }] : [];
  const workers = []; // Canlı picker katmanı veri gelince açılacak; şimdilik sahneyi karmaşıklaştırma.
  const routes = [
    { id: 'ground-route', floor: 0, points: route, color: '#df1067' },
    { id: 'mezz-route', floor: 1, points: mezzanineRoute, color: '#7b61ff' },
  ];
  const coldRoutes = [{ id: 'cold-route', floor: 0, points: coldRoute, color: '#18c7df' }];

  return { floor, floors, fixtures: enrichedFixtures, rackFixtures, roomFixtures, columns, productMarkers, route, coldRoute, routes, coldRoutes, alerts, stairs, workers };
}

export function cameraPresetTarget(preset, selectedFixture, selectedProduct, currentFloor = 0, floorHeight = FLOOR_HEIGHT) {
  const floorOffset = Number(currentFloor || 0) * floorHeight;
  if (selectedProduct?.world) {
    const productFloor = getFloor(selectedProduct);
    const offset = productFloor * floorHeight;
    return { position: [selectedProduct.world[0] + 28, 34 + offset, selectedProduct.world[2] + 34], target: [selectedProduct.world[0], 2 + offset, selectedProduct.world[2]] };
  }
  const presets = {
    overview: { position: [84, 70 + floorOffset, 86], target: [0, floorOffset, 0] },
    top: { position: [0, 112 + floorOffset, 0.1], target: [0, floorOffset, 0] },
    chilled: { position: [58, 46 + floorOffset, -50], target: [46, 2 + floorOffset, -30] },
    frozen: { position: [62, 48 + floorOffset, 54], target: [50, 2 + floorOffset, 30] },
    dispatch: { position: [82, 42 + floorOffset, 10], target: [48, 2 + floorOffset, -6] },
  };
  if (presets[preset]) return presets[preset];
  if (selectedFixture?.world) {
    const fixtureFloor = getFloor(selectedFixture);
    const offset = fixtureFloor * floorHeight;
    const w = selectedFixture.world;
    return { position: [w.x + 30, 36 + offset, w.z + 34], target: [w.x, 1.8 + offset, w.z] };
  }
  return presets.overview;
}
