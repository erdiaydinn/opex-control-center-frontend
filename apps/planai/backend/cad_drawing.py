"""Measured CAD-grade Planogram drawing preview.

This module turns reviewed Store DNA geometry plus a physical Planogram layout
into deterministic SVG/DXF engineering drawings. It intentionally remains a
preview/export surface: repository geometry is not field installation evidence,
and Architecture V2 arbitrary-angle truth is not promoted to production
authority merely because it can be drawn.
"""

from __future__ import annotations

import hashlib
import io
import json
from math import cos, radians, sin
from typing import Any

import ezdxf

import architecture_truth as architecture_v1
import architecture_truth_v2 as architecture_v2

CAD_DRAWING_CONTRACT = "planogram-measured-cad-preview-v1"
SVG_SCALE_PX_PER_M = 100.0
SVG_MARGIN_M = 1.0
MAX_ROUTE_PATHS = 3
MAX_LABELS = 500

LAYER_FLOOR = "EAY_FLOOR"
LAYER_GRID = "EAY_GRID"
LAYER_WALL = "EAY_ARCH_WALL"
LAYER_OPENING = "EAY_ARCH_OPENING"
LAYER_EGRESS = "EAY_EGRESS"
LAYER_ZONE = "EAY_OPERATION_ZONE"
LAYER_FIXTURE = "EAY_FIXTURE"
LAYER_ROUTE = "EAY_ROUTE"
LAYER_DIMENSION = "EAY_DIMENSION"
LAYER_LABEL = "EAY_LABEL"

DXF_LAYERS = (
    LAYER_FLOOR,
    LAYER_GRID,
    LAYER_WALL,
    LAYER_OPENING,
    LAYER_EGRESS,
    LAYER_ZONE,
    LAYER_FIXTURE,
    LAYER_ROUTE,
    LAYER_DIMENSION,
    LAYER_LABEL,
)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalize_rotation(value: Any) -> float:
    return _number(value) % 360.0


def _orthogonal_rotation(value: Any) -> float:
    raw = _normalize_rotation(value)
    candidates = (0.0, 90.0, 180.0, 270.0)
    return min(candidates, key=lambda candidate: abs(raw - candidate))


def _module_dimensions(module: dict[str, Any]) -> tuple[float, float]:
    width = _number(module.get("width_m"))
    depth = _number(module.get("depth_m"))
    if width <= 0:
        width = _number(module.get("module_width_cm")) / 100.0
    if depth <= 0:
        depth = _number(module.get("module_depth_cm")) / 100.0
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
    return width, depth


def _rectangle_points(
    raw: dict[str, Any],
    *,
    width_m: float,
    depth_m: float,
    schema_version: int,
) -> list[tuple[float, float]]:
    rotation = _normalize_rotation(raw.get("rotation_deg"))
    if schema_version == 1:
        rotation = _orthogonal_rotation(rotation)
        swaps = rotation in (90.0, 270.0)
        footprint_width = depth_m if swaps else width_m
        footprint_depth = width_m if swaps else depth_m
        center_x = _number(raw.get("x_m")) + footprint_width / 2.0
        center_y = _number(raw.get("y_m")) + footprint_depth / 2.0
    else:
        center_x_value = raw.get("center_x_m")
        center_y_value = raw.get("center_y_m")
        if center_x_value not in (None, "") and center_y_value not in (None, ""):
            center_x = _number(center_x_value)
            center_y = _number(center_y_value)
        else:
            center_x = _number(raw.get("x_m")) + width_m / 2.0
            center_y = _number(raw.get("y_m")) + depth_m / 2.0

    half_w = width_m / 2.0
    half_d = depth_m / 2.0
    angle = radians(rotation)
    c = cos(angle)
    s = sin(angle)
    points = []
    for local_x, local_y in (
        (-half_w, -half_d),
        (half_w, -half_d),
        (half_w, half_d),
        (-half_w, half_d),
    ):
        points.append(
            (
                center_x + local_x * c - local_y * s,
                center_y + local_x * s + local_y * c,
            )
        )
    return points


