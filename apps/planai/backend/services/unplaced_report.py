from typing import Any, Dict, List, Optional
from datetime import datetime


def _get(product: Dict[str, Any], *keys, default=None):
    for key in keys:
        if key in product and product.get(key) not in [None, ""]:
            return product.get(key)
    return default


def _num(v, default=0):
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace(",", "."))
    except Exception:
        return default


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


REASON_ACTION_MAP = {
    "STORAGE_MISMATCH": "Ürün storage class ile uyumlu fixture bulunamadı. Doğru soğuk/donuk/ambient fixture kontrol edilmeli.",
    "PRODUCT_TOO_WIDE_FOR_SHELF": "Ürün raf genişliğine sığmıyor. Raf ölçüsü veya ürün ölçüsü doğrulanmalı.",
    "PRODUCT_TOO_WIDE_FOR_REMAINING_SPACE": "Raf üzerinde kalan genişlik yetersiz. Facing azalt veya ürünü başka rafa taşı.",
    "PRODUCT_TOO_DEEP_FOR_SHELF": "Ürün raf derinliğine sığmıyor. Daha derin fixture gerekir.",
    "PRODUCT_TOO_TALL_FOR_SHELF": "Ürün raf yüksekliğine sığmıyor. Raf yüksekliği veya ürün ölçüsü doğrulanmalı.",
    "WEIGHT_LIMIT_EXCEEDED": "Raf ağırlık limiti aşılıyor. Ürün alt/ağır ürün rafına alınmalı.",
    "FIXTURE_NOT_AVAILABLE": "Bu ürün için uygun fixture yok. Store DNA içinde ilgili fixture eklenmeli.",
    "CAPACITY_NOT_ENOUGH": "Uygun fixture var ama kapasite yetersiz. Fixture sayısı veya shelf kapasitesi artırılmalı.",
    "MISSING_PRODUCT_DIMENSION": "Ürün ölçüsü eksik. Master catalog veya ürün override ile ölçü tamamlanmalı.",
    "MERCHANDISING_CONFLICT": "Gıda / kokulu non-food gibi komşuluk kuralı ihlal ediliyor.",
    "NO_COMPATIBLE_SLOT": "Uygun raf/slot bulunamadı. Storage, fixture ve kapasite birlikte kontrol edilmeli.",
}


def make_unplaced(
    product: Dict[str, Any],
    reason_code: str,
    message: Optional[str] = None,
    **details
) -> Dict[str, Any]:
    """Compatibility function expected by V1.7.4/V1.7.5/V1.8 physics engine."""

    reason = str(reason_code or "NO_COMPATIBLE_SLOT").upper()
    human_action = details.pop("human_action", None) or REASON_ACTION_MAP.get(
        reason,
        "Ürün yerleşemedi. Ürün ölçüsü, storage class, fixture tipi ve kapasite birlikte kontrol edilmeli."
    )

    record = {
        "sku": _get(product, "sku", "SKU", "barcode", default=""),
        "barcode": _get(product, "barcode", "Barcode", "product_barcodes", default=""),
        "product_name": _get(product, "product_name", "Product Name", "name", default="Unnamed Product"),
        "brand": _get(product, "brand", "brand_name", "Brand", default="UNKNOWN"),
        "category_l1": _get(product, "category_l1", "frontend_category_local", "category", default="GENERAL"),
        "category_l2": _get(product, "category_l2", "frontend_subcategory_local", "subcategory", default="GENERAL"),
        "storage_class": _get(product, "storage_class", "storage_type", "_storage", default="AMBIENT"),
        "storage_type": _get(product, "storage_type", "storage_class", "_storage", default="AMBIENT"),
        "width_cm": _num(_get(product, "width_cm", "product_width_in_cm", default=0), 0),
        "height_cm": _num(_get(product, "height_cm", "product_height_in_cm", default=0), 0),
        "depth_cm": _num(_get(product, "depth_cm", "product_length_in_cm", default=0), 0),
        "weight_kg": _num(_get(product, "weight_kg", "product_weight_value", default=0), 0),
        "reason": reason,
        "reason_code": reason,
        "message": message or reason,
        "human_action": human_action,
        "suggested_action": human_action,
        "created_at": now_iso(),
    }

    record.update(details)
    return record


def build_unplaced_record(product: Dict[str, Any], reason: str, **details) -> Dict[str, Any]:
    return make_unplaced(product, reason, **details)


def summarize_unplaced(unplaced: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_reason: Dict[str, int] = {}
    by_storage: Dict[str, int] = {}

    for item in unplaced or []:
        reason = str(item.get("reason_code") or item.get("reason") or "UNKNOWN")
        storage = str(item.get("storage_class") or item.get("storage_type") or "UNKNOWN")
        by_reason[reason] = by_reason.get(reason, 0) + 1
        by_storage[storage] = by_storage.get(storage, 0) + 1

    return {
        "total_unplaced": len(unplaced or []),
        "by_reason": by_reason,
        "by_storage": by_storage,
    }


def export_unplaced_rows(unplaced: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return list(unplaced or [])
