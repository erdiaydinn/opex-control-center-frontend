"""Fail-closed container provisioning control plane for Jarvis workers.

No subprocess or container CLI is used here. Production Kubernetes/Docker adapters
implement the ports below and must return an attested observation. Scheduling a
container never grants tool, truth, business or side-effect authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

AGENT_WORKER_PROVISIONING_CONTRACT = "eay-agent-worker-provisioning-v1"
_DIGEST = r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$"


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode()).hexdigest()


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


class WorkerRuntimeKind(str, Enum):
    KUBERNETES = "kubernetes"
    DOCKER = "docker"


class WorkerProvisioningStatus(str, Enum):
    PROVISIONING = "provisioning"
    READY = "ready"
    UNHEALTHY = "unhealthy"
    REVOKED = "revoked"
    STOPPED = "stopped"
    RECOVERY_REQUIRED = "recovery_required"


class AllowedWorkerImage(BaseModel):
    image_ref: str = Field(pattern=_DIGEST)
    worker_classes: tuple[str, ...] = Field(min_length=1)
    attestation_policy_ref: str = Field(min_length=1)
    enabled: bool = True

    @model_validator(mode="after")
    def unique_classes(self) -> AllowedWorkerImage:
        if len(self.worker_classes) != len(set(self.worker_classes)):
            raise ValueError("agent_worker_image_classes_must_be_unique")
        return self


class WorkerImageAllowlist(BaseModel):
    contract: str = AGENT_WORKER_PROVISIONING_CONTRACT
    policy_version: str = Field(min_length=1)
    images: tuple[AllowedWorkerImage, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_images(self) -> WorkerImageAllowlist:
        refs = [item.image_ref for item in self.images]
        if len(refs) != len(set(refs)):
            raise ValueError("agent_worker_allowlist_image_duplicate")
        return self


class WorkerSpawnRequest(BaseModel):
    contract: str = AGENT_WORKER_PROVISIONING_CONTRACT
    tenant_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    worker_class: str = Field(min_length=1)
    image_ref: str = Field(pattern=_DIGEST)
    workload_identity_ref: str = Field(min_length=1)
    runtime_kind: WorkerRuntimeKind
    generation: int = Field(ge=1)
    requested_at: datetime
    max_runtime_seconds: int = Field(default=900, ge=30, le=86_400)
    network_policy_ref: str = Field(min_length=1)
    secret_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def safe_request(self) -> WorkerSpawnRequest:
        _aware(self.requested_at, "agent_worker_requested_at_requires_timezone")
        if len(self.secret_refs) != len(set(self.secret_refs)):
            raise ValueError("agent_worker_secret_refs_must_be_unique")
        if any(not ref.startswith("vault://") for ref in self.secret_refs):
            raise ValueError("agent_worker_plaintext_secret_forbidden")
        return self


class WorkerAttestation(BaseModel):
    tenant_id: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    image_ref: str = Field(pattern=_DIGEST)
    workload_identity_ref: str = Field(min_length=1)
    policy_ref: str = Field(min_length=1)
    verified_at: datetime
    verifier_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    verified: bool

    @model_validator(mode="after")
    def valid_attestation(self) -> WorkerAttestation:
        _aware(self.verified_at, "agent_worker_attestation_time_requires_timezone")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("agent_worker_attestation_evidence_must_be_unique")
        return self


class WorkerRuntimeObservation(BaseModel):
    runtime_ref: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    image_ref: str = Field(pattern=_DIGEST)
    workload_identity_ref: str = Field(min_length=1)
    isolated_tenant_namespace: str = Field(min_length=1)
    observed_at: datetime
    heartbeat_at: datetime
    running: bool
    attestation: WorkerAttestation

    @model_validator(mode="after")
    def valid_observation(self) -> WorkerRuntimeObservation:
        _aware(self.observed_at, "agent_worker_observed_at_requires_timezone")
        _aware(self.heartbeat_at, "agent_worker_heartbeat_at_requires_timezone")
        if self.heartbeat_at > self.observed_at:
            raise ValueError("agent_worker_heartbeat_from_future")
        return self


class ProvisionedWorker(BaseModel):
    contract: str = AGENT_WORKER_PROVISIONING_CONTRACT
    tenant_id: str
    job_id: str
    worker_id: str
    runtime_ref: str
    runtime_kind: WorkerRuntimeKind
    image_ref: str
    workload_identity_ref: str
    generation: int = Field(ge=1)
    status: WorkerProvisioningStatus
    created_at: datetime
    updated_at: datetime
    heartbeat_at: datetime | None = None
    revocation_generation: int = Field(default=0, ge=0)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def integrity_sealed(self) -> ProvisionedWorker:
        _aware(self.created_at, "agent_worker_created_at_requires_timezone")
        _aware(self.updated_at, "agent_worker_updated_at_requires_timezone")
        if self.updated_at < self.created_at:
            raise ValueError("agent_worker_update_predates_create")
        if self.heartbeat_at is not None:
            _aware(self.heartbeat_at, "agent_worker_heartbeat_at_requires_timezone")
        if self.fingerprint != _hash(_worker_payload(self)):
            raise ValueError("agent_worker_fingerprint_mismatch")
        return self


class ContainerOrchestratorAdapter(Protocol):
    """Production boundary implemented by Kubernetes/Docker API clients."""

    def spawn_isolated(self, request: WorkerSpawnRequest) -> WorkerRuntimeObservation: ...
    def observe(self, *, tenant_id: str, runtime_ref: str) -> WorkerRuntimeObservation: ...
    def stop(self, *, tenant_id: str, runtime_ref: str, generation: int, reason: str) -> None: ...


class WorkerProvisioningRepository(Protocol):
    def get(self, *, tenant_id: str, worker_id: str) -> ProvisionedWorker | None: ...
    def create(self, worker: ProvisionedWorker) -> ProvisionedWorker: ...
    def compare_and_set(
        self, *, tenant_id: str, worker_id: str, expected_generation: int,
        worker: ProvisionedWorker,
    ) -> ProvisionedWorker: ...
    def list_active(self, *, tenant_id: str, limit: int) -> tuple[ProvisionedWorker, ...]: ...


def _worker_payload(worker: ProvisionedWorker) -> dict[str, object]:
    return worker.model_dump(mode="json", exclude={"fingerprint"})


def _seal(**values: object) -> ProvisionedWorker:
    draft = ProvisionedWorker.model_construct(**values, fingerprint="0" * 64)
    return ProvisionedWorker(**values, fingerprint=_hash(_worker_payload(draft)))


class AgentWorkerProvisioningControlPlane:
    def __init__(self, *, allowlist: WorkerImageAllowlist,
                 adapter: ContainerOrchestratorAdapter,
                 repository: WorkerProvisioningRepository,
                 heartbeat_timeout_seconds: int = 90):
        if heartbeat_timeout_seconds < 10:
            raise ValueError("agent_worker_heartbeat_timeout_too_small")
        self.allowlist = allowlist
        self.adapter = adapter
        self.repository = repository
        self.heartbeat_timeout = timedelta(seconds=heartbeat_timeout_seconds)

    def _load(self, *, tenant_id: str, worker_id: str) -> ProvisionedWorker | None:
        candidate = self.repository.get(tenant_id=tenant_id, worker_id=worker_id)
        if candidate is None:
            return None
        worker = ProvisionedWorker.model_validate(candidate.model_dump(mode="json"))
        if worker.tenant_id != tenant_id:
            raise ValueError("agent_worker_repository_tenant_violation")
        return worker

    def _allowed(self, request: WorkerSpawnRequest) -> AllowedWorkerImage:
        matches = [item for item in self.allowlist.images if item.enabled and item.image_ref == request.image_ref]
        if len(matches) != 1:
            raise ValueError("agent_worker_image_not_allowlisted")
        if request.worker_class not in matches[0].worker_classes:
            raise ValueError("agent_worker_class_not_allowed_for_image")
        return matches[0]

    @staticmethod
    def _validate_observation(request: WorkerSpawnRequest, observation: WorkerRuntimeObservation,
                              image: AllowedWorkerImage) -> None:
        expected = (request.tenant_id, request.job_id, request.worker_id, request.generation,
                    request.image_ref, request.workload_identity_ref)
        actual = (observation.tenant_id, observation.job_id, observation.worker_id,
                  observation.generation, observation.image_ref, observation.workload_identity_ref)
        if actual != expected:
            raise ValueError("agent_worker_runtime_binding_mismatch")
        if observation.isolated_tenant_namespace != f"tenant:{request.tenant_id}":
            raise ValueError("agent_worker_tenant_namespace_not_isolated")
        att = observation.attestation
        if not att.verified or att.policy_ref != image.attestation_policy_ref:
            raise ValueError("agent_worker_attestation_rejected")
        if att.verified_at > observation.observed_at:
            raise ValueError("agent_worker_attestation_from_future")
        if (att.tenant_id, att.worker_id, att.generation, att.image_ref, att.workload_identity_ref) != (
            request.tenant_id, request.worker_id, request.generation,
            request.image_ref, request.workload_identity_ref,
        ):
            raise ValueError("agent_worker_attestation_binding_mismatch")

    def spawn(self, request: WorkerSpawnRequest) -> ProvisionedWorker:
        request = WorkerSpawnRequest.model_validate(request.model_dump(mode="json"))
        image = self._allowed(request)
        existing = self._load(tenant_id=request.tenant_id, worker_id=request.worker_id)
        if existing is not None:
            if existing.generation == request.generation and existing.job_id == request.job_id:
                return existing
            raise ValueError("agent_worker_generation_conflict")
        observation = self.adapter.spawn_isolated(request)
        try:
            self._validate_observation(request, observation, image)
        except Exception:
            self.adapter.stop(tenant_id=request.tenant_id, runtime_ref=observation.runtime_ref,
                              generation=request.generation, reason="provisioning_validation_failed")
            raise
        if not observation.running:
            self.adapter.stop(tenant_id=request.tenant_id, runtime_ref=observation.runtime_ref,
                              generation=request.generation, reason="runtime_not_running")
            raise ValueError("agent_worker_runtime_not_running")
        worker = _seal(
            tenant_id=request.tenant_id, job_id=request.job_id, worker_id=request.worker_id,
            runtime_ref=observation.runtime_ref, runtime_kind=request.runtime_kind,
            image_ref=request.image_ref, workload_identity_ref=request.workload_identity_ref,
            generation=request.generation, status=WorkerProvisioningStatus.READY,
            created_at=request.requested_at, updated_at=observation.observed_at,
            heartbeat_at=observation.heartbeat_at, revocation_generation=0,
        )
        return self.repository.create(worker)

    def status(self, *, tenant_id: str, worker_id: str, now: datetime) -> ProvisionedWorker:
        _aware(now, "agent_worker_status_time_requires_timezone")
        worker = self._load(tenant_id=tenant_id, worker_id=worker_id)
        if worker is None:
            raise KeyError("agent_worker_not_found")
        if worker.status in {WorkerProvisioningStatus.REVOKED, WorkerProvisioningStatus.STOPPED}:
            return worker
        observation = self.adapter.observe(tenant_id=tenant_id, runtime_ref=worker.runtime_ref)
        request = WorkerSpawnRequest(
            tenant_id=worker.tenant_id, job_id=worker.job_id, worker_id=worker.worker_id,
            worker_class="status-validation", image_ref=worker.image_ref,
            workload_identity_ref=worker.workload_identity_ref, runtime_kind=worker.runtime_kind,
            generation=worker.generation, requested_at=worker.created_at,
            network_policy_ref="status://existing",
        )
        # Binding is checked here without re-applying worker-class allowlisting.
        image = next((x for x in self.allowlist.images if x.image_ref == worker.image_ref and x.enabled), None)
        if image is None:
            raise ValueError("agent_worker_image_revoked")
        self._validate_observation(request, observation, image)
        healthy = observation.running and now - observation.heartbeat_at <= self.heartbeat_timeout
        updated = _seal(**{
            **worker.model_dump(exclude={"fingerprint"}),
            "status": WorkerProvisioningStatus.READY if healthy else WorkerProvisioningStatus.UNHEALTHY,
            "updated_at": now, "heartbeat_at": observation.heartbeat_at,
        })
        return self.repository.compare_and_set(
            tenant_id=tenant_id, worker_id=worker_id,
            expected_generation=worker.generation, worker=updated,
        )

    def stop(self, *, tenant_id: str, worker_id: str, expected_generation: int,
             stopped_at: datetime, reason: str) -> ProvisionedWorker:
        _aware(stopped_at, "agent_worker_stop_time_requires_timezone")
        worker = self._load(tenant_id=tenant_id, worker_id=worker_id)
        if worker is None:
            raise KeyError("agent_worker_not_found")
        if worker.generation != expected_generation:
            raise ValueError("agent_worker_revocation_generation_conflict")
        self.adapter.stop(tenant_id=tenant_id, runtime_ref=worker.runtime_ref,
                          generation=expected_generation, reason=reason)
        updated = _seal(**{
            **worker.model_dump(exclude={"fingerprint"}),
            "status": WorkerProvisioningStatus.REVOKED, "updated_at": stopped_at,
            "revocation_generation": worker.revocation_generation + 1,
        })
        return self.repository.compare_and_set(
            tenant_id=tenant_id, worker_id=worker_id,
            expected_generation=expected_generation, worker=updated,
        )

    def recover(self, *, tenant_id: str, now: datetime, limit: int = 256) -> tuple[ProvisionedWorker, ...]:
        recovered: list[ProvisionedWorker] = []
        for candidate in self.repository.list_active(tenant_id=tenant_id, limit=limit):
            worker = ProvisionedWorker.model_validate(candidate.model_dump(mode="json"))
            if worker.tenant_id != tenant_id:
                raise ValueError("agent_worker_repository_tenant_violation")
            current = self.status(tenant_id=tenant_id, worker_id=worker.worker_id, now=now)
            if current.status is WorkerProvisioningStatus.UNHEALTHY:
                recovery = _seal(**{
                    **current.model_dump(exclude={"fingerprint"}),
                    "status": WorkerProvisioningStatus.RECOVERY_REQUIRED,
                })
                current = self.repository.compare_and_set(
                    tenant_id=tenant_id, worker_id=current.worker_id,
                    expected_generation=current.generation, worker=recovery,
                )
            recovered.append(current)
        return tuple(recovered)
