from __future__ import annotations

import threading

import pytest
from app.agent_budget_ledger import (
    AgentBudgetLedgerPort,
    BudgetAccount,
    BudgetMutation,
    BudgetMutationKind,
    BudgetTransaction,
    BudgetTransactionResult,
    BudgetVector,
    execute_budget_transaction,
)


def vector(value: int) -> BudgetVector:
    return BudgetVector(
        tokens=value,
        cost_units=value,
        wall_time_seconds=value,
        tool_calls=value,
        transitions=value,
        descendants=value,
    )


class FakeDurablePort(AgentBudgetLedgerPort):
    """Test port that models one serializable durable transaction."""

    def __init__(self, root: BudgetAccount):
        self.accounts = {root.account_id: root}
        self.results: dict[tuple[str, str], BudgetTransactionResult] = {}
        self.fingerprints: dict[tuple[str, str], str] = {}
        self.reservations: dict[tuple[str, str], BudgetVector] = {}
        self.lock = threading.Lock()

    def get_account(self, *, tenant_id: str, account_id: str) -> BudgetAccount | None:
        item = self.accounts.get(account_id)
        return item if item is not None and item.tenant_id == tenant_id else None

    def transact(self, transaction: BudgetTransaction) -> BudgetTransactionResult:
        with self.lock:
            replay_key = (transaction.tenant_id, transaction.idempotency_key)
            prior_fingerprint = self.fingerprints.get(replay_key)
            if prior_fingerprint is not None:
                if prior_fingerprint != transaction.request_fingerprint:
                    raise ValueError("agent_budget_idempotency_conflict")
                return self.results[replay_key].model_copy(update={"replayed": True})

            current: dict[str, BudgetAccount] = {}
            for mutation in transaction.mutations:
                account = self.accounts.get(mutation.account_id)
                if account is None or account.tenant_id != transaction.tenant_id:
                    raise ValueError("agent_budget_account_not_found")
                if account.root_account_id != transaction.root_account_id:
                    raise ValueError("agent_budget_root_mismatch")
                if account.version != mutation.expected_version:
                    raise ValueError("agent_budget_version_conflict")
                current[mutation.account_id] = account

            updated: list[BudgetAccount] = []
            child_creations: list[BudgetAccount] = []
            reservation_updates = dict(self.reservations)
            for mutation in transaction.mutations:
                account = current[mutation.account_id]
                changes = {"version": account.version + 1}
                reservation_key = (account.account_id, mutation.reservation_ref or "")
                if mutation.kind is BudgetMutationKind.RESERVE:
                    if not mutation.amount.fits_within(account.available()):
                        raise ValueError("agent_budget_insufficient")
                    changes["reserved"] = account.reserved.plus(mutation.amount)
                    reservation_updates[reservation_key] = mutation.amount
                elif mutation.kind is BudgetMutationKind.CONSUME:
                    held = reservation_updates.get(reservation_key)
                    if held is None or not mutation.amount.fits_within(held):
                        raise ValueError("agent_budget_reservation_missing")
                    changes["reserved"] = account.reserved.minus(mutation.amount)
                    changes["consumed"] = account.consumed.plus(mutation.amount)
                    reservation_updates[reservation_key] = held.minus(mutation.amount)
                elif mutation.kind is BudgetMutationKind.RELEASE:
                    held = reservation_updates.get(reservation_key)
                    if held is None or not mutation.amount.fits_within(held):
                        raise ValueError("agent_budget_reservation_missing")
                    if not mutation.amount.fits_within(
                        account.reserved.minus(account.unknown_effect_held)
                    ):
                        raise ValueError("agent_budget_unknown_effect_release_forbidden")
                    changes["reserved"] = account.reserved.minus(mutation.amount)
                    reservation_updates[reservation_key] = held.minus(mutation.amount)
                elif mutation.kind is BudgetMutationKind.HOLD_UNKNOWN_EFFECT:
                    held = reservation_updates.get(reservation_key)
                    if held is None or not mutation.amount.fits_within(held):
                        raise ValueError("agent_budget_reservation_missing")
                    changes["unknown_effect_held"] = account.unknown_effect_held.plus(
                        mutation.amount
                    )
                elif mutation.kind is BudgetMutationKind.RESOLVE_UNKNOWN_EFFECT:
                    if not mutation.amount.fits_within(account.unknown_effect_held):
                        raise ValueError("agent_budget_unknown_effect_hold_missing")
                    changes["unknown_effect_held"] = account.unknown_effect_held.minus(
                        mutation.amount
                    )
                else:
                    if mutation.child_account_id in self.accounts:
                        raise ValueError("agent_budget_child_reset_forbidden")
                    if not mutation.amount.fits_within(account.available()):
                        raise ValueError("agent_budget_insufficient")
                    changes["delegated"] = account.delegated.plus(mutation.amount)
                    child_creations.append(BudgetAccount(
                        account_id=mutation.child_account_id or "",
                        tenant_id=account.tenant_id,
                        root_account_id=account.root_account_id,
                        parent_account_id=account.account_id,
                        allocation=mutation.amount,
                        version=0,
                    ))
                updated.append(account.model_copy(update=changes))

            for account in (*updated, *child_creations):
                self.accounts[account.account_id] = account
            self.reservations = reservation_updates
            result = BudgetTransactionResult(
                transaction_id=transaction.transaction_id,
                idempotency_key=transaction.idempotency_key,
                request_fingerprint=transaction.request_fingerprint,
                accounts=tuple(updated),
            )
            self.fingerprints[replay_key] = transaction.request_fingerprint
            self.results[replay_key] = result
            return result


