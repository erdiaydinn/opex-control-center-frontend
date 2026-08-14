"""Fail-closed, non-mutating patch candidate for the orders-v2 consumption ledger."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.ai_orders_v2_policy_consumption_ledger import (
    OrdersV2PolicyConsumptionLedger,
    build_next_orders_v2_policy_consumption_entry,
)
from app.core.ai_orders_v2_policy_consumption_review import (
    OrdersV2PolicyConsumptionReviewProposal,
)

SHA256_PATTERN = r"^[0-9a-f]{64}$"
CONSUMPTION_PATCH_VERSION = 1
CONSUMPTION_PATCH_BLOCKER = "orders_v2_manual_ledger_commit_required"


class OrdersV2PolicyConsumptionPatchArtifact(BaseModel):
    """Immutable proof that one reviewed append matches exact ledger state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    kind: Literal["orders_v2_policy_consumption_patch_candidate"]
    review_fingerprint: str = Field(pattern=SHA256_PATTERN)
    current_ledger_fingerprint: str = Field(pattern=SHA256_PATTERN)
    proposed_entry_fingerprint: str = Field(pattern=SHA256_PATTERN)
    expected_next_sequence: int = Field(ge=1)
    resulting_ledger_fingerprint: str = Field(pattern=SHA256_PATTERN)
    append_validation_passed: Literal[True]
    manual_version_control_commit_required: Literal[True]
    ledger_mutation_permitted: Literal[False]
    policy_mutation_permitted: Literal[False]
    execution_enable_permitted: Literal[False]
    promotion_eligible: Literal[False]
    production_ready: Literal[False]
    production_blocker: Literal["orders_v2_manual_ledger_commit_required"]

    @model_validator(mode="after")
    def validate_non_mutating_state(self) -> OrdersV2PolicyConsumptionPatchArtifact:
        if self.expected_next_sequence < 1:
            raise ValueError("expected ledger sequence is invalid")
        return self

    @property
    def patch_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def build_orders_v2_policy_consumption_patch_candidate(
    *,
    ledger: OrdersV2PolicyConsumptionLedger,
    review: OrdersV2PolicyConsumptionReviewProposal,
) -> OrdersV2PolicyConsumptionPatchArtifact:
    """Validate exact reviewed append without mutating canonical ledger state."""

    if review.human_review_completed is not True:
        raise ValueError("consumption review is incomplete")
    if review.version_controlled_ledger_append_required is not True:
        raise ValueError("consumption review append state is invalid")
    if review.ledger_mutation_permitted is not False:
        raise ValueError("consumption review mutation state is invalid")
    if review.policy_mutation_permitted is not False:
        raise ValueError("consumption review policy state is invalid")
    if review.execution_enable_permitted is not False:
        raise ValueError("consumption review execution state is invalid")
    if review.current_ledger_fingerprint != ledger.ledger_fingerprint:
        raise ValueError("consumption ledger drift detected")
    if review.proposal_fingerprint in ledger.consumed_proposal_fingerprints:
        raise ValueError("policy proposal already consumed")

    expected_sequence = len(ledger.entries) + 1
    if review.proposed_entry_sequence != expected_sequence:
        raise ValueError("proposed ledger sequence mismatch")

    expected_entry = build_next_orders_v2_policy_consumption_entry(
        ledger=ledger,
        proposal_fingerprint=review.proposal_fingerprint,
        guard_fingerprint=review.guard_fingerprint,
        consumed_at=review.reviewed_at,
    )
    if review.proposed_entry_fingerprint != expected_entry.entry_fingerprint:
        raise ValueError("proposed ledger entry fingerprint mismatch")

    resulting_ledger = OrdersV2PolicyConsumptionLedger(
        version=ledger.version,
        kind=ledger.kind,
        entries=(*ledger.entries, expected_entry),
    )
    return OrdersV2PolicyConsumptionPatchArtifact(
        version=CONSUMPTION_PATCH_VERSION,
        kind="orders_v2_policy_consumption_patch_candidate",
        review_fingerprint=review.review_fingerprint,
        current_ledger_fingerprint=ledger.ledger_fingerprint,
        proposed_entry_fingerprint=expected_entry.entry_fingerprint,
        expected_next_sequence=expected_sequence,
        resulting_ledger_fingerprint=resulting_ledger.ledger_fingerprint,
        append_validation_passed=True,
        manual_version_control_commit_required=True,
        ledger_mutation_permitted=False,
        policy_mutation_permitted=False,
        execution_enable_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=CONSUMPTION_PATCH_BLOCKER,
    )
