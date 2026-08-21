"""Non-promoting evidence contract for live BigQuery cross-tenant verification.

This module deliberately does not execute BigQuery and does not turn a claimed
live run into production authority. It defines the exact evidence shape that a
later human promotion review must consume. The contract binds live-run metadata
to the reviewed orders-v2 query, parameter adapter, SDK adapter and schema
attestation artifact while minimizing raw tenant/store disclosure.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.ai_orders_v2_bigquery_parameters import (
    orders_v2_bigquery_parameter_contract_fingerprint,
)
from app.core.ai_orders_v2_bigquery_sdk_adapter import (
    orders_v2_bigquery_sdk_adapter_fingerprint,
)
from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_orders_v2_schema_attestation import (
    OrdersV2SchemaAttestationArtifact,
)

LIVE_CROSS_TENANT_EVIDENCE_VERSION = 1
LIVE_CROSS_TENANT_REVIEW_BLOCKER = (
    "orders_v2_live_cross_tenant_evidence_human_review_required"
)
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class OrdersV2LiveCrossTenantEvidence(BaseModel):
    """Reviewable claim about one controlled live cross-tenant BigQuery run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[1]
    kind: Literal["live_bigquery_cross_tenant_evidence_candidate"]
    project: str = Field(min_length=1, max_length=256)
    location: str | None = Field(default=None, max_length=128)
    executed_at: datetime
    query_job_id_sha256: str = Field(pattern=SHA256_PATTERN)
    authorized_scope_sha256: str = Field(pattern=SHA256_PATTERN)
    foreign_sentinel_scope_sha256: str = Field(pattern=SHA256_PATTERN)
    returned_rowset_sha256: str = Field(pattern=SHA256_PATTERN)
    foreign_sentinel_match_count: Literal[0]
    candidate_template_fingerprint: str = Field(pattern=SHA256_PATTERN)
    parameter_contract_fingerprint: str = Field(pattern=SHA256_PATTERN)
    sdk_adapter_fingerprint: str = Field(pattern=SHA256_PATTERN)
    schema_attestation_fingerprint: str = Field(pattern=SHA256_PATTERN)
    live_bigquery_run_claimed: Literal[True]
    cryptographically_attested: Literal[False]
    promotion_eligible: Literal[False]
    human_review_required: Literal[True]
    production_blocker: Literal[
        "orders_v2_live_cross_tenant_evidence_human_review_required"
    ]

    @model_validator(mode="after")
    def validate_review_contract(self) -> OrdersV2LiveCrossTenantEvidence:
        if (
            self.candidate_template_fingerprint
            != ORDERS_V2_CANDIDATE.template_fingerprint
        ):
            raise ValueError("candidate template fingerprint mismatch")
        if (
            self.parameter_contract_fingerprint
            != orders_v2_bigquery_parameter_contract_fingerprint()
        ):
            raise ValueError("parameter contract fingerprint mismatch")
        if (
            self.sdk_adapter_fingerprint
            != orders_v2_bigquery_sdk_adapter_fingerprint()
        ):
            raise ValueError("SDK adapter fingerprint mismatch")
        if self.authorized_scope_sha256 == self.foreign_sentinel_scope_sha256:
            raise ValueError("authorized and foreign scopes must be distinct")
        return self

    @property
    def evidence_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def sha256_text(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("evidence text must be non-empty")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_orders_v2_live_cross_tenant_evidence_candidate(
    *,
    schema_attestation: OrdersV2SchemaAttestationArtifact,
    executed_at: datetime,
    query_job_id: str,
    authorized_scope_descriptor: str,
    foreign_sentinel_scope_descriptor: str,
    canonical_returned_rowset: str,
    foreign_sentinel_match_count: int,
) -> OrdersV2LiveCrossTenantEvidence:
    """Bind a claimed live run to exact reviewed contracts without promoting it."""

    if schema_attestation.promotion_eligible is not False:
        raise ValueError("schema attestation promotion state is invalid")
    if schema_attestation.human_review_required is not True:
        raise ValueError("schema attestation review state is invalid")
    if foreign_sentinel_match_count != 0:
        raise ValueError("foreign sentinel leakage detected")

    return OrdersV2LiveCrossTenantEvidence(
        version=LIVE_CROSS_TENANT_EVIDENCE_VERSION,
        kind="live_bigquery_cross_tenant_evidence_candidate",
        project=schema_attestation.project,
        location=schema_attestation.location,
        executed_at=executed_at,
        query_job_id_sha256=sha256_text(query_job_id),
        authorized_scope_sha256=sha256_text(authorized_scope_descriptor),
        foreign_sentinel_scope_sha256=sha256_text(
            foreign_sentinel_scope_descriptor
        ),
        returned_rowset_sha256=sha256_text(canonical_returned_rowset),
        foreign_sentinel_match_count=0,
        candidate_template_fingerprint=(
            schema_attestation.candidate_template_fingerprint
        ),
        parameter_contract_fingerprint=(
            schema_attestation.parameter_contract_fingerprint
        ),
        sdk_adapter_fingerprint=schema_attestation.sdk_adapter_fingerprint,
        schema_attestation_fingerprint=schema_attestation.artifact_fingerprint,
        live_bigquery_run_claimed=True,
        cryptographically_attested=False,
        promotion_eligible=False,
        human_review_required=True,
        production_blocker=LIVE_CROSS_TENANT_REVIEW_BLOCKER,
    )
