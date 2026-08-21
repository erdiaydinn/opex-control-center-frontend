import { buildPlanogramAuthoringDocument, buildStoreScene, projectStoreScene3D } from "./planogramAuthoringModel.js";

const DEFAULT_MODULE_WIDTH_M = 1;
const DEFAULT_MODULE_DEPTH_M = 0.5;
const DEFAULT_SHELF_HEIGHT_M = 0.36;
const DEFAULT_AISLE_GAP_M = 1.4;
const MAX_VISIBLE_ROUTE_HOTSPOTS = 12;
const ROTATION_EPSILON_DEG = 1e-6;

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

function normalizedRotation(value) {
  const raw = ((number(value, 0) % 360) + 360) % 360;
  return Math.abs(raw - 360) <= ROTATION_EPSILON_DEG ? 0 : raw;
}

function normalizedOrthogonalRotation(value) {
  const raw = normalizedRotation(value);
  const candidates = [0, 90, 180, 270, 360];
  const closest = candidates.reduce((best, candidate) =>
    Math.abs(candidate - raw) < Math.abs(best - raw) ? candidate : best
  , 0);
  return closest === 360 ? 0 : closest;
}

function legacyOrthogonalFootprint(widthM, depthM, rotationDeg) {
  const rotation = normalizedOrthogonalRotation(rotationDeg);
  const swapsAxes = rotation === 90 || rotation === 270;
  return {
    rotationDeg: rotation,
    footprintWidthM: swapsAxes ? depthM : widthM,
    footprintDepthM: swapsAxes ? widthM : depthM,
  };
}

function arbitraryAngleFootprint(widthM, depthM, rotationDeg) {
  const rotation = normalizedRotation(rotationDeg);
  const radians = (rotation * Math.PI) / 180;
  const cos = Math.abs(Math.cos(radians));
  const sin = Math.abs(Math.sin(radians));
  return {
    rotationDeg: rotation,
    footprintWidthM: widthM * cos + depthM * sin,
    footprintDepthM: widthM * sin + depthM * cos,
  };
}

function spatialFootprint(widthM, depthM, rotationDeg, arbitraryAngles) {
  return arbitraryAngles
    ? arbitraryAngleFootprint(widthM, depthM, rotationDeg)
    : legacyOrthogonalFootprint(widthM, depthM, rotationDeg);
}

function moduleKey(aisleId, moduleId) {
  const moduleText = text(moduleId);
  if (moduleText.includes("::")) return moduleText;
  return `${text(aisleId)}::${moduleText}`;
}

