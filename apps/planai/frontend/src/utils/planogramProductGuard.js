export function classifyFrontendPlanogramProduct(product = {}) {
  const raw = [
    product.sku,
    product.SKU,
    product.product_name,
    product["Product Name"],
    product.brand,
    product.brand_name,
    product.category_l1,
    product.category_l2,
    product["Category L1"],
    product["Category L2"],
    product.storage_type,
    product["Storage Type"],
  ]
    .filter(Boolean)
    .join(" ")
    .toUpperCase();

  if (
    raw.includes("SHOPPING BAG") ||
    raw.includes("ALIŞVERİŞ POŞET") ||
    raw.includes("ALISVERIS POSET") ||
    raw.includes("POŞET") ||
    raw.includes("POSET") ||
    raw.includes("CARRIER BAG")
  ) {
    return {
      exclude: true,
      reason: "OPERATIONAL_SUPPLY_NOT_SHELF_PRODUCT",
      planogramClass: "EXCLUDED_OPERATIONAL_SUPPLY",
    };
  }

  if (
    raw.includes("EVERYDAY") ||
    raw.includes("COFFEE MACHINE") ||
    raw.includes("KAHVE MAKINESI") ||
    raw.includes("KAHVE MAKİNESİ") ||
    raw.includes("EQUIPMENT") ||
    raw.includes("EKIPMAN") ||
    raw.includes("EKİPMAN")
  ) {
    return {
      exclude: true,
      reason: "EQUIPMENT_NOT_SHELF_PRODUCT",
      planogramClass: "EXCLUDED_EQUIPMENT",
    };
  }

  if (
    raw.includes("LA LORRAINE") ||
    raw.includes("BAGUETTE") ||
    raw.includes("BAGEL") ||
    raw.includes("RAMAZAN PIDESI") ||
    raw.includes("RAMAZAN PİDESİ") ||
    raw.includes("PIDE") ||
    raw.includes("PİDE") ||
    raw.includes("BAKERY") ||
    raw.includes("FIRIN") ||
    raw.includes("EKMEK") ||
    raw.includes("BREAD")
  ) {
    return {
      exclude: true,
      reason: "BAKERY_FLOW_NOT_REGULAR_SHELF",
      planogramClass: "BAKERY_FLOW_REVIEW",
    };
  }

  return {
    exclude: false,
    reason: "SELLABLE_PRODUCT",
    planogramClass: "SELLABLE_PLANOGRAM_PRODUCT",
  };
}

export function productStorage(product = {}) {
  return String(product.storage_type || product.storage_class || product._storage || "AMBIENT").toUpperCase();
}

export function shelfStorage(shelf = {}) {
  return String(shelf.allowed_storage_type || shelf.storage_type || shelf.storage_class || "AMBIENT").toUpperCase();
}

export function sanitizeShelfProductsForRender(products = [], shelf = {}) {
  const allowedStorage = shelfStorage(shelf);

  const removed = [];
  const visible = [];

  for (const product of products || []) {
    const cls = classifyFrontendPlanogramProduct(product);

    if (cls.exclude) {
      removed.push({ ...product, ...cls });
      continue;
    }

    const pStorage = productStorage(product);

    if (pStorage !== allowedStorage) {
      removed.push({
        ...product,
        exclude: true,
        reason: "FRONTEND_STORAGE_MISMATCH_RENDER_BLOCKED",
        planogramClass: "RENDER_BLOCKED",
      });
      continue;
    }

    visible.push(product);
  }

  return {
    visible,
    removed,
  };
}
