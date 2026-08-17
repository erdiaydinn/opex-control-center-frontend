from __future__ import annotations

import hashlib
import json
from typing import Any


class PlanogramExecutionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def canonical_fingerprint(payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_plan_payload(plan_payload: dict[str, Any]) -> dict[str, Any]:
    aisles = plan_payload.get("aisles")
    if not isinstance(aisles, list) or not aisles:
        raise PlanogramExecutionError("plan_payload_requires_aisles")
    placement_count = 0
    seen_locations: set[tuple[str, str, str, str]] = set()
    for aisle in aisles:
        aisle_id = str(aisle.get("aisle_id") or "").strip()
        if not aisle_id:
            raise PlanogramExecutionError("plan_payload_requires_aisle_id")
        modules = aisle.get("modules") or []
        if not isinstance(modules, list):
            raise PlanogramExecutionError("plan_payload_modules_must_be_list")
        for module in modules:
            module_id = str(module.get("module_id") or "").strip()
            if not module_id:
                raise PlanogramExecutionError("plan_payload_requires_module_id")
            shelves = module.get("shelves") or []
            if not isinstance(shelves, list):
                raise PlanogramExecutionError("plan_payload_shelves_must_be_list")
            for shelf in shelves:
                shelf_no = str(shelf.get("shelf_no") or "").strip()
                if not shelf_no:
                    raise PlanogramExecutionError("plan_payload_requires_shelf_no")
                products = shelf.get("products") or []
                if not isinstance(products, list):
                    raise PlanogramExecutionError("plan_payload_products_must_be_list")
                for product in products:
                    sku = str(product.get("sku") or product.get("SKU") or "").strip()
                    if not sku:
                        raise PlanogramExecutionError("plan_payload_requires_sku")
                    facing = int(product.get("facing_count") or product.get("facing") or 1)
                    if facing < 1:
                        raise PlanogramExecutionError("plan_payload_requires_positive_facing")
                    key = (sku, aisle_id, module_id, shelf_no)
                    if key in seen_locations:
                        raise PlanogramExecutionError("duplicate_sku_location_in_plan")
                    seen_locations.add(key)
                    placement_count += 1
    if placement_count == 0:
        raise PlanogramExecutionError("plan_payload_requires_product_placement")
    return plan_payload


def plan_fingerprint(plan_payload: dict[str, Any]) -> str:
    validate_plan_payload(plan_payload)
    return canonical_fingerprint(plan_payload)


def expected_locations(plan_payload: dict[str, Any], sku: str) -> list[dict[str, Any]]:
    target = sku.strip()
    if not target:
        raise PlanogramExecutionError("sku_required")
    locations: list[dict[str, Any]] = []
    for aisle in plan_payload.get("aisles") or []:
        aisle_id = str(aisle.get("aisle_id") or "")
        for module in aisle.get("modules") or []:
            module_id = str(module.get("module_id") or "")
            for shelf in module.get("shelves") or []:
                shelf_no = str(shelf.get("shelf_no") or "")
                for product in shelf.get("products") or []:
                    product_sku = str(product.get("sku") or product.get("SKU") or "").strip()
                    if product_sku != target:
                        continue
                    locations.append(
                        {
                            "aisle_id": aisle_id,
                            "module_id": module_id,
                            "shelf_no": shelf_no,
                            "facing_count": int(
                                product.get("facing_count") or product.get("facing") or 1
                            ),
                        }
                    )
    return locations


def evaluate_compliance(
    plan_payload: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    sku = str(candidate.get("sku") or "").strip()
    if not sku:
        raise PlanogramExecutionError("compliance_candidate_requires_sku")
    expected = expected_locations(plan_payload, sku)
    actual = {
        "aisle_id": str(candidate.get("actual_aisle_id") or "").strip(),
        "module_id": str(candidate.get("actual_module_id") or "").strip(),
        "shelf_no": str(candidate.get("actual_shelf_no") or "").strip(),
        "facing_count": int(candidate.get("actual_facing_count") or 0),
    }
    if not actual["aisle_id"] or not actual["module_id"] or not actual["shelf_no"]:
        raise PlanogramExecutionError("compliance_candidate_requires_actual_location")
    if actual["facing_count"] < 1:
        raise PlanogramExecutionError("compliance_candidate_requires_positive_facing")

    if not expected:
        return {
            "sku": sku,
            "expected_locations": [],
            "actual_location": actual,
            "result": "deviation",
            "deviation_codes": ["sku_not_in_approved_plan"],
        }

    for location in expected:
        if actual == location:
            return {
                "sku": sku,
                "expected_locations": expected,
                "actual_location": actual,
                "result": "compliant",
                "deviation_codes": [],
            }

    closest = min(
        expected,
        key=lambda location: sum(
            location[key] != actual[key]
            for key in ("aisle_id", "module_id", "shelf_no", "facing_count")
        ),
    )
    codes: list[str] = []
    if actual["aisle_id"] != closest["aisle_id"]:
        codes.append("aisle_mismatch")
    if actual["module_id"] != closest["module_id"]:
        codes.append("module_mismatch")
    if actual["shelf_no"] != closest["shelf_no"]:
        codes.append("shelf_mismatch")
    if actual["facing_count"] != closest["facing_count"]:
        codes.append("facing_mismatch")
    return {
        "sku": sku,
        "expected_locations": expected,
        "actual_location": actual,
        "result": "deviation",
        "deviation_codes": codes,
    }
