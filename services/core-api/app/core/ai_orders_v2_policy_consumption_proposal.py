"""Reviewed, non-mutating proposal for consuming one orders-v2 policy proposal.

This artifact binds one transition-guard decision to the exact canonical
consumption-ledger fingerprint and the exact next append-only ledger entry. It
cannot mutate the canonical ledger; applying the entry still requires a separate
version-controlled reviewed change.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.ai_orders_v2_policy_consumption_ledger import (
    build_next_orders_v2_policy_consumption_entry,
    get_orders_v2_policy_consumption_ledger,
)
from app.core.ai_orders_v2_policy_transition_guard import (
    OrdersV2PolicyTransitionGuardArtifact,
)

SHA256_PATTERN = r"^[0-9a-f]{64}$"
CONSUMPTION_PROPOSAL_VERSION = 1
CONSUMPTION_PROPOSAL_BLOCKER = "orders_v2_consumption_ledger_patch_required"


class OrdersV2PolicyConsumptionProposal(BaseModel):
    """Immutable proposal to append one reviewed entry to the canonical ledger."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    kind: Literal["orders_v2_policy_consumption_proposal"]
    proposed_at: datetime
    proposal_fingerprint: str = Field(pattern=SHA256_PATTERN)
    guard_fingerprint: str = Field(pattern=SHA256_PATTERN)
    current_ledger_fingerprint: str = Field(pattern=SHA256_PATTERN)
    proposed_entry_fingerprint: str = Field(pattern=SHA256_PATTERN)
    proposed_entry_sequence: int = Field(ge=1)
    proposed_entry_previous_fingerprint: str = Field(pattern=SHA256_PATTERN)
    manual_version_control_change_required: Literal[True]
    ledger_mutation_permitted: Literal[False]
    policy_mutation_permitted: Literal[False]
    execution_enable_permitted: Literal[False]
    promotion_eligible: Literal[False]
    production_ready: Literal[False]
    production_blocker: Literal["orders_v2_consumption_ledger_patch_required"]

    @model_validator(mode="after")
    def validate_timestamp(self) -> OrdersV2PolicyConsumptionProposal:
        if self.proposed_at.tzinfo is None or self.proposed_at.utcoffset() is None:
            raise ValueError("consumption proposal timestamp must be timezone-aware")
        return self

    @property
    def consumption_proposal_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def build_orders_v2_policy_consumption_proposal(
    *,
    guard: OrdersV2PolicyTransitionGuardArtifact,
    proposed_at: datetime,
) -> OrdersV2PolicyConsumptionProposal:
    """Bind a passed guard to the exact current ledger without appending to it."""

    if proposed_at.tzinfo is None or proposed_at.utcoffset() is None:
        raise ValueError("consumption proposal timestamp must be timezone-aware")
    if proposed_at < guard.evaluated_at:
        raise ValueError("consumption proposal cannot precede guard evaluation")
    if guard.transition_guard_passed is not True:
        raise ValueError("transition guard did not pass")
    if guard.policy_mutation_permitted is not False:
        raise ValueError("guard policy mutation state is invalid")
    if guard.execution_enable_permitted is not False:
        raise ValueError("guard execution state is invalid")
    if guard.promotion_eligible is not False or guard.production_ready is not False:
        raise ValueError("guard promotion state is invalid")

    ledger = get_orders_v2_policy_consumption_ledger()
    if guard.consumption_ledger_fingerprint != ledger.ledger_fingerprint:
        raise ValueError("consumption ledger drift detected")
    if guard.proposal_fingerprint in ledger.consumed_proposal_fingerprints:
        raise ValueError("policy proposal already consumed")

    entry = build_next_orders_v2_policy_consumption_entry(
        ledger=ledger,
        proposal_fingerprint=guard.proposal_fingerprint,
        guard_fingerprint=guard.guard_fingerprint,
        consumed_at=proposed_at,
    )
    return OrdersV2PolicyConsumptionProposal(
        version=CONSUMPTION_PROPOSAL_VERSION,
        kind="orders_v2_policy_consumption_proposal",
        proposed_at=proposed_at,
        proposal_fingerprint=guard.proposal_fingerprint,
        guard_fingerprint=guard.guard_fingerprint,
        current_ledger_fingerprint=ledger.ledger_fingerprint,
        proposed_entry_fingerprint=entry.entry_fingerprint,
        proposed_entry_sequence=entry.sequence,
        proposed_entry_previous_fingerprint=entry.previous_entry_fingerprint,
        manual_version_control_change_required=True,
        ledger_mutation_permitted=False,
        policy_mutation_permitted=False,
        execution_enable_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=CONSUMPTION_PROPOSAL_BLOCKER,
    )
