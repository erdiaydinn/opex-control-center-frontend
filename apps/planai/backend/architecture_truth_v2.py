"""Preview-only arbitrary-angle spatial truth for PlanAI.

Architecture V1 remains the production-facing contract. V2 preserves measured
camera/CAD angles as oriented polygons so scans are never snapped to an axis and
adds bounded polygon-aware collision and route evidence for market-leadership
benchmarking.
"""

from __future__ import annotations

import hashlib
import heapq
import json
from math import hypot, isfinite
from typing import Any

from shapely.affinity import rotate
from shapely.geometry import Point, Polygon, box

ARCHITECTURE_V2_CONTRACT_VERSION = "store-architecture-v2-oriented-polygons"
ROUTE_V2_OBJECTIVE_VERSION = "architecture-polygon-astar-v2"
DEFAULT_GRID_RESOLUTION_M = 0.25
DEFAULT_EGRESS_CLEARANCE_M = 1.0
MAX_ROUTE_PATH_POINTS = 160
MAX_ROUTE_GRID_CELLS = 250_000

ARCHITECTURE_TYPES = {
    "wall",
    "column",
    "door",
    "opening",
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
MEASURED_SOURCES = {
    "manual_survey",
    "cad_import",
    "floorplan_import",
    "lidar_scan",
}
ORTHOGONAL_ROTATIONS = (0.0, 90.0, 180.0, 270.0, 360.0)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _is_non_orthogonal(rotation_deg: float) -> bool:
    rotation = rotation_deg % 360.0
    return min(abs(rotation - value) for value in ORTHOGONAL_ROTATIONS) > 1e-6


def _centered_rect(
    *,
    center_x_m: float,
    center_y_m: float,
    width_m: float,
    depth_m: float,
    rotation_deg: float = 0.0,
    inflate_m: float = 0.0,
) -> Polygon | None:
    if width_m <= 0 or depth_m <= 0 or inflate_m < 0:
        return None
    half_width = width_m / 2.0 + inflate_m
    half_depth = depth_m / 2.0 + inflate_m
    polygon = box(
        center_x_m - half_width,
        center_y_m - half_depth,
        center_x_m + half_width,
        center_y_m + half_depth,
    )
    if rotation_deg % 360.0:
        polygon = rotate(
            polygon,
            rotation_deg,
            origin=(center_x_m, center_y_m),
            use_radians=False,
        )
    return polygon


def _center(
    row: dict[str, Any],
    *,
    width_m: float,
    depth_m: float,
) -> tuple[float, float] | None:
    center_x = _number(row.get("center_x_m"))
    center_y = _number(row.get("center_y_m"))
    if center_x is not None and center_y is not None:
        return center_x, center_y
    x_m = _number(row.get("x_m"))
    y_m = _number(row.get("y_m"))
    if x_m is None or y_m is None:
        return None
    return x_m + width_m / 2.0, y_m + depth_m / 2.0


def _element_polygon(
    element: dict[str, Any],
    *,
    egress_clearance: bool = False,
) -> Polygon | None:
    width = _number(element.get("width_m"))
    depth = _number(element.get("depth_m"))
    if width is None or depth is None or width <= 0 or depth <= 0:
        return None
    center = _center(element, width_m=width, depth_m=depth)
    if center is None:
        return None
    clearance = 0.0
    if (
        egress_clearance
        and _text(element.get("element_type")).lower() == "emergency_exit"
    ):
        clearance = max(
            DEFAULT_EGRESS_CLEARANCE_M,
            _number(element.get("clearance_m")) or DEFAULT_EGRESS_CLEARANCE_M,
        )
    return _centered_rect(
        center_x_m=center[0],
        center_y_m=center[1],
        width_m=width,
        depth_m=depth,
        rotation_deg=_number(element.get("rotation_deg")) or 0.0,
        inflate_m=clearance,
    )


def _module_dimensions(module: dict[str, Any]) -> tuple[float, float]:
    width = _number(module.get("width_m")) or 0.0
    depth = _number(module.get("depth_m")) or 0.0
    if width <= 0:
        width = (_number(module.get("module_width_cm")) or 0.0) / 100.0
    if depth <= 0:
        depth = (_number(module.get("module_depth_cm")) or 0.0) / 100.0
    if width <= 0:
        width = (_number(module.get("width_cm")) or 0.0) / 100.0
    if depth <= 0:
        depth = (_number(module.get("depth_cm")) or 0.0) / 100.0
    shelves = module.get("shelves") or []
    if shelves:
        first = shelves[0] or {}
        if width <= 0:
            width = (_number(first.get("shelf_width_cm")) or 0.0) / 100.0
        if depth <= 0:
            depth = (_number(first.get("shelf_depth_cm")) or 0.0) / 100.0
    return width, depth


def _module_polygon(module: dict[str, Any]) -> Polygon | None:
    width, depth = _module_dimensions(module)
    if width <= 0 or depth <= 0:
        return None
    center = _center(module, width_m=width, depth_m=depth)
    if center is None:
        return None
    return _centered_rect(
        center_x_m=center[0],
        center_y_m=center[1],
        width_m=width,
        depth_m=depth,
        rotation_deg=_number(module.get("rotation_deg")) or 0.0,
    )


def _fingerprint(architecture: dict[str, Any]) -> str:
    payload = json.dumps(
        architecture,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def architecture_truth_report_v2(
    store_dna: dict[str, Any] | None,
) -> dict[str, Any]:
    architecture = (store_dna or {}).get("architecture")
    if not isinstance(architecture, dict) or not architecture:
        return {
            "contract": ARCHITECTURE_V2_CONTRACT_VERSION,
            "present": False,
            "valid": False,
            "authoritative": False,
            "preview_only": True,
            "blockers": ["architecture_missing"],
            "fingerprint": None,
        }

    blockers: list[str] = []
    if round(_number(architecture.get("schema_version")) or 0) != 2:
        blockers.append("architecture_schema_version_unsupported")
    coordinate_system = _text(architecture.get("coordinate_system"))
    if coordinate_system not in {"cartesian_m_centered_rect", "cartesian_m"}:
        blockers.append("architecture_coordinate_system_invalid")

    floor_width = _number(architecture.get("floor_width_m")) or 0.0
    floor_depth = _number(architecture.get("floor_depth_m")) or 0.0
    if floor_width <= 0 or floor_depth <= 0:
        blockers.append("architecture_floorplate_invalid")
    floor = box(0.0, 0.0, max(0.0, floor_width), max(0.0, floor_depth))

    elements = architecture.get("elements") or []
    if not isinstance(elements, list):
        elements = []
        blockers.append("architecture_elements_invalid")

    seen: set[str] = set()
    invalid: list[str] = []
    picker_entries = 0
    non_orthogonal_count = 0
    for index, raw in enumerate(elements):
        if not isinstance(raw, dict):
            invalid.append(f"index:{index}")
            continue
        element_id = _text(raw.get("element_id")) or f"index:{index}"
        if element_id in seen:
            blockers.append(f"architecture_duplicate_element_id:{element_id}")
            continue
        seen.add(element_id)
        element_type = _text(raw.get("element_type")).lower()
        if element_type not in ARCHITECTURE_TYPES:
            invalid.append(element_id)
            continue
        if element_type == "picker_entry":
            picker_entries += 1
        rotation = _number(raw.get("rotation_deg")) or 0.0
        if _is_non_orthogonal(rotation):
            non_orthogonal_count += 1
        polygon = _element_polygon(raw)
        if polygon is None or polygon.is_empty or not polygon.is_valid:
            invalid.append(element_id)
            continue
        if floor_width > 0 and floor_depth > 0 and not floor.covers(polygon):
            blockers.append(f"architecture_element_outside_floorplate:{element_id}")

    if invalid:
        blockers.append(
            "architecture_invalid_elements:" + ",".join(sorted(invalid)[:20])
        )
    if picker_entries == 0:
        blockers.append("architecture_picker_entry_missing")
    elif picker_entries > 1:
        blockers.append("architecture_picker_entry_ambiguous")

    source = _text(architecture.get("source"))
    source_ref = _text(architecture.get("source_ref"))
    if source not in MEASURED_SOURCES:
        blockers.append("architecture_source_not_measured")
    if not source_ref:
        blockers.append("architecture_source_ref_missing")

    return {
        "contract": ARCHITECTURE_V2_CONTRACT_VERSION,
        "present": True,
        "valid": not blockers,
        "authoritative": False,
        "preview_only": True,
        "source": source or None,
        "source_ref": source_ref or None,
        "floor_width_m": floor_width or None,
        "floor_depth_m": floor_depth or None,
        "element_count": len(elements),
        "picker_entry_count": picker_entries,
        "non_orthogonal_element_count": non_orthogonal_count,
        "blockers": blockers,
        "fingerprint": _fingerprint(architecture),
    }


def iter_layout_modules(layout: dict[str, Any] | None):
    for aisle in (layout or {}).get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            yield aisle, module


def _spatial_module_id(aisle: dict[str, Any], module: dict[str, Any]) -> str:
    module_id = _text(module.get("module_id"))
    aisle_id = _text(aisle.get("aisle_id"))
    if "::" in module_id or not aisle_id:
        return module_id
    return f"{aisle_id}::{module_id}"


def layout_architecture_report_v2(
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
) -> dict[str, Any]:
    truth = architecture_truth_report_v2(store_dna)
    modules = list(iter_layout_modules(layout))
    if not truth["valid"]:
        return {
            "contract": ARCHITECTURE_V2_CONTRACT_VERSION,
            "preview_only": True,
            "valid": False,
            "module_count": len(modules),
            "coordinate_coverage_pct": 0.0,
            "violations": [],
            "blockers": list(truth["blockers"]),
        }

    architecture = (store_dna or {})["architecture"]
    floor = box(0.0, 0.0, truth["floor_width_m"], truth["floor_depth_m"])
    obstacles: list[tuple[str, str, Polygon]] = []
    for element in architecture.get("elements") or []:
        element_type = _text(element.get("element_type")).lower()
        if element_type not in PLACEMENT_BLOCKING_TYPES:
            continue
        polygon = _element_polygon(element, egress_clearance=True)
        if polygon is not None:
            obstacles.append(
                (element_type, _text(element.get("element_id")), polygon)
            )

    coordinate_count = 0
    non_orthogonal_module_count = 0
    violations: list[dict[str, Any]] = []
    for aisle, module in modules:
        module_id = _spatial_module_id(aisle, module)
        polygon = _module_polygon(module)
        if polygon is None:
            violations.append(
                {"type": "module_geometry_missing", "module_id": module_id}
            )
            continue
        coordinate_count += 1
        if _is_non_orthogonal(_number(module.get("rotation_deg")) or 0.0):
            non_orthogonal_module_count += 1
        if not floor.covers(polygon):
            violations.append(
                {"type": "module_outside_floorplate", "module_id": module_id}
            )
        for element_type, element_id, obstacle in obstacles:
            if polygon.intersects(obstacle) and not polygon.touches(obstacle):
                violations.append(
                    {
                        "type": "module_architecture_collision",
                        "module_id": module_id,
                        "element_id": element_id,
                        "element_type": element_type,
                    }
                )

    coverage = (
        round(coordinate_count * 100.0 / len(modules), 2) if modules else 0.0
    )
    blockers: list[str] = []
    if modules and coordinate_count != len(modules):
        blockers.append("layout_module_geometry_incomplete")
    if violations:
        blockers.append("layout_architecture_hard_violation")
    return {
        "contract": ARCHITECTURE_V2_CONTRACT_VERSION,
        "preview_only": True,
        "valid": not blockers,
        "module_count": len(modules),
        "coordinate_module_count": coordinate_count,
        "coordinate_coverage_pct": coverage,
        "non_orthogonal_module_count": non_orthogonal_module_count,
        "violation_count": len(violations),
        "violations": violations,
        "blockers": blockers,
    }


def _picker_entry_center(
    architecture: dict[str, Any],
) -> tuple[float, float] | None:
    for element in architecture.get("elements") or []:
        if _text(element.get("element_type")).lower() != "picker_entry":
            continue
        polygon = _element_polygon(element)
        if polygon is not None:
            center = polygon.centroid
            return center.x, center.y
    return None


def _walk_obstacles(architecture: dict[str, Any]) -> list[Polygon]:
    result: list[Polygon] = []
    for element in architecture.get("elements") or []:
        if _text(element.get("element_type")).lower() not in WALK_BLOCKING_TYPES:
            continue
        polygon = _element_polygon(element)
        if polygon is not None:
            result.append(polygon)
    return result


def _sample_path(
    path: list[tuple[float, float]],
    *,
    max_points: int = MAX_ROUTE_PATH_POINTS,
) -> list[list[float]]:
    if len(path) <= max_points:
        return [[round(x, 3), round(y, 3)] for x, y in path]
    stride = max(1, len(path) // (max_points - 1))
    sampled = path[::stride]
    if sampled[-1] != path[-1]:
        sampled.append(path[-1])
    return [[round(x, 3), round(y, 3)] for x, y in sampled[:max_points]]


def route_between_points_v2(
    store_dna: dict[str, Any],
    *,
    target_x_m: float,
    target_y_m: float,
    resolution_m: float = DEFAULT_GRID_RESOLUTION_M,
) -> dict[str, Any]:
    """Return a bounded 8-neighbour A* route around oriented obstacles."""
    truth = architecture_truth_report_v2(store_dna)
    if not truth["valid"]:
        return {
            "contract": ROUTE_V2_OBJECTIVE_VERSION,
            "preview_only": True,
            "available": False,
            "reason": "architecture_v2_invalid",
            "blockers": list(truth["blockers"]),
        }
    if not 0.1 <= resolution_m <= 1.0:
        return {
            "contract": ROUTE_V2_OBJECTIVE_VERSION,
            "preview_only": True,
            "available": False,
            "reason": "resolution_out_of_bounds",
        }

    architecture = (store_dna or {})["architecture"]
    start = _picker_entry_center(architecture)
    if start is None:
        return {
            "contract": ROUTE_V2_OBJECTIVE_VERSION,
            "preview_only": True,
            "available": False,
            "reason": "picker_entry_missing",
        }

    width = float(truth["floor_width_m"])
    depth = float(truth["floor_depth_m"])
    target = float(target_x_m), float(target_y_m)
    floor = box(0.0, 0.0, width, depth)
    if not floor.covers(Point(*target)):
        return {
            "contract": ROUTE_V2_OBJECTIVE_VERSION,
            "preview_only": True,
            "available": False,
            "reason": "target_outside_floorplate",
        }

    cols = max(1, round(width / resolution_m) + 1)
    rows = max(1, round(depth / resolution_m) + 1)
    if cols * rows > MAX_ROUTE_GRID_CELLS:
        return {
            "contract": ROUTE_V2_OBJECTIVE_VERSION,
            "preview_only": True,
            "available": False,
            "reason": "route_grid_too_large",
            "grid_cells": cols * rows,
        }
    obstacles = _walk_obstacles(architecture)

    def to_cell(point: tuple[float, float]) -> tuple[int, int]:
        return (
            max(0, min(cols - 1, round(point[0] / resolution_m))),
            max(0, min(rows - 1, round(point[1] / resolution_m))),
        )

    def to_point(cell: tuple[int, int]) -> tuple[float, float]:
        return cell[0] * resolution_m, cell[1] * resolution_m

    def blocked(cell: tuple[int, int]) -> bool:
        point = Point(*to_point(cell))
        return any(obstacle.covers(point) for obstacle in obstacles)

    start_cell = to_cell(start)
    target_cell = to_cell(target)
    if blocked(start_cell) or blocked(target_cell):
        return {
            "contract": ROUTE_V2_OBJECTIVE_VERSION,
            "preview_only": True,
            "available": False,
            "reason": "endpoint_blocked",
        }

    root_two = 2**0.5
    neighbours = (
        (-1, 0, 1.0),
        (1, 0, 1.0),
        (0, -1, 1.0),
        (0, 1, 1.0),
        (-1, -1, root_two),
        (-1, 1, root_two),
        (1, -1, root_two),
        (1, 1, root_two),
    )
    open_heap: list[tuple[float, float, tuple[int, int]]] = [
        (0.0, 0.0, start_cell)
    ]
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    cost = {start_cell: 0.0}
    visited = 0

    while open_heap:
        _, current_cost, current = heapq.heappop(open_heap)
        if current_cost > cost.get(current, float("inf")) + 1e-12:
            continue
        visited += 1
        if current == target_cell:
            break
        for dx, dy, multiplier in neighbours:
            candidate = current[0] + dx, current[1] + dy
            if not (0 <= candidate[0] < cols and 0 <= candidate[1] < rows):
                continue
            if blocked(candidate):
                continue
            if dx and dy:
                side_x = current[0] + dx, current[1]
                side_y = current[0], current[1] + dy
                if blocked(side_x) or blocked(side_y):
                    continue
            candidate_cost = current_cost + multiplier * resolution_m
            if candidate_cost + 1e-12 >= cost.get(candidate, float("inf")):
                continue
            cost[candidate] = candidate_cost
            came_from[candidate] = current
            point = to_point(candidate)
            heuristic = hypot(point[0] - target[0], point[1] - target[1])
            heapq.heappush(
                open_heap,
                (candidate_cost + heuristic, candidate_cost, candidate),
            )

    if target_cell not in cost:
        return {
            "contract": ROUTE_V2_OBJECTIVE_VERSION,
            "preview_only": True,
            "available": False,
            "reason": "target_unreachable",
            "visited_cells": visited,
        }

    cells = [target_cell]
    while cells[-1] != start_cell:
        cells.append(came_from[cells[-1]])
    cells.reverse()
    path = [to_point(cell) for cell in cells]
    straight = hypot(target[0] - start[0], target[1] - start[1])
    return {
        "contract": ROUTE_V2_OBJECTIVE_VERSION,
        "preview_only": True,
        "available": True,
        "distance_m": round(cost[target_cell], 3),
        "straight_line_m": round(straight, 3),
        "detour_m": round(cost[target_cell] - straight, 3),
        "resolution_m": resolution_m,
        "visited_cells": visited,
        "path_m": _sample_path(path),
    }