def root(*, tenant: str = "YS_TR", amount: int = 10) -> BudgetAccount:
    return BudgetAccount(
        account_id="budget://root",
        tenant_id=tenant,
        root_account_id="budget://root",
        allocation=vector(amount),
        version=0,
    )


def tx(key: str, mutation: BudgetMutation, *, fingerprint: str = "a" * 64, tenant="YS_TR"):
    return BudgetTransaction(
        transaction_id=f"txn://{key}",
        idempotency_key=key,
        request_fingerprint=fingerprint,
        tenant_id=tenant,
        root_account_id="budget://root",
        mutations=(mutation,),
    )


def test_reserve_replay_is_exactly_once_and_conflicting_payload_is_rejected():
    port = FakeDurablePort(root())
    mutation = BudgetMutation(
        kind=BudgetMutationKind.RESERVE,
        account_id="budget://root",
        expected_version=0,
        amount=vector(3),
        reservation_ref="reservation://job-1",
    )
    first = execute_budget_transaction(port=port, transaction=tx("reserve-1", mutation))
    replay = execute_budget_transaction(port=port, transaction=tx("reserve-1", mutation))
    assert first.accounts[0].reserved == vector(3)
    assert replay.replayed is True
    assert port.accounts["budget://root"].version == 1
    with pytest.raises(ValueError, match="agent_budget_idempotency_conflict"):
        execute_budget_transaction(
            port=port,
            transaction=tx("reserve-1", mutation, fingerprint="b" * 64),
        )


def test_child_allocation_is_conserved_and_existing_child_cannot_be_reset():
    port = FakeDurablePort(root())
    allocate = BudgetMutation(
        kind=BudgetMutationKind.ALLOCATE_CHILD,
        account_id="budget://root",
        expected_version=0,
        amount=vector(6),
        child_account_id="budget://child-1",
    )
    execute_budget_transaction(port=port, transaction=tx("child-1", allocate))
    assert port.accounts["budget://root"].delegated == vector(6)
    assert port.accounts["budget://child-1"].allocation == vector(6)
    assert port.accounts["budget://root"].available() == vector(4)
    with pytest.raises(ValueError, match="agent_budget_child_reset_forbidden"):
        execute_budget_transaction(
            port=port,
            transaction=tx(
                "child-reset",
                allocate.model_copy(update={"expected_version": 1}),
                fingerprint="c" * 64,
            ),
        )


