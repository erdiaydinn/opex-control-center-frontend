"""Experimental physical-layout search above Planogram optimizer V4.

V4 searches product-allocation scoring profiles on a fixed measured layout. V5
adds a bounded physical search over explicitly relocatable, physically equivalent
fixtures by swapping complete spatial poses and re-running the basket-aware
optimizer for every valid alternative.

This is intentionally conservative:
- only fixtures explicitly marked ``relocatable=true`` participate;
- fixture and shelf physical/capability signatures must match exactly;
- cold/utility fixtures require explicit relocation attestation;
- measured Architecture V1 hard gates are re-run after every relocation;
- baseline is always retained;
- no CAPEX or installation authority is inferred;
- this is a bounded search, not a global-optimum claim.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from itertools import combinations
from typing import Any

import physical_optimizer_v3 as objective_v3
import physical_optimizer_v4 as allocation_v4
from architecture_truth import layout_architecture_report

PHYSICAL_LAYOUT_OPTIMIZER_VERSION = "physical-layout-optimizer-v5-relocation-search"
DEFAULT_LAYOUT_CANDIDATES = 16
MAX_LAYOUT_CANDIDATES = 32
DEFAULT_ALLOCATION_CANDIDATES = 12
MAX_ALLOCATION_CANDIDATES = 24
MAX_ALTERNATIVES = 5
SPATIAL_FIELDS = (
    "x_m",
    "y_m",
    "center_x_m",
    "center_y_m",
    "rotation_deg",
)
UTILITY_ATTESTATION_FIELDS = (
    "utility_relocation_attested",
    "relocation_utility_attested",
)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y", "evet"}


def _module_key(aisle: dict[str, Any], module: dict[str, Any]) -> str:
    aisle_id = _text(aisle.get("aisle_id"))
    module_id = _text(module.get("module_id"))
    if "::" in module_id:
        return module_id
    return f"{aisle_id}::{module_id}" if aisle_id else module_id


def _module_dimensions(module: dict[str, Any]) -> tuple[float, float]:
    width = _number(module.get("width_m"))
    depth = _number(module.get("depth_m"))
    if width <= 0:
        width = _number(module.get("width_cm")) / 100.0
    if depth <= 0:
        depth = _number(module.get("depth_cm")) / 100.0
    shelves = module.get("shelves") or []
    if shelves:
        first = shelves[0] or {}
        if width <= 0:
            width = _number(first.get("shelf_width_cm")) / 100.0
        if depth <= 0:
            depth = _number(first.get("shelf_depth_cm")) / 100.0
    return round(width, 4), round(depth, 4)


def _shelf_signature(shelf: dict[str, Any]) -> tuple[Any, ...]:
    return (
        round(_number(shelf.get("shelf_width_cm")), 3),
        round(_number(shelf.get("shelf_height_cm")), 3),
        round(_number(shelf.get("shelf_depth_cm")), 3),
        round(_number(shelf.get("max_weight_kg")), 3),
        _text(shelf.get("allowed_storage_type")).upper(),
        _text(shelf.get("zone_type")).lower(),
    )


def _requires_utility_attestation(module: dict[str, Any]) -> bool:
    if any(
        _truthy(module.get(field))
        for field in (
            "requires_power",
            "requires_plumbing",
            "requires_network",
            "requires_drain",
        )
    ):
        return True
    fixture = _text(
        module.get("fixture_type")
        or module.get("fixture_class")
        or module.get("module_type")
    ).lower()
    storage = _text(module.get("storage_type")).upper()
    return any(
        token in fixture
        for token in ("chill", "cool", "freez", "refriger", "cold")
    ) or storage in {"CHILLED", "FROZEN", "COLD"}


def _utility_relocation_attested(module: dict[str, Any]) -> bool:
    return any(_truthy(module.get(field)) for field in UTILITY_ATTESTATION_FIELDS)


def _fixture_signature(module: dict[str, Any]) -> tuple[Any, ...] | None:
    if not _truthy(module.get("relocatable")):
        return None
    if _requires_utility_attestation(module) and not _utility_relocation_attested(
        module
    ):
        return None

    width, depth = _module_dimensions(module)
    if width <= 0 or depth <= 0:
        return None
    shelves = module.get("shelves") or []
    shelf_profile = tuple(_shelf_signature(shelf or {}) for shelf in shelves)
    return (
        _text(
            module.get("fixture_type")
            or module.get("fixture_class")
            or module.get("module_type")
        ).upper(),
        _text(module.get("storage_type")).upper(),
        width,
        depth,
        shelf_profile,
        _truthy(module.get("requires_power")),
        _truthy(module.get("requires_plumbing")),
        _truthy(module.get("requires_network")),
        _truthy(module.get("requires_drain")),
    )


def _module_refs(
    layout: dict[str, Any],
) -> list[tuple[int, int, str, dict[str, Any]]]:
    result = []
    for aisle_index, aisle in enumerate(layout.get("aisles", []) or []):
        for module_index, module in enumerate(aisle.get("modules", []) or []):
            result.append(
                (
                    aisle_index,
                    module_index,
                    _module_key(aisle, module),
                    module,
                )
            )
    return result


def _relocation_pairs(layout: dict[str, Any]) -> list[tuple[str, str]]:
    groups: dict[tuple[Any, ...], list[str]] = {}
    for _, _, key, module in _module_refs(layout):
        signature = _fixture_signature(module)
        if signature is None:
            continue
        groups.setdefault(signature, []).append(key)

    pairs: list[tuple[str, str]] = []
    for signature in sorted(groups, key=str):
        keys = sorted(set(groups[signature]))
        pairs.extend(combinations(keys, 2))
    return pairs


def _swap_spatial_pose(
    layout: dict[str, Any],
    left_key: str,
    right_key: str,
) -> dict[str, Any]:
    candidate = deepcopy(layout)
    index = {key: module for _, _, key, module in _module_refs(candidate)}
    if left_key not in index or right_key not in index or left_key == right_key:
        raise ValueError("invalid_relocation_pair")

    left = index[left_key]
    right = index[right_key]
    left_pose = {field: left.get(field) for field in SPATIAL_FIELDS}
    right_pose = {field: right.get(field) for field in SPATIAL_FIELDS}
    for field in SPATIAL_FIELDS:
        if right_pose[field] is None:
            left.pop(field, None)
        else:
            left[field] = right_pose[field]
        if left_pose[field] is None:
            right.pop(field, None)
        else:
            right[field] = left_pose[field]
    return candidate


def _layout_fingerprint(layout: dict[str, Any]) -> str:
    rows = []
    for _, _, key, module in _module_refs(layout):
        rows.append(
            (
                key,
                tuple(module.get(field) for field in SPATIAL_FIELDS),
            )
        )
    payload = json.dumps(
        sorted(rows),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _selected_meta(result: dict[str, Any]) -> dict[str, Any]:
    market = result.get("market_search_optimizer")
    if isinstance(market, dict) and isinstance(
        market.get("selected_objective"), dict
    ):
        return market
    picker = result.get("picker_tour_optimizer")
    if isinstance(picker, dict) and isinstance(
        picker.get("selected_objective"), dict
    ):
        return picker
    return {}


def _candidate_summary(
    *,
    label: str,
    layout: dict[str, Any],
    result: dict[str, Any],
    moved_modules: list[str],
) -> dict[str, Any]:
    meta = _selected_meta(result)
    objective = meta.get("selected_objective") or {}
    tour = meta.get("selected_tour") or {}
    return {
        "label": label,
        "layout_fingerprint": _layout_fingerprint(layout),
        "moved_module_count": len(moved_modules),
        "moved_modules": moved_modules,
        "selected_strategy": meta.get("selected_strategy"),
        "objective": objective,
        "objective_key": (
            list(objective_v3.objective_key(objective)) if objective else None
        ),
        "tour_p95_m": tour.get("p95_m"),
        "tour_average_m": tour.get("average_m"),
        "tour_coverage_pct": tour.get("coverage_pct"),
        "allocation_candidate_count": meta.get("candidate_count"),
        "production_authority": False,
    }


def _inactive_result(
    *,
    baseline: dict[str, Any],
    layout: dict[str, Any],
    reason: str,
    max_layout_candidates: int,
    max_allocation_candidates: int,
) -> dict[str, Any]:
    result = deepcopy(baseline)
    result["physical_layout"] = deepcopy(layout)
    result["physical_layout_optimizer"] = {
        "optimizer_version": PHYSICAL_LAYOUT_OPTIMIZER_VERSION,
        "allowed": True,
        "effective": False,
        "reason": reason,
        "production_authority": False,
        "physical_relocation_authority": False,
        "installation_approved": False,
        "baseline_preserved": True,
        "improved": False,
        "selected_layout_label": "baseline",
        "selected_layout_fingerprint": _layout_fingerprint(layout),
        "baseline_layout_fingerprint": _layout_fingerprint(layout),
        "selected_moved_modules": [],
        "layout_candidate_budget": max_layout_candidates,
        "allocation_candidate_budget_per_layout": max_allocation_candidates,
        "eligible_relocation_pair_count": 0,
        "evaluated_layout_count": 1,
        "rejected_layout_count": 0,
        "candidates": [
            _candidate_summary(
                label="baseline",
                layout=layout,
                result=baseline,
                moved_modules=[],
            )
        ],
        "alternatives": [],
        "evidence_boundary": (
            "no eligible equivalent relocatable fixture pair was available; "
            "baseline remains unchanged"
        ),
    }
    return result


def optimize_physical_layout(
    *,
    products: list[dict[str, Any]],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: list[dict[str, Any]],
    mode: str = "HYBRID",
    max_layout_candidates: int = DEFAULT_LAYOUT_CANDIDATES,
    max_allocation_candidates: int = DEFAULT_ALLOCATION_CANDIDATES,
    require_images: bool = True,
) -> dict[str, Any]:
    """Search a bounded set of safe equivalent-fixture relocations."""
    max_layout_candidates = max(
        1,
        min(int(max_layout_candidates), MAX_LAYOUT_CANDIDATES),
    )
    max_allocation_candidates = max(
        8,
        min(int(max_allocation_candidates), MAX_ALLOCATION_CANDIDATES),
    )
    architecture = (store_dna or {}).get("architecture") or {}
    if int(_number(architecture.get("schema_version"), 0)) != 1:
        return {
            "optimizer_version": PHYSICAL_LAYOUT_OPTIMIZER_VERSION,
            "allowed": False,
            "effective": False,
            "reason": "architecture_v1_required_for_v5_relocation_search",
            "production_authority": False,
            "physical_relocation_authority": False,
        }
    if not orders:
        return {
            "optimizer_version": PHYSICAL_LAYOUT_OPTIMIZER_VERSION,
            "allowed": False,
            "effective": False,
            "reason": "order_baskets_missing",
            "production_authority": False,
            "physical_relocation_authority": False,
        }

    baseline_truth = layout_architecture_report(layout, store_dna)
    if not baseline_truth.get("valid"):
        return {
            "optimizer_version": PHYSICAL_LAYOUT_OPTIMIZER_VERSION,
            "allowed": False,
            "effective": False,
            "reason": "baseline_layout_architecture_invalid",
            "blockers": baseline_truth.get("blockers") or [],
            "production_authority": False,
            "physical_relocation_authority": False,
        }

    baseline = allocation_v4.optimize_production_plan(
        products=deepcopy(products),
        layout=deepcopy(layout),
        store_dna=deepcopy(store_dna),
        orders=deepcopy(orders),
        mode=mode,
        require_images=require_images,
        max_candidates=max_allocation_candidates,
    )
    baseline_meta = _selected_meta(baseline)
    baseline_objective = baseline_meta.get("selected_objective")
    if not isinstance(baseline_objective, dict):
        return {
            **baseline,
            "physical_layout_optimizer": {
                "optimizer_version": PHYSICAL_LAYOUT_OPTIMIZER_VERSION,
                "allowed": False,
                "effective": False,
                "reason": "baseline_basket_objective_unavailable",
                "production_authority": False,
                "physical_relocation_authority": False,
            },
        }

    pairs = _relocation_pairs(layout)
    if not pairs:
        return _inactive_result(
            baseline=baseline,
            layout=layout,
            reason="no_eligible_relocation_pairs",
            max_layout_candidates=max_layout_candidates,
            max_allocation_candidates=max_allocation_candidates,
        )

    candidates: list[
        tuple[
            tuple[float, ...],
            int,
            str,
            dict[str, Any],
            dict[str, Any],
            list[str],
        ]
    ] = [
        (
            objective_v3.objective_key(baseline_objective),
            0,
            "baseline",
            deepcopy(layout),
            baseline,
            [],
        )
    ]
    rejected: list[dict[str, Any]] = []
    for order, (left_key, right_key) in enumerate(
        pairs[: max(0, max_layout_candidates - 1)],
        start=1,
    ):
        candidate_layout = _swap_spatial_pose(layout, left_key, right_key)
        truth = layout_architecture_report(candidate_layout, store_dna)
        if not truth.get("valid"):
            rejected.append(
                {
                    "label": f"swap::{left_key}<->{right_key}",
                    "reason": "layout_architecture_invalid",
                    "blockers": truth.get("blockers") or [],
                }
            )
            continue
        candidate_result = allocation_v4.optimize_production_plan(
            products=deepcopy(products),
            layout=candidate_layout,
            store_dna=deepcopy(store_dna),
            orders=deepcopy(orders),
            mode=mode,
            require_images=require_images,
            max_candidates=max_allocation_candidates,
        )
        meta = _selected_meta(candidate_result)
        objective = meta.get("selected_objective")
        if not isinstance(objective, dict):
            rejected.append(
                {
                    "label": f"swap::{left_key}<->{right_key}",
                    "reason": "basket_objective_unavailable",
                    "blockers": [],
                }
            )
            continue
        candidates.append(
            (
                objective_v3.objective_key(objective),
                order,
                f"swap::{left_key}<->{right_key}",
                candidate_layout,
                candidate_result,
                [left_key, right_key],
            )
        )

    selected = min(candidates, key=lambda row: (row[0], row[1]))
    selected_key, _, selected_label, selected_layout, selected_result, moved = (
        selected
    )
    baseline_key = objective_v3.objective_key(baseline_objective)
    if selected_key > baseline_key:
        selected_key = baseline_key
        selected_label = "baseline"
        selected_layout = deepcopy(layout)
        selected_result = baseline
        moved = []

    ranked = sorted(candidates, key=lambda row: (row[0], row[1]))
    summaries = [
        _candidate_summary(
            label=label,
            layout=candidate_layout,
            result=result,
            moved_modules=moved_modules,
        )
        for _, _, label, candidate_layout, result, moved_modules in ranked
    ]
    result = deepcopy(selected_result)
    result["physical_layout"] = selected_layout
    result["physical_layout_optimizer"] = {
        "optimizer_version": PHYSICAL_LAYOUT_OPTIMIZER_VERSION,
        "allowed": True,
        "effective": True,
        "production_authority": False,
        "physical_relocation_authority": False,
        "installation_approved": False,
        "baseline_preserved": selected_key <= baseline_key,
        "improved": selected_key < baseline_key,
        "selected_layout_label": selected_label,
        "selected_layout_fingerprint": _layout_fingerprint(selected_layout),
        "baseline_layout_fingerprint": _layout_fingerprint(layout),
        "selected_moved_modules": moved,
        "layout_candidate_budget": max_layout_candidates,
        "allocation_candidate_budget_per_layout": max_allocation_candidates,
        "eligible_relocation_pair_count": len(pairs),
        "evaluated_layout_count": len(candidates),
        "rejected_layout_count": len(rejected),
        "rejected_layouts": rejected[:50],
        "candidates": summaries,
        "alternatives": summaries[:MAX_ALTERNATIVES],
        "evidence_boundary": (
            "relocation search covers only explicitly relocatable equivalent "
            "fixtures; CAPEX, utilities, installer feasibility and live KPI "
            "effects remain external"
        ),
        "promotion_blockers": [
            "physical_fixture_move_cost_attestation_required",
            "installation_engineering_review_required",
            "blind_expert_benchmark_required",
            "real_store_kpi_backtest_required",
        ],
    }
    return result
