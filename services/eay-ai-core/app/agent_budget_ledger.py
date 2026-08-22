"""Persistence-agnostic, atomic budget ledger contract for delegated agents.

The product deliberately does not ship an in-memory or SQLite authority.  A durable
adapter must implement :class:`AgentBudgetLedgerPort` and commit every transaction
with compare-and-swap and idempotency in one storage transaction.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

AGENT_BUDGET_LEDGER_CONTRACT = "eay-agent-budget-ledger-v1"


class BudgetVector(BaseModel):
    tokens: int = Field(default=0, ge=0)
    cost_units: int = Field(default=0, ge=0)
    wall_time_seconds: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    transitions: int = Field(default=0, ge=0)
    descendants: int = Field(default=0, ge=0)

    def plus(self, other: BudgetVector) -> BudgetVector:
        values = {
            name: getattr(self, name) + getattr(other, name)
            for name in type(self).model_fields
        }
        return BudgetVector(**values)

    def minus(self, other: BudgetVector) -> BudgetVector:
        values = {
            name: getattr(self, name) - getattr(other, name)
            for name in type(self).model_fields
        }
        if any(value < 0 for value in values.values()):
            raise ValueError("agent_budget_underflow")
        return BudgetVector(**values)

    def fits_within(self, other: BudgetVector) -> bool:
        return all(
            getattr(self, name) <= getattr(other, name)
            for name in type(self).model_fields
        )

    def is_zero(self) -> bool:
        return all(getattr(self, name) == 0 for name in type(self).model_fields)


class BudgetAccount(BaseModel):
    contract: str = AGENT_BUDGET_LEDGER_CONTRACT
    account_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    root_account_id: str = Field(min_length=1)
    parent_account_id: str | None = None
    allocation: BudgetVector
    reserved: BudgetVector = Field(default_factory=BudgetVector)
    consumed: BudgetVector = Field(default_factory=BudgetVector)
    delegated: BudgetVector = Field(default_factory=BudgetVector)
    unknown_effect_held: BudgetVector = Field(default_factory=BudgetVector)
    version: int = Field(ge=0)

    @model_validator(mode="after")
    def account_is_conservative(self) -> BudgetAccount:
        if self.parent_account_id is None and self.account_id != self.root_account_id:
            raise ValueError("agent_budget_root_identity_mismatch")
        if self.parent_account_id is not None and self.account_id == self.root_account_id:
            raise ValueError("agent_budget_child_cannot_be_root")
        committed = self.reserved.plus(self.consumed).plus(self.delegated)
        if not committed.fits_within(self.allocation):
            raise ValueError("agent_budget_allocation_exceeded")
        if not self.unknown_effect_held.fits_within(self.reserved):
            raise ValueError("agent_budget_unknown_effect_must_remain_reserved")
        return self

    def available(self) -> BudgetVector:
        return self.allocation.minus(self.reserved.plus(self.consumed).plus(self.delegated))


class BudgetMutationKind(str, Enum):
    RESERVE = "reserve"
    CONSUME = "consume"
    RELEASE = "release"
    HOLD_UNKNOWN_EFFECT = "hold_unknown_effect"
    RESOLVE_UNKNOWN_EFFECT = "resolve_unknown_effect"
    ALLOCATE_CHILD = "allocate_child"


class BudgetMutation(BaseModel):
    kind: BudgetMutationKind
    account_id: str = Field(min_length=1)
    expected_version: int = Field(ge=0)
    amount: BudgetVector
    reservation_ref: str | None = None
    child_account_id: str | None = None

    @model_validator(mode="after")
    def mutation_has_required_identity(self) -> BudgetMutation:
        if self.amount.is_zero():
            raise ValueError("agent_budget_zero_mutation_forbidden")
        if self.kind is BudgetMutationKind.ALLOCATE_CHILD:
            if not self.child_account_id or self.reservation_ref is not None:
                raise ValueError("agent_budget_child_allocation_identity_invalid")
        elif not self.reservation_ref or self.child_account_id is not None:
            raise ValueError("agent_budget_reservation_identity_invalid")
        return self


class BudgetTransaction(BaseModel):
    contract: str = AGENT_BUDGET_LEDGER_CONTRACT
    transaction_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    tenant_id: str = Field(min_length=1)
    root_account_id: str = Field(min_length=1)
    mutations: tuple[BudgetMutation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def transaction_is_unambiguous(self) -> BudgetTransaction:
        account_ids = [mutation.account_id for mutation in self.mutations]
        if len(account_ids) != len(set(account_ids)):
            raise ValueError("agent_budget_transaction_duplicate_account_mutation")
        return self


class BudgetTransactionResult(BaseModel):
    contract: str = AGENT_BUDGET_LEDGER_CONTRACT
    transaction_id: str
    idempotency_key: str
    request_fingerprint: str
    accounts: tuple[BudgetAccount, ...]
    replayed: bool = False


@runtime_checkable
class AgentBudgetLedgerPort(Protocol):
    """Durable authority; CAS, idempotency and all mutations are one commit."""

    def get_account(self, *, tenant_id: str, account_id: str) -> BudgetAccount | None: ...

    def transact(self, transaction: BudgetTransaction) -> BudgetTransactionResult: ...


def validate_transaction_result(
    *, transaction: BudgetTransaction, result: BudgetTransactionResult
) -> None:
    """Reject a lying/misbound persistence adapter at the application boundary."""

    if result.transaction_id != transaction.transaction_id:
        raise ValueError("agent_budget_result_transaction_mismatch")
    if result.idempotency_key != transaction.idempotency_key:
        raise ValueError("agent_budget_result_idempotency_mismatch")
    if result.request_fingerprint != transaction.request_fingerprint:
        raise ValueError("agent_budget_result_fingerprint_mismatch")
    mutated_ids = {item.account_id for item in transaction.mutations}
    if {item.account_id for item in result.accounts} != mutated_ids:
        raise ValueError("agent_budget_result_account_coverage_mismatch")
    if any(item.tenant_id != transaction.tenant_id for item in result.accounts):
        raise ValueError("agent_budget_result_tenant_mismatch")
    if any(item.root_account_id != transaction.root_account_id for item in result.accounts):
        raise ValueError("agent_budget_result_root_mismatch")


def execute_budget_transaction(
    *, port: AgentBudgetLedgerPort, transaction: BudgetTransaction
) -> BudgetTransactionResult:
    result = port.transact(transaction)
    validate_transaction_result(transaction=transaction, result=result)
    return result
