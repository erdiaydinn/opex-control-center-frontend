"""Fail-closed live-source bindings for the Jarvis company world model.

This is an ingestion gate, not a second source of truth. Live observations only
become existing ``WorldAssertion`` objects after exact policy, identity,
schema, freshness and independently trusted evidence checks. Synthetic,
repository and model-derived evidence can never be promoted to live truth.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Collection

from pydantic import BaseModel, Field, model_validator

from app.world_model import (
    TruthClass,
    WorldAssertion,
    WorldEntity,
    WorldSnapshot,
    build_world_snapshot,
)

LIVE_COMPANY_REALITY_CONTRACT = "eay-live-company-reality-v1"


class LiveSourceKind(str, Enum):
    ORDERS = "orders"
    INVENTORY = "inventory"
    WORKFORCE = "workforce"
    PLANOGRAM = "planogram"
    BUDGET = "budget"
    EXTERNAL_CONTEXT = "external_context"


class LiveEvidenceClass(str, Enum):
    AUTHORITATIVE_LIVE = "authoritative_live"
    CONTROLLED_LIVE = "controlled_live"
    SYNTHETIC = "synthetic"
    REPOSITORY = "repository"
    MODEL_DERIVED = "model_derived"


class LiveBindingStatus(str, Enum):
    ACCEPTED = "accepted"
    STALE = "stale"
    SOURCE_UNAVAILABLE = "source_unavailable"
    REJECTED = "rejected"


class LiveRealityStatus(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    SOURCE_UNAVAILABLE = "source_unavailable"
    CONFLICT = "conflict"


class LiveSourceBindingPolicy(BaseModel):
    binding_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    source_kind: LiveSourceKind
    source_ref: str = Field(min_length=1)
    schema_contract: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    environment_ref: str = Field(min_length=1)
    execution_identity_ref: str = Field(min_length=1)
    verifier_ref: str = Field(min_length=1)
    truth_class: TruthClass
    max_observation_age_seconds: int = Field(gt=0)
    max_attestation_age_seconds: int = Field(gt=0)
    allowed_fields: tuple[str, ...] = ()
    allowed_field_prefixes: tuple[str, ...] = ()
    required: bool = True

    @model_validator(mode="after")
    def authority_and_namespace_contract(self) -> "LiveSourceBindingPolicy":
        if self.truth_class is TruthClass.ANALYTIC_INFERENCE:
            raise ValueError("live_binding_cannot_promote_analytic_inference")
        if not self.allowed_fields and not self.allowed_field_prefixes:
            raise ValueError("live_binding_requires_field_namespace")
        namespace = (*self.allowed_fields, *self.allowed_field_prefixes)
        if any(not item for item in namespace):
            raise ValueError("live_binding_field_namespace_must_be_nonempty")
        return self


class LiveSourceAttestation(BaseModel):
    binding_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    source_kind: LiveSourceKind
    source_ref: str = Field(min_length=1)
    schema_contract: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    environment_ref: str = Field(min_length=1)
    execution_identity_ref: str = Field(min_length=1)
    verifier_ref: str = Field(min_length=1)
    verified_at: datetime
    evidence_ref: str = Field(min_length=1)
    source_receipt_ref: str = Field(min_length=1)
    evidence_class: LiveEvidenceClass
    field_production_verified: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def integrity_contract(self) -> "LiveSourceAttestation":
        _require_aware(
            self.verified_at,
            "live_attestation_verified_at_requires_timezone",
        )
        expected = _attestation_fingerprint(
            _attestation_payload(
                binding_id=self.binding_id,
                tenant_id=self.tenant_id,
                source_kind=self.source_kind,
                source_ref=self.source_ref,
                schema_contract=self.schema_contract,
                schema_version=self.schema_version,
                environment_ref=self.environment_ref,
                execution_identity_ref=self.execution_identity_ref,
                verifier_ref=self.verifier_ref,
                verified_at=self.verified_at,
                evidence_ref=self.evidence_ref,
                source_receipt_ref=self.source_receipt_ref,
                evidence_class=self.evidence_class,
                field_production_verified=self.field_production_verified,
            )
        )
        if self.fingerprint != expected:
            raise ValueError("live_attestation_fingerprint_mismatch")
        return self


class LiveFactObservation(BaseModel):
    binding_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    source_kind: LiveSourceKind
    source_ref: str = Field(min_length=1)
    schema_contract: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    field_name: str = Field(min_length=1)
    value: Any
    valid_from: datetime
    valid_to: datetime | None = None
    observed_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    attestation: LiveSourceAttestation

    @model_validator(mode="after")
    def temporal_contract(self) -> "LiveFactObservation":
        _require_aware(self.valid_from, "live_fact_valid_from_requires_timezone")
        _require_aware(self.observed_at, "live_fact_observed_at_requires_timezone")
        if self.valid_to is not None:
            _require_aware(self.valid_to, "live_fact_valid_to_requires_timezone")
            if self.valid_to <= self.valid_from:
                raise ValueError("live_fact_valid_to_must_follow_valid_from")
        return self


class LiveBindingReceipt(BaseModel):
    contract: str = LIVE_COMPANY_REALITY_CONTRACT
    binding_id: str
    tenant_id: str
    source_kind: LiveSourceKind
    source_ref: str
    status: LiveBindingStatus
    entity_id: str | None = None
    field_name: str | None = None
    observed_at: datetime | None = None
    evidence_ref: str | None = None
    source_receipt_ref: str | None = None
    attestation_fingerprint: str | None = None
    assertion_id: str | None = None
    reasons: tuple[str, ...] = ()


class LiveBindingOutcome(BaseModel):
    receipt: LiveBindingReceipt
    assertion: WorldAssertion | None = None


class LiveCompanyRealitySnapshot(BaseModel):
    contract: str = LIVE_COMPANY_REALITY_CONTRACT
    tenant_id: str
    as_of: datetime
    status: LiveRealityStatus
    world: WorldSnapshot
    binding_receipts: tuple[LiveBindingReceipt, ...]
    unavailable_binding_ids: tuple[str, ...]
    degraded_binding_ids: tuple[str, ...]


def _require_aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _canonical_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _attestation_payload(
    *,
    binding_id: str,
    tenant_id: str,
    source_kind: LiveSourceKind,
    source_ref: str,
    schema_contract: str,
    schema_version: str,
    environment_ref: str,
    execution_identity_ref: str,
    verifier_ref: str,
    verified_at: datetime,
    evidence_ref: str,
    source_receipt_ref: str,
    evidence_class: LiveEvidenceClass,
    field_production_verified: bool,
) -> dict[str, Any]:
    return {
        "binding_id": binding_id,
        "tenant_id": tenant_id,
        "source_kind": source_kind.value,
        "source_ref": source_ref,
        "schema_contract": schema_contract,
        "schema_version": schema_version,
        "environment_ref": environment_ref,
        "execution_identity_ref": execution_identity_ref,
        "verifier_ref": verifier_ref,
        "verified_at": verified_at.isoformat(),
        "evidence_ref": evidence_ref,
        "source_receipt_ref": source_receipt_ref,
        "evidence_class": evidence_class.value,
        "field_production_verified": field_production_verified,
    }


def _attestation_fingerprint(payload: dict[str, Any]) -> str:
    return _canonical_hash(payload)


def build_live_source_attestation(
    *,
    binding_id: str,
    tenant_id: str,
    source_kind: LiveSourceKind,
    source_ref: str,
    schema_contract: str,
    schema_version: str,
    environment_ref: str,
    execution_identity_ref: str,
    verifier_ref: str,
    verified_at: datetime,
    evidence_ref: str,
    source_receipt_ref: str,
    evidence_class: LiveEvidenceClass,
    field_production_verified: bool,
) -> LiveSourceAttestation:
    payload = _attestation_payload(
        binding_id=binding_id,
        tenant_id=tenant_id,
        source_kind=source_kind,
        source_ref=source_ref,
        schema_contract=schema_contract,
        schema_version=schema_version,
        environment_ref=environment_ref,
        execution_identity_ref=execution_identity_ref,
        verifier_ref=verifier_ref,
        verified_at=verified_at,
        evidence_ref=evidence_ref,
        source_receipt_ref=source_receipt_ref,
        evidence_class=evidence_class,
        field_production_verified=field_production_verified,
    )
    return LiveSourceAttestation(
        **payload,
        fingerprint=_attestation_fingerprint(payload),
    )


def _field_allowed(policy: LiveSourceBindingPolicy, field_name: str) -> bool:
    return field_name in policy.allowed_fields or any(
        field_name.startswith(prefix)
        for prefix in policy.allowed_field_prefixes
    )


def _assertion_id(
    policy: LiveSourceBindingPolicy,
    observation: LiveFactObservation,
) -> str:
    payload = {
        "binding_id": policy.binding_id,
        "tenant_id": observation.tenant_id,
        "source_ref": observation.source_ref,
        "schema_contract": observation.schema_contract,
        "schema_version": observation.schema_version,
        "entity_id": observation.entity_id,
        "field_name": observation.field_name,
        "value": observation.value,
        "valid_from": observation.valid_from.isoformat(),
        "valid_to": (
            observation.valid_to.isoformat()
            if observation.valid_to is not None
            else None
        ),
        "observed_at": observation.observed_at.isoformat(),
        "attestation_fingerprint": observation.attestation.fingerprint,
    }
    return "live:" + _canonical_hash(payload)


def bind_live_observation(
    *,
    policy: LiveSourceBindingPolicy,
    observation: LiveFactObservation,
    as_of: datetime,
    known_entity_ids: Collection[str],
    trusted_attestation_fingerprints: Collection[str],
) -> LiveBindingOutcome:
    """Validate one observation and convert it to existing world-model truth."""

    _require_aware(as_of, "live_binding_as_of_requires_timezone")
    attestation = observation.attestation
    reasons: list[str] = []

    if observation.binding_id != policy.binding_id:
        reasons.append("binding_id_mismatch")
    if observation.tenant_id != policy.tenant_id:
        reasons.append("tenant_mismatch")
    if observation.source_kind != policy.source_kind:
        reasons.append("source_kind_mismatch")
    if observation.source_ref != policy.source_ref:
        reasons.append("source_ref_mismatch")
    if observation.schema_contract != policy.schema_contract:
        reasons.append("schema_contract_mismatch")
    if observation.schema_version != policy.schema_version:
        reasons.append("schema_version_mismatch")
    if observation.entity_id not in known_entity_ids:
        reasons.append("entity_unknown_for_tenant")
    if not _field_allowed(policy, observation.field_name):
        reasons.append("field_namespace_not_allowed")

    if attestation.binding_id != policy.binding_id:
        reasons.append("attestation_binding_mismatch")
    if attestation.binding_id != observation.binding_id:
        reasons.append("attestation_binding_mismatch")
    if attestation.tenant_id != policy.tenant_id:
        reasons.append("attestation_tenant_mismatch")
    if attestation.tenant_id != observation.tenant_id:
        reasons.append("attestation_tenant_mismatch")
    if attestation.source_kind != policy.source_kind:
        reasons.append("attestation_source_kind_mismatch")
    if attestation.source_kind != observation.source_kind:
        reasons.append("attestation_source_kind_mismatch")
    if attestation.source_ref != policy.source_ref:
        reasons.append("attestation_source_ref_mismatch")
    if attestation.source_ref != observation.source_ref:
        reasons.append("attestation_source_ref_mismatch")
    if attestation.schema_contract != policy.schema_contract:
        reasons.append("attestation_schema_contract_mismatch")
    if attestation.schema_version != policy.schema_version:
        reasons.append("attestation_schema_version_mismatch")
    if attestation.environment_ref != policy.environment_ref:
        reasons.append("attestation_environment_mismatch")
    if attestation.execution_identity_ref != policy.execution_identity_ref:
        reasons.append("attestation_execution_identity_mismatch")
    if attestation.verifier_ref != policy.verifier_ref:
        reasons.append("attestation_verifier_mismatch")
    if attestation.fingerprint not in trusted_attestation_fingerprints:
        reasons.append("attestation_not_in_trusted_registry")
    if attestation.evidence_class != LiveEvidenceClass.AUTHORITATIVE_LIVE:
        reasons.append("evidence_not_authoritative_live")
    if not attestation.field_production_verified:
        reasons.append("field_production_not_verified")
    if observation.observed_at > as_of:
        reasons.append("observation_from_future")
    if attestation.verified_at > as_of:
        reasons.append("attestation_from_future")

    if reasons:
        return LiveBindingOutcome(
            receipt=_receipt(
                policy,
                observation,
                LiveBindingStatus.REJECTED,
                tuple(sorted(set(reasons))),
            )
        )

    stale_reasons: list[str] = []
    observation_age = (as_of - observation.observed_at).total_seconds()
    attestation_age = (as_of - attestation.verified_at).total_seconds()
    if observation_age > policy.max_observation_age_seconds:
        stale_reasons.append("observation_stale")
    if attestation_age > policy.max_attestation_age_seconds:
        stale_reasons.append("attestation_stale")
    if stale_reasons:
        return LiveBindingOutcome(
            receipt=_receipt(
                policy,
                observation,
                LiveBindingStatus.STALE,
                tuple(stale_reasons),
            )
        )

    assertion_id = _assertion_id(policy, observation)
    assertion = WorldAssertion(
        assertion_id=assertion_id,
        tenant_id=observation.tenant_id,
        entity_id=observation.entity_id,
        field_name=observation.field_name,
        value=observation.value,
        truth_class=policy.truth_class,
        valid_from=observation.valid_from,
        valid_to=observation.valid_to,
        observed_at=observation.observed_at,
        source_ref=observation.source_ref,
        evidence_ref=attestation.evidence_ref,
        confidence=observation.confidence,
    )
    return LiveBindingOutcome(
        receipt=_receipt(
            policy,
            observation,
            LiveBindingStatus.ACCEPTED,
            (),
            assertion_id=assertion_id,
        ),
        assertion=assertion,
    )


def _receipt(
    policy: LiveSourceBindingPolicy,
    observation: LiveFactObservation,
    status: LiveBindingStatus,
    reasons: tuple[str, ...],
    *,
    assertion_id: str | None = None,
) -> LiveBindingReceipt:
    attestation = observation.attestation
    return LiveBindingReceipt(
        binding_id=policy.binding_id,
        tenant_id=policy.tenant_id,
        source_kind=policy.source_kind,
        source_ref=policy.source_ref,
        status=status,
        entity_id=observation.entity_id,
        field_name=observation.field_name,
        observed_at=observation.observed_at,
        evidence_ref=attestation.evidence_ref,
        source_receipt_ref=attestation.source_receipt_ref,
        attestation_fingerprint=attestation.fingerprint,
        assertion_id=assertion_id,
        reasons=reasons,
    )


def build_live_company_reality_snapshot(
    *,
    tenant_id: str,
    as_of: datetime,
    entities: list[WorldEntity],
    policies: list[LiveSourceBindingPolicy],
    observations: list[LiveFactObservation],
    trusted_attestation_fingerprints: Collection[str],
) -> LiveCompanyRealitySnapshot:
    """Build a snapshot from independently trusted live-source evidence."""

    _require_aware(as_of, "live_reality_as_of_requires_timezone")
    if any(policy.tenant_id != tenant_id for policy in policies):
        raise ValueError("live_reality_policy_tenant_mismatch")

    policy_by_id = {policy.binding_id: policy for policy in policies}
    if len(policy_by_id) != len(policies):
        raise ValueError("live_reality_duplicate_binding_id")

    tenant_entity_ids = {
        entity.entity_id
        for entity in entities
        if entity.tenant_id == tenant_id
    }
    observations_by_binding: dict[str, list[LiveFactObservation]] = {}
    for observation in observations:
        observations_by_binding.setdefault(
            observation.binding_id,
            [],
        ).append(observation)

    unknown_binding_ids = sorted(
        set(observations_by_binding) - set(policy_by_id)
    )
    if unknown_binding_ids:
        raise ValueError("live_reality_observation_binding_unknown")

    outcomes: list[LiveBindingOutcome] = []
    unavailable: list[str] = []
    degraded: list[str] = []
    assertions: list[WorldAssertion] = []

    for policy in policies:
        items = observations_by_binding.get(policy.binding_id, [])
        if not items:
            if policy.required:
                unavailable.append(policy.binding_id)
            reason = (
                "required_source_observation_missing"
                if policy.required
                else "optional_source_observation_missing"
            )
            outcomes.append(
                LiveBindingOutcome(
                    receipt=LiveBindingReceipt(
                        binding_id=policy.binding_id,
                        tenant_id=policy.tenant_id,
                        source_kind=policy.source_kind,
                        source_ref=policy.source_ref,
                        status=LiveBindingStatus.SOURCE_UNAVAILABLE,
                        reasons=(reason,),
                    )
                )
            )
            continue

        accepted_for_binding = 0
        nonaccepted_for_binding = False
        for observation in items:
            outcome = bind_live_observation(
                policy=policy,
                observation=observation,
                as_of=as_of,
                known_entity_ids=tenant_entity_ids,
                trusted_attestation_fingerprints=(
                    trusted_attestation_fingerprints
                ),
            )
            outcomes.append(outcome)
            if outcome.assertion is not None:
                assertions.append(outcome.assertion)
                accepted_for_binding += 1
            else:
                nonaccepted_for_binding = True

        if policy.required and accepted_for_binding == 0:
            unavailable.append(policy.binding_id)
        elif nonaccepted_for_binding:
            degraded.append(policy.binding_id)

    world = build_world_snapshot(
        tenant_id=tenant_id,
        as_of=as_of,
        entities=entities,
        assertions=assertions,
    )

    if world.blocked_field_keys:
        status = LiveRealityStatus.CONFLICT
    elif unavailable:
        status = LiveRealityStatus.SOURCE_UNAVAILABLE
    elif degraded:
        status = LiveRealityStatus.DEGRADED
    else:
        status = LiveRealityStatus.READY

    return LiveCompanyRealitySnapshot(
        tenant_id=tenant_id,
        as_of=as_of,
        status=status,
        world=world,
        binding_receipts=tuple(outcome.receipt for outcome in outcomes),
        unavailable_binding_ids=tuple(sorted(set(unavailable))),
        degraded_binding_ids=tuple(sorted(set(degraded))),
    )
