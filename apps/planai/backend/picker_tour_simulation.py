"""Deterministic obstacle-aware picker-tour simulation for measured Planograms.

This is an evaluation primitive, not production evidence by itself. It accepts
explicit observed/test order baskets and a physical Planogram candidate, maps
SKUs to exact spatial fixtures, and computes bounded shortest-path walking tours
on measured Store DNA. It never invents orders or fills missing SKU locations.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise
from math import ceil
from typing import Any

from architecture_truth import (
    DEFAULT_GRID_RESOLUTION_M,
    _contains_point,
    _element_rect,
    _module_center,
    _spatial_module_id,
    _text,
    _walk_obstacles,
    architecture_truth_report,
    iter_layout_modules,
    layout_architecture_report,
)

PICKER_TOUR_SIMULATION_VERSION = "picker-tour-simulation-v1"
MAX_ORDERS_PER_SIMULATION = 5_000
MAX_UNIQUE_STOPS_PER_ORDER = 80
MAX_EXPLAINED_ORDERS = 50
MAX_PATH_POINTS_PER_SEGMENT = 64


@dataclass(frozen=True)
class GridShape:
    width_m: float
    depth_m: float
    resolution_m: float
    columns: int
    rows: int


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _sku(value: Any) -> str:
    return _text(value).upper()


def _point_for_element(
    architecture: dict[str, Any],
    element_type: str,
) -> tuple[float, float] | None:
    for element in architecture.get("elements") or []:
        if _text(element.get("element_type")).lower() != element_type:
            continue
        rect = _element_rect(element)
        if rect is not None:
            return ((rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0)
    return None


class MeasuredGridRouter:
    def __init__(
        self,
        architecture: dict[str, Any],
        *,
        resolution_m: float = DEFAULT_GRID_RESOLUTION_M,
    ) -> None:
        width = _num(architecture.get("floor_width_m"))
        depth = _num(architecture.get("floor_depth_m"))
        if width <= 0 or depth <= 0 or resolution_m <= 0:
            raise ValueError("picker_tour_grid_invalid")
        self.shape = GridShape(
            width_m=width,
            depth_m=depth,
            resolution_m=resolution_m,
            columns=max(1, int(width / resolution_m) + 1),
            rows=max(1, int(depth / resolution_m) + 1),
        )
        self._obstacles = _walk_obstacles(architecture)
        self._fields: dict[
            tuple[int, int],
            tuple[
                dict[tuple[int, int], float],
                dict[tuple[int, int], tuple[int, int]],
            ],
        ] = {}

    def to_cell(self, point: tuple[float, float]) -> tuple[int, int]:
        return (
            max(
                0,
                min(
                    self.shape.columns - 1,
                    round(point[0] / self.shape.resolution_m),
                ),
            ),
            max(
                0,
                min(
                    self.shape.rows - 1,
                    round(point[1] / self.shape.resolution_m),
                ),
            ),
        )

    def point_for_cell(self, cell: tuple[int, int]) -> list[float]:
        return [
            round(cell[0] * self.shape.resolution_m, 3),
            round(cell[1] * self.shape.resolution_m, 3),
        ]

    def blocked(self, cell: tuple[int, int]) -> bool:
        point = self.point_for_cell(cell)
        return any(_contains_point(rect, point[0], point[1]) for rect in self._obstacles)

    def _field(
        self,
        source: tuple[int, int],
    ) -> tuple[
        dict[tuple[int, int], float],
        dict[tuple[int, int], tuple[int, int]],
    ]:
        cached = self._fields.get(source)
        if cached is not None:
            return cached
        if self.blocked(source):
            result = ({}, {})
            self._fields[source] = result
            return result

        distances = {source: 0.0}
        parents: dict[tuple[int, int], tuple[int, int]] = {}
        queue: deque[tuple[int, int]] = deque([source])
        while queue:
            current = queue.popleft()
            candidate_distance = distances[current] + self.shape.resolution_m
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (current[0] + dx, current[1] + dy)
                if not (
                    0 <= nxt[0] < self.shape.columns
                    and 0 <= nxt[1] < self.shape.rows
                ):
                    continue
                if nxt in distances or self.blocked(nxt):
                    continue
                distances[nxt] = candidate_distance
                parents[nxt] = current
                queue.append(nxt)
        result = (distances, parents)
        self._fields[source] = result
        return result

    def distance(
        self,
        source: tuple[int, int],
        target: tuple[int, int],
    ) -> float | None:
        distances, _ = self._field(source)
        return distances.get(target)

    def path(
        self,
        source: tuple[int, int],
        target: tuple[int, int],
    ) -> list[list[float]]:
        distances, parents = self._field(source)
        if target not in distances:
            return []
        if source == target:
            return [self.point_for_cell(source)]
        cells = [target]
        cursor = target
        while cursor != source:
            cursor = parents.get(cursor)
            if cursor is None:
                return []
            cells.append(cursor)
        cells.reverse()
        simplified = _simplify_grid_path(cells)
        return [self.point_for_cell(cell) for cell in simplified]


def _simplify_grid_path(
    path: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    if len(path) <= 2:
        return path
    result = [path[0]]
    direction = (path[1][0] - path[0][0], path[1][1] - path[0][1])
    for index in range(1, len(path) - 1):
        nxt = (
            path[index + 1][0] - path[index][0],
            path[index + 1][1] - path[index][1],
        )
        if nxt != direction:
            result.append(path[index])
            direction = nxt
    result.append(path[-1])
    if len(result) <= MAX_PATH_POINTS_PER_SEGMENT:
        return result
    last = len(result) - 1
    denominator = MAX_PATH_POINTS_PER_SEGMENT - 1
    sampled = [
        result[min(last, round(index * last / denominator))]
        for index in range(MAX_PATH_POINTS_PER_SEGMENT)
    ]
    return list(dict.fromkeys(sampled))


def _plan_sku_locations(
    result: dict[str, Any],
) -> dict[str, str]:
    locations: dict[str, str] = {}
    duplicates: set[str] = set()
    for aisle in (result.get("planogram") or {}).get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            spatial_id = _spatial_module_id(aisle, module)
            for shelf in module.get("shelves", []) or []:
                for product in shelf.get("products", []) or []:
                    sku = _sku(product.get("sku") or product.get("SKU"))
                    if not sku:
                        continue
                    if sku in locations and locations[sku] != spatial_id:
                        duplicates.add(sku)
                    else:
                        locations.setdefault(sku, spatial_id)
    for sku in duplicates:
        locations.pop(sku, None)
    return locations


def _layout_stop_cells(
    layout: dict[str, Any],
    router: MeasuredGridRouter,
) -> dict[str, tuple[int, int]]:
    cells: dict[str, tuple[int, int]] = {}
    for aisle, module in iter_layout_modules(layout):
        center = _module_center(module)
        if center is None:
            continue
        cells[_spatial_module_id(aisle, module)] = router.to_cell(center)
    return cells


def _order_skus(order: dict[str, Any]) -> list[str]:
    raw = order.get("skus")
    if raw is None:
        raw = order.get("items")
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            value = item.get("sku") or item.get("SKU")
        else:
            value = item
        sku = _sku(value)
        if sku:
            result.append(sku)
    return result


def _nearest_neighbor_order(
    router: MeasuredGridRouter,
    start: tuple[int, int],
    stops: list[tuple[str, tuple[int, int]]],
) -> list[tuple[str, tuple[int, int]]] | None:
    remaining = sorted(stops, key=lambda row: row[0])
    ordered: list[tuple[str, tuple[int, int]]] = []
    current = start
    while remaining:
        ranked = []
        for stop in remaining:
            distance = router.distance(current, stop[1])
            if distance is None:
                continue
            ranked.append((distance, stop[0], stop))
        if not ranked:
            return None
        _, _, selected = min(ranked, key=lambda row: (row[0], row[1]))
        ordered.append(selected)
        remaining.remove(selected)
        current = selected[1]
    return ordered


def _tour_distance(
    router: MeasuredGridRouter,
    cells: list[tuple[int, int]],
) -> float | None:
    distance = 0.0
    for source, target in pairwise(cells):
        segment = router.distance(source, target)
        if segment is None:
            return None
        distance += segment
    return round(distance, 6)


def _two_opt(
    router: MeasuredGridRouter,
    start: tuple[int, int],
    ordered: list[tuple[str, tuple[int, int]]],
    end: tuple[int, int],
) -> list[tuple[str, tuple[int, int]]]:
    if len(ordered) < 3:
        return ordered
    best = list(ordered)
    best_distance = _tour_distance(
        router,
        [start] + [stop[1] for stop in best] + [end],
    )
    if best_distance is None:
        return ordered

    # Bounded deterministic local improvement. The cap prevents large orders
    # from turning a web preview into an unbounded combinatorial workload.
    passes = min(4, len(best))
    for _ in range(passes):
        improved = False
        for left in range(len(best) - 1):
            for right in range(left + 1, len(best)):
                candidate = best[:left] + list(reversed(best[left : right + 1])) + best[right + 1 :]
                distance = _tour_distance(
                    router,
                    [start] + [stop[1] for stop in candidate] + [end],
                )
                if distance is not None and distance + 1e-9 < best_distance:
                    best = candidate
                    best_distance = distance
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break
    return best


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 3)


def simulate_picker_tours(
    *,
    result: dict[str, Any],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: Iterable[dict[str, Any]],
    resolution_m: float = DEFAULT_GRID_RESOLUTION_M,
) -> dict[str, Any]:
    """Evaluate observed/test order baskets against one physical plan candidate."""
    truth = architecture_truth_report(store_dna)
    layout_truth = layout_architecture_report(layout, store_dna)
    blockers = list(truth.get("blockers") or []) + list(layout_truth.get("blockers") or [])
    if not truth.get("valid") or not layout_truth.get("valid"):
        return {
            "simulation_version": PICKER_TOUR_SIMULATION_VERSION,
            "available": False,
            "reason": "physical_architecture_truth_invalid",
            "blockers": list(dict.fromkeys(blockers)),
            "production_evidence": False,
        }

    architecture = store_dna["architecture"]
    picker_entry = _point_for_element(architecture, "picker_entry")
    picker_exit = _point_for_element(architecture, "picker_exit") or picker_entry
    if picker_entry is None or picker_exit is None:
        return {
            "simulation_version": PICKER_TOUR_SIMULATION_VERSION,
            "available": False,
            "reason": "picker_tour_anchor_missing",
            "blockers": ["picker_entry_or_exit_missing"],
            "production_evidence": False,
        }

    order_rows = list(orders or [])
    if not order_rows:
        return {
            "simulation_version": PICKER_TOUR_SIMULATION_VERSION,
            "available": False,
            "reason": "order_baskets_missing",
            "blockers": ["observed_or_test_order_baskets_required"],
            "production_evidence": False,
        }
    if len(order_rows) > MAX_ORDERS_PER_SIMULATION:
        return {
            "simulation_version": PICKER_TOUR_SIMULATION_VERSION,
            "available": False,
            "reason": "order_basket_limit_exceeded",
            "blockers": [f"max_orders:{MAX_ORDERS_PER_SIMULATION}"],
            "production_evidence": False,
        }

    router = MeasuredGridRouter(architecture, resolution_m=resolution_m)
    start_cell = router.to_cell(picker_entry)
    end_cell = router.to_cell(picker_exit)
    sku_locations = _plan_sku_locations(result)
    stop_cells = _layout_stop_cells(layout, router)

    explained_orders: list[dict[str, Any]] = []
    distance_values: list[float] = []
    missing_skus: Counter[str] = Counter()
    unreachable_orders: list[str] = []
    invalid_orders: list[str] = []

    for index, order in enumerate(order_rows):
        order_id = _text(order.get("order_id") or order.get("id")) or f"row:{index + 1}"
        skus = _order_skus(order)
        if not skus:
            invalid_orders.append(order_id)
            continue

        unique_stops: dict[str, tuple[int, int]] = {}
        order_missing = []
        for sku in skus:
            module_id = sku_locations.get(sku)
            cell = stop_cells.get(module_id or "")
            if module_id is None or cell is None:
                missing_skus[sku] += 1
                order_missing.append(sku)
                continue
            unique_stops[module_id] = cell

        if order_missing or not unique_stops:
            continue
        if len(unique_stops) > MAX_UNIQUE_STOPS_PER_ORDER:
            invalid_orders.append(order_id)
            continue

        ordered = _nearest_neighbor_order(
            router,
            start_cell,
            list(unique_stops.items()),
        )
        if ordered is None:
            unreachable_orders.append(order_id)
            continue
        optimized = _two_opt(router, start_cell, ordered, end_cell)
        cells = [start_cell] + [stop[1] for stop in optimized] + [end_cell]
        distance = _tour_distance(router, cells)
        if distance is None:
            unreachable_orders.append(order_id)
            continue
        distance_values.append(distance)

        if len(explained_orders) < MAX_EXPLAINED_ORDERS:
            segments = []
            labels = ["picker_entry"] + [stop[0] for stop in optimized] + ["picker_exit"]
            for segment_index, (source, target) in enumerate(pairwise(cells)):
                segments.append(
                    {
                        "from": labels[segment_index],
                        "to": labels[segment_index + 1],
                        "distance_m": round(router.distance(source, target) or 0.0, 3),
                        "path_m": router.path(source, target),
                    }
                )
            explained_orders.append(
                {
                    "order_id": order_id,
                    "sku_count": len(skus),
                    "unique_stop_count": len(unique_stops),
                    "visit_sequence": [stop[0] for stop in optimized],
                    "distance_m": round(distance, 3),
                    "segments": segments,
                }
            )

    total_orders = len(order_rows)
    simulated_orders = len(distance_values)
    total_distance = round(sum(distance_values), 3)
    average_distance = round(total_distance / simulated_orders, 3) if simulated_orders else 0.0
    return {
        "simulation_version": PICKER_TOUR_SIMULATION_VERSION,
        "available": simulated_orders > 0,
        "production_evidence": False,
        "evidence_boundary": (
            "tour metrics describe only supplied baskets and measured geometry; "
            "they are not production field acceptance"
        ),
        "routing_algorithm": "nearest-neighbor-plus-bounded-2opt-on-shortest-path-grid",
        "grid_resolution_m": resolution_m,
        "orders": {
            "input_count": total_orders,
            "simulated_count": simulated_orders,
            "coverage_pct": round(simulated_orders * 100.0 / total_orders, 2) if total_orders else 0.0,
            "invalid_count": len(invalid_orders),
            "unreachable_count": len(unreachable_orders),
            "missing_sku_occurrence_count": int(sum(missing_skus.values())),
        },
        "distance_m": {
            "total": total_distance,
            "average": average_distance,
            "p50": _percentile(distance_values, 0.50),
            "p90": _percentile(distance_values, 0.90),
            "p95": _percentile(distance_values, 0.95),
            "max": round(max(distance_values), 3) if distance_values else 0.0,
        },
        "missing_skus": [
            {"sku": sku, "occurrences": count}
            for sku, count in sorted(missing_skus.items(), key=lambda row: (-row[1], row[0]))[:100]
        ],
        "invalid_order_ids": sorted(invalid_orders)[:100],
        "unreachable_order_ids": sorted(unreachable_orders)[:100],
        "explained_orders": explained_orders,
        "explainability_order_limit": MAX_EXPLAINED_ORDERS,
        "architecture_fingerprint": truth.get("fingerprint"),
    }
