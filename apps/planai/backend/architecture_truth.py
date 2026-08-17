"""Architecture-aware physical truth and walk-distance primitives for PlanAI.

This module is intentionally dependency-free and deterministic. It introduces the
first canonical contract for a measured store floorplate, fixed architectural
obstacles, circulation anchors and module coordinates without weakening the
existing product/fixture physical-truth gates.

Architecture is opt-in during migration: legacy Store DNA remains readable. Once
an ``architecture`` object is supplied, however, the contract is fail-closed and
invalid geometry must never be treated as authoritative physical truth.
"""

from __future__ import annotations

import hashlib
import heapq
import json
from collections import deque
from typing import Any, Iterable

ARCHITECTURE_CONTRACT_VERSION = "store-architecture-v1"
ROUTE_OBJECTIVE_VERSION = "architecture-grid-astar-v1"
DEFAULT_GRID_RESOLUTION_M = 0.5
DEFAULT_EGRESS_CLEARANCE_M = 1.0

ARCHITECTURE_TYPES = {
    "wall",
    "column",
    "door",
    "emergency_exit",
    "no_go",
    "technical",
    "inbound",
    "dispatch",
    "picker_entry",
    "picker_exit",
    "chiller",
    "freezer",
}
WALK_BLOCKING_TYPES = {"wall", "column", "no_go", "technical"}
PLACEMENT_BLOCKING_TYPES = WALK_BLOCKING_TYPES | {"emergency_exit"}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _rect(
    *,
    x_m: float,
    y_m: float,
    width_m: float,
    depth_m: float,
    rotation_deg: float = 0.0,
    inflate_m: float = 0.0,
) -> tuple[float, float, float, float] | None:
    """Return an axis-aligned rectangle for orthogonal CAD geometry.

    V1 intentionally accepts only orthogonal rotations. This makes collision and
    routing semantics deterministic and explainable while leaving a clean path
    to polygon geometry in a later contract revision.
    """
    rotation = rotation_deg % 360.0
    if min(abs(rotation - allowed) for allowed in (0.0, 90.0, 180.0, 270.0, 360.0)) > 1e-6:
        return None
    if 45.0 <= rotation < 135.0 or 225.0 <= rotation < 315.0:
        width_m, depth_m = depth_m, width_m
    return (
        x_m - inflate_m,
        y_m - inflate_m,
        x_m + width_m + inflate_m,
        y_m + depth_m + inflate_m,
    )


