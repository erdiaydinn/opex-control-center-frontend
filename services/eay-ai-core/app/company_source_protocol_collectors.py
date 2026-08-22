"""Protocol-specific, proof-bound collectors for governed live company reads.

The generic company-source runtime intentionally does not know transport details.
This module adds transport/protocol evidence without creating a second truth path:
BigQuery, internal API, and browser observations may produce normalized read-only
batches only when their runtime proof demonstrates non-mutating behavior.

Collectors never promote Company World truth. Promotion remains exclusively behind
the independent LiveSourceAttestation gate in ``live_company_source_runtime``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from .company_source_adapter_registry import CompanySourceProtocol
from .live_company_source_runtime import (
    ReadOnlyCompanySourceAdapter,
    ReadOnlySourceBatch,
    ReadOnlySourceField,
    ReadOnlySourcePlan,
)

COMPANY_SOURCE_PROTOCOL_COLLECTOR_CONTRACT = "eay-company-source-protocol-collector-v1"


class CompanyReadProtocolProof(BaseModel):
    contract: str = COMPANY_SOURCE_PROTOCOL_COLLECTOR_CONTRACT
    protocol: CompanySourceProtocol
    operation_ref: str = Field(min_length=1)
    executed_at: datetime
    evidence_ref: str = Field(min_length=1)
    read_only: bool = True
    mutation_detected: bool = False
    raw_request_retained: bool = False
    raw_response_retained: bool = False
    credential_material_retained: bool = False

    # Protocol-specific normalized facts. These are intentionally low-cardinality
    # execution facts rather than query text, URLs, headers, cookies or payloads.
    statement_type: str | None = None
    destination_write_detected: bool = False
    http_method: str | None = None
    http_status: int | None = Field(default=None, ge=100, le=599)
    form_submit_detected: bool = False

    @model_validator(mode="after")
    def proof_is_read_only_and_secret_safe(self) -> "CompanyReadProtocolProof":
        if self.executed_at.tzinfo is None or self.executed_at.utcoffset() is None:
            raise ValueError("company_source_protocol_proof_requires_timezone")
        if not self.read_only or self.mutation_detected:
            raise ValueError("company_source_protocol_proof_detected_mutation")
        if (
            self.raw_request_retained
            or self.raw_response_retained
            or self.credential_material_retained
        ):
            raise ValueError("company_source_protocol_proof_cannot_retain_sensitive_transport")
        if self.protocol is CompanySourceProtocol.BIGQUERY:
            if (self.statement_type or "").upper() != "SELECT":
                raise ValueError("company_source_bigquery_requires_select_statement")
            if self.destination_write_detected:
                raise ValueError("company_source_bigquery_destination_write_forbidden")
            if self.http_method is not None or self.http_status is not None:
                raise ValueError("company_source_bigquery_cannot_claim_http_transport")
            if self.form_submit_detected:
                raise ValueError("company_source_bigquery_cannot_claim_form_submit")
        elif self.protocol is CompanySourceProtocol.INTERNAL_API:
            if (self.http_method or "").upper() not in {"GET", "HEAD"}:
                raise ValueError("company_source_internal_api_requires_get_or_head")
            if self.http_status is None or not 200 <= self.http_status < 300:
                raise ValueError("company_source_internal_api_requires_success_status")
            if self.statement_type is not None or self.destination_write_detected:
                raise ValueError("company_source_internal_api_cannot_claim_bigquery_execution")
            if self.form_submit_detected:
                raise ValueError("company_source_internal_api_cannot_claim_form_submit")
        elif self.protocol is CompanySourceProtocol.BROWSER_OBSERVATION:
            if (self.http_method or "").upper() not in {"GET", "HEAD"}:
                raise ValueError("company_source_browser_observation_requires_get_or_head")
            if self.http_status is None or not 200 <= self.http_status < 400:
                raise ValueError("company_source_browser_observation_requires_success_status")
            if self.form_submit_detected:
                raise ValueError("company_source_browser_observation_form_submit_forbidden")
            if self.statement_type is not None or self.destination_write_detected:
                raise ValueError("company_source_browser_observation_cannot_claim_bigquery_execution")
        return self


class NormalizedCompanyReadResult(BaseModel):
    contract: str = COMPANY_SOURCE_PROTOCOL_COLLECTOR_CONTRACT
    operation_ref: str = Field(min_length=1)
    observed_at: datetime
    source_receipt_ref: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)
    fields: tuple[ReadOnlySourceField, ...]
    proof: CompanyReadProtocolProof
    truth_promoted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def result_is_collection_only(self) -> "NormalizedCompanyReadResult":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("company_source_normalized_result_requires_timezone")
        if self.truth_promoted:
            raise ValueError("company_source_normalized_result_never_promotes_truth")
        if self.execution_authority_granted:
            raise ValueError("company_source_normalized_result_never_grants_execution")
        if self.operation_ref != self.proof.operation_ref:
            raise ValueError("company_source_normalized_result_operation_proof_mismatch")
        if self.proof.executed_at > self.observed_at:
            raise ValueError("company_source_protocol_proof_executes_after_observation")
        return self


class PreparedCompanyReadExecutor(Protocol):
    def execute(self, plan: ReadOnlySourcePlan) -> NormalizedCompanyReadResult: ...


@dataclass(frozen=True)
class ProtocolBoundCompanySourceAdapter(ReadOnlyCompanySourceAdapter):
    """Bind one reviewed protocol to an injected prepared-operation executor."""

    protocol: CompanySourceProtocol
    executor: PreparedCompanyReadExecutor

    def collect(self, plan: ReadOnlySourcePlan) -> ReadOnlySourceBatch:
        result = self.executor.execute(plan)
        # Rehydrate so ``model_copy`` cannot bypass protocol validation.
        result = NormalizedCompanyReadResult.model_validate(result.model_dump(mode="json"))
        if result.proof.protocol is not self.protocol:
            raise ValueError("company_source_runtime_protocol_proof_mismatch")
        if result.operation_ref != plan.operation_ref:
            raise ValueError("company_source_runtime_operation_mismatch")
        if result.observed_at < plan.requested_at:
            raise ValueError("company_source_runtime_observation_predates_request")
        requested = set(plan.requested_fields)
        if any(field.field_name not in requested for field in result.fields):
            raise ValueError("company_source_runtime_returned_unrequested_field")

        return ReadOnlySourceBatch(
            binding_id=plan.binding_id,
            tenant_id=plan.tenant_id,
            source_kind=plan.source_kind,
            source_ref=plan.source_ref,
            schema_contract=plan.schema_contract,
            schema_version=plan.schema_version,
            environment_ref=plan.environment_ref,
            execution_identity_ref=plan.execution_identity_ref,
            operation_ref=plan.operation_ref,
            observed_at=result.observed_at,
            source_receipt_ref=result.source_receipt_ref,
            evidence_ref=result.evidence_ref,
            fields=result.fields,
        )
