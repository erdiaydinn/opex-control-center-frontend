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

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    OrdersV2InformationSchemaEvidence,
    validate_orders_v2_schema_evidence,
)

SCHEMA_ATTESTATION_VERSION = 1
SCHEMA_ATTESTATION_PROMOTION_BLOCKER = (
    "orders_v2_human_promotion_review_required"
)
SHA256_PATTERN = r"^[0-9a-f]{64}$"


def _collector_observation_payload_from_artifact(
    artifact: OrdersV2SchemaAttestationArtifact,
) -> dict[str, object]:
    """Reconstruct the exact collector observation committed by the artifact."""

    return {
        "provenance_kind": "collector_observation_unattested",
        "evidence": artifact.evidence.model_dump(mode="json"),
        "client_project": artifact.project,
        "client_location": artifact.location,
        "metadata_row_count": 1,
        "attested_live_run": False,
        "production_blocker": UNATTESTED_COLLECTOR_BLOCKER,
    }


def _collector_observation_payload_fingerprint(
    payload: dict[str, object],
) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    evidence: OrdersV2InformationSchemaEvidence
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

    @model_validator(mode="after")
    def validate_embedded_evidence_binding(
        self,
    ) -> OrdersV2SchemaAttestationArtifact:
        evidence_fingerprint = validate_orders_v2_schema_evidence(
            self.evidence
        )
        if self.project != self.evidence.table_catalog:
            raise ValueError(
                "attestation project does not match embedded evidence"
            )
        if self.observed_at != self.evidence.observed_at.isoformat():
            raise ValueError(
                "attestation timestamp does not match embedded evidence"
            )
        if self.schema_evidence_fingerprint != evidence_fingerprint:
            raise ValueError("schema evidence fingerprint mismatch")
        if (
            self.collector_query_sha256
            != ORDERS_V2_SCHEMA_EVIDENCE_QUERY_SHA256
        ):
            raise ValueError("collector query fingerprint mismatch")
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
        expected_observation_fingerprint = (
            _collector_observation_payload_fingerprint(
                _collector_observation_payload_from_artifact(self)
            )
        )
        if (
            self.collector_observation_fingerprint
            != expected_observation_fingerprint
        ):
            raise ValueError("collector observation fingerprint mismatch")
        return self

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
    return _collector_observation_payload_fingerprint(
        observation.model_dump(mode="json")
    )


def build_orders_v2_schema_attestation_candidate(
    observation: OrdersV2CollectedSchemaObservation,
) -> OrdersV2SchemaAttestationArtifact:
    """Bind one collector observation to the exact reviewed code contracts."""

    if observation.attested_live_run is not False:
        raise ValueError(
            "collector observation attestation state is invalid"
        )
    if observation.production_blocker != UNATTESTED_COLLECTOR_BLOCKER:
        raise ValueError("collector observation blocker is invalid")
    if observation.metadata_row_count != 1:
        raise ValueError("collector observation row count is invalid")

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
        evidence=observation.evidence,
        schema_evidence_fingerprint=evidence_fingerprint,
        collector_query_sha256=ORDERS_V2_SCHEMA_EVIDENCE_QUERY_SHA256,
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
