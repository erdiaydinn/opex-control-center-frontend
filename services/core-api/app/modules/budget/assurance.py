from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
from typing import Any

from .permissions import BudgetUnitOfWork
from .read_models import financial_events, variance_summary


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _fingerprint(payload: object) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _severity(exposure: Decimal, budget: Decimal) -> str:
    if budget <= 0 and exposure > 0:
        return "critical"
    ratio = exposure / budget if budget > 0 else Decimal("0")
    if ratio >= Decimal("1.10"):
        return "critical"
    if ratio >= Decimal("1.00"):
        return "high"
    if ratio >= Decimal("0.90"):
        return "medium"
    return "low"


async def build_financial_control_tower(uow: BudgetUnitOfWork) -> dict[str, object]:
    report = await variance_summary(uow)
    rows = report["items"]

    total_budget = sum((_decimal(row.get("budget_base_amount")) for row in rows), Decimal("0"))
    total_actual = sum((_decimal(row.get("actual_base_amount")) for row in rows), Decimal("0"))
    total_commitment = sum((_decimal(row.get("committed_base_amount")) for row in rows), Decimal("0"))
    total_forecast = sum((_decimal(row.get("forecast_base_amount")) for row in rows), Decimal("0"))
    remaining = total_budget - total_actual - total_commitment
    forecast_variance = total_budget - total_forecast

    by_cost_center: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"budget": Decimal("0"), "actual": Decimal("0"), "commitment": Decimal("0"), "forecast": Decimal("0")}
    )
    by_category: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"budget": Decimal("0"), "actual": Decimal("0"), "forecast": Decimal("0")}
    )
    by_supplier: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    findings: list[dict[str, object]] = []

    for row in rows:
        budget = _decimal(row.get("budget_base_amount"))
        actual = _decimal(row.get("actual_base_amount"))
        commitment = _decimal(row.get("committed_base_amount"))
        forecast = _decimal(row.get("forecast_base_amount"))
        exposure = actual + commitment
        cost_center = str(row.get("cost_center") or "UNASSIGNED")
        category = str(row.get("category") or "UNASSIGNED")
        supplier = str(row.get("supplier_name") or row.get("supplier_id") or "UNASSIGNED")

        cc = by_cost_center[cost_center]
        cc["budget"] += budget
        cc["actual"] += actual
        cc["commitment"] += commitment
        cc["forecast"] += forecast

        cat = by_category[category]
        cat["budget"] += budget
        cat["actual"] += actual
        cat["forecast"] += forecast
        by_supplier[supplier] += actual + commitment

        severity = _severity(max(exposure, forecast), budget)
        if severity in {"critical", "high", "medium"}:
            finding_payload = {
                "budget_line_id": str(row.get("budget_line_id")),
                "cost_center": cost_center,
                "category": category,
                "supplier": supplier,
                "budget": _money(budget),
                "actual": _money(actual),
                "commitment": _money(commitment),
                "forecast": _money(forecast),
                "severity": severity,
            }
            findings.append(
                {
                    **finding_payload,
                    "finding_id": _fingerprint(finding_payload)[:24],
                    "evidence_fingerprint": _fingerprint({"tenant": str(uow.tenant_id), **finding_payload}),
                    "reason": "forecast_above_budget" if forecast > budget else "exposure_pressure",
                    "requires_human_review": True,
                    "automatic_financial_mutation_permitted": False,
                }
            )

    cost_centers = [
        {
            "cost_center": key,
            **{name: _money(value) for name, value in values.items()},
            "forecast_variance": _money(values["budget"] - values["forecast"]),
        }
        for key, values in sorted(by_cost_center.items())
    ]
    categories = [
        {
            "category": key,
            **{name: _money(value) for name, value in values.items()},
            "forecast_variance": _money(values["budget"] - values["forecast"]),
        }
        for key, values in sorted(by_category.items(), key=lambda item: (-item[1]["actual"], item[0]))
    ]
    suppliers = [
        {"supplier": key, "exposure": _money(value)}
        for key, value in sorted(by_supplier.items(), key=lambda item: (-item[1], item[0]))[:20]
    ]

    findings.sort(
        key=lambda item: (
            {"critical": 0, "high": 1, "medium": 2}.get(str(item["severity"]), 3),
            str(item["cost_center"]),
            str(item["category"]),
        )
    )

    payload = {
        "tenant_id": str(uow.tenant_id),
        "as_of_authority": "postgresql_finance_state",
        "summary": {
            "budget": _money(total_budget),
            "actual": _money(total_actual),
            "commitment": _money(total_commitment),
            "forecast": _money(total_forecast),
            "remaining_headroom": _money(remaining),
            "forecast_variance": _money(forecast_variance),
            "utilization_pct": str(((total_actual + total_commitment) / total_budget * 100).quantize(Decimal("0.01"))) if total_budget else "0.00",
            "forecast_utilization_pct": str((total_forecast / total_budget * 100).quantize(Decimal("0.01"))) if total_budget else "0.00",
        },
        "cost_centers": cost_centers,
        "categories": categories,
        "suppliers": suppliers,
        "findings": findings,
        "report_catalog": [
            "executive_monthly_pack",
            "budget_vs_actual",
            "forecast_risk",
            "commitment_exposure",
            "supplier_spend",
            "cost_center_performance",
            "variance_root_cause",
            "reconciliation_controls",
            "financial_assurance",
        ],
        "truth_boundary": {
            "browser_formula_authority": False,
            "ai_financial_mutation_authority": False,
            "human_review_required_for_findings": True,
            "production_ready": False,
        },
    }
    payload["evidence_fingerprint"] = _fingerprint(payload)
    return payload


async def build_financial_assurance(uow: BudgetUnitOfWork, event_limit: int = 200) -> dict[str, object]:
    tower = await build_financial_control_tower(uow)
    events = await financial_events(uow, event_limit)
    event_fingerprints = [str(item.get("event_hash") or "") for item in events["items"] if item.get("event_hash")]
    payload = {
        "tenant_id": str(uow.tenant_id),
        "findings": tower["findings"],
        "financial_event_count": events["count"],
        "financial_event_tip": event_fingerprints[0] if event_fingerprints else None,
        "control_model": {
            "finding_to_evidence": True,
            "human_owner_required": True,
            "closure_requires_verification": True,
            "ai_disagreement_is_review_signal_not_sanction": True,
        },
        "source_fingerprint": tower["evidence_fingerprint"],
    }
    payload["assurance_fingerprint"] = _fingerprint(payload)
    return payload
