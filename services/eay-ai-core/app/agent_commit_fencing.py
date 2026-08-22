"""Fail-closed commit fencing for mutating Jarvis agent tools.

Planning, worker assignment and a global lane lease are necessary but are not commit
authority.  This module defines the final, atomic authority check that a mutating
adapter must perform immediately before its backend write.  Resource and idempotency
identities are derived from canonical tool arguments rather than accepted from a
model.  Cancellation, stale lease generations, stale fencing tokens and replay are
therefore rejected at the commit boundary.

The authority port is expected to be backed by one durable transaction/CAS operation.
Neither a permit nor a verified receipt grants business authority; the ordinary tool
authorization and global lease boundaries remain mandatory inputs.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

AGENT_COMMIT_FENCING_CONTRACT = "eay-agent-commit-fencing-v1"


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class CommitFenceDisposition(str, Enum):
    VERIFIED_COMMIT = "verified_commit"
    REJECTED = "rejected"
    UNKNOWN_EFFECT = "unknown_effect"


class CommitFenceError(RuntimeError):
    """A write was rejected before backend dispatch."""


class CanonicalCommitIdentity(BaseModel):
    contract: str = AGENT_COMMIT_FENCING_CONTRACT
    tenant_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    resource_ref: str = Field(min_length=1)
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")


def derive_commit_identity(
    *, tenant_id: str, tool_name: str, arguments: dict[str, object]
) -> CanonicalCommitIdentity:
    """Derive collision-resistant commit claims from normalized trusted inputs."""

    tenant = tenant_id.strip()
    tool = tool_name.strip()
    if not tenant or not tool:
        raise ValueError("agent_commit_identity_requires_tenant_and_tool")
    canonical_arguments = _canonical_json(arguments)
    arguments_sha256 = hashlib.sha256(canonical_arguments.encode("utf-8")).hexdigest()
    binding = {
        "contract": AGENT_COMMIT_FENCING_CONTRACT,
        "tenant_id": tenant,
        "tool_name": tool,
        "arguments_sha256": arguments_sha256,
    }
    binding_hash = _hash(binding)
    return CanonicalCommitIdentity(
        tenant_id=tenant,
        tool_name=tool,
        arguments_sha256=arguments_sha256,
        resource_ref=f"agent-tool-resource://{tenant}/{tool}/{binding_hash}",
        idempotency_key=_hash({**binding, "purpose": "idempotent-commit"}),
    )


class CommitFenceRequest(BaseModel):
    contract: str = AGENT_COMMIT_FENCING_CONTRACT
    job_id: str = Field(min_length=1)
    root_job_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    lease_generation: int = Field(ge=1)
    fencing_token: int = Field(ge=1)
    cancellation_epoch: int = Field(ge=0)
    authorization_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity: CanonicalCommitIdentity
    requested_at: datetime
    business_execution_authority_granted: bool = False

    @model_validator(mode="after")
    def request_is_bound_and_non_authoritative(self) -> CommitFenceRequest:
        _aware(self.requested_at, "agent_commit_request_requires_timezone")
        if self.identity.tenant_id != self.tenant_id:
            raise ValueError("agent_commit_identity_tenant_mismatch")
        if self.business_execution_authority_granted:
            raise ValueError("agent_commit_fence_never_grants_business_authority")
        return self


class AtomicCommitPermit(BaseModel):
    contract: str = AGENT_COMMIT_FENCING_CONTRACT
    permit_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    root_job_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    lease_id: str = Field(min_length=1)
    lease_generation: int = Field(ge=1)
    fencing_token: int = Field(ge=1)
    cancellation_epoch: int = Field(ge=0)
    resource_ref: str = Field(min_length=1)
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    authorization_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    issued_at: datetime
    consumed: bool = True
    business_execution_authority_granted: bool = False

    @model_validator(mode="after")
    def permit_is_single_use_and_non_authoritative(self) -> AtomicCommitPermit:
        _aware(self.issued_at, "agent_commit_permit_requires_timezone")
        if not self.consumed:
            raise ValueError("agent_commit_permit_must_be_atomically_consumed")
        if self.business_execution_authority_granted:
            raise ValueError("agent_commit_permit_never_grants_business_authority")
        return self


class AtomicCommitAuthority(Protocol):
    async def authorize_and_consume(
        self, request: CommitFenceRequest
    ) -> AtomicCommitPermit:
        """Atomically validate epoch/generation/token and burn idempotency key."""


class BackendCommitOutcome(BaseModel):
    transaction_ref: str | None = None
    committed: bool | None = None
    effect_verified: bool = False
    evidence_refs: tuple[str, ...] = ()
    error_code: str | None = None

    @model_validator(mode="after")
    def outcome_is_consistent(self) -> BackendCommitOutcome:
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("agent_commit_evidence_refs_must_be_unique")
        if self.effect_verified and (self.committed is not True or not self.transaction_ref):
            raise ValueError("agent_commit_verification_requires_transaction")
        return self


class AgentCommitReceipt(BaseModel):
    contract: str = AGENT_COMMIT_FENCING_CONTRACT
    disposition: CommitFenceDisposition
    job_id: str
    root_job_id: str
    tenant_id: str
    permit_id: str
    lease_id: str
    lease_generation: int
    fencing_token: int
    cancellation_epoch: int
    resource_ref: str
    idempotency_key: str
    authorization_fingerprint: str
    transaction_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()
    error_code: str | None = None
    recorded_at: datetime
    effect_verified: bool = False
    lease_release_allowed: bool = False
    business_execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def receipt_is_integral(self) -> AgentCommitReceipt:
        _aware(self.recorded_at, "agent_commit_receipt_requires_timezone")
        if self.business_execution_authority_granted:
            raise ValueError("agent_commit_receipt_never_grants_business_authority")
        if self.disposition is CommitFenceDisposition.VERIFIED_COMMIT:
            if not self.effect_verified or not self.transaction_ref or not self.evidence_refs:
                raise ValueError("agent_commit_verified_receipt_incomplete")
            if not self.lease_release_allowed:
                raise ValueError("agent_commit_verified_receipt_must_allow_release")
        else:
            if self.effect_verified or self.lease_release_allowed:
                raise ValueError("agent_commit_unverified_receipt_cannot_release_lease")
        expected = _hash(self.model_dump(mode="json", exclude={"fingerprint"}))
        if self.fingerprint != expected:
            raise ValueError("agent_commit_receipt_fingerprint_mismatch")
        return self


def _validate_permit(request: CommitFenceRequest, permit: AtomicCommitPermit) -> None:
    pairs = (
        (permit.job_id, request.job_id),
        (permit.root_job_id, request.root_job_id),
        (permit.tenant_id, request.tenant_id),
        (permit.lease_id, request.lease_id),
        (permit.lease_generation, request.lease_generation),
        (permit.fencing_token, request.fencing_token),
        (permit.cancellation_epoch, request.cancellation_epoch),
        (permit.resource_ref, request.identity.resource_ref),
        (permit.idempotency_key, request.identity.idempotency_key),
        (permit.authorization_fingerprint, request.authorization_fingerprint),
    )
    if any(actual != expected for actual, expected in pairs):
        raise CommitFenceError("agent_commit_atomic_permit_binding_mismatch")


def _receipt(
    *,
    request: CommitFenceRequest,
    permit: AtomicCommitPermit,
    disposition: CommitFenceDisposition,
    recorded_at: datetime,
    outcome: BackendCommitOutcome,
) -> AgentCommitReceipt:
    payload = {
        "disposition": disposition,
        "job_id": request.job_id,
        "root_job_id": request.root_job_id,
        "tenant_id": request.tenant_id,
        "permit_id": permit.permit_id,
        "lease_id": request.lease_id,
        "lease_generation": request.lease_generation,
        "fencing_token": request.fencing_token,
        "cancellation_epoch": request.cancellation_epoch,
        "resource_ref": request.identity.resource_ref,
        "idempotency_key": request.identity.idempotency_key,
        "authorization_fingerprint": request.authorization_fingerprint,
        "transaction_ref": outcome.transaction_ref,
        "evidence_refs": outcome.evidence_refs,
        "error_code": outcome.error_code,
        "recorded_at": recorded_at,
        "effect_verified": disposition is CommitFenceDisposition.VERIFIED_COMMIT,
        "lease_release_allowed": disposition is CommitFenceDisposition.VERIFIED_COMMIT,
    }
    draft = AgentCommitReceipt.model_construct(**payload, fingerprint="0" * 64)
    return AgentCommitReceipt(
        **payload,
        fingerprint=_hash(draft.model_dump(mode="json", exclude={"fingerprint"})),
    )


async def execute_fenced_commit(
    *,
    request: CommitFenceRequest,
    authority: AtomicCommitAuthority,
    commit: Callable[[AtomicCommitPermit], BackendCommitOutcome | Awaitable[BackendCommitOutcome]],
    recorded_at: datetime,
) -> AgentCommitReceipt:
    """Consume atomic authority, dispatch once, and fail closed on uncertain effect."""

    request = CommitFenceRequest.model_validate(request.model_dump(mode="json"))
    _aware(recorded_at, "agent_commit_recorded_at_requires_timezone")
    permit = await authority.authorize_and_consume(request)
    permit = AtomicCommitPermit.model_validate(permit.model_dump(mode="json"))
    _validate_permit(request, permit)

    try:
        result = commit(permit)
        outcome = await result if inspect.isawaitable(result) else result
        outcome = BackendCommitOutcome.model_validate(outcome)
    except Exception as exc:  # noqa: BLE001 - dispatch failure means effect is unknowable
        outcome = BackendCommitOutcome(
            committed=None,
            error_code=f"agent_commit_backend_outcome_unknown:{type(exc).__name__}",
        )
        return _receipt(
            request=request,
            permit=permit,
            disposition=CommitFenceDisposition.UNKNOWN_EFFECT,
            recorded_at=recorded_at,
            outcome=outcome,
        )

    if outcome.committed is True and outcome.effect_verified:
        disposition = CommitFenceDisposition.VERIFIED_COMMIT
    elif outcome.committed is False:
        disposition = CommitFenceDisposition.REJECTED
    else:
        disposition = CommitFenceDisposition.UNKNOWN_EFFECT
    return _receipt(
        request=request,
        permit=permit,
        disposition=disposition,
        recorded_at=recorded_at,
        outcome=outcome,
    )
