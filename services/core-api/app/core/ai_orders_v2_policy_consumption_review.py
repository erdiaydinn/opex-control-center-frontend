"""Human-reviewed proposal for one append-only orders-v2 consumption entry.

This module binds a successful transition-guard artifact to the exact current
version-controlled consumption ledger and one independent reviewer. It only
produces a reviewable proposal for a later code-reviewed ledger append; it never
mutates canonical ledger state, query policy, or execution readiness.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.ai_orders_v2_live_cross_tenant_evidence import sha256_text
from app.core.ai_orders_v2_manual_policy_promotion import (
    OrdersV2ManualPolicyPromotionProposal,
)
from app.core.ai_orders_v2_policy_consumption_ledger import (
    OrdersV2PolicyConsumptionLedger,
    build_next_orders_v2_policy_consumption_entry,
)
from app.core.ai_orders_v2_policy_transition_guard import (
    OrdersV2PolicyTransitionGuardArtifact,
)

SHA256_PATTERN = r"^[0-9a-f]{64}$"
CONSUMPTION_REVIEW_VERSION = 1
CONSUMPTION_REVIEW_BLOCKER = "orders_v2_consumption_ledger_append_required"


class OrdersV2PolicyConsumptionReviewProposal(BaseModel):
    """Immutable approval to propose one ledger entry, never to append it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    kind: Literal["orders_v2_policy_consumption_review_proposal"]
    reviewed_at: datetime
    reviewer_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    current_ledger_fingerprint: str = Field(pattern=SHA256_PATTERN)
    proposal_fingerprint: str = Field(pattern=SHA256_PATTERN)
    guard_fingerprint: str = Field(pattern=SHA256_PATTERN)
    proposed_entry_fingerprint: str = Field(pattern=SHA256_PATTERN)
    proposed_entry_sequence: int = Field(ge=1)
    review_decision: Literal["APPROVE_FOR_VERSION_CONTROLLED_LEDGER_APPEND"]
    human_review_completed: Literal[True]
    version_controlled_ledger_append_required: Literal[True]
    ledger_mutation_permitted: Literal[False]
    policy_mutation_permitted: Literal[False]
    execution_enable_permitted: Literal[False]
    promotion_eligible: Literal[False]
    production_ready: Literal[False]
    production_blocker: Literal["orders_v2_consumption_ledger_append_required"]

    @model_validator(mode="after")
    def validate_snapshot(self) -> OrdersV2PolicyConsumptionReviewProposal:
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("consumption review timestamp must be timezone-aware")
        return self

    @property
    def review_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def build_orders_v2_policy_consumption_review_proposal(
    *,
    ledger: OrdersV2PolicyConsumptionLedger,
    proposal: OrdersV2ManualPolicyPromotionProposal,
    guard: OrdersV2PolicyTransitionGuardArtifact,
    reviewer_identity: str,
    reviewed_at: datetime,
) -> OrdersV2PolicyConsumptionReviewProposal:
    """Bind one independent human review to exact guard/proposal/ledger state."""

    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ValueError("consumption review timestamp must be timezone-aware")
    if reviewed_at < proposal.proposed_at:
        raise ValueError("consumption review cannot precede policy proposal")
    if reviewed_at < guard.evaluated_at:
        raise ValueError("consumption review cannot precede transition guard")
    if guard.transition_guard_passed is not True:
        raise ValueError("transition guard did not pass")
    if guard.policy_mutation_permitted is not False:
        raise ValueError("transition guard policy mutation state is invalid")
    if guard.execution_enable_permitted is not False:
        raise ValueError("transition guard execution state is invalid")
    if guard.proposal_fingerprint != proposal.proposal_fingerprint:
        raise ValueError("transition guard is not bound to proposal")
    if guard.consumption_ledger_fingerprint != ledger.ledger_fingerprint:
        raise ValueError("consumption ledger drift detected")
    if proposal.proposal_fingerprint in ledger.consumed_proposal_fingerprints:
        raise ValueError("policy proposal already consumed")

    reviewer_sha256 = sha256_text(reviewer_identity)
    if reviewer_sha256 == proposal.policy_promoter_identity_sha256:
        raise ValueError("consumption reviewer must be independent of policy promoter")

    proposed_entry = build_next_orders_v2_policy_consumption_entry(
        ledger=ledger,
        proposal_fingerprint=proposal.proposal_fingerprint,
        guard_fingerprint=guard.guard_fingerprint,
        consumed_at=reviewed_at,
    )
    return OrdersV2PolicyConsumptionReviewProposal(
        version=CONSUMPTION_REVIEW_VERSION,
        kind="orders_v2_policy_consumption_review_proposal",
        reviewed_at=reviewed_at,
        reviewer_identity_sha256=reviewer_sha256,
        current_ledger_fingerprint=ledger.ledger_fingerprint,
        proposal_fingerprint=proposal.proposal_fingerprint,
        guard_fingerprint=guard.guard_fingerprint,
        proposed_entry_fingerprint=proposed_entry.entry_fingerprint,
        proposed_entry_sequence=proposed_entry.sequence,
        review_decision="APPROVE_FOR_VERSION_CONTROLLED_LEDGER_APPEND",
        human_review_completed=True,
        version_controlled_ledger_append_required=True,
        ledger_mutation_permitted=False,
        policy_mutation_permitted=False,
        execution_enable_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=CONSUMPTION_REVIEW_BLOCKER,
    )
