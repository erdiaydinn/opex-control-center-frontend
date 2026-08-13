from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

import app.cli.attest_orders_v2_schema as cli
from app.core.ai_orders_v2_live_schema_collector import (
    UNATTESTED_COLLECTOR_BLOCKER,
    OrdersV2CollectedSchemaObservation,
)
from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_orders_v2_schema_attestation import (
    SCHEMA_ATTESTATION_PROMOTION_BLOCKER,
    OrdersV2SchemaAttestationArtifact,
    build_orders_v2_schema_attestation_candidate,
)
from app.core.ai_orders_v2_schema_evidence import (
    build_orders_v2_information_schema_evidence,
)
from app.core.ai_query_contract_policy import AI_QUERY_CONTRACT_POLICIES


def observation() -> OrdersV2CollectedSchemaObservation:
    evidence = build_orders_v2_information_schema_evidence(
        row={
            "table_catalog": "example-project",
            "table_schema": "curated_data_shared_coredata_business",
            "table_name": "orders",
            "column_name": "entity",
            "field_path": "entity.id",
            "data_type": "STRING",
        },
        observed_at=datetime(2026, 8, 13, 6, 0, tzinfo=UTC),
    )
    return OrdersV2CollectedSchemaObservation(
        provenance_kind="collector_observation_unattested",
        evidence=evidence,
        client_project="example-project",
        client_location="EU",
        metadata_row_count=1,
        attested_live_run=False,
        production_blocker=UNATTESTED_COLLECTOR_BLOCKER,
    )


def test_attestation_candidate_is_reviewable_but_never_self_promoting() -> None:
    artifact = build_orders_v2_schema_attestation_candidate(
        observation()
    )

    assert artifact.kind == "live_bigquery_schema_attestation_candidate"
    assert artifact.project == "example-project"
    assert artifact.location == "EU"
    assert artifact.evidence.field_path == "entity.id"
    assert artifact.evidence.data_type == "STRING"
    assert artifact.live_collector_run_claimed is True
    assert artifact.cryptographically_attested is False
    assert artifact.promotion_eligible is False
    assert artifact.human_review_required is True
    assert artifact.production_blocker == (
        SCHEMA_ATTESTATION_PROMOTION_BLOCKER
    )
    assert len(artifact.schema_evidence_fingerprint) == 64
    assert len(artifact.collector_observation_fingerprint) == 64
    assert len(artifact.artifact_fingerprint) == 64

    active = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    assert active.contract_id == "ops.kpi.orders.v1"
    assert active.production_ready is False
    assert ORDERS_V2_CANDIDATE.schema_evidence_fingerprint is None


def test_attestation_rejects_promotion_and_embedded_evidence_tamper() -> None:
    artifact = build_orders_v2_schema_attestation_candidate(
        observation()
    )

    for field, value in (
        ("promotion_eligible", True),
        ("human_review_required", False),
        ("cryptographically_attested", True),
        ("production_blocker", ""),
    ):
        payload = artifact.model_dump(mode="python")
        payload[field] = value
        with pytest.raises(ValidationError):
            OrdersV2SchemaAttestationArtifact.model_validate(payload)

    payload = artifact.model_dump(mode="python")
    payload["project"] = "other-project"
    with pytest.raises(ValidationError):
        OrdersV2SchemaAttestationArtifact.model_validate(payload)

    payload = artifact.model_dump(mode="python")
    payload["schema_evidence_fingerprint"] = "f" * 64
    with pytest.raises(ValidationError):
        OrdersV2SchemaAttestationArtifact.model_validate(payload)

    payload = artifact.model_dump(mode="python")
    payload["collector_observation_fingerprint"] = "f" * 64
    with pytest.raises(ValidationError):
        OrdersV2SchemaAttestationArtifact.model_validate(payload)


def test_observation_rejects_noncanonical_row_count_at_typed_boundary() -> None:
    payload = observation().model_dump(mode="python")
    payload["metadata_row_count"] = 2

    with pytest.raises(ValidationError, match="metadata_row_count"):
        OrdersV2CollectedSchemaObservation.model_validate(payload)


def test_cli_requires_explicit_live_network_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def must_not_build(config):
        del config
        pytest.fail("client must not be constructed when attestation is disabled")

    monkeypatch.setattr(
        cli,
        "build_default_orders_v2_schema_client",
        must_not_build,
    )

    for environ in (
        {},
        {"EAY_BQ_SCHEMA_ATTESTATION_ENABLED": "false"},
        {"EAY_BQ_SCHEMA_ATTESTATION_ENABLED": "1"},
    ):
        with pytest.raises(cli.OrdersV2SchemaAttestationDisabled):
            cli.run_orders_v2_schema_attestation(environ)


def test_cli_enabled_path_uses_canonical_config_and_collector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}
    fake_client = object()

    def build_client(config):
        calls["config"] = config
        return fake_client

    def collect(*, client, config):
        calls["client"] = client
        calls["collect_config"] = config
        return observation()

    monkeypatch.setattr(
        cli,
        "build_default_orders_v2_schema_client",
        build_client,
    )
    monkeypatch.setattr(
        cli,
        "collect_orders_v2_schema_observation",
        collect,
    )

    artifact = cli.run_orders_v2_schema_attestation(
        {
            "EAY_BQ_SCHEMA_ATTESTATION_ENABLED": " TRUE ",
            "EAY_BQ_PROJECT": "example-project",
            "EAY_BQ_LOCATION": "EU",
        }
    )

    assert calls["client"] is fake_client
    assert calls["config"] == calls["collect_config"]
    assert artifact.project == "example-project"
    assert artifact.promotion_eligible is False


def test_rendered_artifact_contains_reviewable_metadata_but_no_credentials() -> None:
    rendered = cli.render_orders_v2_schema_attestation(
        build_orders_v2_schema_attestation_candidate(observation())
    )
    parsed = json.loads(rendered)

    assert len(parsed["artifact_fingerprint"]) == 64
    assert parsed["artifact"]["evidence"]["field_path"] == "entity.id"
    assert parsed["artifact"]["evidence"]["data_type"] == "STRING"
    assert parsed["artifact"]["promotion_eligible"] is False
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in rendered
    assert "private_key" not in rendered
    assert "access_token" not in rendered
