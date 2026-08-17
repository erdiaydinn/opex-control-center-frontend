const DEFAULT_MODULE_WIDTH_M = 1;
const DEFAULT_MODULE_DEPTH_M = 0.5;
const DEFAULT_SHELF_HEIGHT_M = 0.36;
const DEFAULT_AISLE_GAP_M = 1.4;
const MAX_VISIBLE_ROUTE_HOTSPOTS = 12;

function number(value, fallback = 0) {
  const parsed = Number(String(value ?? "").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : fallback;
}

function positive(value, fallback) {
  const parsed = number(value, 0);
  return parsed > 0 ? parsed : fallback;
}

function text(value) {
  return String(value ?? "").trim();
}

function hasFiniteCoordinate(value) {
  if (value === null || value === undefined || value === "") return false;
  return Number.isFinite(Number(value));
}

function normalizedOrthogonalRotation(value) {
  const raw = ((number(value, 0) % 360) + 360) % 360;
  const candidates = [0, 90, 180, 270, 360];
  const closest = candidates.reduce((best, candidate) =>
    Math.abs(candidate - raw) < Math.abs(best - raw) ? candidate : best
  , 0);
  return closest === 360 ? 0 : closest;
}

function orthogonalFootprint(widthM, depthM, rotationDeg) {
  const rotation = normalizedOrthogonalRotation(rotationDeg);
  const swapsAxes = rotation === 90 || rotation === 270;
  return {
    rotationDeg: rotation,
    footprintWidthM: swapsAxes ? depthM : widthM,
    footprintDepthM: swapsAxes ? widthM : depthM,
  };
}

function moduleKey(aisleId, moduleId) {
  const moduleText = text(moduleId);
  if (moduleText.includes("::")) return moduleText;
  return `${text(aisleId)}::${moduleText}`;
}

function shelfGeometry(module) {
  const first = Array.isArray(module?.shelves) ? module.shelves[0] || {} : {};
  return {
    widthM: positive(
      module?.width_m,
      positive(module?.width_cm, 0) / 100 || positive(first?.shelf_width_cm, DEFAULT_MODULE_WIDTH_M * 100) / 100
    ),
    depthM: positive(
      module?.depth_m,
      positive(module?.depth_cm, 0) / 100 || positive(first?.shelf_depth_cm, DEFAULT_MODULE_DEPTH_M * 100) / 100
    ),
  };
}

function buildInputModuleIndex(candidate) {
  const index = new Map();
  for (const aisle of candidate?.layout?.aisles || []) {
    for (const module of aisle?.modules || []) {
      index.set(moduleKey(aisle?.aisle_id, module?.module_id), module);
    }
  }
  return index;
}

function architectureElement(element) {
  const widthM = positive(element?.width_m, 0);
  const depthM = positive(element?.depth_m, 0);
  const footprint = orthogonalFootprint(widthM, depthM, element?.rotation_deg);
  const xM = number(element?.x_m);
  const yM = number(element?.y_m);
  return {
    id: text(element?.element_id),
    type: text(element?.element_type).toLowerCase(),
    xM,
    yM,
    widthM,
    depthM,
    ...footprint,
    centerXM: xM + footprint.footprintWidthM / 2,
    centerYM: yM + footprint.footprintDepthM / 2,
    clearanceM: positive(element?.clearance_m, 0),
  };
}

function inferTopologyPosition(aisleIndex, moduleIndex, moduleWidth, moduleDepth) {
  const aisleStride = Math.max(DEFAULT_AISLE_GAP_M + moduleDepth * 2, 2.4);
  const sideOffset = moduleIndex % 2 === 0 ? moduleDepth + DEFAULT_AISLE_GAP_M : 0;
  const sequence = Math.floor(moduleIndex / 2);
  return {
    xM: sequence * (moduleWidth + 0.18) + 0.5,
    yM: aisleIndex * aisleStride + sideOffset + 0.5,
  };
}

function productSummary(shelves) {
  let productCount = 0;
  let facingCount = 0;
  let sales7d = 0;
  const products = [];

  for (const shelf of shelves || []) {
    const rows = Array.isArray(shelf?.products) ? shelf.products : [];
    for (const product of rows) {
      const facing = Math.max(1, Math.round(number(product?.facing_count ?? product?.facing, 1)));
      const sales = number(
        product?.sales_qty_7d ?? product?.sales_7d ?? product?.qty_7d ?? product?.weekly_sales,
        0
      );
      productCount += 1;
      facingCount += facing;
      sales7d += Math.max(0, sales);
      products.push({
        sku: text(product?.sku ?? product?.SKU),
        name: text(product?.product_name ?? product?.name),
        brand: text(product?.brand ?? product?.brand_name),
        storageType: text(product?.temperature_zone ?? product?.storage_type).toUpperCase(),
        widthCm: positive(product?.width_cm, 0),
        heightCm: positive(product?.height_cm, 0),
        depthCm: positive(product?.depth_cm, 0),
        facing,
        sales7d: Math.max(0, sales),
      });
    }
  }

  return { productCount, facingCount, sales7d, products };
}

function measuredArchitecture(candidate) {
  const architecture = candidate?.store_dna?.architecture;
  return Boolean(
    architecture &&
      typeof architecture === "object" &&
      !Array.isArray(architecture) &&
      number(architecture?.schema_version) === 1 &&
      text(architecture?.coordinate_system) === "cartesian_m" &&
      positive(architecture?.floor_width_m, 0) > 0 &&
      positive(architecture?.floor_depth_m, 0) > 0
  );
}

function normalizeRoutePath(path) {
  if (!Array.isArray(path)) return [];
  return path.slice(0, 64).flatMap((point) => {
    if (!Array.isArray(point) || point.length < 2) return [];
    const xM = number(point[0], Number.NaN);
    const yM = number(point[1], Number.NaN);
    return Number.isFinite(xM) && Number.isFinite(yM) ? [[xM, yM]] : [];
  });
}

function routeProjection(rawRoute) {
  if (!rawRoute || typeof rawRoute !== "object") return null;
  const moduleDistances = rawRoute?.module_distances_m && typeof rawRoute.module_distances_m === "object"
    ? Object.fromEntries(Object.entries(rawRoute.module_distances_m).map(([key, value]) => [text(key), number(value, 0)]))
    : {};
  const hotspots = Array.isArray(rawRoute?.route_hotspots)
    ? rawRoute.route_hotspots.slice(0, MAX_VISIBLE_ROUTE_HOTSPOTS).map((row, index) => ({
        rank: index + 1,
        moduleId: text(row?.module_id),
        distanceM: number(row?.distance_m, 0),
        salesWeight: number(row?.sales_weight, 0),
        placedProductCount: Math.max(0, Math.round(number(row?.placed_product_count, 0))),
        weightedCost: number(row?.weighted_cost, 0),
        pathM: normalizeRoutePath(row?.path_m),
      }))
    : [];
  const pickerEntry = Array.isArray(rawRoute?.picker_entry_m) && rawRoute.picker_entry_m.length >= 2
    ? [number(rawRoute.picker_entry_m[0]), number(rawRoute.picker_entry_m[1])]
    : null;

  return {
    available: Boolean(rawRoute?.available),
    metric: text(rawRoute?.metric),
    value: number(rawRoute?.value, 0),
    basis: text(rawRoute?.basis),
    unreachableModuleIds: Array.isArray(rawRoute?.unreachable_module_ids)
      ? rawRoute.unreachable_module_ids.map(text)
      : [],
    pickerEntryM: pickerEntry,
    moduleDistancesM: moduleDistances,
    hotspots,
  };
}

export function buildPlanogramDigitalTwinModel(engineResult, candidate) {
  const planogram = engineResult?.planogram;
  if (!planogram || !Array.isArray(planogram?.aisles)) return null;

  const inputModules = buildInputModuleIndex(candidate);
  const architecture = candidate?.store_dna?.architecture || null;
  const hasMeasuredArchitecture = measuredArchitecture(candidate);
  const modules = [];
  let measuredCoordinateCount = 0;

  for (const [aisleIndex, aisle] of planogram.aisles.entries()) {
    const aisleId = text(aisle?.aisle_id || `A${aisleIndex + 1}`);
    for (const [moduleIndex, outputModule] of (aisle?.modules || []).entries()) {
      const moduleId = text(outputModule?.module_id || moduleIndex + 1);
      const key = moduleKey(aisleId, moduleId);
      const sourceModule = inputModules.get(key) || {};
      const merged = { ...sourceModule, ...outputModule };
      for (const field of ["x_m", "y_m", "width_m", "depth_m", "rotation_deg"]) {
        if ((merged[field] === null || merged[field] === undefined || merged[field] === "") && sourceModule[field] != null && sourceModule[field] !== "") {
          merged[field] = sourceModule[field];
        }
      }
      const geometry = shelfGeometry(merged);
      const rotation = orthogonalFootprint(geometry.widthM, geometry.depthM, merged?.rotation_deg);
      const hasCoordinates = hasFiniteCoordinate(merged?.x_m) && hasFiniteCoordinate(merged?.y_m);
      const fallback = inferTopologyPosition(aisleIndex, moduleIndex, rotation.footprintWidthM, rotation.footprintDepthM);
      const xM = hasCoordinates ? number(merged?.x_m) : fallback.xM;
      const yM = hasCoordinates ? number(merged?.y_m) : fallback.yM;
      const summary = productSummary(outputModule?.shelves || []);
      if (hasCoordinates) measuredCoordinateCount += 1;

      modules.push({
        key,
        aisleId,
        moduleId,
        side: text(merged?.side).toUpperCase(),
        fixtureType: text(merged?.fixture_class ?? merged?.fixture_type ?? merged?.module_type ?? merged?.storage_type).toUpperCase(),
        xM,
        yM,
        widthM: geometry.widthM,
        depthM: geometry.depthM,
        ...rotation,
        centerXM: xM + rotation.footprintWidthM / 2,
        centerYM: yM + rotation.footprintDepthM / 2,
        coordinateAuthority: hasCoordinates ? "measured" : "topology",
        shelfCount: Array.isArray(outputModule?.shelves) ? outputModule.shelves.length : 0,
        shelves: outputModule?.shelves || [],
        ...summary,
      });
    }
  }

  if (!modules.length) return null;

  const elements = hasMeasuredArchitecture
    ? (architecture?.elements || []).map(architectureElement).filter((item) => item.widthM > 0 && item.depthM > 0)
    : [];

  const inferredMaxX = Math.max(...modules.map((module) => module.xM + module.footprintWidthM), 1) + 0.5;
  const inferredMaxY = Math.max(...modules.map((module) => module.yM + module.footprintDepthM), 1) + 0.5;
  const floorWidthM = hasMeasuredArchitecture ? positive(architecture?.floor_width_m, inferredMaxX) : inferredMaxX;
  const floorDepthM = hasMeasuredArchitecture ? positive(architecture?.floor_depth_m, inferredMaxY) : inferredMaxY;
  const route = routeProjection(engineResult?.architecture_route_objective || null);
  const hotspotByModule = new Map((route?.hotspots || []).map((row) => [row.moduleId, row]));
  const enrichedModules = modules.map((module) => ({
    ...module,
    routeDistanceM: route?.moduleDistancesM?.[module.key] ?? null,
    routeHotspot: hotspotByModule.get(module.key) || null,
  }));

  const placedProductCount = enrichedModules.reduce((sum, module) => sum + module.productCount, 0);
  const facingCount = enrichedModules.reduce((sum, module) => sum + module.facingCount, 0);
  const sales7d = enrichedModules.reduce((sum, module) => sum + module.sales7d, 0);
  const measuredPct = enrichedModules.length ? (measuredCoordinateCount * 100) / enrichedModules.length : 0;

  return {
    contract: "planogram-digital-twin-v1",
    geometryAuthority: hasMeasuredArchitecture && measuredCoordinateCount === enrichedModules.length ? "measured" : "topology-preview",
    architectureSource: hasMeasuredArchitecture ? text(architecture?.source) : "",
    architectureSourceRef: hasMeasuredArchitecture ? text(architecture?.source_ref) : "",
    floor: { widthM: floorWidthM, depthM: floorDepthM },
    elements,
    modules: enrichedModules,
    stats: {
      moduleCount: enrichedModules.length,
      measuredCoordinateCount,
      measuredCoordinatePct: Math.round(measuredPct * 100) / 100,
      placedProductCount,
      facingCount,
      sales7d: Math.round(sales7d * 100) / 100,
    },
    route,
  };
}

export const PLANOGRAM_DIGITAL_TWIN_LIMITS = Object.freeze({
  maxProductInstances3d: 1500,
  maxVisibleRouteHotspots: MAX_VISIBLE_ROUTE_HOTSPOTS,
  fallbackShelfHeightM: DEFAULT_SHELF_HEIGHT_M,
});
