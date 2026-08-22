"""Fail-closed Shelf Scan compliance evaluation for Planogram previews.

The recognition model is intentionally outside this module. This evaluator
accepts detector observations with confidence/coverage evidence and compares
those observations against a Planogram baseline without converting uncertain
vision output into operational truth.

Key rule: "not detected" is never interpreted as "missing" unless the exact
shelf scan is declared complete, image quality is sufficient, occlusion is
bounded and all observations for that shelf are structurally valid.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from app.modules.planogram.execution import (
    PlanogramExecutionError,
    plan_fingerprint,
    validate_plan_payload,
)

SHELF_SCAN_CONTRACT = "planogram-shelf-scan-compliance-v1"
DEFAULT_MIN_DETECTION_CONFIDENCE = 0.80
DEFAULT_MIN_IMAGE_QUALITY = 0.70
DEFAULT_MAX_OCCLUSION_PCT = 35.0
MAX_SCAN_SHELVES = 2_000
MAX_OBSERVATIONS = 20_000


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ".").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y", "evet"}


def _location_key(
    aisle_id: Any,
    module_id: Any,
    shelf_no: Any,
) -> tuple[str, str, str]:
    return (
        _text(aisle_id),
        _text(module_id),
        _text(shelf_no),
    )


def _expected_by_shelf(
    plan_payload: dict[str, Any],
) -> dict[tuple[str, str, str], dict[str, int]]:
    validate_plan_payload(plan_payload)
    expected: dict[tuple[str, str, str], dict[str, int]] = {}
    for aisle in plan_payload.get("aisles") or []:
        aisle_id = _text(aisle.get("aisle_id"))
        for module in aisle.get("modules") or []:
            module_id = _text(module.get("module_id"))
            for shelf in module.get("shelves") or []:
                shelf_no = _text(shelf.get("shelf_no"))
                key = _location_key(aisle_id, module_id, shelf_no)
                products: dict[str, int] = {}
                for product in shelf.get("products") or []:
                    sku = _text(product.get("sku") or product.get("SKU")).upper()
                    facing = int(
                        product.get("facing_count")
                        or product.get("facing")
                        or 1
                    )
                    products[sku] = facing
                expected[key] = products
    return expected


def _expected_locations(
    expected: dict[tuple[str, str, str], dict[str, int]],
) -> dict[str, set[tuple[str, str, str]]]:
    locations: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for shelf_key, products in expected.items():
        for sku in products:
            locations[sku].add(shelf_key)
    return dict(locations)


def _scan_fingerprint(
    *,
    plan_fingerprint_value: str,
    shelves: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> str:
    payload = json.dumps(
        {
            "plan_fingerprint": plan_fingerprint_value,
            "shelves": shelves,
            "observations": observations,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def evaluate_shelf_scan(
    *,
    plan_payload: dict[str, Any],
    shelves: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    min_detection_confidence: float = DEFAULT_MIN_DETECTION_CONFIDENCE,
    min_image_quality: float = DEFAULT_MIN_IMAGE_QUALITY,
    max_occlusion_pct: float = DEFAULT_MAX_OCCLUSION_PCT,
) -> dict[str, Any]:
    """Compare detector output with a Planogram without inventing visual truth."""
    if not 0.5 <= min_detection_confidence <= 1.0:
        raise PlanogramExecutionError("shelf_scan_confidence_threshold_invalid")
    if not 0.0 <= min_image_quality <= 1.0:
        raise PlanogramExecutionError("shelf_scan_image_quality_threshold_invalid")
    if not 0.0 <= max_occlusion_pct <= 100.0:
        raise PlanogramExecutionError("shelf_scan_occlusion_threshold_invalid")
    if not shelves or len(shelves) > MAX_SCAN_SHELVES:
        raise PlanogramExecutionError("shelf_scan_shelf_count_invalid")
    if len(observations) > MAX_OBSERVATIONS:
        raise PlanogramExecutionError("shelf_scan_observation_limit_exceeded")

    expected = _expected_by_shelf(plan_payload)
    expected_locations = _expected_locations(expected)
    plan_fp = plan_fingerprint(plan_payload)

    scan_evidence: dict[tuple[str, str, str], dict[str, Any]] = {}
    blockers: list[str] = []
    for index, row in enumerate(shelves):
        key = _location_key(
            row.get("aisle_id"),
            row.get("module_id"),
            row.get("shelf_no"),
        )
        if not all(key):
            blockers.append(f"scan_shelf_location_missing:index:{index}")
            continue
        if key in scan_evidence:
            blockers.append("duplicate_scan_shelf:" + "::".join(key))
            continue
        image_quality = _number(row.get("image_quality_score"), -1.0)
        occlusion_pct = _number(row.get("occlusion_pct"), -1.0)
        coverage_complete = _truthy(row.get("coverage_complete"))
        structurally_valid = (
            0.0 <= image_quality <= 1.0
            and 0.0 <= occlusion_pct <= 100.0
        )
        usable_for_absence = (
            structurally_valid
            and coverage_complete
            and image_quality >= min_image_quality
            and occlusion_pct <= max_occlusion_pct
        )
        scan_evidence[key] = {
            "location": {
                "aisle_id": key[0],
                "module_id": key[1],
                "shelf_no": key[2],
            },
            "source_ref": _text(row.get("source_ref")) or None,
            "coverage_complete": coverage_complete,
            "image_quality_score": image_quality,
            "occlusion_pct": occlusion_pct,
            "structurally_valid": structurally_valid,
            "usable_for_absence": usable_for_absence,
        }

    confident: dict[
        tuple[str, str, str],
        dict[str, dict[str, Any]],
    ] = defaultdict(dict)
    uncertain: list[dict[str, Any]] = []
    duplicate_observations: list[str] = []
    invalid_observations: list[str] = []

    for index, row in enumerate(observations):
        key = _location_key(
            row.get("aisle_id"),
            row.get("module_id"),
            row.get("shelf_no"),
        )
        sku = _text(row.get("sku") or row.get("SKU")).upper()
        confidence = _number(row.get("confidence"), -1.0)
        facing = int(_number(row.get("facing_count"), 0))
        if not all(key) or not sku or not 0.0 <= confidence <= 1.0 or facing < 1:
            invalid_observations.append(f"index:{index}")
            continue
        observation = {
            "sku": sku,
            "confidence": confidence,
            "facing_count": facing,
            "location": {
                "aisle_id": key[0],
                "module_id": key[1],
                "shelf_no": key[2],
            },
            "source_ref": _text(row.get("source_ref")) or None,
        }
        if confidence < min_detection_confidence:
            uncertain.append(
                {
                    **observation,
                    "result": "review_required",
                    "reason": "detection_confidence_below_threshold",
                }
            )
            continue
        if sku in confident[key]:
            duplicate_observations.append("::".join((*key, sku)))
            continue
        confident[key][sku] = observation

    deviations: list[dict[str, Any]] = []
    compliant: list[dict[str, Any]] = []
    review_required = list(uncertain)
    observed_expected_keys: set[tuple[tuple[str, str, str], str]] = set()

    for key, products in confident.items():
        expected_here = expected.get(key, {})
        scan = scan_evidence.get(key)
        if scan is None:
            review_required.extend(
                {
                    **observation,
                    "result": "review_required",
                    "reason": "scan_shelf_evidence_missing",
                }
                for observation in products.values()
            )
            continue
        if not scan["structurally_valid"]:
            review_required.extend(
                {
                    **observation,
                    "result": "review_required",
                    "reason": "scan_quality_evidence_invalid",
                }
                for observation in products.values()
            )
            continue

        for sku, observation in products.items():
            expected_facing = expected_here.get(sku)
            if expected_facing is not None:
                observed_expected_keys.add((key, sku))
                if observation["facing_count"] == expected_facing:
                    compliant.append(
                        {
                            **observation,
                            "result": "compliant",
                            "expected_facing_count": expected_facing,
                        }
                    )
                else:
                    deviations.append(
                        {
                            **observation,
                            "result": "deviation",
                            "deviation_code": "facing_mismatch",
                            "expected_facing_count": expected_facing,
                        }
                    )
                continue

            expected_elsewhere = expected_locations.get(sku) or set()
            deviations.append(
                {
                    **observation,
                    "result": "deviation",
                    "deviation_code": (
                        "sku_misplaced"
                        if expected_elsewhere
                        else "sku_not_in_approved_plan"
                    ),
                    "expected_locations": [
                        {
                            "aisle_id": location[0],
                            "module_id": location[1],
                            "shelf_no": location[2],
                        }
                        for location in sorted(expected_elsewhere)
                    ],
                }
            )

    missing_count = 0
    scanned_expected_count = 0
    for key, expected_products in expected.items():
        scan = scan_evidence.get(key)
        if scan is None or not scan["usable_for_absence"]:
            if scan is not None and expected_products:
                review_required.append(
                    {
                        "location": scan["location"],
                        "result": "review_required",
                        "reason": "shelf_absence_not_provable",
                        "coverage_complete": scan["coverage_complete"],
                        "image_quality_score": scan["image_quality_score"],
                        "occlusion_pct": scan["occlusion_pct"],
                    }
                )
            continue
        scanned_expected_count += len(expected_products)
        for sku, expected_facing in expected_products.items():
            if (key, sku) in observed_expected_keys:
                continue
            missing_count += 1
            deviations.append(
                {
                    "sku": sku,
                    "location": scan["location"],
                    "result": "deviation",
                    "deviation_code": "expected_sku_not_detected",
                    "expected_facing_count": expected_facing,
                    "absence_evidence": {
                        "coverage_complete": True,
                        "image_quality_score": scan["image_quality_score"],
                        "occlusion_pct": scan["occlusion_pct"],
                    },
                }
            )

    if duplicate_observations:
        blockers.append("duplicate_high_confidence_observation")
    if invalid_observations:
        blockers.append("invalid_scan_observation")

    confirmed_evaluations = len(compliant) + len(deviations)
    compliance_pct = (
        round(len(compliant) * 100.0 / confirmed_evaluations, 2)
        if confirmed_evaluations
        else None
    )
    fully_evaluable = (
        not blockers
        and not review_required
        and all(
            scan["usable_for_absence"]
            for scan in scan_evidence.values()
        )
    )
    normalized_shelves = sorted(
        scan_evidence.values(),
        key=lambda row: (
            row["location"]["aisle_id"],
            row["location"]["module_id"],
            row["location"]["shelf_no"],
        ),
    )
    normalized_observations = sorted(
        [
            observation
            for products in confident.values()
            for observation in products.values()
        ],
        key=lambda row: (
            row["location"]["aisle_id"],
            row["location"]["module_id"],
            row["location"]["shelf_no"],
            row["sku"],
        ),
    )

    return {
        "contract": SHELF_SCAN_CONTRACT,
        "available": bool(scan_evidence) and not blockers,
        "preview_only": True,
        "production_evidence": False,
        "field_truth": False,
        "auto_accept_allowed": False,
        "auto_correct_allowed": False,
        "plan_fingerprint": plan_fp,
        "scan_fingerprint": _scan_fingerprint(
            plan_fingerprint_value=plan_fp,
            shelves=normalized_shelves,
            observations=normalized_observations,
        ),
        "thresholds": {
            "min_detection_confidence": min_detection_confidence,
            "min_image_quality": min_image_quality,
            "max_occlusion_pct": max_occlusion_pct,
        },
        "shelf_count": len(scan_evidence),
        "observation_count": len(observations),
        "high_confidence_observation_count": len(normalized_observations),
        "compliant_count": len(compliant),
        "deviation_count": len(deviations),
        "missing_expected_sku_count": missing_count,
        "review_required_count": len(review_required),
        "scanned_expected_sku_count": scanned_expected_count,
        "compliance_pct": compliance_pct,
        "fully_evaluable": fully_evaluable,
        "candidate_ready_for_human_review": (
            not blockers and confirmed_evaluations > 0
        ),
        "compliant": compliant[:5_000],
        "deviations": deviations[:5_000],
        "review_required": review_required[:5_000],
        "blockers": list(dict.fromkeys(blockers)),
        "duplicate_observations": duplicate_observations[:200],
        "invalid_observations": invalid_observations[:200],
        "evidence_boundary": (
            "detector output is observation evidence only; missing SKU conclusions "
            "require complete high-quality shelf coverage and human/field governance"
        ),
    }