def test_consume_and_release_are_idempotent_across_every_dimension():
    port = FakeDurablePort(root())
    reserve = BudgetMutation(
        kind=BudgetMutationKind.RESERVE,
        account_id="budget://root",
        expected_version=0,
        amount=vector(8),
        reservation_ref="reservation://job",
    )
    execute_budget_transaction(port=port, transaction=tx("r", reserve))
    consume = BudgetMutation(
        kind=BudgetMutationKind.CONSUME,
        account_id="budget://root",
        expected_version=1,
        amount=vector(5),
        reservation_ref="reservation://job",
    )
    execute_budget_transaction(port=port, transaction=tx("c", consume, fingerprint="b" * 64))
    release = BudgetMutation(
        kind=BudgetMutationKind.RELEASE,
        account_id="budget://root",
        expected_version=2,
        amount=vector(3),
        reservation_ref="reservation://job",
    )
    execute_budget_transaction(port=port, transaction=tx("x", release, fingerprint="c" * 64))
    execute_budget_transaction(port=port, transaction=tx("x", release, fingerprint="c" * 64))
    account = port.accounts["budget://root"]
    assert account.consumed == vector(5)
    assert account.reserved.is_zero()
    assert account.version == 3


def test_concurrent_last_budget_race_has_one_cas_winner():
    port = FakeDurablePort(root(amount=1))
    outcomes: list[str] = []

    def reserve(key: str) -> None:
        try:
            execute_budget_transaction(
                port=port,
                transaction=tx(key, BudgetMutation(
                    kind=BudgetMutationKind.RESERVE,
                    account_id="budget://root",
                    expected_version=0,
                    amount=vector(1),
                    reservation_ref=f"reservation://{key}",
                ), fingerprint=("a" if key == "one" else "b") * 64),
            )
            outcomes.append("won")
        except ValueError as exc:
            outcomes.append(str(exc))

    threads = [threading.Thread(target=reserve, args=(key,)) for key in ("one", "two")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcomes.count("won") == 1
    assert outcomes.count("agent_budget_version_conflict") == 1
    assert port.accounts["budget://root"].reserved == vector(1)


def test_unknown_effect_hold_cannot_be_released_until_explicit_resolution():
    port = FakeDurablePort(root())
    reserve = BudgetMutation(
        kind=BudgetMutationKind.RESERVE,
        account_id="budget://root",
        expected_version=0,
        amount=vector(4),
        reservation_ref="reservation://effect",
    )
    execute_budget_transaction(port=port, transaction=tx("reserve", reserve))
    hold = BudgetMutation(
        kind=BudgetMutationKind.HOLD_UNKNOWN_EFFECT,
        account_id="budget://root",
        expected_version=1,
        amount=vector(4),
        reservation_ref="reservation://effect",
    )
    execute_budget_transaction(port=port, transaction=tx("hold", hold, fingerprint="b" * 64))
    release = BudgetMutation(
        kind=BudgetMutationKind.RELEASE,
        account_id="budget://root",
        expected_version=2,
        amount=vector(4),
        reservation_ref="reservation://effect",
    )
    with pytest.raises(ValueError, match="unknown_effect_release_forbidden"):
        execute_budget_transaction(
            port=port,
            transaction=tx("release", release, fingerprint="c" * 64),
        )


def test_tenant_isolation_and_result_adapter_binding_fail_closed():
    port = FakeDurablePort(root())
    mutation = BudgetMutation(
        kind=BudgetMutationKind.RESERVE,
        account_id="budget://root",
        expected_version=0,
        amount=vector(1),
        reservation_ref="reservation://foreign",
    )
    with pytest.raises(ValueError, match="agent_budget_account_not_found"):
        execute_budget_transaction(
            port=port,
            transaction=tx("foreign", mutation, tenant="tenant-b"),
        )
