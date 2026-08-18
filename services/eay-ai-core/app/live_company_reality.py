"""Fail-closed live-source bindings for the Jarvis company world model.

This module is an ingestion gate, not a second source of truth. A live source may
only create a ``WorldAssertion`` when its tenant, source identity, schema,
authority, freshness and evidence all match an explicit runtime policy.
Repository fixtures, synthetic proof and model-derived content can never be
promoted to live company truth by this layer.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

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
    truth_class: TruthClass
    max_observation_age_seconds: int = Field(gt=0)
    allowed_fields: tuple[str, ...] = ()
    allowed_field_prefixes: tuple[str, ...] = ()
    required: bool = True

    @model_validator(mode="after")
    def authority_and_namespace_contract(self) -> "LiveSourceBindingPolicy":
        if self.truth_class is TruthClass.ANALYTIC_INFERENCE:
            raise ValueError("live_binding_cannot_promote_analytic_inference")
        if not self.allowed_fields and not self.allowed_field_prefixes:
            raise ValueError("live_binding_requires_field_namespace")
        if any(not item for item in (*self.allowed_fields, *self.allowed_field_prefixes)):
            raise ValueError("live_binding_field_namespace_must_be_nonempty")
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
    evidence_ref: str = Field(min_length=1)
    source_receipt_ref: str = Field(min_length=1)
    evidence_class: LiveEvidenceClass
    live_source_verified: bool = False
    confidence: float = Field(ge=0.0, le=1.0)

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


def _field_allowed(policy: LiveSourceBindingPolicy, field_name: str) -> bool:
    return field_name in policy.allowed_fields or any(
        field_name.startswith(prefix) for prefix in policy.allowed_field_prefixes
    )


def _assertion_id(policy: LiveSourceBindingPolicy, observation: LiveFactObservation) -> str:
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
        "valid_to": observation.valid_to.isoformat() if observation.valid_to else None,
        "observed_at": observation.observed_at.isoformat(),
        "evidence_ref": observation.evidence_ref,
        "source_receipt_ref": observation.source_receipt_ref,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "live:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def bind_live_observation(
    *,
    policy: LiveSourceBindingPolicy,
    observation: LiveFactObservation,
    as_of: datetime,
) -> LiveBindingOutcome:
    """Validate one observation and convert it to existing world-model truth."""

    _require_aware(as_of, "live_binding_as_of_requires_timezone")
    reasons: list[str] = []

    if observation.binding_id != policy.binding_id:
        reasons.append("binding_id_mismatch")
    if observation.tenant_id != policy.tenant_id:
        reasons.append("tenant_mismatch")
    if observation.source_kind is not policy.source_kind:
        reasons.append("source_kind_mismatch")
    if observation.source_ref != policy.source_ref:
        reasons.append("source_ref_mismatch")
    if observation.schema_contract != policy.schema_contract:
        reasons.append("schema_contract_mismatch")
    if observation.schema_version != policy.schema_version:
        reasons.append("schema_version_mismatch")
    if not _field_allowed(policy, observation.field_name):
        reasons.append("field_namespace_not_allowed")
    if observation.evidence_class is not LiveEvidenceClass.AUTHORITATIVE_LIVE:
        reasons.append("evidence_not_authoritative_live")
    if not observation.live_source_verified:
        reasons.append("live_source_not_verified")
    if observation.observed_at > as_of:
        reasons.append("observation_from_future")

    if reasons:
        return LiveBindingOutcome(
            receipt=_receipt(policy, observation, LiveBindingStatus.REJECTED, tuple(sorted(set(reasons))))
        )

    age_seconds = (as_of - observation.observed_at).total_seconds()
    if age_seconds > policy.max_observation_age_seconds:
        return LiveBindingOutcome(
            receipt=_receipt(policy, observation, LiveBindingStatus.STALE, ("observation_stale",))
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
        evidence_ref=observation.evidence_ref,
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
    return LiveBindingReceipt(
        binding_id=policy.binding_id,
        tenant_id=policy.tenant_id,
        source_kind=policy.source_kind,
        source_ref=policy.source_ref,
        status=status,
        entity_id=observation.entity_id,
        field_name=observation.field_name,
        observed_at=observation.observed_at,
        evidence_ref=observation.evidence_ref,
        source_receipt_ref=observation.source_receipt_ref,
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
) -> LiveCompanyRealitySnapshot:
    """Build a world snapshot from explicitly governed live-source policies.

    A required binding with no accepted current observation makes the live
    reality unavailable. Rejected/stale observations never enter the world
    model. Existing equal-authority world-model conflicts remain fail-closed.
    """

    _require_aware(as_of, "live_reality_as_of_requires_timezone")
    if any(policy.tenant_id != tenant_id for policy in policies):
        raise ValueError("live_reality_policy_tenant_mismatch")

    policy_by_id = {policy.binding_id: policy for policy in policies}
    if len(policy_by_id) != len(policies):
        raise ValueError("live_reality_duplicate_binding_id")

    outcomes: list[LiveBindingOutcome] = []
    observations_by_binding: dict[str, list[LiveFactObservation]] = {}
    for observation in observations:
        observations_by_binding.setdefault(observation.binding_id, []).append(observation)

    unknown_binding_ids = sorted(set(observations_by_binding) - set(policy_by_id))
    if unknown_binding_ids:
        raise ValueError("live_reality_observation_binding_unknown")

    unavailable: list[str] = []
    degraded: list[str] = []
    assertions: list[WorldAssertion] = []

    for policy in policies:
        items = observations_by_binding.get(policy.binding_id, [])
        if not items:
            if policy.required:
                unavailable.append(policy.binding_id)
            outcomes.append(
                LiveBindingOutcome(
                    receipt=LiveBindingReceipt(
                        binding_id=policy.binding_id,
                        tenant_id=policy.tenant_id,
                        source_kind=policy.source_kind,
                        source_ref=policy.source_ref,
                        status=LiveBindingStatus.SOURCE_UNAVAILABLE,
                        reasons=("required_source_observation_missing",) if policy.required else ("optional_source_observation_missing",),
                    )
                )
            )
            continue

        accepted_for_binding = 0
        nonaccepted_for_binding = False
        for observation in items:
            outcome = bind_live_observation(policy=policy, observation=observation, as_of=as_of)
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
