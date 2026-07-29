
from __future__ import annotations
from typing import Any, Dict, List


def review_planogram(payload: Dict[str, Any]) -> Dict[str, Any]:
    products: List[Dict[str, Any]] = payload.get("products") or []
    layout: Dict[str, Any] = payload.get("layout") or {}
    high_velocity = [p for p in products if float(p.get("sales_qty_7d") or p.get("qty_7d") or 0) > 100]
    chilled = [p for p in products if "CHILL" in str(p.get("storage_type", "")).upper()]
    frozen = [p for p in products if "FROZEN" in str(p.get("storage_type", "")).upper() or "-18" in str(p.get("storage_type", ""))]
    aisles = layout.get("aisles") or []

    agents = [
        {"role": "Sales Optimizer", "score": 0.88, "verdict": f"{len(high_velocity)} high velocity SKU needs facing/depth priority."},
        {"role": "Operations Lead", "score": 0.82, "verdict": "Picker route should keep heavy products near the final leg and dispatch flow."},
        {"role": "Cold Chain Guardian", "score": 0.9, "verdict": f"{len(chilled)} chilled and {len(frozen)} frozen SKUs must stay isolated from ambient."},
        {"role": "Space Architect", "score": 0.8, "verdict": f"{len(aisles)} aisles require collision and width validation."},
        {"role": "Skeptic Auditor", "score": 0.74, "verdict": "Congestion risk remains if fast movers cluster inside one corridor."},
    ]
    confidence = round(sum(a["score"] for a in agents) / len(agents), 2)
    return {
        "decision": "approved_with_warnings" if confidence >= 0.75 else "needs_revision",
        "confidence": confidence,
        "agents": agents,
        "why": [a["verdict"] for a in agents[:4]],
        "risks": [agents[-1]["verdict"]],
        "next_best_action": "Review facing/depth for top fast-moving ambient SKUs and validate cold-chain isolation.",
    }