function shelfGeometry(module) {
  const first = Array.isArray(module?.shelves) ? module.shelves[0] || {} : {};
  const shelfCount = Math.max(1, Array.isArray(module?.shelves) ? module.shelves.length : 1);
  return {
    widthM: positive(
      module?.width_m,
      positive(module?.module_width_cm, 0) / 100 ||
        positive(module?.width_cm, 0) / 100 ||
        positive(first?.shelf_width_cm, DEFAULT_MODULE_WIDTH_M * 100) / 100
    ),
    depthM: positive(
      module?.depth_m,
      positive(module?.module_depth_cm, 0) / 100 ||
        positive(module?.depth_cm, 0) / 100 ||
        positive(first?.shelf_depth_cm, DEFAULT_MODULE_DEPTH_M * 100) / 100
    ),
    heightM: positive(
      module?.height_m,
      positive(module?.module_height_cm, 0) / 100 ||
        positive(module?.height_cm, 0) / 100 ||
        shelfCount * DEFAULT_SHELF_HEIGHT_M
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

function architectureProfile(candidate) {
  const architecture = candidate?.store_dna?.architecture;
  if (!architecture || typeof architecture !== "object" || Array.isArray(architecture)) return null;

  const schemaVersion = Math.round(number(architecture?.schema_version, 0));
  const coordinateSystem = text(architecture?.coordinate_system);
  const validCoordinateSystem = schemaVersion === 1
    ? coordinateSystem === "cartesian_m"
    : schemaVersion === 2 && ["cartesian_m", "cartesian_m_centered_rect"].includes(coordinateSystem);

  if (
    !validCoordinateSystem ||
    positive(architecture?.floor_width_m, 0) <= 0 ||
    positive(architecture?.floor_depth_m, 0) <= 0
  ) {
    return null;
  }

  return {
    architecture,
    schemaVersion,
    arbitraryAngles: schemaVersion === 2,
    previewOnly: schemaVersion === 2,
    spatialContract: schemaVersion === 2
      ? "store-architecture-v2-oriented-polygons"
      : "store-architecture-v1",
  };
}

function resolveSpatialPlacement(raw, widthM, depthM, footprint, arbitraryAngles, fallback = null) {
  const hasXY = hasFiniteCoordinate(raw?.x_m) && hasFiniteCoordinate(raw?.y_m);
  const hasCenter = hasFiniteCoordinate(raw?.center_x_m) && hasFiniteCoordinate(raw?.center_y_m);

  if (arbitraryAngles && hasCenter) {
    const centerXM = number(raw?.center_x_m);
    const centerYM = number(raw?.center_y_m);
    return {
      hasCoordinates: true,
      xM: centerXM - footprint.footprintWidthM / 2,
      yM: centerYM - footprint.footprintDepthM / 2,
      centerXM,
      centerYM,
    };
  }

  if (hasXY) {
    const sourceXM = number(raw?.x_m);
    const sourceYM = number(raw?.y_m);
    if (arbitraryAngles) {
      const centerXM = sourceXM + widthM / 2;
      const centerYM = sourceYM + depthM / 2;
      return {
        hasCoordinates: true,
        xM: centerXM - footprint.footprintWidthM / 2,
        yM: centerYM - footprint.footprintDepthM / 2,
        centerXM,
        centerYM,
      };
    }
    return {
      hasCoordinates: true,
      xM: sourceXM,
      yM: sourceYM,
      centerXM: sourceXM + footprint.footprintWidthM / 2,
      centerYM: sourceYM + footprint.footprintDepthM / 2,
    };
  }

  const fallbackXM = fallback?.xM ?? 0;
  const fallbackYM = fallback?.yM ?? 0;
  if (arbitraryAngles) {
    const centerXM = fallbackXM + widthM / 2;
    const centerYM = fallbackYM + depthM / 2;
    return {
      hasCoordinates: false,
      xM: centerXM - footprint.footprintWidthM / 2,
      yM: centerYM - footprint.footprintDepthM / 2,
      centerXM,
      centerYM,
    };
  }
  return {
    hasCoordinates: false,
    xM: fallbackXM,
    yM: fallbackYM,
    centerXM: fallbackXM + footprint.footprintWidthM / 2,
    centerYM: fallbackYM + footprint.footprintDepthM / 2,
  };
}

function architectureElement(element, profile) {
  const widthM = positive(element?.width_m, 0);
  const depthM = positive(element?.depth_m, 0);
  const footprint = spatialFootprint(widthM, depthM, element?.rotation_deg, profile.arbitraryAngles);
  const placement = resolveSpatialPlacement(
    element,
    widthM,
    depthM,
    footprint,
    profile.arbitraryAngles
  );
  return {
    id: text(element?.element_id),
    type: text(element?.element_type).toLowerCase(),
    widthM,
    depthM,
    ...footprint,
    ...placement,
    clearanceM: positive(element?.clearance_m, 0),
    coordinateAuthority: "measured",
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

function normalizeRoutePath(path) {
  if (!Array.isArray(path)) return [];
  return path.slice(0, 160).flatMap((point) => {
    if (!Array.isArray(point) || point.length < 2) return [];
    const xM = number(point[0], Number.NaN);
    const yM = number(point[1], Number.NaN);
    return Number.isFinite(xM) && Number.isFinite(yM) ? [[xM, yM]] : [];
  });
}

function routeProjection(rawRoute) {
  if (!rawRoute || typeof rawRoute !== "object") return null;

  if (rawRoute?.contract === "architecture-polygon-astar-v2") {
    return {
      available: Boolean(rawRoute?.available),
      metric: "point_to_point_walk_m",
      value: number(rawRoute?.distance_m, 0),
      basis: text(rawRoute?.contract),
      previewOnly: true,
      unreachableModuleIds: [],
      pickerEntryM: null,
      moduleDistancesM: {},
      hotspots: rawRoute?.available && Array.isArray(rawRoute?.path_m)
        ? [{
            rank: 1,
            moduleId: "architecture-v2-target",
            distanceM: number(rawRoute?.distance_m, 0),
            salesWeight: 0,
            placedProductCount: 0,
            weightedCost: number(rawRoute?.distance_m, 0),
            pathM: normalizeRoutePath(rawRoute?.path_m),
          }]
        : [],
    };
  }

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
    previewOnly: false,
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
  const profile = architectureProfile(candidate);
  const architecture = profile?.architecture || null;
  const arbitraryAngles = Boolean(profile?.arbitraryAngles);
  const modules = [];
  let measuredCoordinateCount = 0;

  for (const [aisleIndex, aisle] of planogram.aisles.entries()) {
    const aisleId = text(aisle?.aisle_id || `A${aisleIndex + 1}`);
    for (const [moduleIndex, outputModule] of (aisle?.modules || []).entries()) {
      const moduleId = text(outputModule?.module_id || moduleIndex + 1);
      const key = moduleKey(aisleId, moduleId);
      const sourceModule = inputModules.get(key) || {};
      const merged = { ...sourceModule, ...outputModule };
      for (const field of ["x_m", "y_m", "center_x_m", "center_y_m", "width_m", "depth_m", "rotation_deg"]) {
        if ((merged[field] === null || merged[field] === undefined || merged[field] === "") && sourceModule[field] != null && sourceModule[field] !== "") {
          merged[field] = sourceModule[field];
        }
      }
      const geometry = shelfGeometry(merged);
      const footprint = spatialFootprint(
        geometry.widthM,
        geometry.depthM,
        merged?.rotation_deg,
        arbitraryAngles
      );
      const fallback = inferTopologyPosition(
        aisleIndex,
        moduleIndex,
        footprint.footprintWidthM,
        footprint.footprintDepthM
      );
      const placement = resolveSpatialPlacement(
        merged,
        geometry.widthM,
        geometry.depthM,
        footprint,
        arbitraryAngles,
        fallback
      );
      const summary = productSummary(outputModule?.shelves || []);
      if (placement.hasCoordinates) measuredCoordinateCount += 1;

      modules.push({
        key,
        aisleId,
        moduleId,
        side: text(merged?.side).toUpperCase(),
        fixtureType: text(merged?.fixture_class ?? merged?.fixture_type ?? merged?.module_type ?? merged?.storage_type).toUpperCase(),
        widthM: geometry.widthM,
        depthM: geometry.depthM,
        heightM: geometry.heightM,
        ...footprint,
        ...placement,
        coordinateAuthority: placement.hasCoordinates ? "measured" : "topology",
        shelfCount: Array.isArray(outputModule?.shelves) ? outputModule.shelves.length : 0,
        shelves: outputModule?.shelves || [],
        ...summary,
      });
    }
  }

  if (!modules.length) return null;

  const storeScene = profile
    ? buildStoreScene(candidate, buildPlanogramAuthoringDocument(candidate))
    : null;
  const storeScene3D = storeScene ? projectStoreScene3D(storeScene) : null;
  const elements = profile
    ? (storeScene3D?.nodes || []).map((node) => architectureElement({
        element_id: node.nodeId,
        element_type: node.nodeType,
        center_x_m: node.geometry.centerXM,
        center_y_m: node.geometry.centerYM,
        width_m: node.geometry.widthM,
        depth_m: node.geometry.depthM,
        rotation_deg: node.geometry.rotationDeg,
        clearance_m: node.metadata?.clearanceM ?? 0,
      }, profile)).filter((item) => item.widthM > 0 && item.depthM > 0)
    : [];

  const inferredMaxX = Math.max(...modules.map((module) => module.xM + module.footprintWidthM), 1) + 0.5;
  const inferredMaxY = Math.max(...modules.map((module) => module.yM + module.footprintDepthM), 1) + 0.5;
  const floorWidthM = profile ? positive(architecture?.floor_width_m, inferredMaxX) : inferredMaxX;
  const floorDepthM = profile ? positive(architecture?.floor_depth_m, inferredMaxY) : inferredMaxY;
  const route = routeProjection(
    engineResult?.architecture_route_objective_v2 ||
    engineResult?.architecture_route_objective ||
    null
  );
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
  const fullyMeasured = Boolean(profile) && measuredCoordinateCount === enrichedModules.length;
  const geometryAuthority = fullyMeasured
    ? (profile.previewOnly ? "measured-preview-v2" : "measured")
    : "topology-preview";

  return {
    contract: "planogram-digital-twin-v1",
    spatialContract: profile?.spatialContract || "topology-preview",
    architectureSchemaVersion: profile?.schemaVersion || null,
    spatialPreviewOnly: Boolean(profile?.previewOnly),
    arbitraryAngleGeometry: arbitraryAngles,
    geometryAuthority,
    architectureSource: profile ? text(architecture?.source) : "",
    architectureSourceRef: profile ? text(architecture?.source_ref) : "",
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
