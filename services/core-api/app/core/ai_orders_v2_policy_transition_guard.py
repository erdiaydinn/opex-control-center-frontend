"""Fail-closed transition guard for the blocked orders-v2 policy proposal.

This module evaluates whether one manual policy-promotion proposal is still
fresh, still bound to the exact active blocked policy, and has not already been
consumed. Replay state comes only from the version-controlled canonical ledger;
callers cannot provide or suppress consumed proposal fingerprints.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.ai_orders_v2_manual_policy_promotion import (
    OrdersV2ManualPolicyPromotionProposal,
)
from app.core.ai_orders_v2_policy_consumption_ledger import (
    get_orders_v2_policy_consumption_ledger,
)
from app.core.ai_query_contract_policy import (
    AI_QUERY_CONTRACT_POLICIES,
    ai_query_contract_policy_fingerprint,
)

ORDERS_V2_POLICY_TRANSITION_GUARD_VERSION = 1
ORDERS_V2_POLICY_PROPOSAL_MAX_AGE = timedelta(hours=6)
ORDERS_V2_POLICY_TRANSITION_BLOCKER = "orders_v2_manual_policy_patch_required"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class OrdersV2PolicyTransitionGuardArtifact(BaseModel):
    """Immutable evidence that one proposal passed freshness/drift/replay checks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    kind: Literal["orders_v2_policy_transition_guard"]
    environment: Literal["production"]
    evaluated_at: datetime
    proposal_fingerprint: str = Field(pattern=SHA256_PATTERN)
    proposal_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    proposal_current_policy_fingerprint: str = Field(pattern=SHA256_PATTERN)
    observed_current_policy_fingerprint: str = Field(pattern=SHA256_PATTERN)
    target_review_fingerprint: str = Field(pattern=SHA256_PATTERN)
    consumption_ledger_fingerprint: str = Field(pattern=SHA256_PATTERN)
    proposal_age_seconds: int = Field(ge=0)
    proposal_max_age_seconds: Literal[21600]
    drift_detected: Literal[False]
    replay_detected: Literal[False]
    expired: Literal[False]
    transition_guard_passed: Literal[True]
    manual_version_control_change_required: Literal[True]
    policy_mutation_permitted: Literal[False]
    execution_enable_permitted: Literal[False]
    promotion_eligible: Literal[False]
    production_ready: Literal[False]
    production_blocker: Literal["orders_v2_manual_policy_patch_required"]

    @model_validator(mode="after")
    def validate_guard_snapshot(self) -> OrdersV2PolicyTransitionGuardArtifact:
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("transition evaluation timestamp must be timezone-aware")
        if (
            self.proposal_current_policy_fingerprint
            != self.observed_current_policy_fingerprint
        ):
            raise ValueError("policy drift detected")
        if self.proposal_age_seconds > self.proposal_max_age_seconds:
            raise ValueError("policy proposal expired")
        return self

    @property
    def guard_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def build_orders_v2_policy_transition_guard(
    *,
    proposal: OrdersV2ManualPolicyPromotionProposal,
    evaluated_at: datetime,
) -> OrdersV2PolicyTransitionGuardArtifact:
    """Reject stale, replayed, or drifted proposals without mutating policy."""

    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ValueError("transition evaluation timestamp must be timezone-aware")
    if proposal.proposed_at.tzinfo is None or proposal.proposed_at.utcoffset() is None:
        raise ValueError("policy proposal timestamp must be timezone-aware")
    if evaluated_at < proposal.proposed_at:
        raise ValueError("transition evaluation cannot precede proposal")
    if proposal.environment != "production":
        raise ValueError("transition guard requires production proposal")
    if proposal.manual_version_control_change_required is not True:
        raise ValueError("proposal manual change state is invalid")
    if proposal.policy_mutation_permitted is not False:
        raise ValueError("proposal policy mutation state is invalid")
    if proposal.execution_enable_permitted is not False:
        raise ValueError("proposal execution state is invalid")
    if proposal.promotion_eligible is not False or proposal.production_ready is not False:
        raise ValueError("proposal promotion state is invalid")

    ledger = get_orders_v2_policy_consumption_ledger()
    proposal_fingerprint = proposal.proposal_fingerprint
    if proposal_fingerprint in ledger.consumed_proposal_fingerprints:
        raise ValueError("policy proposal replay detected")

    current = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    observed_current_policy_fingerprint = ai_query_contract_policy_fingerprint(current)
    if proposal.current_policy_fingerprint != observed_current_policy_fingerprint:
        raise ValueError("active policy drift detected")

    age = evaluated_at - proposal.proposed_at
    if age > ORDERS_V2_POLICY_PROPOSAL_MAX_AGE:
        raise ValueError("policy proposal expired")

    age_seconds = int(age.total_seconds())
    return OrdersV2PolicyTransitionGuardArtifact(
        version=ORDERS_V2_POLICY_TRANSITION_GUARD_VERSION,
        kind="orders_v2_policy_transition_guard",
        environment="production",
        evaluated_at=evaluated_at,
        proposal_fingerprint=proposal_fingerprint,
        proposal_manifest_sha256=proposal.proposal_manifest_sha256,
        proposal_current_policy_fingerprint=proposal.current_policy_fingerprint,
        observed_current_policy_fingerprint=observed_current_policy_fingerprint,
        target_review_fingerprint=proposal.target_review_fingerprint,
        consumption_ledger_fingerprint=ledger.ledger_fingerprint,
        proposal_age_seconds=age_seconds,
        proposal_max_age_seconds=21600,
        drift_detected=False,
        replay_detected=False,
        expired=False,
        transition_guard_passed=True,
        manual_version_control_change_required=True,
        policy_mutation_permitted=False,
        execution_enable_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=ORDERS_V2_POLICY_TRANSITION_BLOCKER,
    )
