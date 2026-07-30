function getProductName(product = {}) {
  return (
    product?.name ||
    product?.product_name ||
    product?.productName ||
    product?.["Product Name"] ||
    product?.sku ||
    product?.SKU ||
    "Ürün"
  );
}

function getProductImage(product = {}) {
  const candidates = [
    product?.image_url,
    product?.product_image_url,
    product?.["Product Image URL"],
    product?.catalog_image_url,
    product?.pim_image_url,
    product?.image,
  ];

  return candidates.find((x) => /^https?:\/\//i.test(String(x || ""))) || "";
}

function getFallback(product = {}) {
  return String(
    product?.brand ||
    product?.brand_name ||
    product?.name ||
    product?.product_name ||
    product?.sku ||
    "SKU"
  )
    .slice(0, 2)
    .toUpperCase();
}

function shouldHideFromShelf(product = {}) {
  const raw = [
    product?.sku,
    product?.SKU,
    product?.name,
    product?.product_name,
    product?.productName,
    product?.["Product Name"],
    product?.brand,
    product?.brand_name,
    product?.category_l1,
    product?.category_l2,
    product?.["Category L1"],
    product?.["Category L2"],
    product?.frontend_category_local,
    product?.frontend_subcategory_local,
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
    raw.includes("CARRIER BAG") ||
    raw.includes("MARKET BAG") ||
    raw.includes("DISPOSABLE BAG")
  ) {
    return true;
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
    return true;
  }

  if (
    raw.includes("LA LORRAINE") ||
    raw.includes("BAGUETTE") ||
    raw.includes("BAGEL") ||
    raw.includes("SİMİT") ||
    raw.includes("SIMIT") ||
    raw.includes("RAMAZAN PIDESI") ||
    raw.includes("RAMAZAN PİDESİ") ||
    raw.includes("PIDE") ||
    raw.includes("PİDE") ||
    raw.includes("BAKERY") ||
    raw.includes("FIRIN") ||
    raw.includes("EKMEK") ||
    raw.includes("BREAD")
  ) {
    return true;
  }

  return false;
}

export function ProductThumb({ product, small = false }) {
  if (shouldHideFromShelf(product)) return null;

  const size = small ? { width: 28, height: 36, fontSize: 14 } : undefined;
  const img = getProductImage(product);
  const fallback = getFallback(product);
  const name = getProductName(product);

  return (
    <div
      className="product-thumb"
      style={{
        background: product?.color || "#DF1067",
        ...size,
      }}
      title={name}
    >
      {img ? (
        <img
          src={img}
          alt={name}
          loading="lazy"
          decoding="async"
          onError={(e) => {
            e.currentTarget.style.display = "none";
          }}
        />
      ) : (
        <span>{fallback}</span>
      )}

      {img && <span className="product-thumb-fallback">{fallback}</span>}
    </div>
  );
}

export function ProductChip({ product, onClick }) {
  if (shouldHideFromShelf(product)) return null;

  const img = getProductImage(product);
  const name = getProductName(product);
  const fallback = getFallback(product);

  const handleKeyDown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onClick?.(event);
    }
  };

  return (
    <div
      className={`product-chip ${product?.storage || product?.storage_type || ""}`}
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={handleKeyDown}
      title={`${name} • Facing ${product?.facing || product?.facing_count || "-"}`}
    >
      {img ? (
        <img
          src={img}
          alt=""
          loading="lazy"
          decoding="async"
          onError={(e) => {
            e.currentTarget.style.display = "none";
          }}
        />
      ) : (
        fallback
      )}
    </div>
  );
}

export function storageTone(storage) {
  if (storage === "CHILLED") return "cyan";
  if (storage === "FROZEN") return "purple";
  return "green";
}