def _profile(store_dna: dict[str, Any] | None) -> dict[str, Any]:
    architecture = (store_dna or {}).get("architecture")
    if not isinstance(architecture, dict) or not architecture:
        return {
            "available": False,
            "reason": "architecture_missing",
            "schema_version": None,
            "truth": None,
            "layout_truth": None,
        }

    schema_version = int(_number(architecture.get("schema_version"), 0))
    if schema_version == 1:
        truth = architecture_v1.architecture_truth_report(store_dna)
        return {
            "available": bool(truth.get("valid")),
            "reason": None if truth.get("valid") else "architecture_v1_invalid",
            "schema_version": 1,
            "truth": truth,
        }
    if schema_version == 2:
        truth = architecture_v2.architecture_truth_report_v2(store_dna)
        return {
            "available": bool(truth.get("valid")),
            "reason": None if truth.get("valid") else "architecture_v2_invalid",
            "schema_version": 2,
            "truth": truth,
        }
    return {
        "available": False,
        "reason": "architecture_schema_unsupported",
        "schema_version": schema_version,
        "truth": None,
    }


def _layout_truth(
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
    schema_version: int,
) -> dict[str, Any]:
    if schema_version == 1:
        return architecture_v1.layout_architecture_report(layout, store_dna)
    return architecture_v2.layout_architecture_report_v2(layout, store_dna)


def _module_key(aisle: dict[str, Any], module: dict[str, Any]) -> str:
    aisle_id = _text(aisle.get("aisle_id"))
    module_id = _text(module.get("module_id"))
    if "::" in module_id:
        return module_id
    return f"{aisle_id}::{module_id}" if aisle_id else module_id


