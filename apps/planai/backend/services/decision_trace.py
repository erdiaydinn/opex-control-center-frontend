from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _get(obj: Dict[str, Any], *keys, default=None):
    for key in keys:
        if isinstance(obj, dict) and key in obj and obj.get(key) not in [None, ""]:
            return obj.get(key)
    return default


def _num(v, default=0):
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace(",", "."))
    except Exception:
        return default


def _product_identity(product: Dict[str, Any]) -> Dict[str, Any]:
    return {
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
    }


def _slot_identity(slot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    slot = slot or {}
    return {
        "slot_id": _get(slot, "slot_id", "id", default=""),
        "fixture_instance_id": _get(slot, "fixture_instance_id", "fixture_id", default=""),
        "fixture_type": _get(slot, "fixture_type", "fixture_key", "module_type", default=""),
        "storage_class": _get(slot, "storage_class", "allowed_storage_type", "storage_type", default=""),
        "aisle_id": _get(slot, "aisle_id", "aisle", default=""),
        "module_id": _get(slot, "module_id", default=None),
        "shelf_no": _get(slot, "shelf_no", "shelf", default=None),
        "shelf_width_cm": _num(_get(slot, "shelf_width_cm", "width_cm", default=0), 0),
        "shelf_depth_cm": _num(_get(slot, "shelf_depth_cm", "depth_cm", default=0), 0),
        "remaining_width_cm": _num(_get(slot, "remaining_width_cm", default=0), 0),
    }


def _capacity_math(product: Dict[str, Any], slot: Optional[Dict[str, Any]], decision_data: Dict[str, Any]) -> Dict[str, Any]:
    slot = slot or {}
    final_facing = _get(
        decision_data,
        "final_facing", "facing", "facing_count",
        default=_get(slot, "final_facing", "facing", "facing_count", default=_get(product or {}, "facing_count", "facing", default=1)),
    )
    depth_units = _get(decision_data, "depth_units", default=_get(slot, "depth_units", default=None))
    capacity_units = _get(
        decision_data,
        "capacity_units", "total_capacity_units",
        default=_get(slot, "capacity_units", "total_capacity_units", default=None),
    )
    return {
        "final_facing": int(_num(final_facing, 1)),
        "max_possible_facing": int(_num(_get(decision_data, "max_possible_facing", default=_get(slot, "max_possible_facing", default=final_facing)), _num(final_facing, 1))),
        "depth_units": None if depth_units is None else int(_num(depth_units, 0)),
        "capacity_units": None if capacity_units is None else int(_num(capacity_units, 0)),
        "used_width_cm": _num(_get(decision_data, "used_width_cm", default=_get(slot, "used_width_cm", default=0)), 0),
    }


def placement_trace(product: Dict[str, Any], slot: Optional[Dict[str, Any]] = None, decision: Optional[Dict[str, Any]] = None, **details) -> Dict[str, Any]:
    decision_data = decision or {}
    cap = _capacity_math(product or {}, slot or {}, decision_data)
    return {
        "trace_id": str(uuid.uuid4()),
        "event_type": "PLACEMENT",
        "status": "PLACED",
        "decision": "PLACED",  # V1.7.5 backward compatibility
        "capacity_math": cap,   # V1.7.5 backward compatibility
        "decision_details": {
            "reason_code": _get(decision_data, "reason_code", default="PHYSICAL_FIT_OK"),
            "message": _get(decision_data, "message", default="Product placed after passing physical and storage constraints."),
            "score": _num(_get(decision_data, "score", "placement_score", default=_get(slot or {}, "placement_score", default=0)), 0),
            "facing": cap["final_facing"],
            "depth_units": cap["depth_units"],
            "capacity_units": cap["capacity_units"],
        },
        "created_at": now_iso(),
        "product": _product_identity(product or {}),
        "slot": _slot_identity(slot),
        "checks": details.pop("checks", []),
        "details": details,
    }


def rejection_trace(product: Dict[str, Any], reason_code: str, slot: Optional[Dict[str, Any]] = None, decision: Optional[Dict[str, Any]] = None, **details) -> Dict[str, Any]:
    decision_data = decision or {}
    reason = str(reason_code or "NO_COMPATIBLE_SLOT").upper()
    return {
        "trace_id": str(uuid.uuid4()),
        "event_type": "REJECTION",
        "status": "UNPLACED",
        "decision": "UNPLACED",  # V1.7.5 backward compatibility
        "reason_code": reason,
        "decision_details": {
            "reason_code": reason,
            "message": _get(decision_data, "message", default=reason),
            "score": _num(_get(decision_data, "score", "placement_score", default=0), 0),
        },
        "created_at": now_iso(),
        "product": _product_identity(product or {}),
        "slot": _slot_identity(slot),
        "checks": details.pop("checks", []),
        "details": details,
    }


def summarize_traces(traces: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_status: Dict[str, int] = {}
    by_reason: Dict[str, int] = {}
    for trace in traces or []:
        status = str(trace.get("status") or trace.get("decision") or "UNKNOWN")
        details = trace.get("decision_details") or {}
        reason = str(details.get("reason_code") or trace.get("reason_code") or "UNKNOWN") if isinstance(details, dict) else "UNKNOWN"
        by_status[status] = by_status.get(status, 0) + 1
        by_reason[reason] = by_reason.get(reason, 0) + 1
    return {"total_traces": len(traces or []), "by_status": by_status, "by_reason": by_reason}


def build_decision_trace(*args, **kwargs) -> Dict[str, Any]:
    event_type = str(kwargs.pop("event_type", "PLACEMENT")).upper()
    if event_type in {"REJECTION", "UNPLACED"}:
        return rejection_trace(*args, **kwargs)
    return placement_trace(*args, **kwargs)
