"""Read-only live-company source runtime for Jarvis.

This module deliberately separates source collection from truth promotion.
An adapter may collect a bounded read-only batch, but that batch cannot become
Company World truth until an independently issued ``LiveSourceAttestation`` is
supplied and trusted by the existing ``live_company_reality`` gate.

The runtime is generic across Orders, Inventory, Workforce, Planogram and
Budget. It never accepts mutation semantics, raw credential retention or raw
transport payload retention.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Collection, Protocol

from pydantic import BaseModel, Field, model_validator

from .live_company_reality import (
    LiveBindingOutcome,
    LiveFactObservation,
    LiveSourceAttestation,
    LiveSourceBindingPolicy,
    LiveSourceKind,
    bind_live_observation,
)

LIVE_COMPANY_SOURCE_RUNTIME_CONTRACT = "eay-live-company-source-runtime-v1"


class ReadOnlySourceField(BaseModel):
    entity_id: str = Field(min_length=1)
    field_name: str = Field(min_length=1)
    value: Any
    valid_from: datetime
    valid_to: datetime | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def temporal_contract(self) -> "ReadOnlySourceField":
        if self.valid_from.tzinfo is None or self.valid_from.utcoffset() is None:
            raise ValueError("read_only_source_valid_from_requires_timezone")
        if self.valid_to is not None:
            if self.valid_to.tzinfo is None or self.valid_to.utcoffset() is None:
                raise ValueError("read_only_source_valid_to_requires_timezone")
            if self.valid_to <= self.valid_from:
                raise ValueError("read_only_source_valid_to_must_follow_valid_from")
        return self


class ReadOnlySourcePlan(BaseModel):
    contract: str = LIVE_COMPANY_SOURCE_RUNTIME_CONTRACT
    binding_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    source_kind: LiveSourceKind
    source_ref: str = Field(min_length=1)
    schema_contract: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    environment_ref: str = Field(min_length=1)
    execution_identity_ref: str = Field(min_length=1)
    operation_ref: str = Field(min_length=1)
    requested_fields: tuple[str, ...] = Field(min_length=1)
    requested_at: datetime
    read_only: bool = True
    mutation_requested: bool = False
    credential_material_present: bool = False

    @model_validator(mode="after")
    def plan_is_read_only(self) -> "ReadOnlySourcePlan":
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("read_only_source_plan_requires_timezone")
        if not self.read_only or self.mutation_requested:
            raise ValueError("live_company_source_runtime_forbids_mutation")
        if self.credential_material_present:
            raise ValueError("live_company_source_plan_cannot_embed_credentials")
        if len(self.requested_fields) != len(set(self.requested_fields)):
            raise ValueError("read_only_source_requested_fields_must_be_unique")
        return self


class ReadOnlySourceBatch(BaseModel):
    contract: str = LIVE_COMPANY_SOURCE_RUNTIME_CONTRACT
    binding_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    source_kind: LiveSourceKind
    source_ref: str = Field(min_length=1)
    schema_contract: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    environment_ref: str = Field(min_length=1)
    execution_identity_ref: str = Field(min_length=1)
    operation_ref: str = Field(min_length=1)
    observed_at: datetime
    source_receipt_ref: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)
    fields: tuple[ReadOnlySourceField, ...]
    mutation_observed: bool = False
    raw_payload_retained: bool = False
    credential_material_retained: bool = False

    @model_validator(mode="after")
    def batch_is_safe(self) -> "ReadOnlySourceBatch":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("read_only_source_batch_requires_timezone")
        if self.mutation_observed:
            raise ValueError("read_only_source_batch_observed_mutation")
        if self.raw_payload_retained:
            raise ValueError("read_only_source_batch_cannot_retain_raw_payload")
        if self.credential_material_retained:
            raise ValueError("read_only_source_batch_cannot_retain_credentials")
        return self


class ReadOnlyCompanySourceAdapter(Protocol):
    def collect(self, plan: ReadOnlySourcePlan) -> ReadOnlySourceBatch: ...


class ReadOnlyCollectionReceipt(BaseModel):
    contract: str = LIVE_COMPANY_SOURCE_RUNTIME_CONTRACT
    plan: ReadOnlySourcePlan
    batch: ReadOnlySourceBatch
    truth_promoted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def collection_is_not_truth(self) -> "ReadOnlyCollectionReceipt":
        if self.truth_promoted:
            raise ValueError("read_only_collection_never_promotes_truth")
        if self.execution_authority_granted:
            raise ValueError("read_only_collection_never_grants_execution_authority")
        return self


class ReadOnlyPromotionResult(BaseModel):
    contract: str = LIVE_COMPANY_SOURCE_RUNTIME_CONTRACT
    source_receipt_ref: str
    outcomes: tuple[LiveBindingOutcome, ...]
    authoritative_assertion_count: int = Field(ge=0)
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def promotion_never_grants_execution(self) -> "ReadOnlyPromotionResult":
        if self.execution_authority_granted:
            raise ValueError("read_only_promotion_never_grants_execution_authority")
        accepted = sum(item.assertion is not None for item in self.outcomes)
        if accepted != self.authoritative_assertion_count:
            raise ValueError("read_only_promotion_assertion_count_mismatch")
        return self


def _field_allowed(policy: LiveSourceBindingPolicy, field_name: str) -> bool:
    return field_name in policy.allowed_fields or any(
        field_name.startswith(prefix) for prefix in policy.allowed_field_prefixes
    )


def _validate_plan_against_policy(
    plan: ReadOnlySourcePlan,
    policy: LiveSourceBindingPolicy,
) -> None:
    exact_pairs = (
        (plan.binding_id, policy.binding_id, "binding"),
        (plan.tenant_id, policy.tenant_id, "tenant"),
        (plan.source_kind, policy.source_kind, "source_kind"),
        (plan.source_ref, policy.source_ref, "source_ref"),
        (plan.schema_contract, policy.schema_contract, "schema_contract"),
        (plan.schema_version, policy.schema_version, "schema_version"),
        (plan.environment_ref, policy.environment_ref, "environment"),
        (
            plan.execution_identity_ref,
            policy.execution_identity_ref,
            "execution_identity",
        ),
    )
    for actual, expected, label in exact_pairs:
        if actual != expected:
            raise ValueError(f"read_only_source_plan_{label}_mismatch")
    if any(not _field_allowed(policy, name) for name in plan.requested_fields):
        raise ValueError("read_only_source_plan_field_not_allowed")


def _validate_batch_against_plan(
    batch: ReadOnlySourceBatch,
    plan: ReadOnlySourcePlan,
) -> None:
    exact_pairs = (
        (batch.binding_id, plan.binding_id, "binding"),
        (batch.tenant_id, plan.tenant_id, "tenant"),
        (batch.source_kind, plan.source_kind, "source_kind"),
        (batch.source_ref, plan.source_ref, "source_ref"),
        (batch.schema_contract, plan.schema_contract, "schema_contract"),
        (batch.schema_version, plan.schema_version, "schema_version"),
        (batch.environment_ref, plan.environment_ref, "environment"),
        (
            batch.execution_identity_ref,
            plan.execution_identity_ref,
            "execution_identity",
        ),
        (batch.operation_ref, plan.operation_ref, "operation"),
    )
    for actual, expected, label in exact_pairs:
        if actual != expected:
            raise ValueError(f"read_only_source_batch_{label}_mismatch")
    requested = set(plan.requested_fields)
    if any(item.field_name not in requested for item in batch.fields):
        raise ValueError("read_only_source_batch_returned_unrequested_field")
    if batch.observed_at < plan.requested_at:
        raise ValueError("read_only_source_batch_predates_request")


def collect_read_only_source(
    *,
    plan: ReadOnlySourcePlan,
    policy: LiveSourceBindingPolicy,
    adapter: ReadOnlyCompanySourceAdapter,
) -> ReadOnlyCollectionReceipt:
    """Collect evidence without granting truth or execution authority."""

    _validate_plan_against_policy(plan, policy)
    batch = adapter.collect(plan)
    _validate_batch_against_plan(batch, plan)
    return ReadOnlyCollectionReceipt(plan=plan, batch=batch)


def promote_verified_read_only_batch(
    *,
    collection: ReadOnlyCollectionReceipt,
    policy: LiveSourceBindingPolicy,
    attestation: LiveSourceAttestation,
    as_of: datetime,
    known_entity_ids: Collection[str],
    trusted_attestation_fingerprints: Collection[str],
) -> ReadOnlyPromotionResult:
    """Promote only through the existing authoritative live-truth gate."""

    _validate_plan_against_policy(collection.plan, policy)
    _validate_batch_against_plan(collection.batch, collection.plan)
    batch = collection.batch
    if attestation.source_receipt_ref != batch.source_receipt_ref:
        raise ValueError("read_only_source_attestation_receipt_mismatch")
    if attestation.binding_id != batch.binding_id:
        raise ValueError("read_only_source_attestation_binding_mismatch")
    if attestation.tenant_id != batch.tenant_id:
        raise ValueError("read_only_source_attestation_tenant_mismatch")
    if attestation.source_ref != batch.source_ref:
        raise ValueError("read_only_source_attestation_source_mismatch")
    if attestation.schema_contract != batch.schema_contract:
        raise ValueError("read_only_source_attestation_schema_contract_mismatch")
    if attestation.schema_version != batch.schema_version:
        raise ValueError("read_only_source_attestation_schema_version_mismatch")
    if attestation.environment_ref != batch.environment_ref:
        raise ValueError("read_only_source_attestation_environment_mismatch")
    if attestation.execution_identity_ref != batch.execution_identity_ref:
        raise ValueError("read_only_source_attestation_identity_mismatch")

    outcomes: list[LiveBindingOutcome] = []
    for item in batch.fields:
        observation = LiveFactObservation(
            binding_id=batch.binding_id,
            tenant_id=batch.tenant_id,
            source_kind=batch.source_kind,
            source_ref=batch.source_ref,
            schema_contract=batch.schema_contract,
            schema_version=batch.schema_version,
            entity_id=item.entity_id,
            field_name=item.field_name,
            value=item.value,
            valid_from=item.valid_from,
            valid_to=item.valid_to,
            observed_at=batch.observed_at,
            confidence=item.confidence,
            attestation=attestation,
        )
        outcomes.append(
            bind_live_observation(
                policy=policy,
                observation=observation,
                as_of=as_of,
                known_entity_ids=known_entity_ids,
                trusted_attestation_fingerprints=trusted_attestation_fingerprints,
            )
        )

    return ReadOnlyPromotionResult(
        source_receipt_ref=batch.source_receipt_ref,
        outcomes=tuple(outcomes),
        authoritative_assertion_count=sum(item.assertion is not None for item in outcomes),
    )
