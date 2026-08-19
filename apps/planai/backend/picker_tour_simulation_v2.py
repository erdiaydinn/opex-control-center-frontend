"""Arbitrary-angle picker-tour simulation for Architecture V2 previews.

The V1 simulator remains the production-facing route evidence. This module uses
oriented Shapely polygons and a bounded 8-neighbour A* pair router so Store Scan
or CAD geometry at real-world angles can participate in blind A/B benchmarks
without being snapped to an orthogonal grid contract.

Results are preview/repository evidence only and never production field proof.
"""

from __future__ import annotations

import heapq
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise
from math import hypot, sqrt
from typing import Any

from shapely.geometry import Point

from architecture_truth_v2 import (
    DEFAULT_GRID_RESOLUTION_M,
    MAX_ROUTE_GRID_CELLS,
    _element_polygon,
    _module_polygon,
    _spatial_module_id,
    _text,
    _walk_obstacles,
    architecture_truth_report_v2,
    iter_layout_modules,
    layout_architecture_report_v2,
)
from picker_tour_simulation import (
    MAX_EXPLAINED_ORDERS,
    MAX_ORDERS_PER_SIMULATION,
    MAX_PATH_POINTS_PER_SEGMENT,
    MAX_UNIQUE_STOPS_PER_ORDER,
    _nearest_neighbor_order,
    _order_skus,
    _percentile,
    _plan_sku_locations,
    _two_opt,
)

PICKER_TOUR_SIMULATION_V2_VERSION = "picker-tour-simulation-v2-oriented-polygons"
MAX_PAIR_ROUTE_CACHE = 20_000


@dataclass(frozen=True)
class GridShapeV2:
    width_m: float
    depth_m: float
    resolution_m: float
    columns: int
    rows: int


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _point_for_element(
    architecture: dict[str, Any],
    element_type: str,
) -> tuple[float, float] | None:
    for element in architecture.get("elements") or []:
        if _text(element.get("element_type")).lower() != element_type:
            continue
        polygon = _element_polygon(element)
        if polygon is not None:
            centroid = polygon.centroid
            return centroid.x, centroid.y
    return None


