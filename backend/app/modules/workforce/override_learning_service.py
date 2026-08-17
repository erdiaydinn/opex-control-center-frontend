"""Service composition for roadmap 16/60 manager override learning."""

from __future__ import annotations

from .optimizer_authority import OptimizationCandidate, OptimizerProposal
from .optimizer_service import compute_and_persist_optimizer_proposal
from .override_learning_authority import (
    OverrideLearningDraft,
    apply_approved_learning_policy,
    build_override_learning_draft,
)
from .override_learning_repository import (
    load_approved_learning_policy,
    load_override_learning_observations,
    persist_learning_draft,
    persist_optimizer_learning_receipt,
)


def compute_and_persist_learning_draft(
    *,
    actor_subject: str,
) -> tuple[OverrideLearningDraft, dict[str, object]]:
    observations = load_override_learning_observations()
    draft = build_override_learning_draft(observations)
    receipt = persist_learning_draft(draft, actor_subject=actor_subject)
    return draft, receipt


def compute_learned_optimizer_proposal(
    *,
    location_id: str,
    raw_candidates: tuple[OptimizationCandidate, ...],
    max_incremental_cost_minor_units: int,
    learning_version: str,
    actor_subject: str,
    required_skill: str | None = None,
    max_actions: int = 4,
) -> tuple[OptimizerProposal, dict[str, object], dict[str, object]]:
    """Apply one explicitly approved learning version, then call item14 optimizer."""

    policy = load_approved_learning_policy(learning_version)
    adjusted_candidates = apply_approved_learning_policy(raw_candidates, policy)
    proposal, proposal_receipt = compute_and_persist_optimizer_proposal(
        location_id=location_id,
        candidates=adjusted_candidates,
        max_incremental_cost_minor_units=max_incremental_cost_minor_units,
        actor_subject=actor_subject,
        required_skill=required_skill,
        max_actions=max_actions,
    )
    learning_receipt = persist_optimizer_learning_receipt(
        location_id=location_id,
        optimizer_proposal_fingerprint=proposal.proposal_fingerprint,
        policy=policy,
        raw_candidates=raw_candidates,
        actor_subject=actor_subject,
    )
    return proposal, proposal_receipt, learning_receipt
