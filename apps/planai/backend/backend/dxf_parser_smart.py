"""DXF layout parser for Plonagram.

Goal: avoid treating every construction line as a rack. The parser prefers named
layers/blocks that look like rack/cooler/freezer, then falls back to geometric
clustering of meaningful closed polylines.
"""
from __future__ import annotations
from typing import Any, Dict, List
import math
import ezdxf

RACK_TOKENS = ("RACK", "RAF", "SHELF", "MODUL", "MODULE", "GONDOLA", "AISLE", "KORIDOR", "DOLAP", "COOL", "CHILL", "FRIDGE", "FREEZER", "+4", "-18")
IGNORE_TOKENS = ("WALL", "DUVAR", "TEXT", "DIM", "DIMENSION", "HATCH", "GRID", "AXIS", "KOLON", "COLUMN", "DOOR", "KAPI", "WINDOW", "CAM")

def _upper(x: Any) -> str:
    return str(x or "").upper()

def _rect_from_points(points, layer=""):
    if len(points) < 4:
        return None
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    w, h = abs(max_x - min_x), abs(max_y - min_y)
    if w <= 0 or h <= 0:
        return None
    return {"x": min_x, "y": min_y, "w": w, "h": h, "cx": (min_x + max_x) / 2, "cy": (min_y + max_y) / 2, "layer": str(layer or "")}

def _looks_like_rack(layer: str, w: float, h: float, preferred: bool = False) -> bool:
    lu = _upper(layer)
    if any(t in lu for t in IGNORE_TOKENS) and not any(t in lu for t in RACK_TOKENS):
        return False
    if preferred and any(t in lu for t in RACK_TOKENS):
        return True
    # rack-like rectangles are elongated or module-sized; remove tiny CAD fragments
    if min(w, h) < 18 or max(w, h) < 45:
        return False
    ratio = max(w, h) / max(min(w, h), 1)
    area = w * h
    if area < 1200:
        return False
    if ratio >= 1.5:
        return True
    return any(t in lu for t in RACK_TOKENS)

def _module_type(layer: str):
    lu = _upper(layer)
    if any(t in lu for t in ("FROZEN", "FREEZER", "-18", "DONUK")):
        return "FROZEN", "freezer", 4, 60
    if any(t in lu for t in ("COLD", "CHILL", "FRIDGE", "+4", "SOGUK", "SOĞUK")):
        return "CHILLED", "fridge", 5, 55
    return "AMBIENT", "regular_shelf", 6, 50

def _make_shelves(count, storage, width, depth):
    return [
        {
            "shelf_no": i + 1,
            "shelf_width_cm": width,
            "shelf_height_cm": 40 if storage == "FROZEN" else 35,
            "shelf_depth_cm": depth,
            "max_weight_kg": 70 if storage == "FROZEN" else 60 if storage == "CHILLED" else 45,
            "zone_type": "bottom" if i == 0 else "top" if i == count - 1 else "eye" if i >= count // 2 else "mid",
            "allowed_storage_type": storage,
            "assignment_rule": None,
            "products": [],
            "used_width_cm": 0,
            "used_weight_kg": 0,
        }
        for i in range(count)
    ]

def _cluster_rows(rects: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    if not rects:
        return []
    rects = sorted(rects, key=lambda r: r["cy"])
    median_h = sorted([min(r["w"], r["h"]) for r in rects])[len(rects)//2]
    tol = max(80, median_h * 2.2)
    rows: List[List[Dict[str, Any]]] = []
    for r in rects:
        for row in rows:
            avg = sum(x["cy"] for x in row) / len(row)
            if abs(r["cy"] - avg) <= tol:
                row.append(r); break
        else:
            rows.append([r])
    return [sorted(row, key=lambda r: r["cx"]) for row in sorted(rows, key=lambda row: sum(r["cy"] for r in row)/len(row))]

def parse_dxf_to_layout_smart(file_path: str, store_code: str = "AUTO") -> Dict[str, Any]:
    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()
    candidates: List[Dict[str, Any]] = []
    preferred: List[Dict[str, Any]] = []

    for e in msp:
        try:
            typ = e.dxftype()
            layer = str(getattr(e.dxf, "layer", "") or "")
            rect = None
            if typ == "LWPOLYLINE":
                rect = _rect_from_points([(p[0], p[1]) for p in e.get_points()], layer)
            elif typ == "POLYLINE":
                rect = _rect_from_points([(v.dxf.location.x, v.dxf.location.y) for v in e.vertices], layer)
            elif typ == "INSERT":
                name = str(e.dxf.name or "")
                x, y = float(e.dxf.insert.x), float(e.dxf.insert.y)
                sx, sy = float(getattr(e.dxf, "xscale", 1) or 1), float(getattr(e.dxf, "yscale", 1) or 1)
                rect = {"x": x, "y": y, "w": max(60, 100 * abs(sx)), "h": max(30, 50 * abs(sy)), "cx": x, "cy": y, "layer": f"{layer} {name}"}
            if not rect:
                continue
            lu = _upper(rect["layer"])
            is_pref = any(t in lu for t in RACK_TOKENS)
            if _looks_like_rack(rect["layer"], rect["w"], rect["h"], preferred=is_pref):
                candidates.append(rect)
                if is_pref:
                    preferred.append(rect)
        except Exception:
            continue

    # If layer names are useful, trust them. Otherwise use geometric candidates.
    rects = preferred if len(preferred) >= 3 else candidates

    # Remove extreme building-outline rectangles: keep middle 90% by area when enough candidates exist.
    if len(rects) > 20:
        areas = sorted([r["w"] * r["h"] for r in rects])
        low = areas[max(0, int(len(areas) * 0.05) - 1)]
        high = areas[min(len(areas)-1, int(len(areas) * 0.92))]
        rects = [r for r in rects if low <= r["w"] * r["h"] <= high]

    rows = _cluster_rows(rects)
    aisle_names = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    aisles = []
    for row_idx, row in enumerate(rows):
        # If a row has many CAD fragments, merge nearby fragments into module groups.
        modules = []
        for idx, r in enumerate(row[:24]):
            storage, module_type, shelf_count, depth = _module_type(r["layer"])
            long_side = max(r["w"], r["h"])
            width_cm = max(60, min(220, round(long_side / 10)))
            modules.append({
                "module_id": idx + 1,
                "side": "L" if idx % 2 == 0 else "R",
                "module_type": module_type,
                "module_width_cm": width_cm,
                "module_depth_cm": depth,
                "module_height_cm": 210,
                "source_layer": r["layer"],
                "cad_x": r["x"], "cad_y": r["y"], "cad_w": r["w"], "cad_h": r["h"],
                "shelves": _make_shelves(shelf_count, storage, width_cm, depth),
            })
        if modules:
            aisle_id = aisle_names[len(aisles)] if len(aisles) < len(aisle_names) else f"A{len(aisles)+1}"
            aisles.append({
                "aisle_id": aisle_id,
                "row": row_idx + 1,
                "position": 1,
                "direction": "LTR" if row_idx % 2 == 0 else "RTL",
                "aisle_type": "dxf_smart_detected",
                "modules": modules,
            })

    return {
        "store_code": store_code,
        "route_strategy": "DXF_SMART_LAYER_GEOMETRY",
        "source": "DXF",
        "detected_candidates": len(candidates),
        "used_candidates": len(rects),
        "parser_note": "Layer isimleri RACK/RAF/MODULE/COOL/FROZEN gibi standardize edilirse doğruluk yükselir.",
        "aisles": aisles,
    }
