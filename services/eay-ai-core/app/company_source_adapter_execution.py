"""Execution composition for reviewed read-only company source adapters.

This layer joins the adapter registry to ``live_company_source_runtime`` without
creating a second truth or authorization path. A collector is callable only
after exact registry routing succeeds, the descriptor is at least CONTROLLED,
and the injected runtime binding declares the same reviewed protocol.

A successful call still returns collection evidence only. Truth promotion stays
behind the independent LiveSourceAttestation path and execution authority is
never granted here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from pydantic import BaseModel, model_validator

from .company_source_adapter_registry import (
    AdapterAcceptance,
    CompanySourceAdapterRegistry,
    CompanySourceProtocol,
    CompanySourceRoute,
    resolve_company_source_route,
)
from .live_company_reality import LiveSourceBindingPolicy
from .live_company_source_runtime import (
    ReadOnlyCollectionReceipt,
    ReadOnlyCompanySourceAdapter,
    ReadOnlySourcePlan,
    collect_read_only_source,
)

COMPANY_SOURCE_ADAPTER_EXECUTION_CONTRACT = "eay-company-source-adapter-execution-v1"


@dataclass(frozen=True)
class CompanySourceRuntimeBinding:
    adapter_ref: str
    protocol: CompanySourceProtocol
    collector: ReadOnlyCompanySourceAdapter


class CompanySourceExecutionReceipt(BaseModel):
    contract: str = COMPANY_SOURCE_ADAPTER_EXECUTION_CONTRACT
    route: CompanySourceRoute
    collection: ReadOnlyCollectionReceipt
    truth_promoted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def receipt_is_non_authoritative(self) -> "CompanySourceExecutionReceipt":
        if self.truth_promoted:
            raise ValueError("company_source_execution_never_promotes_truth")
        if self.execution_authority_granted:
            raise ValueError("company_source_execution_never_grants_execution_authority")
        if self.collection.truth_promoted:
            raise ValueError("company_source_execution_collection_cannot_be_truth")
        if self.collection.execution_authority_granted:
            raise ValueError("company_source_execution_collection_cannot_grant_execution")
        if self.route.adapter_ref == "" or self.route.operation_ref == "":
            raise ValueError("company_source_execution_route_incomplete")
        if self.route.operation_ref != self.collection.plan.operation_ref:
            raise ValueError("company_source_execution_operation_drift")
        return self


def _descriptor_for_adapter(
    registry: CompanySourceAdapterRegistry,
    adapter_ref: str,
):
    matches = [item for item in registry.adapters if item.adapter_ref == adapter_ref]
    if len(matches) != 1:
        raise ValueError("company_source_execution_adapter_not_registered")
    return matches[0]


def execute_registered_company_read(
    *,
    registry: CompanySourceAdapterRegistry,
    plan: ReadOnlySourcePlan,
    policy: LiveSourceBindingPolicy,
    adapter_ref: str,
    runtime_bindings: Mapping[str, CompanySourceRuntimeBinding],
) -> CompanySourceExecutionReceipt:
    """Collect through one exact reviewed route; never promote truth here."""

    # Route resolution happens before any runtime collector can be touched. It
    # validates tenant/source/schema/environment/identity/operation/field scope.
    route = resolve_company_source_route(
        registry=registry,
        plan=plan,
        adapter_ref=adapter_ref,
    )
    descriptor = _descriptor_for_adapter(registry, adapter_ref)

    if descriptor.acceptance is AdapterAcceptance.REPOSITORY_ONLY:
        raise ValueError("company_source_execution_adapter_not_controlled")

    runtime = runtime_bindings.get(adapter_ref)
    if runtime is None:
        raise ValueError("company_source_execution_runtime_binding_missing")
    if runtime.adapter_ref != adapter_ref:
        raise ValueError("company_source_execution_runtime_adapter_ref_mismatch")
    if runtime.protocol is not descriptor.protocol:
        raise ValueError("company_source_execution_runtime_protocol_mismatch")

    collection = collect_read_only_source(
        plan=plan,
        policy=policy,
        adapter=runtime.collector,
    )
    return CompanySourceExecutionReceipt(route=route, collection=collection)
