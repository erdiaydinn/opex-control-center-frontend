"""Manager override learning authority for roadmap 16/60.

Learning is advisory and versioned. Override/outcome evidence can produce a draft
policy, but no draft can modify production optimizer behavior automatically. Only
an explicitly approved policy version may be applied to future candidate scoring,
and its use is separately auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json

from .optimizer_authority import OptimizationCandidate

ZERO = Decimal("0")
ONE = Decimal("1")


class OverrideLearningError(ValueError):
    pass


def _decimal_text(value: Decimal) -> str:
    if value == ZERO:
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _hash(value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class OverrideLearningObservation:
    override_id: str
    optimizer_proposal_fingerprint: str
    decision: str
    reason_code: str
    action_type: str
    worked: bool | None
    pre_kpi_context_ref: str
    post_kpi_context_ref: str | None
    source_ref: str

    def __post_init__(self) -> None:
        if not self.override_id.strip():
            raise OverrideLearningError("override_id is required")
        if len(self.optimizer_proposal_fingerprint) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.optimizer_proposal_fingerprint
        ):
            raise OverrideLearningError("optimizer proposal fingerprint must be lowercase SHA-256")
        if self.decision not in {"accepted", "rejected", "modified"}:
            raise OverrideLearningError("override decision is unsupported")
        if not self.reason_code.strip() or not self.action_type.strip():
            raise OverrideLearningError("reason_code and action_type are required")
        if not self.pre_kpi_context_ref.strip() or not self.source_ref.strip():
            raise OverrideLearningError("override learning observation requires provenance")
        if self.worked is not None and not (self.post_kpi_context_ref or "").strip():
            raise OverrideLearningError("worked outcome requires post_kpi_context_ref")

    def canonical(self) -> dict[str, object]:
        return {
            "override_id": self.override_id,
            "optimizer_proposal_fingerprint": self.optimizer_proposal_fingerprint,
            "decision": self.decision,
            "reason_code": self.reason_code,
            "action_type": self.action_type,
            "worked": self.worked,
            "pre_kpi_context_ref": self.pre_kpi_context_ref,
            "post_kpi_context_ref": self.post_kpi_context_ref,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class OverrideLearningDraft:
    model_family: str
    sample_count: int
    completed_outcome_count: int
    reason_counts: dict[str, int]
    frequent_override_reasons: tuple[str, ...]
    action_success_rates: dict[str, Decimal]
    suggested_cost_multipliers: dict[str, Decimal]
    input_fingerprint: str
    draft_fingerprint: str
    automatic_apply_permitted: bool
    human_approval_required: bool

    def as_record(self) -> dict[str, object]:
        return {
            "model_family": self.model_family,
            "sample_count": self.sample_count,
            "completed_outcome_count": self.completed_outcome_count,
            "reason_counts": dict(sorted(self.reason_counts.items())),
            "frequent_override_reasons": list(self.frequent_override_reasons),
            "action_success_rates": {
                key: _decimal_text(value) for key, value in sorted(self.action_success_rates.items())
            },
            "suggested_cost_multipliers": {
                key: _decimal_text(value)
                for key, value in sorted(self.suggested_cost_multipliers.items())
            },
            "input_fingerprint": self.input_fingerprint,
            "draft_fingerprint": self.draft_fingerprint,
            "automatic_apply_permitted": self.automatic_apply_permitted,
            "human_approval_required": self.human_approval_required,
        }


@dataclass(frozen=True, slots=True)
class ApprovedOverrideLearningPolicy:
    version: str
    draft_fingerprint: str
    action_cost_multipliers: dict[str, Decimal]
    approved_by: str
    source_ref: str
    authority_fingerprint: str

    def __post_init__(self) -> None:
        if not self.version.strip() or not self.approved_by.strip() or not self.source_ref.strip():
            raise OverrideLearningError("approved learning policy requires version/provenance/approver")
        for fingerprint, name in (
            (self.draft_fingerprint, "draft_fingerprint"),
            (self.authority_fingerprint, "authority_fingerprint"),
        ):
            if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
                raise OverrideLearningError(f"{name} must be lowercase SHA-256")
        for action_type, multiplier in self.action_cost_multipliers.items():
            if not action_type.strip() or multiplier <= ZERO or multiplier > Decimal("5"):
                raise OverrideLearningError("learning cost multipliers must be in (0,5]")


def build_override_learning_draft(
    observations: tuple[OverrideLearningObservation, ...],
    *,
    model_family: str = "workforce-optimizer-override-learning",
    min_reason_count: int = 3,
    frequent_reason_ratio: Decimal = Decimal("0.30"),
    min_action_outcomes: int = 3,
) -> OverrideLearningDraft:
    if not model_family.strip():
        raise OverrideLearningError("model_family is required")
    if min_reason_count < 1 or min_action_outcomes < 1:
        raise OverrideLearningError("learning sample thresholds must be positive")
    if not (ZERO < frequent_reason_ratio <= ONE):
        raise OverrideLearningError("frequent_reason_ratio must be in (0,1]")
    ids = [item.override_id for item in observations]
    if len(ids) != len(set(ids)):
        raise OverrideLearningError("override observations must be unique")

    ordered = tuple(sorted(observations, key=lambda item: item.override_id))
    reason_counts: dict[str, int] = {}
    action_results: dict[str, list[bool]] = {}
    for observation in ordered:
        reason_counts[observation.reason_code] = reason_counts.get(observation.reason_code, 0) + 1
        if observation.worked is not None:
            action_results.setdefault(observation.action_type, []).append(observation.worked)

    sample_count = len(ordered)
    frequent = tuple(
        reason
        for reason, count in sorted(reason_counts.items())
        if count >= min_reason_count
        and sample_count > 0
        and Decimal(count) / Decimal(sample_count) >= frequent_reason_ratio
    )
    success_rates: dict[str, Decimal] = {}
    multipliers: dict[str, Decimal] = {}
    for action_type, results in sorted(action_results.items()):
        rate = Decimal(sum(1 for result in results if result)) / Decimal(len(results))
        success_rates[action_type] = rate
        if len(results) < min_action_outcomes:
            multipliers[action_type] = ONE
        elif rate < Decimal("0.50"):
            multipliers[action_type] = Decimal("1.50")
        elif rate >= Decimal("0.80"):
            multipliers[action_type] = Decimal("0.90")
        else:
            multipliers[action_type] = ONE

    input_payload = {
        "model_family": model_family,
        "min_reason_count": min_reason_count,
        "frequent_reason_ratio": _decimal_text(frequent_reason_ratio),
        "min_action_outcomes": min_action_outcomes,
        "observations": [item.canonical() for item in ordered],
    }
    input_fingerprint = _hash(input_payload)
    output_payload = {
        **input_payload,
        "input_fingerprint": input_fingerprint,
        "reason_counts": dict(sorted(reason_counts.items())),
        "frequent_override_reasons": list(frequent),
        "action_success_rates": {
            key: _decimal_text(value) for key, value in sorted(success_rates.items())
        },
        "suggested_cost_multipliers": {
            key: _decimal_text(value) for key, value in sorted(multipliers.items())
        },
        "automatic_apply_permitted": False,
        "human_approval_required": True,
    }
    draft_fingerprint = _hash(output_payload)
    return OverrideLearningDraft(
        model_family=model_family,
        sample_count=sample_count,
        completed_outcome_count=sum(len(values) for values in action_results.values()),
        reason_counts=reason_counts,
        frequent_override_reasons=frequent,
        action_success_rates=success_rates,
        suggested_cost_multipliers=multipliers,
        input_fingerprint=input_fingerprint,
        draft_fingerprint=draft_fingerprint,
        automatic_apply_permitted=False,
        human_approval_required=True,
    )


def apply_approved_learning_policy(
    candidates: tuple[OptimizationCandidate, ...],
    policy: ApprovedOverrideLearningPolicy,
) -> tuple[OptimizationCandidate, ...]:
    """Return a new candidate set with versioned advisory cost adjustments."""

    adjusted: list[OptimizationCandidate] = []
    for candidate in candidates:
        multiplier = policy.action_cost_multipliers.get(candidate.action_type, ONE)
        adjusted_cost = int(
            (Decimal(candidate.incremental_cost_minor_units) * multiplier).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        adjusted.append(
            OptimizationCandidate(
                candidate_id=candidate.candidate_id,
                action_type=candidate.action_type,
                capacity_gain_man_hours=candidate.capacity_gain_man_hours,
                incremental_cost_minor_units=adjusted_cost,
                source_ref=(
                    f"{candidate.source_ref}|learning:{policy.version}:"
                    f"{policy.authority_fingerprint}"
                ),
                available=candidate.available,
                legal_eligible=candidate.legal_eligible,
                skill_target=candidate.skill_target,
            )
        )
    return tuple(adjusted)
