from typing import Dict, Any, List
import math

def n(v, d=0.0):
    try:
        if v is None or str(v).strip() == "":
            return d
        return float(str(v).replace(",", "."))
    except Exception:
        return d

def dist(a, b):
    return math.sqrt((n(a.get("x")) - n(b.get("x"))) ** 2 + (n(a.get("y")) - n(b.get("y"))) ** 2)

def route_score(layout: Dict[str, Any], sequence: List[str] = None) -> Dict[str, Any]:
    fixtures = layout.get("fixtures", [])
    if not fixtures:
        return {"total_distance_grid": 0, "steps": [], "warnings": ["fixture_yok"]}

    dispatch = next((f for f in fixtures if str(f.get("type", "")).lower().startswith("dispatch")), None)
    start = layout.get("warehouse", {}).get("picker_start") or {"x": 0, "y": 0}
    end = dispatch or start

    pickable = [f for f in fixtures if f.get("planogram_eligible", True)]
    if sequence:
        order = []
        for sid in sequence:
            found = next((f for f in pickable if str(f.get("id")) == str(sid)), None)
            if found:
                order.append(found)
        order += [f for f in pickable if f not in order]
    else:
        # Operational default: ambient/bulk first, chilled, frozen last, dispatch end.
        zone_rank = {"AMBIENT": 1, "BULK": 2, "CHILLED": 3, "FROZEN": 4}
        order = sorted(pickable, key=lambda f: (zone_rank.get(str(f.get("zone") or f.get("storage_zone") or "AMBIENT").upper(), 2), n(f.get("x")), n(f.get("y"))))

    pos = start
    steps = []
    total = 0
    cold_penalty = 0
    for f in order:
        d = dist(pos, f)
        total += d
        z = str(f.get("zone") or f.get("storage_zone") or "").upper()
        if z == "FROZEN" and any(str(x.get("zone") or x.get("storage_zone") or "").upper() not in ("FROZEN",) for x in order[order.index(f)+1:]):
            cold_penalty += 15
        steps.append({"to": f.get("id"), "type": f.get("type"), "zone": z, "distance_grid": round(d, 2)})
        pos = f

    back = dist(pos, end)
    total += back
    steps.append({"to": "DISPATCH", "distance_grid": round(back, 2)})

    return {
        "total_distance_grid": round(total, 2),
        "estimated_time_sec": round(total * 6 + cold_penalty, 0),
        "cold_penalty_sec": cold_penalty,
        "steps": steps,
        "route_quality": "good" if cold_penalty == 0 else "needs_review",
        "warnings": ["Frozen ürünler rota sonunda kalmalı."] if cold_penalty else []
    }