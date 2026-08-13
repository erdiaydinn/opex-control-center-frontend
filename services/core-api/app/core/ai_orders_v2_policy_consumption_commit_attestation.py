"""Attest an exact version-controlled orders-v2 consumption-ledger candidate.

This is deliberately non-mutating: it proves that a proposed post-commit ledger
is exactly the one authorized by a reviewed patch artifact. It never writes the
canonical ledger or changes query/execution policy.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.ai_orders_v2_policy_consumption_ledger import (
    OrdersV2PolicyConsumptionLedger,
)
from app.core.ai_orders_v2_policy_consumption_patch import (
    OrdersV2PolicyConsumptionPatchArtifact,
)

SHA256_PATTERN = r"^[0-9a-f]{64}$"
COMMIT_ATTESTATION_VERSION = 1
COMMIT_ATTESTATION_BLOCKER = "orders_v2_human_merge_required"


class OrdersV2PolicyConsumptionCommitAttestation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    kind: Literal["orders_v2_policy_consumption_commit_attestation"]
    patch_fingerprint: str = Field(pattern=SHA256_PATTERN)
    previous_ledger_fingerprint: str = Field(pattern=SHA256_PATTERN)
    appended_entry_fingerprint: str = Field(pattern=SHA256_PATTERN)
    resulting_ledger_fingerprint: str = Field(pattern=SHA256_PATTERN)
    resulting_entry_count: int = Field(ge=1)
    commit_candidate_validated: Literal[True]
    human_merge_required: Literal[True]
    ledger_mutation_permitted: Literal[False]
    policy_mutation_permitted: Literal[False]
    execution_enable_permitted: Literal[False]
    promotion_eligible: Literal[False]
    production_ready: Literal[False]
    production_blocker: Literal["orders_v2_human_merge_required"]

    @property
    def attestation_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def attest_orders_v2_policy_consumption_commit_candidate(
    *,
    previous_ledger: OrdersV2PolicyConsumptionLedger,
    candidate_ledger: OrdersV2PolicyConsumptionLedger,
    patch: OrdersV2PolicyConsumptionPatchArtifact,
) -> OrdersV2PolicyConsumptionCommitAttestation:
    """Require the exact single ledger append authorized by the reviewed patch."""

    if patch.append_validation_passed is not True:
        raise ValueError("consumption patch validation did not pass")
    if patch.manual_version_control_commit_required is not True:
        raise ValueError("consumption patch commit state is invalid")
    if (
        patch.ledger_mutation_permitted is not False
        or patch.policy_mutation_permitted is not False
    ):
        raise ValueError("consumption patch mutation state is invalid")
    if patch.execution_enable_permitted is not False:
        raise ValueError("consumption patch execution state is invalid")
    if patch.current_ledger_fingerprint != previous_ledger.ledger_fingerprint:
        raise ValueError("previous ledger fingerprint mismatch")
    if candidate_ledger.ledger_fingerprint != patch.resulting_ledger_fingerprint:
        raise ValueError("resulting ledger fingerprint mismatch")
    if len(candidate_ledger.entries) != len(previous_ledger.entries) + 1:
        raise ValueError("candidate ledger must contain exactly one appended entry")
    if candidate_ledger.entries[:-1] != previous_ledger.entries:
        raise ValueError("candidate ledger rewrites historical entries")

    appended = candidate_ledger.entries[-1]
    if appended.sequence != patch.expected_next_sequence:
        raise ValueError("candidate ledger sequence mismatch")
    if appended.entry_fingerprint != patch.proposed_entry_fingerprint:
        raise ValueError("candidate appended entry fingerprint mismatch")

    return OrdersV2PolicyConsumptionCommitAttestation(
        version=COMMIT_ATTESTATION_VERSION,
        kind="orders_v2_policy_consumption_commit_attestation",
        patch_fingerprint=patch.patch_fingerprint,
        previous_ledger_fingerprint=previous_ledger.ledger_fingerprint,
        appended_entry_fingerprint=appended.entry_fingerprint,
        resulting_ledger_fingerprint=candidate_ledger.ledger_fingerprint,
        resulting_entry_count=len(candidate_ledger.entries),
        commit_candidate_validated=True,
        human_merge_required=True,
        ledger_mutation_permitted=False,
        policy_mutation_permitted=False,
        execution_enable_permitted=False,
        promotion_eligible=False,
        production_ready=False,
        production_blocker=COMMIT_ATTESTATION_BLOCKER,
    )
