"""Governed routing registry for live-company read-only adapters.

Jarvis may choose among BigQuery, browser-observation and internal API read
surfaces, but it may not invent an arbitrary SQL/URL and call it trusted. A
route is valid only when source kind, environment, execution identity,
operation contract and requested fields match a reviewed adapter descriptor.

Routing does not attest or promote truth. Collected data still passes through
``live_company_source_runtime`` and the independent ``LiveSourceAttestation``
path before it can become Company World truth.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .live_company_reality import LiveSourceKind
from .live_company_source_runtime import ReadOnlySourcePlan

COMPANY_SOURCE_ADAPTER_REGISTRY_CONTRACT = "eay-company-source-adapter-registry-v1"


class CompanySourceProtocol(str, Enum):
    BIGQUERY = "bigquery"
    BROWSER_OBSERVATION = "browser_observation"
    INTERNAL_API = "internal_api"


class AdapterAcceptance(str, Enum):
    REPOSITORY_ONLY = "repository_only"
    CONTROLLED = "controlled"
    FIELD_PROVEN = "field_proven"


class CompanySourceOperation(BaseModel):
    operation_ref: str = Field(min_length=1)
    contract_ref: str = Field(min_length=1)
    allowed_fields: tuple[str, ...] = Field(min_length=1)
    parameter_names: tuple[str, ...] = ()
    read_only: bool = True
    mutation_semantics_present: bool = False
    raw_query_or_url_retained: bool = False

    @model_validator(mode="after")
    def operation_is_safe(self) -> "CompanySourceOperation":
        if not self.read_only or self.mutation_semantics_present:
            raise ValueError("company_source_registry_operation_must_be_read_only")
        if self.raw_query_or_url_retained:
            raise ValueError("company_source_registry_forbids_raw_query_or_url_retention")
        if len(self.allowed_fields) != len(set(self.allowed_fields)):
            raise ValueError("company_source_registry_allowed_fields_must_be_unique")
        if len(self.parameter_names) != len(set(self.parameter_names)):
            raise ValueError("company_source_registry_parameter_names_must_be_unique")
        return self


class CompanySourceAdapterDescriptor(BaseModel):
    contract: str = COMPANY_SOURCE_ADAPTER_REGISTRY_CONTRACT
    adapter_ref: str = Field(min_length=1)
    source_kind: LiveSourceKind
    protocol: CompanySourceProtocol
    source_ref: str = Field(min_length=1)
    schema_contract: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    environment_ref: str = Field(min_length=1)
    execution_identity_ref: str = Field(min_length=1)
    operations: tuple[CompanySourceOperation, ...] = Field(min_length=1)
    acceptance: AdapterAcceptance = AdapterAcceptance.REPOSITORY_ONLY
    field_production_verified: bool = False
    adapter_grants_truth_authority: bool = False
    adapter_grants_execution_authority: bool = False

    @model_validator(mode="after")
    def descriptor_is_non_authoritative(self) -> "CompanySourceAdapterDescriptor":
        if self.adapter_grants_truth_authority:
            raise ValueError("company_source_adapter_never_grants_truth_authority")
        if self.adapter_grants_execution_authority:
            raise ValueError("company_source_adapter_never_grants_execution_authority")
        refs = [item.operation_ref for item in self.operations]
        if len(refs) != len(set(refs)):
            raise ValueError("company_source_adapter_operation_refs_must_be_unique")
        if self.field_production_verified != (self.acceptance is AdapterAcceptance.FIELD_PROVEN):
            raise ValueError("company_source_adapter_field_acceptance_mismatch")
        return self


class CompanySourceAdapterRegistry(BaseModel):
    contract: str = COMPANY_SOURCE_ADAPTER_REGISTRY_CONTRACT
    tenant_id: str = Field(min_length=1)
    adapters: tuple[CompanySourceAdapterDescriptor, ...]

    @model_validator(mode="after")
    def adapter_refs_are_unique(self) -> "CompanySourceAdapterRegistry":
        refs = [item.adapter_ref for item in self.adapters]
        if len(refs) != len(set(refs)):
            raise ValueError("company_source_adapter_refs_must_be_unique")
        return self


class CompanySourceRoute(BaseModel):
    contract: str = COMPANY_SOURCE_ADAPTER_REGISTRY_CONTRACT
    adapter_ref: str
    operation_ref: str
    contract_ref: str
    acceptance: AdapterAcceptance
    field_production_verified: bool
    truth_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def route_is_non_authoritative(self) -> "CompanySourceRoute":
        if self.truth_authority_granted:
            raise ValueError("company_source_route_never_grants_truth_authority")
        if self.execution_authority_granted:
            raise ValueError("company_source_route_never_grants_execution_authority")
        return self


def resolve_company_source_route(
    *,
    registry: CompanySourceAdapterRegistry,
    plan: ReadOnlySourcePlan,
    adapter_ref: str,
) -> CompanySourceRoute:
    if plan.tenant_id != registry.tenant_id:
        raise ValueError("company_source_route_tenant_mismatch")
    matches = [item for item in registry.adapters if item.adapter_ref == adapter_ref]
    if len(matches) != 1:
        raise ValueError("company_source_route_adapter_not_found")
    adapter = matches[0]

    exact_pairs = (
        (plan.source_kind, adapter.source_kind, "source_kind"),
        (plan.source_ref, adapter.source_ref, "source_ref"),
        (plan.schema_contract, adapter.schema_contract, "schema_contract"),
        (plan.schema_version, adapter.schema_version, "schema_version"),
        (plan.environment_ref, adapter.environment_ref, "environment"),
        (plan.execution_identity_ref, adapter.execution_identity_ref, "execution_identity"),
    )
    for actual, expected, label in exact_pairs:
        if actual != expected:
            raise ValueError("company_source_route_" + label + "_mismatch")

    operations = [item for item in adapter.operations if item.operation_ref == plan.operation_ref]
    if len(operations) != 1:
        raise ValueError("company_source_route_operation_not_registered")
    operation = operations[0]
    if any(field not in operation.allowed_fields for field in plan.requested_fields):
        raise ValueError("company_source_route_requested_field_not_allowed")

    return CompanySourceRoute(
        adapter_ref=adapter.adapter_ref,
        operation_ref=operation.operation_ref,
        contract_ref=operation.contract_ref,
        acceptance=adapter.acceptance,
        field_production_verified=adapter.field_production_verified,
    )


def field_proven_routes(
    registry: CompanySourceAdapterRegistry,
    *,
    source_kind: LiveSourceKind | None = None,
) -> tuple[str, ...]:
    """Inventory field-proven adapter refs without implying truth promotion."""

    return tuple(
        item.adapter_ref
        for item in registry.adapters
        if item.acceptance is AdapterAcceptance.FIELD_PROVEN
        and item.field_production_verified
        and (source_kind is None or item.source_kind is source_kind)
    )
