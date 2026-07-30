from typing import Any, Dict, List

try:
    from services.product_classification_rules import split_products_for_planogram
except Exception:
    from product_classification_rules import split_products_for_planogram


def build_excluded_report(excluded: List[Dict[str, Any]], review: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_reason = {}
    by_class = {}

    for p in excluded or []:
        reason = str(p.get("reason_code") or "UNKNOWN")
        klass = str(p.get("planogram_class") or "UNKNOWN")
        by_reason[reason] = by_reason.get(reason, 0) + 1
        by_class[klass] = by_class.get(klass, 0) + 1

    return {
        "total_excluded": len(excluded or []),
        "total_review": len(review or []),
        "by_reason": by_reason,
        "by_class": by_class,
        "items": excluded or [],
        "review_items": review or [],
    }


def guard_planogram_input(products: List[Dict[str, Any]]) -> Dict[str, Any]:
    split = split_products_for_planogram(products or [])

    sellable = split.get("sellable_products", [])
    excluded = split.get("excluded_products", [])
    review = split.get("review_products", [])

    return {
        "sellable_products": sellable,
        "excluded_products": excluded,
        "review_products": review,
        "excluded_report": build_excluded_report(excluded, review),
        "summary": split.get("summary", {}),
    }


def attach_guard_report(result: Dict[str, Any], guard: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return result

    result["input_guard_summary"] = guard.get("summary", {})
    result["excluded_products"] = guard.get("excluded_products", [])
    result["review_products"] = guard.get("review_products", [])
    result["excluded_report"] = guard.get("excluded_report", {})

    return result