def _simplify_path(
    cells: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    if len(cells) <= 2:
        return cells
    result = [cells[0]]
    direction = (
        cells[1][0] - cells[0][0],
        cells[1][1] - cells[0][1],
    )
    for index in range(1, len(cells) - 1):
        next_direction = (
            cells[index + 1][0] - cells[index][0],
            cells[index + 1][1] - cells[index][1],
        )
        if next_direction != direction:
            result.append(cells[index])
            direction = next_direction
    result.append(cells[-1])
    if len(result) <= MAX_PATH_POINTS_PER_SEGMENT:
        return result
    last = len(result) - 1
    denominator = MAX_PATH_POINTS_PER_SEGMENT - 1
    sampled = [
        result[min(last, round(index * last / denominator))]
        for index in range(MAX_PATH_POINTS_PER_SEGMENT)
    ]
    return list(dict.fromkeys(sampled))


class OrientedPolygonRouter:
    """Bounded A* router between arbitrary cells with symmetric pair caching."""

    def __init__(
        self,
        architecture: dict[str, Any],
        *,
        resolution_m: float = DEFAULT_GRID_RESOLUTION_M,
    ) -> None:
        width = _number(architecture.get("floor_width_m"))
        depth = _number(architecture.get("floor_depth_m"))
        if width <= 0 or depth <= 0 or not 0.1 <= resolution_m <= 1.0:
            raise ValueError("picker_tour_v2_grid_invalid")
        columns = max(1, round(width / resolution_m) + 1)
        rows = max(1, round(depth / resolution_m) + 1)
        if columns * rows > MAX_ROUTE_GRID_CELLS:
            raise ValueError("picker_tour_v2_grid_too_large")
        self.shape = GridShapeV2(
            width_m=width,
            depth_m=depth,
            resolution_m=resolution_m,
            columns=columns,
            rows=rows,
        )
        self._obstacles = _walk_obstacles(architecture)
        self._route_cache: dict[
            tuple[tuple[int, int], tuple[int, int]],
            tuple[float, list[tuple[int, int]]] | None,
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

    def point_for_cell(self, cell: tuple[int, int]) -> tuple[float, float]:
        return (
            cell[0] * self.shape.resolution_m,
            cell[1] * self.shape.resolution_m,
        )

    def blocked(self, cell: tuple[int, int]) -> bool:
        point = Point(*self.point_for_cell(cell))
        return any(obstacle.covers(point) for obstacle in self._obstacles)

    def _neighbours(
        self,
        cell: tuple[int, int],
    ) -> list[tuple[tuple[int, int], float]]:
        result = []
        for dx, dy, multiplier in (
            (-1, 0, 1.0),
            (1, 0, 1.0),
            (0, -1, 1.0),
            (0, 1, 1.0),
            (-1, -1, sqrt(2.0)),
            (-1, 1, sqrt(2.0)),
            (1, -1, sqrt(2.0)),
            (1, 1, sqrt(2.0)),
        ):
            candidate = cell[0] + dx, cell[1] + dy
            if not (
                0 <= candidate[0] < self.shape.columns
                and 0 <= candidate[1] < self.shape.rows
            ):
                continue
            if self.blocked(candidate):
                continue
            if dx and dy:
                side_x = cell[0] + dx, cell[1]
                side_y = cell[0], cell[1] + dy
                if self.blocked(side_x) or self.blocked(side_y):
                    continue
            result.append((candidate, multiplier * self.shape.resolution_m))
        return result

    def _store_cache(
        self,
        source: tuple[int, int],
        target: tuple[int, int],
        route: tuple[float, list[tuple[int, int]]] | None,
    ) -> None:
        if len(self._route_cache) >= MAX_PAIR_ROUTE_CACHE:
            return
        self._route_cache[(source, target)] = route
        if route is None:
            self._route_cache[(target, source)] = None
        else:
            self._route_cache[(target, source)] = (route[0], list(reversed(route[1])))

    def _route(
        self,
        source: tuple[int, int],
        target: tuple[int, int],
    ) -> tuple[float, list[tuple[int, int]]] | None:
        cached = self._route_cache.get((source, target))
        if cached is not None or (source, target) in self._route_cache:
            return cached
        if self.blocked(source) or self.blocked(target):
            self._store_cache(source, target, None)
            return None
        if source == target:
            route = (0.0, [source])
            self._store_cache(source, target, route)
            return route

        target_point = self.point_for_cell(target)
        open_heap: list[tuple[float, float, tuple[int, int]]] = [(0.0, 0.0, source)]
        cost = {source: 0.0}
        parents: dict[tuple[int, int], tuple[int, int]] = {}

        while open_heap:
            _, current_cost, current = heapq.heappop(open_heap)
            if current_cost > cost.get(current, float("inf")) + 1e-12:
                continue
            if current == target:
                break
            for candidate, step_cost in self._neighbours(current):
                candidate_cost = current_cost + step_cost
                if candidate_cost + 1e-12 >= cost.get(candidate, float("inf")):
                    continue
                cost[candidate] = candidate_cost
                parents[candidate] = current
                point = self.point_for_cell(candidate)
                heuristic = hypot(
                    point[0] - target_point[0],
                    point[1] - target_point[1],
                )
                heapq.heappush(
                    open_heap,
                    (candidate_cost + heuristic, candidate_cost, candidate),
                )

        if target not in cost:
            self._store_cache(source, target, None)
            return None
        cells = [target]
        while cells[-1] != source:
            cells.append(parents[cells[-1]])
        cells.reverse()
        route = (round(cost[target], 6), cells)
        self._store_cache(source, target, route)
        return route

    def distance(
        self,
        source: tuple[int, int],
        target: tuple[int, int],
    ) -> float | None:
        route = self._route(source, target)
        return None if route is None else route[0]

    def path(
        self,
        source: tuple[int, int],
        target: tuple[int, int],
    ) -> list[list[float]]:
        route = self._route(source, target)
        if route is None:
            return []
        return [
            [round(point[0], 3), round(point[1], 3)]
            for point in (
                self.point_for_cell(cell)
                for cell in _simplify_path(route[1])
            )
        ]

    @property
    def cached_pair_count(self) -> int:
        return len(self._route_cache)


def _layout_stop_cells(
    layout: dict[str, Any],
    router: OrientedPolygonRouter,
) -> dict[str, tuple[int, int]]:
    cells: dict[str, tuple[int, int]] = {}
    for aisle, module in iter_layout_modules(layout):
        polygon = _module_polygon(module)
        if polygon is None:
            continue
        centroid = polygon.centroid
        cells[_spatial_module_id(aisle, module)] = router.to_cell(
            (centroid.x, centroid.y)
        )
    return cells


def _tour_distance(
    router: OrientedPolygonRouter,
    cells: list[tuple[int, int]],
) -> float | None:
    total = 0.0
    for source, target in pairwise(cells):
        distance = router.distance(source, target)
        if distance is None:
            return None
        total += distance
    return round(total, 6)


def simulate_picker_tours_v2(
    *,
    result: dict[str, Any],
    layout: dict[str, Any],
    store_dna: dict[str, Any],
    orders: list[dict[str, Any]],
    resolution_m: float = DEFAULT_GRID_RESOLUTION_M,
) -> dict[str, Any]:
    """Evaluate supplied baskets against an arbitrary-angle physical candidate."""
    truth = architecture_truth_report_v2(store_dna)
    layout_truth = layout_architecture_report_v2(layout, store_dna)
    blockers = list(truth.get("blockers") or []) + list(
        layout_truth.get("blockers") or []
    )
    if not truth.get("valid") or not layout_truth.get("valid"):
        return {
            "simulation_version": PICKER_TOUR_SIMULATION_V2_VERSION,
            "available": False,
            "preview_only": True,
            "reason": "physical_architecture_v2_truth_invalid",
            "blockers": list(dict.fromkeys(blockers)),
            "production_evidence": False,
        }
    if not orders:
        return {
            "simulation_version": PICKER_TOUR_SIMULATION_V2_VERSION,
            "available": False,
            "preview_only": True,
            "reason": "order_baskets_missing",
            "blockers": ["observed_or_test_order_baskets_required"],
            "production_evidence": False,
        }
    if len(orders) > MAX_ORDERS_PER_SIMULATION:
        return {
            "simulation_version": PICKER_TOUR_SIMULATION_V2_VERSION,
            "available": False,
            "preview_only": True,
            "reason": "order_basket_limit_exceeded",
            "blockers": [f"max_orders:{MAX_ORDERS_PER_SIMULATION}"],
            "production_evidence": False,
        }

    architecture = store_dna["architecture"]
    picker_entry = _point_for_element(architecture, "picker_entry")
    picker_exit = _point_for_element(architecture, "picker_exit") or picker_entry
    if picker_entry is None or picker_exit is None:
        return {
            "simulation_version": PICKER_TOUR_SIMULATION_V2_VERSION,
            "available": False,
            "preview_only": True,
            "reason": "picker_tour_anchor_missing",
            "blockers": ["picker_entry_or_exit_missing"],
            "production_evidence": False,
        }

    try:
        router = OrientedPolygonRouter(
            architecture,
            resolution_m=resolution_m,
        )
    except ValueError as exc:
        return {
            "simulation_version": PICKER_TOUR_SIMULATION_V2_VERSION,
            "available": False,
            "preview_only": True,
            "reason": str(exc),
            "blockers": [str(exc)],
            "production_evidence": False,
        }

    start_cell = router.to_cell(picker_entry)
    end_cell = router.to_cell(picker_exit)
    sku_locations = _plan_sku_locations(result)
    stop_cells = _layout_stop_cells(layout, router)

    explained_orders: list[dict[str, Any]] = []
    distance_values: list[float] = []
    missing_skus: Counter[str] = Counter()
    unreachable_orders: list[str] = []
    invalid_orders: list[str] = []

    for index, order in enumerate(orders):
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
            labels = ["picker_entry"] + [stop[0] for stop in optimized] + [
                "picker_exit"
            ]
            segments = []
            for segment_index, (source, target) in enumerate(pairwise(cells)):
                segment_distance = router.distance(source, target)
                segments.append(
                    {
                        "from": labels[segment_index],
                        "to": labels[segment_index + 1],
                        "distance_m": round(segment_distance or 0.0, 3),
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

    total_orders = len(orders)
    simulated_orders = len(distance_values)
    total_distance = round(sum(distance_values), 3)
    average_distance = (
        round(total_distance / simulated_orders, 3) if simulated_orders else 0.0
    )
    return {
        "simulation_version": PICKER_TOUR_SIMULATION_V2_VERSION,
        "available": simulated_orders > 0,
        "preview_only": True,
        "production_evidence": False,
        "evidence_boundary": (
            "V2 tour metrics describe only supplied baskets and oriented measured "
            "geometry; they are not production field acceptance"
        ),
        "routing_algorithm": (
            "nearest-neighbor-plus-bounded-2opt-on-oriented-polygon-astar-grid"
        ),
        "grid_resolution_m": resolution_m,
        "route_pair_cache_entries": router.cached_pair_count,
        "orders": {
            "input_count": total_orders,
            "simulated_count": simulated_orders,
            "coverage_pct": (
                round(simulated_orders * 100.0 / total_orders, 2)
                if total_orders
                else 0.0
            ),
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
            for sku, count in sorted(
                missing_skus.items(),
                key=lambda row: (-row[1], row[0]),
            )[:100]
        ],
        "invalid_order_ids": sorted(invalid_orders)[:100],
        "unreachable_order_ids": sorted(unreachable_orders)[:100],
        "explained_orders": explained_orders,
        "explainability_order_limit": MAX_EXPLAINED_ORDERS,
        "architecture_fingerprint": truth.get("fingerprint"),
        "non_orthogonal_element_count": truth.get("non_orthogonal_element_count"),
        "non_orthogonal_module_count": layout_truth.get("non_orthogonal_module_count"),
    }
