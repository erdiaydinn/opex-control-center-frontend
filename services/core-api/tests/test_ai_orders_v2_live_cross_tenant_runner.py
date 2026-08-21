from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest

from app.core.ai_data_scope import AiDataScope, ai_data_scope_fingerprint
from app.core.ai_orders_v2_live_cross_tenant_runner import (
    LIVE_PROOF_MAXIMUM_BYTES_BILLED,
    LIVE_PROOF_TIMEOUT_SECONDS,
    OrdersV2LiveProofError,
    OrdersV2LiveProofSentinels,
    OrdersV2LiveProofWindow,
    run_orders_v2_live_cross_tenant_proof,
)
from app.core.ai_orders_v2_live_schema_collector import (
    UNATTESTED_COLLECTOR_BLOCKER,
    OrdersV2CollectedSchemaObservation,
)
from app.core.ai_orders_v2_schema_attestation import build_orders_v2_schema_attestation_candidate
from app.core.ai_orders_v2_schema_evidence import build_orders_v2_information_schema_evidence
from app.core.ai_tenant_query_context import (
    AiTenantQueryContext,
    AiTenantQueryContextRecord,
    ai_tenant_query_context_fingerprint,
)
from app.core.ai_tool_authorization import AiToolCapability

TENANT_ID = UUID("00000000-0000-0000-0000-000000000111")


class FakeJob:
    def __init__(self, job_id: str, rows: list[dict[str, Any]]) -> None:
        self.job_id = job_id
        self.rows = rows
        self.timeouts: list[float | None] = []

    def result(self, *, timeout: float | None = None):
        self.timeouts.append(timeout)
        return list(self.rows)


class FakeClient:
    project = "example-project"
    location = "EU"

    def __init__(self, rowsets: list[list[dict[str, Any]]]) -> None:
        self.rowsets = list(rowsets)
        self.calls: list[dict[str, Any]] = []
        self.jobs: list[FakeJob] = []

    def query(self, query: str, *, job_config: Any, location=None):
        job = FakeJob(f"job-{len(self.calls) + 1}", self.rowsets.pop(0))
        self.jobs.append(job)
        self.calls.append({"query": query, "job_config": job_config, "location": location})
        return job


def _attestation():
    observed_at = datetime(2026, 8, 13, 20, 0, tzinfo=UTC)
    evidence = build_orders_v2_information_schema_evidence(
        row={
            "table_catalog": "example-project",
            "table_schema": "curated_data_shared_coredata_business",
            "table_name": "orders",
            "column_name": "entity",
            "field_path": "entity.id",
            "data_type": "STRING",
        },
        observed_at=observed_at,
    )
    observation = OrdersV2CollectedSchemaObservation(
        provenance_kind="collector_observation_unattested",
        evidence=evidence,
        client_project="example-project",
        client_location="EU",
        metadata_row_count=1,
        attested_live_run=False,
        production_blocker=UNATTESTED_COLLECTOR_BLOCKER,
    )
    return build_orders_v2_schema_attestation_candidate(observation)


def _authority():
    scope = AiDataScope(version=1, store_names=("Fulya",))
    capability = AiToolCapability(
        tenant_id=TENANT_ID,
        actor_subject="employee:test",
        tool="ops_kpi_query",
        granted_scopes=("ops:read",),
        permission_keys=("ai_assistant.executeOpsRead",),
        authorizing_roles=("ops_manager",),
        data_scope=scope,
        data_scope_fingerprint=ai_data_scope_fingerprint(scope),
        authorization_fingerprint="a" * 64,
    )
    context = AiTenantQueryContext(
        version=1,
        entity_ids=("YS_TR",),
        source_reference="approved production tenant mapping",
    )
    record = AiTenantQueryContextRecord(
        tenant_id=str(TENANT_ID),
        context=context,
        record_fingerprint=ai_tenant_query_context_fingerprint(context),
        updated_by="super-admin:test",
    )
    return capability, record


def _window():
    return OrdersV2LiveProofWindow(date(2026, 8, 12), date(2026, 8, 13))


def _sentinels():
    return OrdersV2LiveProofSentinels(
        foreign_entity_id="FOREIGN_REAL",
        foreign_store="Foreign Real Store",
        foreign_entity_known_to_exist=True,
        foreign_store_known_to_exist=True,
    )


def test_live_runner_uses_authoritative_platform_scope() -> None:
    capability, context = _authority()
    client = FakeClient(
        [[{"date": date(2026, 8, 13), "vendor_name": "Fulya", "orders": 2}], [], []]
    )
    artifact = run_orders_v2_live_cross_tenant_proof(
        client=client,
        schema_attestation=_attestation(),
        capability=capability,
        tenant_query_context=context,
        window=_window(),
        sentinels=_sentinels(),
        executed_at=datetime(2026, 8, 13, 21, 0, tzinfo=UTC),
    )
    assert len(client.calls) == 3
    assert all(call["location"] == "EU" for call in client.calls)
    assert all(
        call["job_config"].maximum_bytes_billed == LIVE_PROOF_MAXIMUM_BYTES_BILLED
        for call in client.calls
    )
    assert all(call["job_config"].use_query_cache is False for call in client.calls)
    assert all(job.timeouts == [LIVE_PROOF_TIMEOUT_SECONDS] for job in client.jobs)
    assert artifact.foreign_sentinel_match_count == 0
    assert artifact.promotion_eligible is False
    serialized = artifact.model_dump_json()
    for raw_value in ("YS_TR", "Fulya", "FOREIGN_REAL", "job-1"):
        assert raw_value not in serialized


def test_live_runner_rejects_authority_mismatch() -> None:
    capability, context = _authority()
    wrong_context = AiTenantQueryContextRecord(
        tenant_id=str(UUID("00000000-0000-0000-0000-000000000222")),
        context=context.context,
        record_fingerprint=context.record_fingerprint,
        updated_by=context.updated_by,
    )
    with pytest.raises(OrdersV2LiveProofError, match="capability and tenant"):
        run_orders_v2_live_cross_tenant_proof(
            client=FakeClient([]),
            schema_attestation=_attestation(),
            capability=capability,
            tenant_query_context=wrong_context,
            window=_window(),
            sentinels=_sentinels(),
        )


def test_live_runner_fails_on_foreign_result() -> None:
    capability, context = _authority()
    client = FakeClient(
        [
            [{"date": date(2026, 8, 13), "vendor_name": "Fulya", "orders": 2}],
            [{"date": date(2026, 8, 13), "vendor_name": "Foreign Real Store", "orders": 1}],
            [],
        ]
    )
    with pytest.raises(OrdersV2LiveProofError, match="cross-tenant leakage"):
        run_orders_v2_live_cross_tenant_proof(
            client=client,
            schema_attestation=_attestation(),
            capability=capability,
            tenant_query_context=context,
            window=_window(),
            sentinels=_sentinels(),
        )
