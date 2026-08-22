"""Evidence-bound paired shadow backtest for Planogram KPI proposals."""

from __future__ import annotations

import hashlib
import json
from statistics import mean, median
from typing import Any

BACKTEST_VERSION = "planogram-shadow-backtest-v1"
DEFAULT_DIRECTIONS = {
    "picking_seconds_per_order": "lower",
    "oos_rate_pct": "lower",
    "nsfr_pct": "lower",
    "replenishment_minutes_per_day": "lower",
    "sales_value": "higher",
    "gross_margin_value": "higher",
}
MAX_PAIRS = 5_000


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_shadow_backtest(
    *,
    pairs: list[dict[str, Any]],
    metric_directions: dict[str, str] | None = None,
    minimum_pairs: int = 3,
) -> dict[str, Any]:
    if not pairs or len(pairs) > MAX_PAIRS:
        return {
            "backtest_version": BACKTEST_VERSION,
            "available": False,
            "blockers": ["pair_count_invalid"],
            "causal_claim_allowed": False,
            "market_leadership_claim_allowed": False,
        }
    directions = dict(DEFAULT_DIRECTIONS)
    for name, direction in (metric_directions or {}).items():
        if direction in {"lower", "higher"}:
            directions[str(name)] = direction

    normalized: list[dict[str, Any]] = []
    blockers: list[str] = []
    metric_improvements: dict[str, list[float]] = {name: [] for name in directions}
    for index, row in enumerate(pairs):
        pair_id = _text(row.get("pair_id"))
        store_code = _text(row.get("store_code"))
        window_id = _text(row.get("window_id"))
        source_ref = _text(row.get("source_ref"))
        attested = row.get("attested") is True
        baseline = row.get("baseline") if isinstance(row.get("baseline"), dict) else {}
        candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
        if not pair_id or not store_code or not window_id:
            blockers.append(f"pair_identity_missing:index:{index}")
            continue
        if not source_ref:
            blockers.append(f"pair_source_ref_missing:index:{index}")
        if not attested:
            blockers.append(f"pair_attestation_missing:index:{index}")
        metrics: dict[str, Any] = {}
        for metric, direction in directions.items():
            before = _number(baseline.get(metric))
            after = _number(candidate.get(metric))
            if before is None or after is None:
                continue
            raw_delta = after - before
            improvement = before - after if direction == "lower" else after - before
            metric_improvements[metric].append(improvement)
            metrics[metric] = {
                "baseline": before,
                "candidate": after,
                "raw_delta_candidate_minus_baseline": raw_delta,
                "improvement": improvement,
                "direction": direction,
                "candidate_better": improvement > 0,
            }
        if not metrics:
            blockers.append(f"pair_metrics_missing:index:{index}")
        normalized.append(
            {
                "pair_id": pair_id,
                "store_code": store_code,
                "window_id": window_id,
                "source_ref": source_ref or None,
                "attested": attested,
                "metrics": metrics,
            }
        )

    summaries: dict[str, Any] = {}
    for metric, values in metric_improvements.items():
        if not values:
            continue
        wins = sum(value > 0 for value in values)
        losses = sum(value < 0 for value in values)
        summaries[metric] = {
            "pair_count": len(values),
            "mean_improvement": round(mean(values), 6),
            "median_improvement": round(median(values), 6),
            "win_count": wins,
            "loss_count": losses,
            "tie_count": len(values) - wins - losses,
            "win_rate_pct": round(wins * 100.0 / len(values), 2),
            "direction": directions[metric],
        }

    incomplete_prefixes = (
        "pair_source_ref_missing",
        "pair_attestation_missing",
        "pair_identity_missing",
    )
    evidence_complete = not any(
        blocker.startswith(incomplete_prefixes) for blocker in blockers
    )
    fingerprint = hashlib.sha256(
        json.dumps(
            {"pairs": normalized, "directions": directions},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    usable_pairs = sum(bool(row["metrics"]) for row in normalized)
    return {
        "backtest_version": BACKTEST_VERSION,
        "available": bool(summaries),
        "preview_only": True,
        "pair_count": len(normalized),
        "usable_pair_count": usable_pairs,
        "minimum_pairs": minimum_pairs,
        "minimum_pair_gate_passed": usable_pairs >= minimum_pairs,
        "evidence_complete": evidence_complete,
        "metric_summaries": summaries,
        "pairs": normalized[:MAX_PAIRS],
        "blockers": list(dict.fromkeys(blockers)),
        "backtest_fingerprint": fingerprint,
        "causal_claim_allowed": False,
        "production_evidence": False,
        "market_leadership_claim_allowed": False,
        "evidence_boundary": (
            "paired shadow deltas describe association under supplied historical windows; "
            "causal lift requires controlled rollout or equivalent experimental evidence"
        ),
    }