def _product_counts(result: dict[str, Any] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for aisle in ((result or {}).get("planogram") or {}).get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            count = 0
            for shelf in module.get("shelves", []) or []:
                count += len(shelf.get("products", []) or [])
            counts[_module_key(aisle, module)] = count
    return counts


def _architecture_layer(element_type: str) -> str:
    if element_type in {"wall", "column", "no_go", "technical"}:
        return LAYER_WALL
    if element_type in {"door", "opening"}:
        return LAYER_OPENING
    if element_type == "emergency_exit":
        return LAYER_EGRESS
    return LAYER_ZONE


def _route_paths(result: dict[str, Any] | None) -> list[dict[str, Any]]:
    route = (result or {}).get("architecture_route_objective_v2")
    if isinstance(route, dict) and route.get("available") and isinstance(route.get("path_m"), list):
        return [{"label": "V2 route", "path": route["path_m"]}]

    route = (result or {}).get("architecture_route_objective")
    if not isinstance(route, dict) or not route.get("available"):
        return []
    paths = []
    for index, hotspot in enumerate(route.get("route_hotspots") or []):
        path = hotspot.get("path_m")
        if not isinstance(path, list) or len(path) < 2:
            continue
        paths.append(
            {
                "label": _text(hotspot.get("module_id")) or f"route-{index + 1}",
                "path": path,
            }
        )
        if len(paths) >= MAX_ROUTE_PATHS:
            break
    return paths


def _svg_point(point: tuple[float, float], floor_depth_m: float) -> tuple[float, float]:
    return (
        (point[0] + SVG_MARGIN_M) * SVG_SCALE_PX_PER_M,
        (floor_depth_m + SVG_MARGIN_M - point[1]) * SVG_SCALE_PX_PER_M,
    )


def _svg_polygon(points: list[tuple[float, float]], floor_depth_m: float) -> str:
    return " ".join(
        f"{x:.3f},{y:.3f}" for x, y in (_svg_point(point, floor_depth_m) for point in points)
    )


def _escape_svg(value: Any) -> str:
    return (
        _text(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_svg(
    *,
    floor_width_m: float,
    floor_depth_m: float,
    architecture_rows: list[dict[str, Any]],
    fixture_rows: list[dict[str, Any]],
    route_rows: list[dict[str, Any]],
) -> str:
    width = (floor_width_m + SVG_MARGIN_M * 2.0) * SVG_SCALE_PX_PER_M
    height = (floor_depth_m + SVG_MARGIN_M * 2.0) * SVG_SCALE_PX_PER_M
    origin_x = SVG_MARGIN_M * SVG_SCALE_PX_PER_M
    origin_y = SVG_MARGIN_M * SVG_SCALE_PX_PER_M
    floor_w = floor_width_m * SVG_SCALE_PX_PER_M
    floor_h = floor_depth_m * SVG_SCALE_PX_PER_M

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.3f} {height:.3f}" data-contract="{CAD_DRAWING_CONTRACT}">',
        "<defs><style>",
        ".floor{fill:none;stroke:#111827;stroke-width:3}.grid{stroke:#d1d5db;stroke-width:1}.wall{fill:#64748b;fill-opacity:.45;stroke:#334155;stroke-width:2}.opening{fill:#dbeafe;stroke:#2563eb;stroke-width:2}.egress{fill:#d1fae5;stroke:#047857;stroke-width:2}.zone{fill:#fef3c7;stroke:#b45309;stroke-width:2}.fixture{fill:#f8fafc;stroke:#111827;stroke-width:2}.route{fill:none;stroke:#df1067;stroke-width:3;stroke-dasharray:8 5}.dim{stroke:#475569;stroke-width:1.5}.label{font:12px sans-serif;fill:#111827}.dimtext{font:12px sans-serif;fill:#334155}",
        "</style></defs>",
        f'<g id="{LAYER_GRID}">',
    ]
    for meter in range(1, int(floor_width_m) + 1):
        x = (SVG_MARGIN_M + meter) * SVG_SCALE_PX_PER_M
        parts.append(f'<line class="grid" x1="{x:.3f}" y1="{origin_y:.3f}" x2="{x:.3f}" y2="{origin_y + floor_h:.3f}"/>')
    for meter in range(1, int(floor_depth_m) + 1):
        y = (SVG_MARGIN_M + meter) * SVG_SCALE_PX_PER_M
        parts.append(f'<line class="grid" x1="{origin_x:.3f}" y1="{y:.3f}" x2="{origin_x + floor_w:.3f}" y2="{y:.3f}"/>')
    parts.extend(
        [
            "</g>",
            f'<g id="{LAYER_FLOOR}"><rect class="floor" x="{origin_x:.3f}" y="{origin_y:.3f}" width="{floor_w:.3f}" height="{floor_h:.3f}"/></g>',
        ]
    )

    layer_groups: dict[str, list[str]] = {
        LAYER_WALL: [],
        LAYER_OPENING: [],
        LAYER_EGRESS: [],
        LAYER_ZONE: [],
        LAYER_FIXTURE: [],
        LAYER_ROUTE: [],
        LAYER_LABEL: [],
    }
    class_by_layer = {
        LAYER_WALL: "wall",
        LAYER_OPENING: "opening",
        LAYER_EGRESS: "egress",
        LAYER_ZONE: "zone",
        LAYER_FIXTURE: "fixture",
    }

    label_count = 0
    for row in architecture_rows + fixture_rows:
        layer = row["layer"]
        css_class = class_by_layer[layer]
        layer_groups[layer].append(
            f'<polygon class="{css_class}" points="{_svg_polygon(row["points"], floor_depth_m)}" data-id="{_escape_svg(row["id"])}"/>'
        )
        if label_count < MAX_LABELS:
            center = row["center"]
            x, y = _svg_point(center, floor_depth_m)
            layer_groups[LAYER_LABEL].append(
                f'<text class="label" x="{x:.3f}" y="{y:.3f}" text-anchor="middle">{_escape_svg(row["label"])}</text>'
            )
            label_count += 1

    for route in route_rows:
        points = []
        for raw in route["path"]:
            if not isinstance(raw, (list, tuple)) or len(raw) < 2:
                continue
            points.append((_number(raw[0]), _number(raw[1])))
        if len(points) >= 2:
            layer_groups[LAYER_ROUTE].append(
                f'<polyline class="route" points="{_svg_polygon(points, floor_depth_m)}" data-route="{_escape_svg(route["label"])}"/>'
            )

    for layer in (LAYER_WALL, LAYER_OPENING, LAYER_EGRESS, LAYER_ZONE, LAYER_FIXTURE, LAYER_ROUTE, LAYER_LABEL):
        parts.append(f'<g id="{layer}">')
        parts.extend(layer_groups[layer])
        parts.append("</g>")

    dim_y = (floor_depth_m + SVG_MARGIN_M * 0.35) * SVG_SCALE_PX_PER_M
    dim_x = SVG_MARGIN_M * 0.35 * SVG_SCALE_PX_PER_M
    parts.extend(
        [
            f'<g id="{LAYER_DIMENSION}">',
            f'<line class="dim" x1="{origin_x:.3f}" y1="{dim_y:.3f}" x2="{origin_x + floor_w:.3f}" y2="{dim_y:.3f}"/>',
            f'<text class="dimtext" x="{origin_x + floor_w / 2:.3f}" y="{dim_y - 7:.3f}" text-anchor="middle">{floor_width_m:.2f} m</text>',
            f'<line class="dim" x1="{dim_x:.3f}" y1="{origin_y:.3f}" x2="{dim_x:.3f}" y2="{origin_y + floor_h:.3f}"/>',
            f'<text class="dimtext" x="{dim_x + 8:.3f}" y="{origin_y + floor_h / 2:.3f}" transform="rotate(-90 {dim_x + 8:.3f} {origin_y + floor_h / 2:.3f})" text-anchor="middle">{floor_depth_m:.2f} m</text>',
            "</g>",
            "</svg>",
        ]
    )
    return "".join(parts)


def _build_dxf(
    *,
    floor_width_m: float,
    floor_depth_m: float,
    architecture_rows: list[dict[str, Any]],
    fixture_rows: list[dict[str, Any]],
    route_rows: list[dict[str, Any]],
) -> str:
    doc = ezdxf.new("R2010", setup=True)
    for layer in DXF_LAYERS:
        if layer not in doc.layers:
            doc.layers.add(layer)
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (floor_width_m, 0), (floor_width_m, floor_depth_m), (0, floor_depth_m)],
        close=True,
        dxfattribs={"layer": LAYER_FLOOR},
    )

    for meter in range(1, int(floor_width_m) + 1):
        msp.add_line((meter, 0), (meter, floor_depth_m), dxfattribs={"layer": LAYER_GRID})
    for meter in range(1, int(floor_depth_m) + 1):
        msp.add_line((0, meter), (floor_width_m, meter), dxfattribs={"layer": LAYER_GRID})

    label_count = 0
    for row in architecture_rows + fixture_rows:
        msp.add_lwpolyline(row["points"], close=True, dxfattribs={"layer": row["layer"]})
        if label_count < MAX_LABELS:
            text_entity = msp.add_text(row["label"], height=0.12, dxfattribs={"layer": LAYER_LABEL})
            text_entity.set_placement(row["center"])
            label_count += 1

    for route in route_rows:
        points = [
            (_number(raw[0]), _number(raw[1]))
            for raw in route["path"]
            if isinstance(raw, (list, tuple)) and len(raw) >= 2
        ]
        if len(points) >= 2:
            msp.add_lwpolyline(points, dxfattribs={"layer": LAYER_ROUTE})

    msp.add_line((0, -0.4), (floor_width_m, -0.4), dxfattribs={"layer": LAYER_DIMENSION})
    width_text = msp.add_text(
        f"{floor_width_m:.2f} m",
        height=0.14,
        dxfattribs={"layer": LAYER_DIMENSION},
    )
    width_text.set_placement((floor_width_m / 2.0, -0.32))
    msp.add_line((-0.4, 0), (-0.4, floor_depth_m), dxfattribs={"layer": LAYER_DIMENSION})
    depth_text = msp.add_text(
        f"{floor_depth_m:.2f} m",
        height=0.14,
        rotation=90,
        dxfattribs={"layer": LAYER_DIMENSION},
    )
    depth_text.set_placement((-0.32, floor_depth_m / 2.0))

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue()


