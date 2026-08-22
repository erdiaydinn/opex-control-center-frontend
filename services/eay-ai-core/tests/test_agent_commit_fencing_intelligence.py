from datetime import UTC, datetime

import pytest

from app.agent_commit_fencing import (
    AgentCommitReceipt,
    AtomicCommitPermit,
    BackendCommitOutcome,
    CommitFenceDisposition,
    CommitFenceError,
    CommitFenceRequest,
    RobotExecutionCommitBinding,
    derive_commit_identity,
    execute_fenced_commit,
)

NOW = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)
AUTH = "a" * 64


def robot_binding(**changes):
    values = {
        "tenant_id": "YS_TR",
        "company_id": "company-a",
        "objective_id": "daily-report",
        "robot_id": "daily-report-download",
        "robot_version": 9,
        "registry_generation": 7,
        "version_fingerprint": "b" * 64,
        "execution_lease_id": "c" * 64,
        "execution_lease_generation": 2,
        "pin_fingerprint": "d" * 64,
    }
    values.update(changes)
    return RobotExecutionCommitBinding(**values)


def request(**changes):
    identity = derive_commit_identity(
        tenant_id="YS_TR", tool_name="inventory.adjust", arguments={"sku": "42", "qty": 3}
    )
    values = {
        "job_id": "job-1",
        "root_job_id": "root-1",
        "tenant_id": "YS_TR",
        "lease_id": "lease-1",
        "lease_generation": 4,
        "fencing_token": 19,
        "cancellation_epoch": 2,
        "authorization_fingerprint": AUTH,
        "identity": identity,
        "requested_at": NOW,
    }
    values.update(changes)
    return CommitFenceRequest(**values)


def permit(req, **changes):
    values = {
        "permit_id": "permit-1",
        "job_id": req.job_id,
        "root_job_id": req.root_job_id,
        "tenant_id": req.tenant_id,
        "lease_id": req.lease_id,
        "lease_generation": req.lease_generation,
        "fencing_token": req.fencing_token,
        "cancellation_epoch": req.cancellation_epoch,
        "resource_ref": req.identity.resource_ref,
        "idempotency_key": req.identity.idempotency_key,
        "authorization_fingerprint": req.authorization_fingerprint,
        "robot_execution": req.robot_execution,
        "issued_at": NOW,
    }
    values.update(changes)
    return AtomicCommitPermit(**values)


class Authority:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = 0

    async def authorize_and_consume(self, req):
        self.calls += 1
        if self.error:
            raise CommitFenceError(self.error)
        return self.response or permit(req)


def test_identity_is_canonical_and_tenant_bound():
    left = derive_commit_identity(
        tenant_id="YS_TR", tool_name="inventory.adjust", arguments={"qty": 3, "sku": "42"}
    )
    right = derive_commit_identity(
        tenant_id="YS_TR", tool_name="inventory.adjust", arguments={"sku": "42", "qty": 3}
    )
    foreign = derive_commit_identity(
        tenant_id="OTHER", tool_name="inventory.adjust", arguments={"sku": "42", "qty": 3}
    )
    assert left == right
    assert left.idempotency_key != foreign.idempotency_key
    assert left.resource_ref != foreign.resource_ref


