const EPSILON = 1e-6;

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function positive(value) {
  const parsed = number(value, 0);
  return parsed > EPSILON ? parsed : 0;
}

function text(value, fallback = "") {
  const normalized = String(value ?? "").trim();
  return normalized || fallback;
}

function numericOrder(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function planogramFrom(source) {
  if (!source || typeof source !== "object") return null;
  if (source.planogram && typeof source.planogram === "object") return source.planogram;
  if (source.engine_result?.planogram) return source.engine_result.planogram;
  if (source.optimizer_result?.planogram) return source.optimizer_result.planogram;
  if (source.plan_payload?.planogram) return source.plan_payload.planogram;
  return null;
}

function productGeometry(product, cursorX) {
  const sourceWidth = positive(product.width_cm);
  const sourceDepth = positive(product.depth_cm);
  const rotated = product.is_rotated === true;
  const width = positive(product.oriented_width_cm) || (rotated ? sourceDepth : sourceWidth);
  const depth = positive(product.oriented_depth_cm) || (rotated ? sourceWidth : sourceDepth);
  const height = positive(product.height_cm);
  const facing = Math.max(1, Math.trunc(number(product.facing_count ?? product.facing, 1)));
  const faceWidth = width * facing;
  const consumedWidth = positive(product.used_width_cm) || faceWidth;
  const geometryReady = Boolean(
    width &&
    height &&
    depth &&
    consumedWidth &&
    consumedWidth + EPSILON >= faceWidth
  );

  return {
    key: [
      text(product.sku, "unknown"),
      text(product.aisle_id ?? product.aisle, "unknown"),
      text(product.module_id, "unknown"),
      text(product.shelf_no, "unknown"),
      text(product.position_order, "unknown"),
    ].join(":"),
    sku: text(product.sku, "—"),
    productName: text(product.product_name, text(product.sku, "—")),
    brand: text(product.brand ?? product.brand_name, ""),
    imageUrl: text(product.image_url, ""),
    widthCm: width,
    heightCm: height,
    depthCm: depth,
    facing,
    consumedWidthCm: consumedWidth,
    positionOrder: numericOrder(product.position_order, 999999),
    dimensionSource: text(product.dimension_source, "unknown"),
    rotated,
    geometryReady,
    xCm: cursorX,
    raw: product,
  };
}

function shelfGeometry(shelf, shelfIndex, yCm) {
  const width = positive(shelf.shelf_width_cm ?? shelf.width_cm);
  const height = positive(shelf.shelf_height_cm ?? shelf.height_cm);
  const depth = positive(shelf.shelf_depth_cm ?? shelf.depth_cm);
  const products = [...(Array.isArray(shelf.products) ? shelf.products : [])]
    .sort((left, right) => numericOrder(left.position_order, 999999) - numericOrder(right.position_order, 999999));

  let cursorX = 0;
  const placedProducts = products.map((product) => {
    const normalized = productGeometry(product, cursorX);
    cursorX += normalized.consumedWidthCm;
    return normalized;
  });

  const productsFit = placedProducts.every((product) => (
    product.geometryReady &&
    product.heightCm <= height + EPSILON &&
    product.depthCm <= depth + EPSILON
  ));
  const geometryReady = Boolean(
    width &&
    height &&
    depth &&
    productsFit &&
    cursorX <= width + EPSILON
  );

  return {
    key: String(shelf.shelf_no ?? shelfIndex + 1),
    shelfNo: shelf.shelf_no ?? shelfIndex + 1,
    widthCm: width,
    heightCm: height,
    depthCm: depth,
    yCm,
    usedWidthCm: positive(shelf.used_width_cm ?? shelf.used),
    products: placedProducts,
    geometryReady,
    raw: shelf,
  };
}

function moduleGeometry(aisle, module, moduleIndex) {
  const rawShelves = Array.isArray(module.shelves) ? module.shelves : [];
  const orderedShelves = [...rawShelves].sort((left, right) => (
    numericOrder(left.shelf_no, 999999) - numericOrder(right.shelf_no, 999999)
  ));
  let yCm = 0;
  const shelves = orderedShelves.map((shelf, shelfIndex) => {
    const normalized = shelfGeometry(shelf, shelfIndex, yCm);
    yCm += normalized.heightCm;
    return normalized;
  });

  const measuredWidth = positive(module.module_width_cm ?? module.width_cm);
  const measuredHeight = positive(module.module_height_cm ?? module.height_cm);
  const measuredDepth = positive(module.module_depth_cm ?? module.depth_cm);
  const shelfWidth = Math.max(0, ...shelves.map((shelf) => shelf.widthCm));
  const shelfDepth = Math.max(0, ...shelves.map((shelf) => shelf.depthCm));
  const shelfHeight = shelves.reduce((sum, shelf) => sum + shelf.heightCm, 0);

  // These fallbacks do not invent measurements. They aggregate exact shelf
  // measurements already present in the authoritative plan payload.
  const width = measuredWidth || shelfWidth;
  const height = measuredHeight || shelfHeight;
  const depth = measuredDepth || shelfDepth;
  const shelvesFitModule = Boolean(
    shelfWidth <= width + EPSILON &&
    shelfDepth <= depth + EPSILON &&
    shelfHeight <= height + EPSILON
  );
  const geometryReady = Boolean(
    width &&
    height &&
    depth &&
    shelves.length &&
    shelvesFitModule &&
    shelves.every((shelf) => shelf.geometryReady)
  );

  return {
    key: `${text(aisle.aisle_id, "?")}:${text(module.module_id, String(moduleIndex + 1))}:${text(module.side, "?")}`,
    aisleId: text(aisle.aisle_id, "—"),
    aisleRow: numericOrder(aisle.row, 999999),
    aislePosition: numericOrder(aisle.position, 999999),
    moduleId: module.module_id ?? moduleIndex + 1,
    side: text(module.side, "—"),
    moduleType: text(module.module_type ?? module.fixture_type, "—"),
    storageType: text(module.storage_type, "—"),
    widthCm: width,
    heightCm: height,
    depthCm: depth,
    shelves,
    geometryReady,
    productCount: shelves.reduce((sum, shelf) => sum + shelf.products.length, 0),
    raw: module,
  };
}

export function buildPlanogramScene(source) {
  const planogram = planogramFrom(source);
  if (!planogram || !Array.isArray(planogram.aisles)) {
    return {
      renderable: false,
      reason: "planogram_missing",
      modules: [],
      aisles: [],
      productCount: 0,
      geometryReadyCount: 0,
    };
  }

  const aisles = [...planogram.aisles]
    .sort((left, right) => {
      const rowDelta = numericOrder(left.row, 999999) - numericOrder(right.row, 999999);
      if (rowDelta) return rowDelta;
      const positionDelta = numericOrder(left.position, 999999) - numericOrder(right.position, 999999);
      if (positionDelta) return positionDelta;
      return text(left.aisle_id).localeCompare(text(right.aisle_id));
    })
    .map((aisle) => ({
      aisleId: text(aisle.aisle_id, "—"),
      modules: (Array.isArray(aisle.modules) ? aisle.modules : []).map((module, moduleIndex) => (
        moduleGeometry(aisle, module, moduleIndex)
      )),
    }));

  const modules = aisles.flatMap((aisle) => aisle.modules);
  const productCount = modules.reduce((sum, module) => sum + module.productCount, 0);
  const geometryReadyCount = modules.filter((module) => module.geometryReady).length;

  return {
    renderable: modules.length > 0,
    reason: modules.length ? null : "modules_missing",
    storeCode: text(planogram.store_code, "—"),
    routeStrategy: text(planogram.route_strategy, "—"),
    modules,
    aisles,
    productCount,
    geometryReadyCount,
  };
}

export function moduleByKey(scene, key) {
  return scene?.modules?.find((module) => module.key === key) || null;
}