def build_cad_preview(
    *,
    result: dict[str, Any] | None,
    layout: dict[str, Any] | None,
    store_dna: dict[str, Any] | None,
    include_dxf: bool = False,
) -> dict[str, Any]:
    """Build a deterministic measured engineering drawing for preview/review."""
    profile = _profile(store_dna)
    if not profile["available"]:
        return {
            "contract": CAD_DRAWING_CONTRACT,
            "available": False,
            "preview_only": True,
            "production_authority": False,
            "production_evidence": False,
            "reason": profile["reason"],
            "blockers": list((profile.get("truth") or {}).get("blockers") or []),
        }

    schema_version = int(profile["schema_version"])
    layout_truth = _layout_truth(layout, store_dna, schema_version)
    if not layout_truth.get("valid"):
        return {
            "contract": CAD_DRAWING_CONTRACT,
            "available": False,
            "preview_only": True,
            "production_authority": False,
            "production_evidence": False,
            "reason": "layout_architecture_invalid",
            "blockers": list(layout_truth.get("blockers") or []),
        }

    architecture = (store_dna or {})["architecture"]
    floor_width_m = _number(architecture.get("floor_width_m"))
    floor_depth_m = _number(architecture.get("floor_depth_m"))
    product_counts = _product_counts(result)

    architecture_rows = []
    for element in architecture.get("elements") or []:
        width = _number(element.get("width_m"))
        depth = _number(element.get("depth_m"))
        if width <= 0 or depth <= 0:
            continue
        points = _rectangle_points(
            element,
            width_m=width,
            depth_m=depth,
            schema_version=schema_version,
        )
        center = (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )
        element_type = _text(element.get("element_type")).lower()
        architecture_rows.append(
            {
                "id": _text(element.get("element_id")),
                "label": _text(element.get("label")) or element_type,
                "type": element_type,
                "layer": _architecture_layer(element_type),
                "rotation_deg": _normalize_rotation(element.get("rotation_deg")),
                "center": center,
                "points": points,
            }
        )

    fixture_rows = []
    for aisle in (layout or {}).get("aisles", []) or []:
        for module in aisle.get("modules", []) or []:
            width, depth = _module_dimensions(module)
            if width <= 0 or depth <= 0:
                continue
            points = _rectangle_points(
                module,
                width_m=width,
                depth_m=depth,
                schema_version=schema_version,
            )
            center = (
                sum(point[0] for point in points) / len(points),
                sum(point[1] for point in points) / len(points),
            )
            key = _module_key(aisle, module)
            product_count = product_counts.get(key, 0)
            fixture_rows.append(
                {
                    "id": key,
                    "label": f"{key} · {product_count} SKU",
                    "type": _text(
                        module.get("fixture_type")
                        or module.get("fixture_class")
                        or module.get("module_type")
                    ),
                    "layer": LAYER_FIXTURE,
                    "rotation_deg": _normalize_rotation(module.get("rotation_deg")),
                    "center": center,
                    "points": points,
                    "product_count": product_count,
                }
            )

    route_rows = _route_paths(result)
    svg = _build_svg(
        floor_width_m=floor_width_m,
        floor_depth_m=floor_depth_m,
        architecture_rows=architecture_rows,
        fixture_rows=fixture_rows,
        route_rows=route_rows,
    )
    dxf = (
        _build_dxf(
            floor_width_m=floor_width_m,
            floor_depth_m=floor_depth_m,
            architecture_rows=architecture_rows,
            fixture_rows=fixture_rows,
            route_rows=route_rows,
        )
        if include_dxf
        else None
    )
    fingerprint_payload = {
        "schema_version": schema_version,
        "architecture_fingerprint": (profile.get("truth") or {}).get("fingerprint"),
        "layout": fixture_rows,
        "routes": route_rows,
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "contract": CAD_DRAWING_CONTRACT,
        "available": True,
        "preview_only": True,
        "production_authority": False,
        "production_evidence": False,
        "installation_approved": False,
        "schema_version": schema_version,
        "spatial_contract": (
            "store-architecture-v2-oriented-polygons"
            if schema_version == 2
            else "store-architecture-v1"
        ),
        "units": "metres",
        "floor": {
            "width_m": floor_width_m,
            "depth_m": floor_depth_m,
        },
        "layers": list(DXF_LAYERS),
        "architecture_element_count": len(architecture_rows),
        "fixture_count": len(fixture_rows),
        "route_count": len(route_rows),
        "fingerprint": fingerprint,
        "svg": svg,
        "dxf": dxf,
        "dxf_included": include_dxf,
        "evidence_boundary": (
            "drawing represents repository-supplied measured geometry; "
            "site survey, installer review and field acceptance remain external"
        ),
    }
