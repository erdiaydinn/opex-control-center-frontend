"""Constraint-aware Workforce optimizer authority for roadmap 14/60.

The optimizer consumes an immutable DPI/root-cause result. It never recomputes
demand, capacity or root cause, and it never executes staffing changes. The
output is a deterministic proposal subject to legal, availability, skill, cost
and action-count constraints plus explicit human approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
from itertools import combinations
import json

ZERO = Decimal("0")
ALLOWED_ACTION_TYPES = frozenset(
    {
        "skill_reassign",
        "skill_call_in",
        "call_in",
        "extend_shift",
        "move_break",
    }
)
SKILL_TARGETED_ACTIONS = frozenset({"skill_reassign", "skill_call_in"})


class OptimizerAuthorityError(ValueError):
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
class OptimizationCandidate:
    candidate_id: str
    action_type: str
    capacity_gain_man_hours: Decimal
    incremental_cost_minor_units: int
    source_ref: str
    available: bool = True
    legal_eligible: bool = True
    skill_target: str | None = None

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise OptimizerAuthorityError("candidate_id is required")
        if self.action_type not in ALLOWED_ACTION_TYPES:
            raise OptimizerAuthorityError(f"unsupported optimizer action: {self.action_type}")
        if self.capacity_gain_man_hours < ZERO:
            raise OptimizerAuthorityError("capacity gain cannot be negative")
        if self.incremental_cost_minor_units < 0:
            raise OptimizerAuthorityError("incremental cost cannot be negative")
        if not self.source_ref.strip():
            raise OptimizerAuthorityError("optimizer candidate requires source_ref provenance")
        if self.action_type in SKILL_TARGETED_ACTIONS and not (self.skill_target or "").strip():
            raise OptimizerAuthorityError("skill-targeted action requires skill_target")

    def canonical(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "action_type": self.action_type,
            "capacity_gain_man_hours": _decimal_text(self.capacity_gain_man_hours),
            "incremental_cost_minor_units": self.incremental_cost_minor_units,
            "source_ref": self.source_ref,
            "available": self.available,
            "legal_eligible": self.legal_eligible,
            "skill_target": self.skill_target,
        }


@dataclass(frozen=True, slots=True)
class OptimizerRequest:
    tenant_id: str
    location_id: str
    model_version: str
    dpi_snapshot_fingerprint: str
    root_cause: str
    manpower_shortage: bool
    capacity_gap_man_hours: Decimal
    skill_deficit_man_hours: Decimal
    candidates: tuple[OptimizationCandidate, ...]
    max_incremental_cost_minor_units: int
    max_actions: int = 4
    required_skill: str | None = None
    gap_tolerance_man_hours: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not self.location_id.strip():
            raise OptimizerAuthorityError("tenant_id and location_id are required")
        if not self.model_version.strip():
            raise OptimizerAuthorityError("model_version is required")
        if len(self.dpi_snapshot_fingerprint) != 64 or any(
            ch not in "0123456789abcdef" for ch in self.dpi_snapshot_fingerprint
        ):
            raise OptimizerAuthorityError("dpi_snapshot_fingerprint must be lowercase SHA-256")
        if self.root_cause not in {
            "skill_mix_constraint",
            "manpower_capacity_shortage",
            "execution_or_process",
            "no_pressure_signal",
        }:
            raise OptimizerAuthorityError("unsupported root cause")
        if self.capacity_gap_man_hours < ZERO or self.skill_deficit_man_hours < ZERO:
            raise OptimizerAuthorityError("optimizer gaps cannot be negative")
        if self.max_incremental_cost_minor_units < 0:
            raise OptimizerAuthorityError("max incremental cost cannot be negative")
        if not (1 <= self.max_actions <= 6):
            raise OptimizerAuthorityError("max_actions must be between 1 and 6")
        if len(self.candidates) > 24:
            raise OptimizerAuthorityError("optimizer candidate pool exceeds reviewed bound of 24")
        ids = [candidate.candidate_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise OptimizerAuthorityError("candidate_id values must be unique")
        if self.root_cause == "skill_mix_constraint" and not (self.required_skill or "").strip():
            raise OptimizerAuthorityError("skill_mix_constraint requires required_skill")


@dataclass(frozen=True, slots=True)
class OptimizerProposal:
    tenant_id: str
    location_id: str
    model_version: str
    dpi_snapshot_fingerprint: str
    input_fingerprint: str
    proposal_fingerprint: str
    recommendation_type: str
    selected_candidate_ids: tuple[str, ...]
    selected_actions: tuple[dict[str, object], ...]
    target_gap_man_hours: Decimal
    covered_gap_man_hours: Decimal
    remaining_gap_man_hours: Decimal
    incremental_cost_minor_units: int
    feasible: bool
    automatic_execution_permitted: bool
    human_approval_required: bool
    explanation: tuple[str, ...]

    def as_record(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "location_id": self.location_id,
            "model_version": self.model_version,
            "dpi_snapshot_fingerprint": self.dpi_snapshot_fingerprint,
            "input_fingerprint": self.input_fingerprint,
            "proposal_fingerprint": self.proposal_fingerprint,
            "recommendation_type": self.recommendation_type,
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "selected_actions": list(self.selected_actions),
            "target_gap_man_hours": _decimal_text(self.target_gap_man_hours),
            "covered_gap_man_hours": _decimal_text(self.covered_gap_man_hours),
            "remaining_gap_man_hours": _decimal_text(self.remaining_gap_man_hours),
            "incremental_cost_minor_units": self.incremental_cost_minor_units,
            "feasible": self.feasible,
            "automatic_execution_permitted": self.automatic_execution_permitted,
            "human_approval_required": self.human_approval_required,
            "explanation": list(self.explanation),
        }


def _eligible_candidates(request: OptimizerRequest) -> tuple[OptimizationCandidate, ...]:
    eligible = [
        candidate
        for candidate in request.candidates
        if candidate.available
        and candidate.legal_eligible
        and candidate.capacity_gain_man_hours > ZERO
        and candidate.incremental_cost_minor_units <= request.max_incremental_cost_minor_units
    ]
    if request.root_cause == "skill_mix_constraint":
        eligible = [
            candidate
            for candidate in eligible
            if candidate.action_type in SKILL_TARGETED_ACTIONS
            and candidate.skill_target == request.required_skill
        ]
    return tuple(sorted(eligible, key=lambda item: item.candidate_id))


def _choose_combination(
    request: OptimizerRequest,
    target_gap: Decimal,
) -> tuple[OptimizationCandidate, ...]:
    eligible = _eligible_candidates(request)
    best: tuple[tuple[object, ...], tuple[OptimizationCandidate, ...]] | None = None
    for action_count in range(1, min(request.max_actions, len(eligible)) + 1):
        for combo in combinations(eligible, action_count):
            cost = sum(candidate.incremental_cost_minor_units for candidate in combo)
            if cost > request.max_incremental_cost_minor_units:
                continue
            gain = sum((candidate.capacity_gain_man_hours for candidate in combo), ZERO)
            remaining = max(target_gap - gain, ZERO)
            covers = remaining <= request.gap_tolerance_man_hours
            # Prefer full coverage, then smallest residual gap, then lowest cost,
            # then fewer actions, then stable candidate ids.
            score = (
                0 if covers else 1,
                remaining,
                cost,
                action_count,
                tuple(candidate.candidate_id for candidate in combo),
            )
            if best is None or score < best[0]:
                best = (score, combo)
    return best[1] if best is not None else ()


def build_optimizer_proposal(request: OptimizerRequest) -> OptimizerProposal:
    input_payload = {
        "tenant_id": request.tenant_id,
        "location_id": request.location_id,
        "model_version": request.model_version,
        "dpi_snapshot_fingerprint": request.dpi_snapshot_fingerprint,
        "root_cause": request.root_cause,
        "manpower_shortage": request.manpower_shortage,
        "capacity_gap_man_hours": _decimal_text(request.capacity_gap_man_hours),
        "skill_deficit_man_hours": _decimal_text(request.skill_deficit_man_hours),
        "required_skill": request.required_skill,
        "max_incremental_cost_minor_units": request.max_incremental_cost_minor_units,
        "max_actions": request.max_actions,
        "gap_tolerance_man_hours": _decimal_text(request.gap_tolerance_man_hours),
        "candidates": [
            candidate.canonical()
            for candidate in sorted(request.candidates, key=lambda item: item.candidate_id)
        ],
    }
    input_fingerprint = _hash(input_payload)

    if request.root_cause in {"execution_or_process", "no_pressure_signal"}:
        selected: tuple[OptimizationCandidate, ...] = ()
        target_gap = ZERO
        recommendation_type = "no_staffing_change"
        explanation = (
            "DPI root cause does not support staffing as the primary corrective action",
            "staffing candidates were intentionally not evaluated for execution",
        )
    elif request.root_cause == "skill_mix_constraint":
        target_gap = max(request.skill_deficit_man_hours, request.capacity_gap_man_hours)
        selected = _choose_combination(request, target_gap)
        recommendation_type = "skill_targeted_capacity_proposal"
        explanation = (
            "generic manpower shortage is not proven",
            "only legal available skill-targeted candidates may cover the governed skill gap",
        )
    else:
        if not request.manpower_shortage:
            raise OptimizerAuthorityError(
                "manpower_capacity_shortage root cause requires manpower_shortage=true"
            )
        target_gap = request.capacity_gap_man_hours
        selected = _choose_combination(request, target_gap)
        recommendation_type = "capacity_gap_proposal"
        explanation = (
            "governed DPI proves a manpower capacity gap",
            "proposal minimizes residual gap then incremental cost under reviewed constraints",
        )

    covered = sum((candidate.capacity_gain_man_hours for candidate in selected), ZERO)
    remaining = max(target_gap - covered, ZERO)
    cost = sum(candidate.incremental_cost_minor_units for candidate in selected)
    feasible = remaining <= request.gap_tolerance_man_hours
    automatic_execution_permitted = False
    human_approval_required = bool(selected)
    selected_ids = tuple(candidate.candidate_id for candidate in selected)
    selected_actions = tuple(candidate.canonical() for candidate in selected)

    output_payload = {
        **input_payload,
        "input_fingerprint": input_fingerprint,
        "recommendation_type": recommendation_type,
        "selected_candidate_ids": list(selected_ids),
        "target_gap_man_hours": _decimal_text(target_gap),
        "covered_gap_man_hours": _decimal_text(covered),
        "remaining_gap_man_hours": _decimal_text(remaining),
        "incremental_cost_minor_units": cost,
        "feasible": feasible,
        "automatic_execution_permitted": automatic_execution_permitted,
        "human_approval_required": human_approval_required,
    }
    proposal_fingerprint = _hash(output_payload)

    return OptimizerProposal(
        tenant_id=request.tenant_id,
        location_id=request.location_id,
        model_version=request.model_version,
        dpi_snapshot_fingerprint=request.dpi_snapshot_fingerprint,
        input_fingerprint=input_fingerprint,
        proposal_fingerprint=proposal_fingerprint,
        recommendation_type=recommendation_type,
        selected_candidate_ids=selected_ids,
        selected_actions=selected_actions,
        target_gap_man_hours=target_gap,
        covered_gap_man_hours=covered,
        remaining_gap_man_hours=remaining,
        incremental_cost_minor_units=cost,
        feasible=feasible,
        automatic_execution_permitted=automatic_execution_permitted,
        human_approval_required=human_approval_required,
        explanation=explanation,
    )