@pytest.mark.asyncio
async def test_verified_commit_returns_integrity_bound_releasable_receipt():
    req = request()
    receipt = await execute_fenced_commit(
        request=req,
        authority=Authority(),
        commit=lambda _: BackendCommitOutcome(
            transaction_ref="tx-1",
            committed=True,
            effect_verified=True,
            evidence_refs=("evidence://tx-1",),
        ),
        recorded_at=NOW,
    )
    assert receipt.disposition is CommitFenceDisposition.VERIFIED_COMMIT
    assert receipt.lease_release_allowed is True
    AgentCommitReceipt.model_validate(receipt.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_verified_robot_commit_retains_exact_registry_and_execution_lease_binding():
    binding = robot_binding()
    req = request(robot_execution=binding)
    receipt = await execute_fenced_commit(
        request=req,
        authority=Authority(),
        commit=lambda _: BackendCommitOutcome(
            transaction_ref="tx-robot-1",
            committed=True,
            effect_verified=True,
            evidence_refs=("evidence://robot/readback",),
        ),
        recorded_at=NOW,
    )
    assert receipt.disposition is CommitFenceDisposition.VERIFIED_COMMIT
    assert receipt.robot_execution == binding
    assert receipt.robot_execution.registry_generation == 7
    assert receipt.robot_execution.robot_version == 9
    assert receipt.evidence_ref.endswith(receipt.fingerprint)


@pytest.mark.asyncio
async def test_atomic_permit_cannot_drop_or_swap_robot_execution_binding():
    req = request(robot_execution=robot_binding())
    called = False

    def backend(_):
        nonlocal called
        called = True
        return BackendCommitOutcome(committed=False)

    dropped = permit(req, robot_execution=None)
    with pytest.raises(CommitFenceError, match="robot_execution_binding_mismatch"):
        await execute_fenced_commit(
            request=req,
            authority=Authority(response=dropped),
            commit=backend,
            recorded_at=NOW,
        )
    assert called is False

    swapped = permit(
        req,
        robot_execution=robot_binding(registry_generation=8),
    )
    with pytest.raises(CommitFenceError, match="robot_execution_binding_mismatch"):
        await execute_fenced_commit(
            request=req,
            authority=Authority(response=swapped),
            commit=backend,
            recorded_at=NOW,
        )
    assert called is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        "agent_commit_stale_fencing_token",
        "agent_commit_cancelled_epoch",
        "agent_commit_stale_lease_generation",
        "agent_commit_idempotency_replay",
        "agent_commit_stale_robot_registry_generation",
    ],
)
async def test_atomic_authority_rejects_stale_cancelled_and_replayed_commit_before_dispatch(error):
    called = False

    def backend(_):
        nonlocal called
        called = True
        return BackendCommitOutcome(committed=False)

    with pytest.raises(CommitFenceError, match=error):
        await execute_fenced_commit(
            request=request(), authority=Authority(error=error), commit=backend, recorded_at=NOW
        )
    assert called is False


@pytest.mark.asyncio
async def test_cancel_or_generation_race_in_returned_permit_fails_before_dispatch():
    req = request()
    stale = permit(req, cancellation_epoch=req.cancellation_epoch + 1)
    called = False

    def backend(_):
        nonlocal called
        called = True
        return BackendCommitOutcome(committed=False)

    with pytest.raises(CommitFenceError, match="atomic_permit_binding_mismatch"):
        await execute_fenced_commit(
            request=req, authority=Authority(response=stale), commit=backend, recorded_at=NOW
        )
    assert called is False


@pytest.mark.asyncio
async def test_backend_timeout_after_dispatch_becomes_unknown_effect_and_holds_lease():
    async def backend(_):
        raise TimeoutError("response lost after possible commit")

    receipt = await execute_fenced_commit(
        request=request(), authority=Authority(), commit=backend, recorded_at=NOW
    )
    assert receipt.disposition is CommitFenceDisposition.UNKNOWN_EFFECT
    assert receipt.effect_verified is False
    assert receipt.lease_release_allowed is False
    assert receipt.error_code == "agent_commit_backend_outcome_unknown:TimeoutError"


@pytest.mark.asyncio
async def test_unverified_success_is_unknown_effect_not_success():
    receipt = await execute_fenced_commit(
        request=request(),
        authority=Authority(),
        commit=lambda _: BackendCommitOutcome(
            transaction_ref="tx-maybe", committed=True, effect_verified=False
        ),
        recorded_at=NOW,
    )
    assert receipt.disposition is CommitFenceDisposition.UNKNOWN_EFFECT
    assert receipt.lease_release_allowed is False


def test_model_cannot_claim_business_authority_or_cross_tenant_identity():
    with pytest.raises(ValueError, match="never_grants_business_authority"):
        request(business_execution_authority_granted=True)
    foreign = derive_commit_identity(
        tenant_id="OTHER", tool_name="inventory.adjust", arguments={"sku": "42", "qty": 3}
    )
    with pytest.raises(ValueError, match="identity_tenant_mismatch"):
        request(identity=foreign)
    with pytest.raises(ValueError, match="robot_execution_tenant_mismatch"):
        request(robot_execution=robot_binding(tenant_id="OTHER"))
