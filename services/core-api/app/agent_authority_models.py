"""Shared sealed models for Jarvis PostgreSQL agent authority."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class BudgetVector(BaseModel):
    cost_units: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    wall_time_seconds: int = Field(default=0, ge=0)
    transitions: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    descendants: int = Field(default=0, ge=0)

    def plus(self, other: "BudgetVector") -> "BudgetVector":
        return BudgetVector(
            cost_units=self.cost_units + other.cost_units,
            tokens=self.tokens + other.tokens,
            wall_time_seconds=self.wall_time_seconds + other.wall_time_seconds,
            transitions=self.transitions + other.transitions,
            tool_calls=self.tool_calls + other.tool_calls,
            descendants=self.descendants + other.descendants,
        )

    def minus(self, other: "BudgetVector") -> "BudgetVector":
        values = {
            "cost_units": self.cost_units - other.cost_units,
            "tokens": self.tokens - other.tokens,
            "wall_time_seconds": self.wall_time_seconds - other.wall_time_seconds,
            "transitions": self.transitions - other.transitions,
            "tool_calls": self.tool_calls - other.tool_calls,
            "descendants": self.descendants - other.descendants,
        }
        if any(value < 0 for value in values.values()):
            raise ValueError("agent_budget_underflow")
        return BudgetVector(**values)

    def fits_within(self, other: "BudgetVector") -> bool:
        return (
            self.cost_units <= other.cost_units
            and self.tokens <= other.tokens
            and self.wall_time_seconds <= other.wall_time_seconds
            and self.transitions <= other.transitions
            and self.tool_calls <= other.tool_calls
            and self.descendants <= other.descendants
        )

    def is_zero(self) -> bool:
        return not any(self.model_dump().values())


class BudgetMutationKind(StrEnum):
    RESERVE = "reserve"
    CONSUME = "consume"
    RELEASE = "release"
    HOLD_UNKNOWN_EFFECT = "hold_unknown_effect"
    RESOLVE_UNKNOWN_EFFECT = "resolve_unknown_effect"
    ALLOCATE_CHILD = "allocate_child"


class BudgetMutation(BaseModel):
    kind: BudgetMutationKind
    account_id: str = Field(min_length=1, max_length=255)
    expected_version: int = Field(ge=0)
    amount: BudgetVector
    reservation_ref: str | None = Field(default=None, max_length=500)
    child_account_id: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_identity(self) -> "BudgetMutation":
        if self.amount.is_zero():
            raise ValueError("agent_budget_zero_mutation_forbidden")
        if self.kind is BudgetMutationKind.ALLOCATE_CHILD:
            if not self.child_account_id or self.reservation_ref is not None:
                raise ValueError("agent_budget_child_allocation_identity_invalid")
        elif not self.reservation_ref or self.child_account_id is not None:
            raise ValueError("agent_budget_reservation_identity_invalid")
        return self


class BudgetTransaction(BaseModel):
    transaction_id: str = Field(min_length=1, max_length=255)
    idempotency_key: str = Field(min_length=1, max_length=240)
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    tenant_id: UUID
    root_account_id: str = Field(min_length=1, max_length=255)
    mutations: tuple[BudgetMutation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_accounts(self) -> "BudgetTransaction":
        account_ids = [item.account_id for item in self.mutations]
        if len(account_ids) != len(set(account_ids)):
            raise ValueError("agent_budget_transaction_duplicate_account_mutation")
        return self


class BudgetAccountRecord(BaseModel):
    tenant_id: UUID
    root_job_id: UUID
    account_id: str
    root_account_id: str
    parent_account_id: str | None
    allocation: BudgetVector
    reserved: BudgetVector
    consumed: BudgetVector
    delegated: BudgetVector
    unknown_effect_held: BudgetVector
    version: int

    def available(self) -> BudgetVector:
        return self.allocation.minus(
            self.reserved.plus(self.consumed).plus(self.delegated)
        )


class BudgetTransactionResult(BaseModel):
    transaction_id: str
    idempotency_key: str
    request_fingerprint: str
    accounts: tuple[BudgetAccountRecord, ...]
    replayed: bool = False


class CommitFenceBinding(BaseModel):
    tenant_id: UUID
    job_id: UUID
    root_job_id: UUID
    resource_ref: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    lease_id: str = Field(min_length=1, max_length=255)
    lease_generation: int = Field(ge=1)
    fencing_token: int = Field(ge=1)
    cancellation_epoch: int = Field(ge=0)
    authorization_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class CommitPermitRecord(BaseModel):
    permit_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding: CommitFenceBinding
    issued_at: datetime
    consumed: bool = True


class WorkerAuthorityRecord(BaseModel):
    tenant_id: UUID
    job_id: UUID
    worker_id: str = Field(min_length=1, max_length=255)
    runtime_instance_ref: str = Field(min_length=1, max_length=500)
    runtime_kind: str = Field(pattern=r"^(kubernetes|docker)$")
    image_digest: str = Field(
        pattern=r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$"
    )
    workload_identity: str = Field(min_length=1, max_length=500)
    tenant_namespace: str = Field(min_length=1, max_length=255)
    attestation_policy_ref: str = Field(min_length=1, max_length=500)
    attestation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    worker_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation: int = Field(ge=1)
    version: int = Field(ge=0)
    state: str
    heartbeat_at: datetime
    revocation_generation: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_namespace(self) -> "WorkerAuthorityRecord":
        if self.tenant_namespace != f"tenant:{self.tenant_id}":
            raise ValueError("agent_worker_tenant_namespace_not_isolated")
        return self


def _vector_from_row(row: Any, suffix: str) -> BudgetVector:
    return BudgetVector(
        cost_units=int(row[f"cost_{suffix}"]),
        tokens=int(row[f"token_{suffix}"]),
        wall_time_seconds=int(row[f"wall_time_{suffix}"]),
        transitions=int(row[f"transition_{suffix}"]),
        tool_calls=int(row[f"tool_call_{suffix}"]),
        descendants=int(row[f"descendant_{suffix}"]),
    )


def _account(row: Any) -> BudgetAccountRecord:
    return BudgetAccountRecord(
        tenant_id=row["tenant_id"],
        root_job_id=row["root_job_id"],
        account_id=row["account_id"],
        root_account_id=row["root_account_id"],
        parent_account_id=row["parent_account_id"],
        allocation=_vector_from_row(row, "limit"),
        reserved=_vector_from_row(row, "reserved"),
        consumed=_vector_from_row(row, "consumed"),
        delegated=_vector_from_row(row, "delegated"),
        unknown_effect_held=_vector_from_row(row, "unknown_effect_held"),
        version=int(row["version"]),
    )


def _vector_params(prefix: str, vector: BudgetVector) -> dict[str, int]:
    return {
        f"{prefix}_cost": vector.cost_units,
        f"{prefix}_token": vector.tokens,
        f"{prefix}_wall_time": vector.wall_time_seconds,
        f"{prefix}_transition": vector.transitions,
        f"{prefix}_tool_call": vector.tool_calls,
        f"{prefix}_descendant": vector.descendants,
    }


def _reservation_vector(row: Any, suffix: str = "units") -> BudgetVector:
    return BudgetVector(
        cost_units=int(row[f"cost_{suffix}"]),
        tokens=int(row[f"token_{suffix}"]),
        wall_time_seconds=int(row[f"wall_time_{suffix}"]),
        transitions=int(row[f"transition_{suffix}"]),
        tool_calls=int(row[f"tool_call_{suffix}"]),
        descendants=int(row[f"descendant_{suffix}"]),
    )
