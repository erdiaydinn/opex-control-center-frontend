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

export function zoneColor(zone) {
  return ZONE_COLORS[String(zone || 'AMBIENT').toUpperCase()] || '#df1067';
}

export function zoneName(zone) {
  return ZONE_NAMES_TR[String(zone || 'AMBIENT').toUpperCase()] || zone || 'Alan';
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

export function buildTwinModel(objects = [], products = []) {
  const floor = { width: 170, depth: 122 };
  const cleanedObjects = (objects || []).filter(Boolean);
  const byId = Object.fromEntries(cleanedObjects.map((o) => [String(o.id), o]));

  const fixtures = cleanedObjects.map((o) => {
    const world = objectToWorld(o);
    const zone = String(o.zone || 'AMBIENT').toUpperCase();
    const isRack = ['corridor', 'steel_rack', 'rack_module'].includes(o.type);
    const isRoom = ['chilled_room', 'frozen_room', 'receiving', 'dispatch', 'rest_area', 'wc', 'manager_desk'].includes(o.type);
    const isColumn = o.type === 'column';
    return {
      ...o,
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

  const rackFixtures = fixtures.filter((f) => f.isRack);
  const roomFixtures = fixtures.filter((f) => f.isFixture && !f.isColumn);
  const columns = fixtures.filter((f) => f.isColumn);

  const productMarkers = (products || []).map((p, idx) => {
    const area = byId[String(p.aisle)] || byId.A || cleanedObjects[0] || { x: 50, y: 50, w: 10, d: 10 };
    const w = objectToWorld(area);
    const lane = ((idx % 7) - 3) * 0.8;
    const depth = ((Math.floor(idx / 7) % 4) - 1.5) * 0.9;
    return {
      ...p,
      world: [w.x + lane, Math.max(2, w.h + 0.8), w.z + depth],
      areaId: area.id,
      color: p.color || zoneColor(p.storage),
    };
  });

  const route = [
    [-70, 0.35, 42], [-52, 0.35, 30], [-36, 0.35, 16], [-10, 0.35, 10], [12, 0.35, 14], [36, 0.35, 8], [55, 0.35, -2], [62, 0.35, -24]
  ];

  const coldRoute = [
    [38, 0.42, -45], [54, 0.42, -35], [60, 0.42, -12], [50, 0.42, 10], [58, 0.42, 34]
  ];

  const alerts = [
    { id: 'refill-alert', type: 'refill', label: 'Refill gerekli', sub: 'Aisle A • Shelf 12', position: [-42, 2.4, 4], color: '#f5b900' },
    { id: 'congestion-alert', type: 'congestion', label: 'Yoğunluk', sub: 'Aisle D', position: [-25, 2.4, 18], color: '#e84a4a' },
    { id: 'cold-alert', type: 'cold', label: 'Soğuk zincir', sub: '+4 / -18 normal', position: [54, 2.4, -18], color: '#18c7df' },
  ];

  return { floor, fixtures, rackFixtures, roomFixtures, columns, productMarkers, route, coldRoute, alerts };
}

export function cameraPresetTarget(preset, selectedFixture, selectedProduct) {
  if (selectedProduct?.world) {
    return { position: [selectedProduct.world[0] + 28, 34, selectedProduct.world[2] + 34], target: [selectedProduct.world[0], 2, selectedProduct.world[2]] };
  }
  if (selectedFixture?.world) {
    const w = selectedFixture.world;
    return { position: [w.x + 30, 36, w.z + 34], target: [w.x, 1.8, w.z] };
  }
  const presets = {
    overview: { position: [84, 70, 86], target: [0, 0, 0] },
    top: { position: [0, 112, 0.1], target: [0, 0, 0] },
    chilled: { position: [58, 46, -50], target: [46, 2, -30] },
    frozen: { position: [62, 48, 54], target: [50, 2, 30] },
    dispatch: { position: [82, 42, 10], target: [48, 2, -6] },
  };
  return presets[preset] || presets.overview;
}
