"""Deterministic counterfactual checks for Jarvis context hypotheses.

Time/geography correlation is useful but not enough. This module adds a simple,
auditable difference-in-differences style check so Jarvis can ask whether a
metric changed more in an affected scope than in a comparable control scope.
It strengthens or weakens a hypothesis but never claims causal proof.
"""

from __future__ import annotations

from enum import Enum
from math import isfinite

from pydantic import BaseModel, Field, model_validator

COUNTERFACTUAL_INTELLIGENCE_CONTRACT = "eay-counterfactual-intelligence-v1"


class CounterfactualStatus(str, Enum):
    SUPPORTS_HYPOTHESIS = "supports_hypothesis"
    WEAK_SIGNAL = "weak_signal"
    INSUFFICIENT = "insufficient"


def _finite(value: float, field: str) -> float:
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{field}_must_be_finite")
    return number


def _pct(change: float, baseline: float) -> float | None:
    if baseline == 0:
        return None
    return round(change * 100.0 / abs(baseline), 6)


class CounterfactualInput(BaseModel):
    metric_name: str = Field(min_length=1, max_length=200)
    affected_scope: str = Field(min_length=1, max_length=300)
    control_scope: str = Field(min_length=1, max_length=300)
    affected_before: float
    affected_during: float
    control_before: float
    control_during: float
    affected_provenance_ref: str = Field(min_length=1, max_length=500)
    control_provenance_ref: str = Field(min_length=1, max_length=500)
    minimum_material_effect_pct: float = Field(default=5.0, ge=0.0, le=1000.0)
    maximum_control_change_pct: float = Field(default=15.0, ge=0.0, le=1000.0)

    @model_validator(mode="after")
    def validate_finite(self) -> "CounterfactualInput":
        for field in (
            "affected_before",
            "affected_during",
            "control_before",
            "control_during",
            "minimum_material_effect_pct",
            "maximum_control_change_pct",
        ):
            _finite(getattr(self, field), field)
        return self


class CounterfactualResult(BaseModel):
    contract: str = COUNTERFACTUAL_INTELLIGENCE_CONTRACT
    metric_name: str
    affected_change_abs: float
    affected_change_pct: float | None
    control_change_abs: float
    control_change_pct: float | None
    difference_in_differences_abs: float
    effect_pct_vs_affected_baseline: float | None
    status: CounterfactualStatus
    causality_proven: bool = False
    evidence_refs: tuple[str, str]
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ("quasi_experimental_signal_is_not_causality",)

    @model_validator(mode="after")
    def prohibit_causal_claim(self) -> "CounterfactualResult":
        if self.causality_proven:
            raise ValueError("counterfactual_engine_cannot_assert_causality")
        return self


def evaluate_counterfactual(payload: CounterfactualInput) -> CounterfactualResult:
    affected_change = payload.affected_during - payload.affected_before
    control_change = payload.control_during - payload.control_before
    did = affected_change - control_change

    affected_change_pct = _pct(affected_change, payload.affected_before)
    control_change_pct = _pct(control_change, payload.control_before)
    effect_pct = _pct(did, payload.affected_before)

    blockers: list[str] = []
    warnings: list[str] = ["quasi_experimental_signal_is_not_causality"]

    if affected_change_pct is None:
        blockers.append("affected_baseline_zero")
    if control_change_pct is None:
        blockers.append("control_baseline_zero")

    if blockers or effect_pct is None or control_change_pct is None:
        status = CounterfactualStatus.INSUFFICIENT
    elif abs(effect_pct) < payload.minimum_material_effect_pct:
        status = CounterfactualStatus.INSUFFICIENT
        blockers.append("counterfactual_effect_not_material")
    elif abs(control_change_pct) > payload.maximum_control_change_pct:
        status = CounterfactualStatus.WEAK_SIGNAL
        warnings.append("control_scope_is_not_stable")
    else:
        status = CounterfactualStatus.SUPPORTS_HYPOTHESIS

    return CounterfactualResult(
        metric_name=payload.metric_name,
        affected_change_abs=round(affected_change, 6),
        affected_change_pct=affected_change_pct,
        control_change_abs=round(control_change, 6),
        control_change_pct=control_change_pct,
        difference_in_differences_abs=round(did, 6),
        effect_pct_vs_affected_baseline=effect_pct,
        status=status,
        evidence_refs=(payload.affected_provenance_ref, payload.control_provenance_ref),
        blockers=tuple(dict.fromkeys(blockers)),
        warnings=tuple(dict.fromkeys(warnings)),
    )
