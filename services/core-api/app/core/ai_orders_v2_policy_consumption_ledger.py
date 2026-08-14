"""Version-controlled append-only consumption ledger for orders-v2 proposals.

The canonical ledger is code-reviewed state, not caller input. Runtime transition
checks can read it but cannot append to it. Consuming a proposal therefore
requires a separate version-controlled change that extends the hash chain.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SHA256_PATTERN = r"^[0-9a-f]{64}$"
LEDGER_VERSION = 1
LEDGER_GENESIS_FINGERPRINT = hashlib.sha256(
    b"EAY:orders-v2-policy-consumption-ledger:v1:genesis"
).hexdigest()


class OrdersV2PolicyConsumptionEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int = Field(ge=1)
    consumed_at: datetime
    proposal_fingerprint: str = Field(pattern=SHA256_PATTERN)
    guard_fingerprint: str = Field(pattern=SHA256_PATTERN)
    previous_entry_fingerprint: str = Field(pattern=SHA256_PATTERN)

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
    kind: Literal["orders_v2_policy_consumption_ledger"]
    entries: tuple[OrdersV2PolicyConsumptionEntry, ...] = ()

    @model_validator(mode="after")
    def validate_append_only_chain(self) -> OrdersV2PolicyConsumptionLedger:
        expected_previous = LEDGER_GENESIS_FINGERPRINT
        seen: set[str] = set()
        for expected_sequence, entry in enumerate(self.entries, start=1):
            if entry.sequence != expected_sequence:
                raise ValueError("consumption ledger sequence is not contiguous")
            if entry.previous_entry_fingerprint != expected_previous:
                raise ValueError("consumption ledger hash chain mismatch")
            if entry.proposal_fingerprint in seen:
                raise ValueError("proposal fingerprint consumed more than once")
            seen.add(entry.proposal_fingerprint)
            expected_previous = entry.entry_fingerprint
        return self

    @property
    def ledger_fingerprint(self) -> str:
        payload = {
            "version": self.version,
            "kind": self.kind,
            "genesis": LEDGER_GENESIS_FINGERPRINT,
            "entry_fingerprints": [entry.entry_fingerprint for entry in self.entries],
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def consumed_proposal_fingerprints(self) -> frozenset[str]:
        return frozenset(entry.proposal_fingerprint for entry in self.entries)


CANONICAL_ORDERS_V2_POLICY_CONSUMPTION_LEDGER = OrdersV2PolicyConsumptionLedger(
    version=LEDGER_VERSION,
    kind="orders_v2_policy_consumption_ledger",
    entries=(),
)


def get_orders_v2_policy_consumption_ledger() -> OrdersV2PolicyConsumptionLedger:
    """Return authoritative version-controlled replay state."""

    return CANONICAL_ORDERS_V2_POLICY_CONSUMPTION_LEDGER


def build_next_orders_v2_policy_consumption_entry(
    *,
    ledger: OrdersV2PolicyConsumptionLedger,
    proposal_fingerprint: str,
    guard_fingerprint: str,
    consumed_at: datetime,
) -> OrdersV2PolicyConsumptionEntry:
    """Build the next reviewable entry without mutating canonical ledger state."""

    if proposal_fingerprint in ledger.consumed_proposal_fingerprints:
        raise ValueError("policy proposal already consumed")
    previous = (
        ledger.entries[-1].entry_fingerprint
        if ledger.entries
        else LEDGER_GENESIS_FINGERPRINT
    )
    return OrdersV2PolicyConsumptionEntry(
        sequence=len(ledger.entries) + 1,
        consumed_at=consumed_at,
        proposal_fingerprint=proposal_fingerprint,
        guard_fingerprint=guard_fingerprint,
        previous_entry_fingerprint=previous,
    )