def _intersects(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return not (
        left[2] <= right[0]
        or right[2] <= left[0]
        or left[3] <= right[1]
        or right[3] <= left[1]
    )


def _contains_point(rect: tuple[float, float, float, float], x_m: float, y_m: float) -> bool:
    return rect[0] <= x_m <= rect[2] and rect[1] <= y_m <= rect[3]


def _element_rect(element: dict[str, Any], *, egress_clearance: bool = False):
    width = _num(element.get("width_m"))
    depth = _num(element.get("depth_m"))
    if width <= 0 or depth <= 0:
        return None
    clearance = 0.0
    if egress_clearance and _text(element.get("element_type")).lower() == "emergency_exit":
        clearance = max(
            DEFAULT_EGRESS_CLEARANCE_M,
            _num(element.get("clearance_m"), DEFAULT_EGRESS_CLEARANCE_M),
        )
    return _rect(
        x_m=_num(element.get("x_m")),
        y_m=_num(element.get("y_m")),
        width_m=width,
        depth_m=depth,
        rotation_deg=_num(element.get("rotation_deg")),
        inflate_m=clearance,
    )


def architecture_fingerprint(architecture: dict[str, Any]) -> str:
    payload = json.dumps(
        architecture,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def architecture_truth_report(store_dna: dict[str, Any] | None) -> dict[str, Any]:
    architecture = (store_dna or {}).get("architecture")
    if not isinstance(architecture, dict) or not architecture:
        return {
            "contract": ARCHITECTURE_CONTRACT_VERSION,
            "present": False,
            "valid": False,
            "authoritative": False,
            "blockers": ["architecture_missing"],
            "fingerprint": None,
        }

    blockers: list[str] = []
    if int(_num(architecture.get("schema_version"), 0)) != 1:
        blockers.append("architecture_schema_version_unsupported")
    if _text(architecture.get("coordinate_system")) != "cartesian_m":
        blockers.append("architecture_coordinate_system_invalid")

    floor_width = _num(architecture.get("floor_width_m"))
    floor_depth = _num(architecture.get("floor_depth_m"))
    if floor_width <= 0 or floor_depth <= 0:
        blockers.append("architecture_floorplate_invalid")

    elements = architecture.get("elements") or []
    if not isinstance(elements, list):
        elements = []
        blockers.append("architecture_elements_invalid")

    seen_ids: set[str] = set()
    picker_entries = 0
    invalid_elements: list[str] = []
    floor_rect = (0.0, 0.0, floor_width, floor_depth)

    for index, raw in enumerate(elements):
        if not isinstance(raw, dict):
            invalid_elements.append(f"index:{index}")
            continue
        element_id = _text(raw.get("element_id")) or f"index:{index}"
        element_type = _text(raw.get("element_type")).lower()
        if element_id in seen_ids:
            blockers.append(f"architecture_duplicate_element_id:{element_id}")
            continue
        seen_ids.add(element_id)
        if element_type not in ARCHITECTURE_TYPES:
            invalid_elements.append(element_id)
            continue
        if element_type == "picker_entry":
            picker_entries += 1

        rect = _element_rect(raw)
        if rect is None:
            invalid_elements.append(element_id)
            continue
        if floor_width > 0 and floor_depth > 0:
            if rect[0] < 0 or rect[1] < 0 or rect[2] > floor_rect[2] or rect[3] > floor_rect[3]:
                blockers.append(f"architecture_element_outside_floorplate:{element_id}")

    if invalid_elements:
        blockers.append("architecture_invalid_elements:" + ",".join(sorted(invalid_elements)[:20]))
    if picker_entries == 0:
        blockers.append("architecture_picker_entry_missing")
    elif picker_entries > 1:
        blockers.append("architecture_picker_entry_ambiguous")

    source = _text(architecture.get("source"))
    source_ref = _text(architecture.get("source_ref"))
    measured = source in {"manual_survey", "cad_import", "floorplan_import", "lidar_scan"}
    if not measured:
        blockers.append("architecture_source_not_measured")
    if not source_ref:
        blockers.append("architecture_source_ref_missing")

    return {
        "contract": ARCHITECTURE_CONTRACT_VERSION,
        "present": True,
        "valid": not blockers,
        "authoritative": not blockers,
        "source": source or None,
        "source_ref": source_ref or None,
        "floor_width_m": floor_width or None,
        "floor_depth_m": floor_depth or None,
        "element_count": len(elements),
        "picker_entry_count": picker_entries,
        "blockers": blockers,
        "fingerprint": architecture_fingerprint(architecture),
    }


def _module_dimensions(module: dict[str, Any]) -> tuple[float, float]:
    width = _num(module.get("width_m"))
    depth = _num(module.get("depth_m"))
    if width <= 0:
        width = _num(module.get("width_cm")) / 100.0
    if depth <= 0:
        depth = _num(module.get("depth_cm")) / 100.0
    shelves = module.get("shelves") or []
    if shelves:
        first = shelves[0] or {}
        if width <= 0:
            width = _num(first.get("shelf_width_cm")) / 100.0
        if depth <= 0:
            depth = _num(first.get("shelf_depth_cm")) / 100.0
    return width, depth


def _module_rect(module: dict[str, Any]):
    x_m = _num(module.get("x_m"), float("nan"))
    y_m = _num(module.get("y_m"), float("nan"))
    if x_m != x_m or y_m != y_m:  # NaN-safe missing check.
        return None
    width, depth = _module_dimensions(module)
    if width <= 0 or depth <= 0:
        return None
    return _rect(
        x_m=x_m,
        y_m=y_m,
        width_m=width,
        depth_m=depth,
        rotation_deg=_num(module.get("rotation_deg")),
    )


def iter_layout_modules(layout: dict[str, Any] | None):
    for aisle in (layout or {}).get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            yield aisle, module


def layout_architecture_report(
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
) -> dict[str, Any]:
    truth = architecture_truth_report(store_dna)
    modules = list(iter_layout_modules(layout))
    if not truth["present"]:
        return {
            "required": False,
            "valid": True,
            "module_count": len(modules),
            "coordinate_coverage_pct": 0.0,
            "violations": [],
            "blockers": [],
        }
    if not truth["valid"]:
        return {
            "required": True,
            "valid": False,
            "module_count": len(modules),
            "coordinate_coverage_pct": 0.0,
            "violations": [],
            "blockers": list(truth["blockers"]),
        }

    architecture = (store_dna or {})["architecture"]
    floor = (0.0, 0.0, truth["floor_width_m"], truth["floor_depth_m"])
    obstacles = []
    for element in architecture.get("elements") or []:
        element_type = _text(element.get("element_type")).lower()
        if element_type not in PLACEMENT_BLOCKING_TYPES:
            continue
        rect = _element_rect(element, egress_clearance=True)
        if rect is not None:
            obstacles.append((element_type, _text(element.get("element_id")), rect))

    coordinate_count = 0
    violations: list[dict[str, Any]] = []
    for _, module in modules:
        module_id = _text(module.get("module_id"))
        rect = _module_rect(module)
        if rect is None:
            violations.append({"type": "module_geometry_missing", "module_id": module_id})
            continue
        coordinate_count += 1
        if rect[0] < 0 or rect[1] < 0 or rect[2] > floor[2] or rect[3] > floor[3]:
            violations.append({"type": "module_outside_floorplate", "module_id": module_id})
        for element_type, element_id, obstacle in obstacles:
            if _intersects(rect, obstacle):
                violations.append(
                    {
                        "type": "module_architecture_collision",
                        "module_id": module_id,
                        "element_id": element_id,
                        "element_type": element_type,
                    }
                )

    pct = round(coordinate_count * 100.0 / len(modules), 2) if modules else 0.0
    blockers = []
    if modules and coordinate_count != len(modules):
        blockers.append("layout_module_geometry_incomplete")
    if violations:
        blockers.append("layout_architecture_hard_violation")
    return {
        "required": True,
        "valid": not blockers,
        "module_count": len(modules),
        "coordinate_module_count": coordinate_count,
        "coordinate_coverage_pct": pct,
        "violation_count": len(violations),
        "violations": violations,
        "blockers": blockers,
    }


def _picker_entry(architecture: dict[str, Any]) -> tuple[float, float] | None:
    for element in architecture.get("elements") or []:
        if _text(element.get("element_type")).lower() != "picker_entry":
            continue
        rect = _element_rect(element)
        if rect is not None:
            return ((rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0)
    return None


def _module_center(module: dict[str, Any]) -> tuple[float, float] | None:
    rect = _module_rect(module)
    if rect is None:
        return None
    return ((rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0)


def _walk_obstacles(architecture: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    obstacles = []
    for element in architecture.get("elements") or []:
        if _text(element.get("element_type")).lower() not in WALK_BLOCKING_TYPES:
            continue
        rect = _element_rect(element)
        if rect is not None:
            obstacles.append(rect)
    return obstacles


def _distance_field(
    architecture: dict[str, Any],
    *,
    resolution_m: float,
) -> tuple[dict[tuple[int, int], float], tuple[int, int]] | None:
    width = _num(architecture.get("floor_width_m"))
    depth = _num(architecture.get("floor_depth_m"))
    start = _picker_entry(architecture)
    if width <= 0 or depth <= 0 or start is None:
        return None

    cols = max(1, int(width / resolution_m) + 1)
    rows = max(1, int(depth / resolution_m) + 1)
    obstacles = _walk_obstacles(architecture)

    def to_cell(point: tuple[float, float]) -> tuple[int, int]:
        return (
            max(0, min(cols - 1, int(round(point[0] / resolution_m)))),
            max(0, min(rows - 1, int(round(point[1] / resolution_m)))),
        )

    def blocked(cell: tuple[int, int]) -> bool:
        x_m = cell[0] * resolution_m
        y_m = cell[1] * resolution_m
        return any(_contains_point(rect, x_m, y_m) for rect in obstacles)

    start_cell = to_cell(start)
    if blocked(start_cell):
        return None

    distances = {start_cell: 0.0}
    queue: deque[tuple[int, int]] = deque([start_cell])
    while queue:
        cell = queue.popleft()
        next_distance = distances[cell] + resolution_m
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (cell[0] + dx, cell[1] + dy)
            if not (0 <= nxt[0] < cols and 0 <= nxt[1] < rows):
                continue
            if nxt in distances or blocked(nxt):
                continue
            distances[nxt] = next_distance
            queue.append(nxt)
    return distances, start_cell


def _sales(row: dict[str, Any]) -> float:
    for field in ("sales_qty_7d", "sales_7d", "qty_7d", "weekly_sales", "sales_qty"):
        value = _num(row.get(field), -1.0)
        if value >= 0:
            return value
    return 0.0


def _sku(row: dict[str, Any]) -> str:
    return _text(row.get("sku") or row.get("SKU"))


def _iter_placed(planogram: dict[str, Any] | None):
    for aisle in (planogram or {}).get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            for shelf in module.get("shelves", []) or []:
                for product in shelf.get("products", []) or []:
                    yield aisle, module, shelf, product


def architecture_route_objective(
    result: dict[str, Any],
    source_products: Iterable[dict[str, Any]],
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
    *,
    resolution_m: float = DEFAULT_GRID_RESOLUTION_M,
) -> dict[str, Any]:
    """Return obstacle-aware, sales-weighted walk distance when geometry permits.

    This is a single-origin travel objective, not yet a multi-order picker-tour
    simulation. It is nevertheless physical: distances are measured in metres on
    the approved floorplate while walls/columns/no-go/technical areas are blocked.
    """
    truth = architecture_truth_report(store_dna)
    layout_report = layout_architecture_report(layout, store_dna)
    if not truth["present"]:
        return {"available": False, "basis": "legacy_rank_v1", "reason": "architecture_missing"}
    if not truth["valid"] or not layout_report["valid"]:
        return {
            "available": False,
            "basis": "legacy_rank_v1",
            "reason": "architecture_truth_invalid",
            "blockers": list(truth.get("blockers") or []) + list(layout_report.get("blockers") or []),
        }

    architecture = (store_dna or {})["architecture"]
    field = _distance_field(architecture, resolution_m=resolution_m)
    if field is None:
        return {"available": False, "basis": "legacy_rank_v1", "reason": "picker_route_origin_unreachable"}
    distances, _ = field
    width = _num(architecture.get("floor_width_m"))
    depth = _num(architecture.get("floor_depth_m"))
    cols = max(1, int(width / resolution_m) + 1)
    rows = max(1, int(depth / resolution_m) + 1)

    def to_cell(point: tuple[float, float]) -> tuple[int, int]:
        return (
            max(0, min(cols - 1, int(round(point[0] / resolution_m)))),
            max(0, min(rows - 1, int(round(point[1] / resolution_m)))),
        )

    source_sales = {_sku(row): _sales(row) for row in source_products}
    layout_modules = {
        _text(module.get("module_id")): module for _, module in iter_layout_modules(layout)
    }
    distance_cache: dict[str, float | None] = {}
    unreachable: set[str] = set()
    weighted_cost = 0.0
    placed_count = 0

    for _, placed_module, _, product in _iter_placed(result.get("planogram")):
        module_id = _text(placed_module.get("module_id"))
        module = layout_modules.get(module_id, placed_module)
        if module_id not in distance_cache:
            center = _module_center(module)
            distance_cache[module_id] = None if center is None else distances.get(to_cell(center))
        distance = distance_cache[module_id]
        placed_count += 1
        if distance is None:
            unreachable.add(module_id)
            continue
        weighted_cost += distance * max(1.0, source_sales.get(_sku(product), _sales(product)))

    if unreachable:
        return {
            "available": False,
            "basis": "legacy_rank_v1",
            "reason": "placed_module_unreachable",
            "unreachable_module_ids": sorted(unreachable),
        }

    return {
        "available": True,
        "basis": ROUTE_OBJECTIVE_VERSION,
        "metric": "sales_weighted_single_origin_walk_m",
        "value": round(weighted_cost, 6),
        "grid_resolution_m": resolution_m,
        "placed_product_count": placed_count,
        "module_distance_count": len(distance_cache),
        "architecture_fingerprint": truth["fingerprint"],
    }
