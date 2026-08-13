"""Fail-closed transition guard for the blocked orders-v2 policy proposal.

Replay state is loaded from a version-controlled append-only ledger colocated
with this module. Callers cannot supply or clear consumed proposal state. The
guard remains non-mutating: passing it only yields reviewable evidence for a
later manual version-controlled policy change.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.ai_orders_v2_manual_policy_promotion import (
    OrdersV2ManualPolicyPromotionProposal,
)
from app.core.ai_query_contract_policy import (
    AI_QUERY_CONTRACT_POLICIES,
    ai_query_contract_policy_fingerprint,
)

ORDERS_V2_POLICY_TRANSITION_GUARD_VERSION = 2
ORDERS_V2_POLICY_PROPOSAL_MAX_AGE = timedelta(hours=6)
ORDERS_V2_POLICY_TRANSITION_BLOCKER = "orders_v2_manual_policy_patch_required"
CONSUMPTION_LEDGER_PATH = Path(__file__).with_name(
    "orders_v2_policy_consumption_ledger.json"
)
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class OrdersV2PolicyConsumptionEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_fingerprint: str = Field(pattern=SHA256_PATTERN)
    consumed_at: datetime
    previous_entry_fingerprint: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )

    @model_validator(mode="after")
    def validate_timestamp(self) -> OrdersV2PolicyConsumptionEntry:
        if self.consumed_at.tzinfo is None or self.consumed_at.utcoffset() is None:
            raise ValueError("consumption timestamp must be timezone-aware")
        return self

    @property
    def entry_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class OrdersV2PolicyConsumptionLedger(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    ledger_kind: Literal["orders_v2_policy_proposal_consumption_ledger"]
    previous_ledger_fingerprint: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    entries: tuple[OrdersV2PolicyConsumptionEntry, ...]

    @model_validator(mode="after")
    def validate_append_only_chain(self) -> OrdersV2PolicyConsumptionLedger:
        seen: set[str] = set()
        previous: str | None = None
        for entry in self.entries:
            if entry.proposal_fingerprint in seen:
                raise ValueError("consumption ledger contains duplicate proposal")
            if entry.previous_entry_fingerprint != previous:
                raise ValueError("consumption ledger fingerprint chain broken")
            seen.add(entry.proposal_fingerprint)
            previous = entry.entry_fingerprint
        return self

    @property
    def ledger_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def consumed_proposal_fingerprints(self) -> frozenset[str]:
        return frozenset(entry.proposal_fingerprint for entry in self.entries)


def load_orders_v2_policy_consumption_ledger() -> OrdersV2PolicyConsumptionLedger:
    try:
        payload = json.loads(CONSUMPTION_LEDGER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("canonical consumption ledger unavailable or invalid") from exc
    return OrdersV2PolicyConsumptionLedger.model_validate(payload)


class OrdersV2PolicyTransitionGuardArtifact(BaseModel):
    """Immutable evidence that one proposal passed freshness/drift/replay checks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[2]
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

    proposal_fingerprint = proposal.proposal_fingerprint
    ledger = load_orders_v2_policy_consumption_ledger()
    if proposal_fingerprint in ledger.consumed_proposal_fingerprints:
        raise ValueError("policy proposal replay detected")

    current = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    observed_current_policy_fingerprint = ai_query_contract_policy_fingerprint(current)
    if proposal.current_policy_fingerprint != observed_current_policy_fingerprint:
        raise ValueError("active policy drift detected")

    age = evaluated_at - proposal.proposed_at
    if age > ORDERS_V2_POLICY_PROPOSAL_MAX_AGE:
        raise ValueError("policy proposal expired")

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
        proposal_age_seconds=int(age.total_seconds()),
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
