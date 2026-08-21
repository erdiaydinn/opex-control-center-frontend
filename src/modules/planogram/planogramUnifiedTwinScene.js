function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function text(value) {
  return String(value ?? "").trim();
}

function fixtureCodeFrom(row) {
  const explicit = text(row?.fixtureCode ?? row?.fixture_code ?? row?.catalogFixtureCode);
  if (explicit) return explicit.toUpperCase();
  const fixtureId = text(row?.fixtureId ?? row?.fixture_id);
  if (!fixtureId) return "";
  const marker = fixtureId.lastIndexOf("@v");
  return (marker > 0 ? fixtureId.slice(0, marker) : fixtureId).toUpperCase();
}

function fixtureIdFrom(row) {
  return text(row?.fixtureId ?? row?.fixture_id);
}

function facingCount(product) {
  return Math.max(1, Math.min(40, Math.round(number(product?.facing_count ?? product?.facing, 1))));
}

function fixtureProducts(row) {
  const shelves = Array.isArray(row?.shelves) ? row.shelves : [];
  const products = [];
  for (let shelfIndex = 0; shelfIndex < shelves.length; shelfIndex += 1) {
    const shelfProducts = Array.isArray(shelves[shelfIndex]?.products) ? shelves[shelfIndex].products : [];
    for (let productIndex = 0; productIndex < shelfProducts.length; productIndex += 1) {
      const product = shelfProducts[productIndex];
      products.push(Object.freeze({
        shelfIndex,
        productIndex,
        sku: text(product?.sku ?? product?.SKU).toUpperCase(),
        facingCount: facingCount(product),
        widthM: number(product?.width_cm, 8) / 100,
        heightM: number(product?.height_cm, 18) / 100,
        depthM: number(product?.depth_cm, 7) / 100,
      }));
    }
  }
  return Object.freeze(products);
}

function authoredScene(model) {
  if (!model?.floor || !Array.isArray(model?.modules)) return null;
  return Object.freeze({
    contract: "eay.planogram.unified-twin-scene.v1",
    sourceKind: "authored_planogram",
    geometryAuthority: text(model.geometryAuthority || "topology-preview"),
    productionReleaseAllowed: false,
    floor: Object.freeze({
      widthM: number(model.floor.widthM),
      depthM: number(model.floor.depthM),
    }),
    architecture: Object.freeze((model.elements || []).map((row) => Object.freeze({
      id: text(row.id),
      type: text(row.type).toLowerCase(),
      centerXM: number(row.centerXM),
      centerYM: number(row.centerYM),
      widthM: number(row.widthM),
      depthM: number(row.depthM),
      rotationDeg: number(row.rotationDeg),
      clearanceM: number(row.clearanceM),
      coordinateAuthority: text(row.coordinateAuthority || model.geometryAuthority),
    }))),
    fixtures: Object.freeze(model.modules.map((row) => Object.freeze({
      id: text(row.key),
      fixtureId: fixtureIdFrom(row),
      fixtureCode: fixtureCodeFrom(row),
      fixtureType: text(row.fixtureType).toUpperCase(),
      side: text(row.side).toUpperCase(),
      centerXM: number(row.centerXM),
      centerYM: number(row.centerYM),
      widthM: number(row.widthM),
      depthM: number(row.depthM),
      heightM: number(row.heightM),
      rotationDeg: number(row.rotationDeg),
      shelfCount: Math.max(1, number(row.shelfCount, Array.isArray(row.shelves) ? row.shelves.length : 1)),
      coordinateAuthority: text(row.coordinateAuthority || model.geometryAuthority),
      moduleKey: text(row.key),
      products: fixtureProducts(row),
    }))),
    route: model.route || null,
    provenance: Object.freeze({
      architectureSourceRef: text(model.architectureSourceRef),
      sourceContract: text(model.contract),
    }),
  });
}

function scannedScene(architecture, recognizedFixtures = []) {
  if (!architecture || !Array.isArray(architecture.elements)) return null;
  return Object.freeze({
    contract: "eay.planogram.unified-twin-scene.v1",
    sourceKind: "reviewed_store_scan_preview",
    geometryAuthority: "reviewed_scan_preview_not_store_dna_authority",
    productionReleaseAllowed: false,
    floor: Object.freeze({
      widthM: number(architecture.floor_width_m),
      depthM: number(architecture.floor_depth_m),
    }),
    architecture: Object.freeze(architecture.elements.map((row) => Object.freeze({
      id: text(row.element_id),
      type: text(row.element_type).toLowerCase(),
      centerXM: number(row.center_x_m),
      centerYM: number(row.center_y_m),
      widthM: number(row.width_m),
      depthM: number(row.depth_m),
      rotationDeg: number(row.rotation_deg),
      clearanceM: number(row.clearance_m),
      coordinateAuthority: "reviewed_scan_measurement_preview",
    }))),
    fixtures: Object.freeze((recognizedFixtures || []).map((row, index) => Object.freeze({
      id: text(row.element_id || row.fixture_element_id || `scan-fixture-${index + 1}`),
      fixtureId: fixtureIdFrom(row),
      fixtureCode: fixtureCodeFrom(row),
      fixtureType: text(row.fixture_type || row.hinted_storage_type || "UNKNOWN").toUpperCase(),
      side: text(row.side).toUpperCase(),
      centerXM: number(row.center_x_m),
      centerYM: number(row.center_y_m),
      widthM: number(row.width_m),
      depthM: number(row.depth_m),
      heightM: number(row.height_m, 1.6),
      rotationDeg: number(row.rotation_deg),
      shelfCount: Math.max(1, number(row.shelf_count, 1)),
      coordinateAuthority: "reviewed_scan_measurement_preview",
      moduleKey: null,
      products: Object.freeze([]),
    }))),
    route: null,
    provenance: Object.freeze({
      architectureSourceRef: text(architecture.source_ref),
      sourceContract: text(architecture.contract || architecture.schema_version),
    }),
  });
}

export function buildPlanogramUnifiedTwinScene({ authoredModel = null, reviewedArchitecture = null, recognizedFixtures = [] } = {}) {
  const authored = authoredScene(authoredModel);
  const scanned = scannedScene(reviewedArchitecture, recognizedFixtures);
  if (authored) return authored;
  if (scanned) return scanned;
  return null;
}

export function compareUnifiedTwinGeometry(left, right, toleranceM = 0.02) {
  if (!left || !right) return Object.freeze({ comparable: false, withinTolerance: false, deltas: [] });
  const leftById = new Map((left.architecture || []).map((row) => [row.id, row]));
  const deltas = [];
  for (const row of right.architecture || []) {
    const base = leftById.get(row.id);
    if (!base) continue;
    const centerDeltaM = Math.hypot(base.centerXM - row.centerXM, base.centerYM - row.centerYM);
    const sizeDeltaM = Math.max(Math.abs(base.widthM - row.widthM), Math.abs(base.depthM - row.depthM));
    const rotationDeltaDeg = Math.abs(base.rotationDeg - row.rotationDeg);
    deltas.push(Object.freeze({ id: row.id, centerDeltaM, sizeDeltaM, rotationDeltaDeg }));
  }
  const comparable = deltas.length > 0;
  const withinTolerance = comparable && deltas.every((row) => row.centerDeltaM <= toleranceM && row.sizeDeltaM <= toleranceM);
  return Object.freeze({ comparable, withinTolerance, toleranceM, deltas: Object.freeze(deltas) });
}
