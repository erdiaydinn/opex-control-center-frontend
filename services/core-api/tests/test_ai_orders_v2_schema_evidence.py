from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.ai_orders_v2_query_contract import ORDERS_V2_CANDIDATE
from app.core.ai_orders_v2_schema_evidence import (
    ORDERS_V2_SCHEMA_EVIDENCE_QUERY,
    ORDERS_V2_SCHEMA_EVIDENCE_QUERY_SHA256,
    OrdersV2InformationSchemaEvidence,
    OrdersV2SchemaEvidenceError,
    build_orders_v2_information_schema_evidence,
    orders_v2_schema_result_row_fingerprint,
    validate_orders_v2_schema_evidence,
)
from app.core.ai_query_contract_policy import AI_QUERY_CONTRACT_POLICIES


def metadata_row() -> dict[str, str]:
    return {
        "table_catalog": "example-project",
        "table_schema": "curated_data_shared_coredata_business",
        "table_name": "orders",
        "column_name": "entity",
        "field_path": "entity.id",
        "data_type": "STRING",
    }


def observed_at() -> datetime:
    return datetime(2026, 8, 13, 3, 30, tzinfo=UTC)


def test_collector_query_is_fixed_explicit_and_parameterized() -> None:
    lowered = ORDERS_V2_SCHEMA_EVIDENCE_QUERY.lower()

    assert "select *" not in lowered
    assert "information_schema.column_field_paths" in lowered
    assert "table_name = @table_name" in lowered
    assert "field_path = @field_path" in lowered
    assert "@table_catalog" not in lowered
    assert len(ORDERS_V2_SCHEMA_EVIDENCE_QUERY_SHA256) == 64


def test_synthetic_metadata_row_can_validate_contract_consistency_only() -> None:
    evidence = build_orders_v2_information_schema_evidence(
        row=metadata_row(),
        observed_at=observed_at(),
    )
    fingerprint = validate_orders_v2_schema_evidence(evidence)

    assert evidence.source_view == "INFORMATION_SCHEMA.COLUMN_FIELD_PATHS"
    assert evidence.field_path == (
        ORDERS_V2_CANDIDATE.tenant_discriminator_expression
    )
    assert evidence.data_type == "STRING"
    assert len(evidence.result_row_sha256) == 64
    assert len(evidence.evidence_fingerprint) == 64
    assert fingerprint == evidence.evidence_fingerprint

    # Contract consistency is not live provenance. Promotion remains blocked.
    active = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    assert active.contract_id == "ops.kpi.orders.v1"
    assert active.production_ready is False
    assert ORDERS_V2_CANDIDATE.schema_evidence_fingerprint is None


def test_metadata_row_fingerprint_rejects_missing_extra_and_nontext_values() -> None:
    missing = metadata_row()
    del missing["data_type"]
    with pytest.raises(
        OrdersV2SchemaEvidenceError,
        match="unexpected columns",
    ):
        orders_v2_schema_result_row_fingerprint(missing)

    extra = metadata_row()
    extra["description"] = "tenant entity identifier"
    with pytest.raises(
        OrdersV2SchemaEvidenceError,
        match="unexpected columns",
    ):
        orders_v2_schema_result_row_fingerprint(extra)

    nontext: dict[str, object] = dict(metadata_row())
    nontext["data_type"] = 123
    with pytest.raises(
        OrdersV2SchemaEvidenceError,
        match="values must be text",
    ):
        orders_v2_schema_result_row_fingerprint(nontext)


def test_evidence_rejects_wrong_table_field_type_and_view() -> None:
    mutations = (
        {"table_schema": "curated_data_shared"},
        {"table_name": "other_orders"},
        {"column_name": "tenant"},
        {"field_path": "tenant.id"},
        {"data_type": "INT64"},
    )

    for mutation in mutations:
        row = metadata_row()
        row.update(mutation)
        with pytest.raises((ValidationError, OrdersV2SchemaEvidenceError)):
            build_orders_v2_information_schema_evidence(
                row=row,
                observed_at=observed_at(),
            )

    valid = build_orders_v2_information_schema_evidence(
        row=metadata_row(),
        observed_at=observed_at(),
    )
    payload = valid.model_dump(mode="python")
    payload["source_view"] = "INFORMATION_SCHEMA.COLUMNS"
    with pytest.raises(ValidationError):
        OrdersV2InformationSchemaEvidence.model_validate(payload)


def test_evidence_rejects_naive_time_and_fingerprint_tamper() -> None:
    with pytest.raises(ValidationError):
        build_orders_v2_information_schema_evidence(
            row=metadata_row(),
            observed_at=datetime(2026, 8, 13, 3, 30),
        )

    valid = build_orders_v2_information_schema_evidence(
        row=metadata_row(),
        observed_at=observed_at(),
    )

    for field in ("collector_query_sha256", "result_row_sha256"):
        payload = valid.model_dump(mode="python")
        payload[field] = "f" * 64
        with pytest.raises(ValidationError):
            OrdersV2InformationSchemaEvidence.model_validate(payload)


def test_evidence_rejects_unsafe_catalog_and_extra_fields() -> None:
    for catalog in (
        " example-project",
        "example project",
        "example-project`",
        "example-project;DROP",
    ):
        row = metadata_row()
        row["table_catalog"] = catalog
        with pytest.raises(ValidationError):
            build_orders_v2_information_schema_evidence(
                row=row,
                observed_at=observed_at(),
            )

    valid = build_orders_v2_information_schema_evidence(
        row=metadata_row(),
        observed_at=observed_at(),
    )
    payload = valid.model_dump(mode="python")
    payload["trusted"] = True
    with pytest.raises(ValidationError):
        OrdersV2InformationSchemaEvidence.model_validate(payload)


def test_evidence_fingerprint_changes_with_project_or_observation() -> None:
    first = build_orders_v2_information_schema_evidence(
        row=metadata_row(),
        observed_at=observed_at(),
    )

    second_row = metadata_row()
    second_row["table_catalog"] = "other-project"
    second = build_orders_v2_information_schema_evidence(
        row=second_row,
        observed_at=observed_at(),
    )

    third = build_orders_v2_information_schema_evidence(
        row=metadata_row(),
        observed_at=datetime(2026, 8, 13, 3, 31, tzinfo=UTC),
    )

    assert first.evidence_fingerprint != second.evidence_fingerprint
    assert first.evidence_fingerprint != third.evidence_fingerprint
