from datetime import datetime, timedelta, timezone

import pytest
from app.agent_worker_provisioning import (
    AgentWorkerProvisioningControlPlane,
    AllowedWorkerImage,
    WorkerAttestation,
    WorkerImageAllowlist,
    WorkerProvisioningStatus,
    WorkerRuntimeKind,
    WorkerRuntimeObservation,
    WorkerSpawnRequest,
)

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
IMAGE = "registry.eay.local/jarvis/research@sha256:" + "a" * 64


class Repo:
    def __init__(self):
        self.rows = {}

    def get(self, *, tenant_id, worker_id):
        return self.rows.get((tenant_id, worker_id))

    def create(self, worker):
        self.rows[(worker.tenant_id, worker.worker_id)] = worker
        return worker

    def compare_and_set(self, *, tenant_id, worker_id, expected_generation, worker):
        current = self.rows[(tenant_id, worker_id)]
        if current.generation != expected_generation:
            raise ValueError("cas_conflict")
        self.rows[(tenant_id, worker_id)] = worker
        return worker

    def list_active(self, *, tenant_id, limit):
        return tuple(v for (t, _), v in self.rows.items() if t == tenant_id and v.status not in {
            WorkerProvisioningStatus.REVOKED, WorkerProvisioningStatus.STOPPED
        })[:limit]


class Adapter:
    def __init__(self):
        self.observation = None
        self.stops = []

    def spawn_isolated(self, request):
        self.observation = observation(request)
        return self.observation

    def observe(self, *, tenant_id, runtime_ref):
        return self.observation

    def stop(self, *, tenant_id, runtime_ref, generation, reason):
        self.stops.append((tenant_id, runtime_ref, generation, reason))


def request(**updates):
    values = {
        "tenant_id": "tenant-a",
        "job_id": "job-1",
        "worker_id": "worker-1",
        "worker_class": "research",
        "image_ref": IMAGE,
        "workload_identity_ref": "spiffe://eay/tenant-a/worker-1",
        "runtime_kind": WorkerRuntimeKind.KUBERNETES,
        "generation": 1,
        "requested_at": NOW,
        "network_policy_ref": "network-policy://research-readonly",
    }
    values.update(updates)
    return WorkerSpawnRequest(**values)


def observation(req, **updates):
    att = WorkerAttestation(tenant_id=req.tenant_id, worker_id=req.worker_id,
        generation=req.generation, image_ref=req.image_ref,
        workload_identity_ref=req.workload_identity_ref, policy_ref="attestation://cosign-v1",
        verified_at=NOW, verifier_ref="verifier://cluster", evidence_refs=("rekor://entry-1",),
        verified=True)
    values = {
        "runtime_ref": "k8s://tenant-a/worker-1",
        "tenant_id": req.tenant_id,
        "job_id": req.job_id,
        "worker_id": req.worker_id,
        "generation": req.generation,
        "image_ref": req.image_ref,
        "workload_identity_ref": req.workload_identity_ref,
        "isolated_tenant_namespace": f"tenant:{req.tenant_id}",
        "observed_at": NOW,
        "heartbeat_at": NOW,
        "running": True,
        "attestation": att,
    }
    values.update(updates)
    return WorkerRuntimeObservation(**values)


def plane(adapter=None):
    adapter = adapter or Adapter()
    return AgentWorkerProvisioningControlPlane(
        allowlist=WorkerImageAllowlist(policy_version="1", images=(AllowedWorkerImage(
            image_ref=IMAGE, worker_classes=("research",),
            attestation_policy_ref="attestation://cosign-v1"),)),
        adapter=adapter, repository=Repo(), heartbeat_timeout_seconds=60), adapter


def test_spawn_requires_allowlisted_digest_and_attested_tenant_identity():
    control, _ = plane()
    worker = control.spawn(request())
    assert worker.status is WorkerProvisioningStatus.READY
    assert worker.image_ref == IMAGE
    with pytest.raises(ValueError, match="agent_worker_image_not_allowlisted"):
        control.spawn(request(worker_id="worker-2", image_ref="evil/x@sha256:" + "b" * 64))


def test_binding_drift_stops_untrusted_runtime_fail_closed():
    adapter = Adapter()
    req = request()
    adapter.spawn_isolated = lambda _: observation(req, tenant_id="tenant-b")
    control, _ = plane(adapter)
    with pytest.raises(ValueError, match="agent_worker_runtime_binding_mismatch"):
        control.spawn(req)
    assert adapter.stops[-1][-1] == "provisioning_validation_failed"


def test_plaintext_secret_and_mutable_tag_are_rejected():
    with pytest.raises(ValueError):
        request(image_ref="registry/jarvis:latest")
    with pytest.raises(ValueError, match="agent_worker_plaintext_secret_forbidden"):
        request(secret_refs=("MY_SECRET=value",))


def test_heartbeat_loss_enters_recovery_required_and_is_tenant_scoped():
    control, adapter = plane()
    worker = control.spawn(request())
    adapter.observation = observation(request(), observed_at=NOW + timedelta(minutes=5),
                                      heartbeat_at=NOW)
    recovered = control.recover(tenant_id="tenant-a", now=NOW + timedelta(minutes=5))
    assert recovered[0].worker_id == worker.worker_id
    assert recovered[0].status is WorkerProvisioningStatus.RECOVERY_REQUIRED
    assert control.recover(tenant_id="tenant-b", now=NOW + timedelta(minutes=5)) == ()


def test_stop_checks_generation_and_records_revocation_generation():
    control, adapter = plane()
    worker = control.spawn(request())
    with pytest.raises(ValueError, match="agent_worker_revocation_generation_conflict"):
        control.stop(tenant_id="tenant-a", worker_id=worker.worker_id,
                     expected_generation=2, stopped_at=NOW + timedelta(seconds=2), reason="cancel")
    stopped = control.stop(tenant_id="tenant-a", worker_id=worker.worker_id,
        expected_generation=1, stopped_at=NOW + timedelta(seconds=2), reason="cancel")
    assert stopped.status is WorkerProvisioningStatus.REVOKED
    assert stopped.revocation_generation == 1
    assert adapter.stops[-1][-1] == "cancel"


def test_spawn_replay_is_stable_but_generation_reuse_is_rejected():
    control, _ = plane()
    first = control.spawn(request())
    assert control.spawn(request()) == first
    with pytest.raises(ValueError, match="agent_worker_generation_conflict"):
        control.spawn(request(job_id="job-2"))
