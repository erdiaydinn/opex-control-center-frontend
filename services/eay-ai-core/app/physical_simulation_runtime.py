"""Simulator-first acceptance gate for Jarvis physical actions.

Simulation evidence can make a physical request eligible for the existing
Physical Capability Gateway preflight, but it never grants execution authority.
Robotic actuation defaults to hardware-in-the-loop evidence; high-risk device
control defaults to a qualified digital twin. Exact request/device/action/
idempotency/payload binding and integrity are required.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .physical_capability_gateway import PhysicalAction, PhysicalActionRequest, PhysicalRisk

PHYSICAL_SIMULATION_RUNTIME_CONTRACT = "eay-physical-simulation-runtime-v1"


class SimulationFidelity(str, Enum):
    MOCK = "mock"
    DIGITAL_TWIN = "digital_twin"
    HARDWARE_IN_LOOP = "hardware_in_loop"


_FIDELITY_ORDER = {
    SimulationFidelity.MOCK: 0,
    SimulationFidelity.DIGITAL_TWIN: 1,
    SimulationFidelity.HARDWARE_IN_LOOP: 2,
}


class PhysicalSimulationPolicy(BaseModel):
    maximum_age: timedelta = timedelta(minutes=10)
    minimum_high_risk_fidelity: SimulationFidelity = SimulationFidelity.DIGITAL_TWIN
    minimum_critical_risk_fidelity: SimulationFidelity = SimulationFidelity.HARDWARE_IN_LOOP
    require_collision_free_for_robotics: bool = True
    require_all_safety_invariants: bool = True
    simulation_grants_execution_authority: bool = False

    @model_validator(mode="after")
    def policy_is_non_authoritative(self) -> "PhysicalSimulationPolicy":
        if self.maximum_age <= timedelta(0) or self.maximum_age > timedelta(hours=1):
            raise ValueError("physical_simulation_maximum_age_invalid")
        if self.simulation_grants_execution_authority:
            raise ValueError("physical_simulation_never_grants_execution_authority")
        return self


class PhysicalSimulationEvidence(BaseModel):
    contract: str = PHYSICAL_SIMULATION_RUNTIME_CONTRACT
    request_ref: str = Field(min_length=1)
    tenant_ref: str = Field(min_length=1)
    device_ref: str = Field(min_length=1)
    action: PhysicalAction
    idempotency_key: str = Field(min_length=16)
    payload_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    simulator_ref: str = Field(min_length=1)
    scenario_ref: str = Field(min_length=1)
    fidelity: SimulationFidelity
    started_at: datetime
    completed_at: datetime
    safety_invariants_checked: tuple[str, ...] = Field(min_length=1)
    safety_invariants_violated: tuple[str, ...] = ()
    collision_free: bool = False
    estimated_effect_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    raw_payload_retained: bool = False
    credential_material_retained: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def evidence_is_safe_and_integral(self) -> "PhysicalSimulationEvidence":
        for value in (self.started_at, self.completed_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("physical_simulation_requires_timezone")
        if self.completed_at <= self.started_at:
            raise ValueError("physical_simulation_completion_must_follow_start")
        if self.raw_payload_retained or self.credential_material_retained:
            raise ValueError("physical_simulation_cannot_retain_sensitive_payload")
        if self.execution_authority_granted:
            raise ValueError("physical_simulation_never_grants_execution_authority")
        expected = _fingerprint(_payload(self, include_fingerprint=False))
        if self.fingerprint != expected:
            raise ValueError("physical_simulation_fingerprint_mismatch")
        return self


class PhysicalSimulationGate(BaseModel):
    contract: str = PHYSICAL_SIMULATION_RUNTIME_CONTRACT
    request_ref: str
    simulator_ref: str | None = None
    eligible_for_physical_preflight: bool = False
    blockers: tuple[str, ...] = ()
    simulation_fingerprint: str | None = None
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def gate_is_non_authoritative(self) -> "PhysicalSimulationGate":
        if self.execution_authority_granted:
            raise ValueError("physical_simulation_gate_never_authorizes_execution")
        if self.eligible_for_physical_preflight and self.blockers:
            raise ValueError("physical_simulation_eligible_gate_cannot_have_blockers")
        return self


def _payload(evidence: PhysicalSimulationEvidence, *, include_fingerprint: bool) -> dict[str, object]:
    payload = evidence.model_dump(mode="json")
    if not include_fingerprint:
        payload.pop("fingerprint", None)
    return payload


def _fingerprint(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_physical_simulation_evidence(
    *,
    request: PhysicalActionRequest,
    simulator_ref: str,
    scenario_ref: str,
    fidelity: SimulationFidelity,
    started_at: datetime,
    completed_at: datetime,
    safety_invariants_checked: tuple[str, ...],
    safety_invariants_violated: tuple[str, ...] = (),
    collision_free: bool = False,
    estimated_effect_ref: str,
    evidence_refs: tuple[str, ...],
) -> PhysicalSimulationEvidence:
    provisional = PhysicalSimulationEvidence.model_construct(
        contract=PHYSICAL_SIMULATION_RUNTIME_CONTRACT,
        request_ref=request.request_ref,
        tenant_ref=request.tenant_ref,
        device_ref=request.device_ref,
        action=request.action,
        idempotency_key=request.idempotency_key,
        payload_digest=request.payload_digest,
        simulator_ref=simulator_ref,
        scenario_ref=scenario_ref,
        fidelity=fidelity,
        started_at=started_at,
        completed_at=completed_at,
        safety_invariants_checked=safety_invariants_checked,
        safety_invariants_violated=safety_invariants_violated,
        collision_free=collision_free,
        estimated_effect_ref=estimated_effect_ref,
        evidence_refs=evidence_refs,
        raw_payload_retained=False,
        credential_material_retained=False,
        execution_authority_granted=False,
        fingerprint="0" * 64,
    )
    return PhysicalSimulationEvidence(
        **provisional.model_dump(exclude={"fingerprint"}),
        fingerprint=_fingerprint(_payload(provisional, include_fingerprint=False)),
    )


def validate_physical_simulation_integrity(
    evidence: PhysicalSimulationEvidence,
) -> PhysicalSimulationEvidence:
    return PhysicalSimulationEvidence.model_validate(evidence.model_dump(mode="json"))


def _minimum_fidelity(
    request: PhysicalActionRequest,
    policy: PhysicalSimulationPolicy,
) -> SimulationFidelity:
    if request.risk is PhysicalRisk.CRITICAL:
        return policy.minimum_critical_risk_fidelity
    if request.risk is PhysicalRisk.HIGH:
        return policy.minimum_high_risk_fidelity
    return SimulationFidelity.MOCK


def evaluate_physical_simulation_gate(
    *,
    request: PhysicalActionRequest,
    evidence: PhysicalSimulationEvidence,
    policy: PhysicalSimulationPolicy,
    now: datetime,
) -> PhysicalSimulationGate:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("physical_simulation_gate_requires_timezone")
    try:
        evidence = validate_physical_simulation_integrity(evidence)
    except ValueError:
        return PhysicalSimulationGate(
            request_ref=request.request_ref,
            blockers=("physical_simulation_evidence_invalid",),
        )

    blockers: list[str] = []
    if evidence.request_ref != request.request_ref:
        blockers.append("physical_simulation_request_mismatch")
    if evidence.tenant_ref != request.tenant_ref:
        blockers.append("physical_simulation_tenant_mismatch")
    if evidence.device_ref != request.device_ref:
        blockers.append("physical_simulation_device_mismatch")
    if evidence.action is not request.action:
        blockers.append("physical_simulation_action_mismatch")
    if evidence.idempotency_key != request.idempotency_key:
        blockers.append("physical_simulation_idempotency_mismatch")
    if evidence.payload_digest != request.payload_digest:
        blockers.append("physical_simulation_payload_digest_mismatch")
    if evidence.started_at < request.requested_at:
        blockers.append("physical_simulation_predates_request")
    if evidence.completed_at > now:
        blockers.append("physical_simulation_from_future")
    if now - evidence.completed_at > policy.maximum_age:
        blockers.append("physical_simulation_stale")

    minimum = _minimum_fidelity(request, policy)
    if _FIDELITY_ORDER[evidence.fidelity] < _FIDELITY_ORDER[minimum]:
        blockers.append("physical_simulation_fidelity_insufficient")
    if policy.require_all_safety_invariants and evidence.safety_invariants_violated:
        blockers.append("physical_simulation_safety_invariant_violated")
    if request.action is PhysicalAction.ROBOTIC_ACTUATION:
        if not evidence.safety_invariants_checked:
            blockers.append("physical_simulation_robot_safety_invariants_missing")
        if policy.require_collision_free_for_robotics and not evidence.collision_free:
            blockers.append("physical_simulation_robot_collision_check_failed")

    if blockers:
        return PhysicalSimulationGate(
            request_ref=request.request_ref,
            simulator_ref=evidence.simulator_ref,
            blockers=tuple(dict.fromkeys(blockers)),
            simulation_fingerprint=evidence.fingerprint,
        )
    return PhysicalSimulationGate(
        request_ref=request.request_ref,
        simulator_ref=evidence.simulator_ref,
        eligible_for_physical_preflight=True,
        simulation_fingerprint=evidence.fingerprint,
    )
