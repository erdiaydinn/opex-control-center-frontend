from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from .legal_promotion_gate import LegalPromotionDecision
from .legal_registry_verification_intake import RegistryBoundVerificationIntake
from .legal_relations import LegalRelationRecord
from .legal_temporal import LegalTemporalState

TEMPORAL_REVIEW_BLOCKER = "requires_human_reviewed_temporal_legal_activation"


class RegistryTemporalPromotionEvidence(BaseModel):
    """Non-mutating proof that registry-bound legal evidence is temporally coherent.

    This artifact is deliberately downstream of exact-source promotion review and the
    existing relation/temporal resolver.  It can prove that a reviewed amendment,
    repeal or supersession produced the expected historical state, but it cannot
    mutate legal records or activate an instrument by itself.
    """

    instrument_id: str
    relation_type: Literal["new", "amends", "repeals", "supersedes"]
    related_instrument_id: str | None
    as_of: date
    intake_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    promotion_decision_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    relation_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    temporal_resolution_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    temporal_state_resolved: Literal[True] = True
    expected_temporal_effect_observed: Literal[True] = True
    human_review_required: Literal[True] = True
    registry_mutation_permitted: Literal[False] = False
    legal_activation_permitted: Literal[False] = False
    auto_promote: Literal[False] = False
    production_blocker: Literal[
        "requires_human_reviewed_temporal_legal_activation"
    ] = TEMPORAL_REVIEW_BLOCKER
    evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def _fingerprint(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_registry_temporal_promotion_evidence(
    intake: RegistryBoundVerificationIntake,
    promotion_decision: LegalPromotionDecision,
    temporal_state: LegalTemporalState,
    *,
    relation: LegalRelationRecord | None = None,
) -> RegistryTemporalPromotionEvidence:
    """Bind exact registry intake, promotion review and resolved temporal state fail closed."""

    if not promotion_decision.eligible:
        raise ValueError("registry_temporal_gate_requires_eligible_promotion_review")
    if promotion_decision.auto_promote or not promotion_decision.requires_human_action:
        raise ValueError("registry_temporal_gate_requires_human_promotion_boundary")
    if promotion_decision.content_sha256 != intake.exact_binding_content_sha256:
        raise ValueError("registry_temporal_gate_promotion_content_mismatch")
    if not temporal_state.resolved:
        raise ValueError("registry_temporal_gate_unresolved_temporal_state")

    as_of = date.fromisoformat(temporal_state.as_of)
    if as_of < intake.effective_from:
        raise ValueError("registry_temporal_gate_state_precedes_effective_date")
    if intake.instrument_key not in temporal_state.active_instrument_ids:
        raise ValueError("registry_temporal_gate_source_instrument_not_active")

    relation_fingerprint: str | None = None
    target = intake.related_instrument_id
    if intake.relation_type == "new":
        if target is not None or relation is not None:
            raise ValueError("registry_temporal_gate_new_instrument_relation_forbidden")
    else:
        if target is None:
            raise ValueError("registry_temporal_gate_relation_target_required")
        if relation is None:
            raise ValueError("registry_temporal_gate_approved_relation_required")
        if relation.status != "approved":
            raise ValueError("registry_temporal_gate_relation_must_be_approved")
        if relation.source_instrument_id != intake.instrument_key:
            raise ValueError("registry_temporal_gate_relation_source_mismatch")
        if relation.relation_type != intake.relation_type:
            raise ValueError("registry_temporal_gate_relation_type_mismatch")
        if relation.target_instrument_id != target:
            raise ValueError("registry_temporal_gate_relation_target_mismatch")
        if relation.id not in temporal_state.applied_relation_ids:
            raise ValueError("registry_temporal_gate_relation_not_applied")
        relation_fingerprint = relation.relation_fingerprint

        target_is_active = target in temporal_state.active_instrument_ids
        target_is_inactive = target in temporal_state.inactive_instrument_ids
        if intake.relation_type == "amends":
            if not target_is_active or target_is_inactive:
                raise ValueError("registry_temporal_gate_amendment_target_state_mismatch")
        else:
            if target_is_active or not target_is_inactive:
                raise ValueError("registry_temporal_gate_inactive_target_required")

    payload: dict[str, object] = {
        "instrument_id": intake.instrument_key,
        "relation_type": intake.relation_type,
        "related_instrument_id": target,
        "as_of": temporal_state.as_of,
        "intake_fingerprint": intake.intake_fingerprint,
        "promotion_decision_fingerprint": promotion_decision.decision_fingerprint,
        "relation_fingerprint": relation_fingerprint,
        "temporal_resolution_fingerprint": temporal_state.resolution_fingerprint,
        "temporal_state_resolved": True,
        "expected_temporal_effect_observed": True,
        "human_review_required": True,
        "registry_mutation_permitted": False,
        "legal_activation_permitted": False,
        "auto_promote": False,
        "production_blocker": TEMPORAL_REVIEW_BLOCKER,
    }
    return RegistryTemporalPromotionEvidence(
        **payload,
        evidence_fingerprint=_fingerprint(payload),
    )
