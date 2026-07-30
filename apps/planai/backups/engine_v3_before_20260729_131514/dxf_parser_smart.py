"""Stable DXF layout parser for Plonagram.

Design goal:
- Do NOT trust arbitrary DXF geometry directly as racks.
- Prefer meaningful rack/cooler/freezer layers/blocks.
- If confidence is low, return a clean operational fallback layout:
  each detected/estimated corridor = 5L + 5R modules, each module = 6 shelves.

This keeps the product usable even when AutoCAD/DXF standards are messy.
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple
import math
import ezdxf

RACK_TOKENS = (
    "RACK", "RAF", "SHELF", "MODUL", "MODULE", "GONDOLA", "AISLE", "KORIDOR",
    "DOLAP", "COOL", "CHILL", "FRIDGE", "FREEZER", "+4", "-18", "REYON"
)
WALL_TOKENS = ("WALL", "DUVAR", "PANEL")
COLUMN_TOKENS = ("COLUMN", "KOLON", "PILLAR")
DOOR_TOKENS = ("DOOR", "KAPI", "ENTRANCE", "GIRIS", "GİRİŞ")
IGNORE_TOKENS = (
    "TEXT", "DIM", "DIMENSION", "HATCH", "GRID", "AXIS", "WINDOW", "CAM",
    "ELECTRIC", "YANGIN", "FIRE", "SPRINKLER"
)


def _upper(x: Any) -> str:
    return str(x or "").upper()


def _num(v: Any, d: float = 0) -> float:
    try:
        return float(v)
    except Exception:
        return d


def _make_shelves(count: int, storage: str, width: float = 100, depth: float = 50) -> List[Dict[str, Any]]:
    count = max(1, int(count or 6))
    height = 40 if storage == "FROZEN" else 35
    max_weight = 70 if storage == "FROZEN" else 60 if storage == "CHILLED" else 45
    return [
        {
            "shelf_no": i + 1,
            "shelf_width_cm": width,
            "shelf_height_cm": height,
            "shelf_depth_cm": depth,
            "max_weight_kg": max_weight,
            "zone_type": "bottom" if i == 0 else "top" if i == count - 1 else "eye" if i in [count // 2, max(0, count // 2 - 1)] else "mid",
            "allowed_storage_type": storage,
            "assignment_rule": None,
            "products": [],
            "used_width_cm": 0,
            "used_weight_kg": 0,
            "used": 0,
        }
        for i in range(count)
    ]


def _make_module(module_id: int, side: str = "L", storage: str = "AMBIENT", module_type: str = "regular_shelf", width_cm: float = 100) -> Dict[str, Any]:
    depth = 60 if storage == "FROZEN" else 55 if storage == "CHILLED" else 50
    shelf_count = 4 if storage == "FROZEN" else 5 if storage == "CHILLED" else 6
    return {
        "module_id": module_id,
        "side": side,
        "module_type": module_type,
        "module_width_cm": width_cm,
        "module_depth_cm": depth,
        "module_height_cm": 210,
        "assignment_rule": None,
        "shelves": _make_shelves(shelf_count, storage, width_cm, depth),
    }


def _fallback_layout(store_code: str = "AUTO", aisle_count: int = 8, reason: str = "LOW_CONFIDENCE_DXF") -> Dict[str, Any]:
    aisle_count = max(1, min(30, int(aisle_count or 8)))
    letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    aisles = []
    for i in range(aisle_count):
        aid = letters[i] if i < len(letters) else f"A{i + 1}"
        modules = []
        for j in range(10):
            side = "L" if j < 5 else "R"
            modules.append(_make_module(j + 1, side=side, storage="AMBIENT", module_type="regular_shelf", width_cm=100))
        aisles.append({
            "aisle_id": aid,
            "row": i + 1,
            "position": 1,
            "direction": "LTR" if i % 2 == 0 else "RTL",
            "aisle_type": "double_sided",
            "left_modules": 5,
            "right_modules": 5,
            "walkway_width_m": 1.2,
            "layout_position": {"grid_x": (i % 2) * 8, "grid_y": (i // 2) * 4, "rotation": 0},
            "modules": modules,
        })
    return {
        "store_code": store_code,
        "route_strategy": f"DXF_FALLBACK_{reason}",
        "source": "DXF_FALLBACK",
        "parser_confidence": 0.15,
        "parser_note": "DXF içinden güvenilir raf/modül okunamadı. Her koridor 5L+5R ve her modül 6 raf olarak üretildi; kullanıcı layout editörde düzeltebilir.",
        "layout_objects": [],
        "aisles": aisles,
    }


def _rect_from_points(points: List[Tuple[float, float]], layer: str = "") -> Dict[str, Any] | None:
    if len(points) < 2:
        return None
    xs = [_num(p[0]) for p in points]
    ys = [_num(p[1]) for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    w, h = abs(max_x - min_x), abs(max_y - min_y)
    if w <= 0 or h <= 0:
        return None
    return {
        "x": min_x, "y": min_y, "w": w, "h": h,
        "cx": (min_x + max_x) / 2, "cy": (min_y + max_y) / 2,
        "layer": str(layer or ""),
    }


def _module_type(layer: str) -> Tuple[str, str, int, float]:
    lu = _upper(layer)
    if any(t in lu for t in ("FROZEN", "FREEZER", "-18", "DONUK")):
        return "FROZEN", "freezer", 4, 60
    if any(t in lu for t in ("COLD", "CHILL", "FRIDGE", "+4", "SOGUK", "SOĞUK")):
        return "CHILLED", "fridge", 5, 55
    return "AMBIENT", "regular_shelf", 6, 50


def _extract_entities(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()
    racks: List[Dict[str, Any]] = []
    walls: List[Dict[str, Any]] = []
    columns: List[Dict[str, Any]] = []
    doors: List[Dict[str, Any]] = []
    all_rects: List[Dict[str, Any]] = []

    for e in msp:
        try:
            typ = e.dxftype()
            layer = str(getattr(e.dxf, "layer", "") or "")
            name = ""
            rect = None
            if typ == "LWPOLYLINE":
                rect = _rect_from_points([(p[0], p[1]) for p in e.get_points()], layer)
            elif typ == "POLYLINE":
                rect = _rect_from_points([(v.dxf.location.x, v.dxf.location.y) for v in e.vertices], layer)
            elif typ == "LINE":
                rect = _rect_from_points([(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)], layer)
            elif typ == "INSERT":
                name = str(e.dxf.name or "")
                x, y = float(e.dxf.insert.x), float(e.dxf.insert.y)
                sx, sy = abs(float(getattr(e.dxf, "xscale", 1) or 1)), abs(float(getattr(e.dxf, "yscale", 1) or 1))
                rect = {"x": x, "y": y, "w": max(80, 100 * sx), "h": max(40, 60 * sy), "cx": x, "cy": y, "layer": f"{layer} {name}"}
            if not rect:
                continue

            rect["layer"] = f"{layer} {name}".strip()
            lu = _upper(rect["layer"])
            min_side, max_side = min(rect["w"], rect["h"]), max(rect["w"], rect["h"])
            area = rect["w"] * rect["h"]
            ratio = max_side / max(min_side, 1)
            all_rects.append(rect)

            if any(t in lu for t in IGNORE_TOKENS):
                continue
            if any(t in lu for t in WALL_TOKENS) or (ratio > 10 and max_side > 250):
                walls.append(rect)
                continue
            if any(t in lu for t in COLUMN_TOKENS):
                columns.append(rect)
                continue
            if any(t in lu for t in DOOR_TOKENS):
                doors.append(rect)
                continue

            named_rack = any(t in lu for t in RACK_TOKENS)
            geometric_rack = min_side >= 18 and max_side >= 70 and area >= 1400 and ratio >= 1.35
            if named_rack or geometric_rack:
                # Skip huge building outlines masquerading as rack candidates.
                if area > 20_000_000:
                    walls.append(rect)
                else:
                    racks.append(rect)
        except Exception:
            continue

    return {"racks": racks, "walls": walls, "columns": columns, "doors": doors, "all": all_rects}


def _cluster_rows(rects: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    if not rects:
        return []
    rects = sorted(rects, key=lambda r: r["cy"])
    short_sides = sorted([min(r["w"], r["h"]) for r in rects])
    median_short = short_sides[len(short_sides) // 2] if short_sides else 100
    tol = max(120, median_short * 2.8)
    rows: List[List[Dict[str, Any]]] = []
    for r in rects:
        placed = False
        for row in rows:
            avg_y = sum(x["cy"] for x in row) / len(row)
            if abs(r["cy"] - avg_y) <= tol:
                row.append(r)
                placed = True
                break
        if not placed:
            rows.append([r])
    rows = [sorted(row, key=lambda r: r["cx"]) for row in rows]
    return sorted(rows, key=lambda row: sum(r["cy"] for r in row) / len(row))


def _grid_pos_from_rect(row_idx: int, rects: List[Dict[str, Any]]) -> Dict[str, float]:
    if not rects:
        return {"grid_x": 0, "grid_y": row_idx * 4, "rotation": 0}
    cx = sum(r["cx"] for r in rects) / len(rects)
    cy = sum(r["cy"] for r in rects) / len(rects)
    # Normalize CAD coordinates to a readable editor grid. Relative precision is enough.
    return {"grid_x": round(cx / 500, 2), "grid_y": round(cy / 500, 2), "rotation": 0}


def _objects_from_entities(entities: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    objects: List[Dict[str, Any]] = []
    for i, r in enumerate(entities.get("walls", [])[:40]):
        objects.append({
            "id": f"wall-{i+1}", "type": "wall", "label": "DUVAR",
            "x": round(r["cx"] / 500, 2), "y": round(r["cy"] / 500, 2),
            "w": max(0.25, round(r["w"] / 500, 2)), "h": max(0.25, round(r["h"] / 500, 2)),
            "rotation": 0,
        })
    for i, r in enumerate(entities.get("columns", [])[:60]):
        objects.append({
            "id": f"column-{i+1}", "type": "column_rect", "label": "KOLON",
            "x": round(r["cx"] / 500, 2), "y": round(r["cy"] / 500, 2),
            "w": max(0.8, round(r["w"] / 500, 2)), "h": max(0.8, round(r["h"] / 500, 2)),
            "rotation": 0,
        })
    return objects


def parse_dxf_to_layout_smart(file_path: str, store_code: str = "AUTO") -> Dict[str, Any]:
    entities = _extract_entities(file_path)
    rack_rects = entities["racks"]
    total_entities = len(entities["all"])

    # Confidence rule: too few rack-like candidates means do not trust geometry.
    if len(rack_rects) < 4:
        # Estimate corridor count from line/object density, but keep safe.
        estimated = 8 if total_entities < 500 else 12 if total_entities < 2500 else 16
        layout = _fallback_layout(store_code, aisle_count=estimated, reason="NO_RELIABLE_RACK_LAYER")
        layout["detected_candidates"] = len(rack_rects)
        layout["detected_entities"] = total_entities
        layout["layout_objects"] = _objects_from_entities(entities)
        return layout

    # Remove outlier areas to avoid building outlines / fragments.
    if len(rack_rects) > 12:
        areas = sorted([r["w"] * r["h"] for r in rack_rects])
        lo = areas[max(0, int(len(areas) * 0.05))]
        hi = areas[min(len(areas) - 1, int(len(areas) * 0.90))]
        rack_rects = [r for r in rack_rects if lo <= r["w"] * r["h"] <= hi]

    rows = _cluster_rows(rack_rects)

    # If row clustering explodes, fallback instead of drawing nonsense.
    if not rows or len(rows) > 40:
        layout = _fallback_layout(store_code, aisle_count=12, reason="UNSTABLE_ROW_CLUSTER")
        layout["detected_candidates"] = len(rack_rects)
        layout["detected_entities"] = total_entities
        layout["layout_objects"] = _objects_from_entities(entities)
        return layout

    letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    aisles: List[Dict[str, Any]] = []

    for row_idx, row in enumerate(rows):
        if not row:
            continue
        # If a row has more than 10 pieces, chunk into 10-module corridors.
        chunks = [row[i:i + 10] for i in range(0, len(row), 10)]
        for chunk_idx, chunk in enumerate(chunks):
            if len(chunk) < 2:
                continue
            aisle_idx = len(aisles)
            aid = letters[aisle_idx] if aisle_idx < len(letters) else f"A{aisle_idx + 1}"
            modules: List[Dict[str, Any]] = []
            for idx, r in enumerate(chunk[:10]):
                storage, module_type, shelf_count, depth = _module_type(r["layer"])
                long_side = max(r["w"], r["h"])
                width_cm = max(80, min(220, round(long_side / 10)))
                side = "L" if idx < 5 else "R"
                modules.append({
                    "module_id": idx + 1,
                    "side": side,
                    "module_type": module_type,
                    "module_width_cm": width_cm,
                    "module_depth_cm": depth,
                    "module_height_cm": 210,
                    "source_layer": r["layer"],
                    "cad_x": r["x"], "cad_y": r["y"], "cad_w": r["w"], "cad_h": r["h"],
                    "shelves": _make_shelves(shelf_count, storage, width_cm, depth),
                })

            # If detected row has fewer than 10 modules, fill to 5L+5R fallback.
            while len(modules) < 10:
                idx = len(modules)
                modules.append(_make_module(idx + 1, side="L" if idx < 5 else "R", storage="AMBIENT", module_type="regular_shelf", width_cm=100))

            aisles.append({
                "aisle_id": aid,
                "row": row_idx + 1,
                "position": chunk_idx + 1,
                "direction": "LTR" if row_idx % 2 == 0 else "RTL",
                "aisle_type": "double_sided",
                "left_modules": 5,
                "right_modules": 5,
                "walkway_width_m": 1.2,
                "layout_position": _grid_pos_from_rect(row_idx, chunk),
                "modules": modules[:10],
            })

    if not aisles:
        layout = _fallback_layout(store_code, aisle_count=8, reason="NO_AISLES_AFTER_CLUSTER")
        layout["detected_candidates"] = len(rack_rects)
        layout["detected_entities"] = total_entities
        layout["layout_objects"] = _objects_from_entities(entities)
        return layout

    confidence = 0.45 if len(rack_rects) < 10 else 0.7
    return {
        "store_code": store_code,
        "route_strategy": "DXF_SMART_SAFE_PARSE_WITH_5L5R_FALLBACK",
        "source": "DXF",
        "detected_entities": total_entities,
        "detected_candidates": len(rack_rects),
        "used_rows": len(rows),
        "parser_confidence": confidence,
        "parser_note": "DXF güvenli parse edildi. Eksik modüller 5L+5R / 6 raf default ile tamamlandı. Layer isimleri RAF/RACK/DOLAP/COLD/FROZEN standardına çekilirse doğruluk artar.",
        "layout_objects": _objects_from_entities(entities),
        "aisles": aisles,
    }
