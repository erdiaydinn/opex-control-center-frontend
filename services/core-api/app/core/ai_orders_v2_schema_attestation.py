"""Human-reviewed live schema attestation candidate for orders v2.

A successful collector run is meaningful evidence, but code must not be able to
self-promote a production query. This artifact therefore records the live-run
claim and all reviewed fingerprints while remaining explicitly non-promoting
until a separate human promotion review consumes it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.ai_orders_v2_bigquery_parameters import (
    orders_v2_bigquery_parameter_contract_fingerprint,
)
from app.core.ai_orders_v2_bigquery_sdk_adapter import (
    orders_v2_bigquery_sdk_adapter_fingerprint,
)
from app.core.ai_orders_v2_live_schema_collector import (
    UNATTESTED_COLLECTOR_BLOCKER,
    OrdersV2CollectedSchemaObservation,
)
from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_orders_v2_schema_evidence import (
    ORDERS_V2_SCHEMA_EVIDENCE_QUERY_SHA256,
    validate_orders_v2_schema_evidence,
)

SCHEMA_ATTESTATION_VERSION = 1
SCHEMA_ATTESTATION_PROMOTION_BLOCKER = (
    "orders_v2_human_promotion_review_required"
)
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class OrdersV2SchemaAttestationArtifact(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    version: Literal[1]
    kind: Literal["live_bigquery_schema_attestation_candidate"]
    project: str = Field(min_length=1, max_length=256)
    location: str | None = Field(default=None, max_length=128)
    observed_at: str
    schema_evidence_fingerprint: str = Field(pattern=SHA256_PATTERN)
    collector_query_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_template_fingerprint: str = Field(pattern=SHA256_PATTERN)
    parameter_contract_fingerprint: str = Field(pattern=SHA256_PATTERN)
    sdk_adapter_fingerprint: str = Field(pattern=SHA256_PATTERN)
    collector_observation_fingerprint: str = Field(pattern=SHA256_PATTERN)
    live_collector_run_claimed: Literal[True]
    cryptographically_attested: Literal[False]
    promotion_eligible: Literal[False]
    human_review_required: Literal[True]
    production_blocker: Literal[
        "orders_v2_human_promotion_review_required"
    ]

    @property
    def artifact_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def orders_v2_collector_observation_fingerprint(
    observation: OrdersV2CollectedSchemaObservation,
) -> str:
    encoded = json.dumps(
        observation.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_orders_v2_schema_attestation_candidate(
    observation: OrdersV2CollectedSchemaObservation,
) -> OrdersV2SchemaAttestationArtifact:
    """Bind one collector observation to the exact reviewed code contracts."""

    if observation.attested_live_run is not False:
        raise ValueError("collector observation attestation state is invalid")
    if observation.production_blocker != UNATTESTED_COLLECTOR_BLOCKER:
        raise ValueError("collector observation blocker is invalid")

    evidence_fingerprint = validate_orders_v2_schema_evidence(
        observation.evidence
    )
    if observation.evidence.table_catalog != observation.client_project:
        raise ValueError("collector observation project binding mismatch")

    return OrdersV2SchemaAttestationArtifact(
        version=SCHEMA_ATTESTATION_VERSION,
        kind="live_bigquery_schema_attestation_candidate",
        project=observation.client_project,
        location=observation.client_location,
        observed_at=observation.evidence.observed_at.isoformat(),
        schema_evidence_fingerprint=evidence_fingerprint,
        collector_query_sha256=(
            ORDERS_V2_SCHEMA_EVIDENCE_QUERY_SHA256
        ),
        candidate_template_fingerprint=(
            ORDERS_V2_CANDIDATE.template_fingerprint
        ),
        parameter_contract_fingerprint=(
            orders_v2_bigquery_parameter_contract_fingerprint()
        ),
        sdk_adapter_fingerprint=(
            orders_v2_bigquery_sdk_adapter_fingerprint()
        ),
        collector_observation_fingerprint=(
            orders_v2_collector_observation_fingerprint(observation)
        ),
        live_collector_run_claimed=True,
        cryptographically_attested=False,
        promotion_eligible=False,
        human_review_required=True,
        production_blocker=SCHEMA_ATTESTATION_PROMOTION_BLOCKER,
    )
