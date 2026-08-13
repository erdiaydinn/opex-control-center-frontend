from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.core.ai_orders_v2_live_cross_tenant_runner import (
    LIVE_PROOF_MAXIMUM_BYTES_BILLED,
    LIVE_PROOF_TIMEOUT_SECONDS,
    OrdersV2LiveProofError,
    OrdersV2LiveProofScopes,
    run_orders_v2_live_cross_tenant_proof,
)
from app.core.ai_orders_v2_live_schema_collector import (
    UNATTESTED_COLLECTOR_BLOCKER,
    OrdersV2CollectedSchemaObservation,
)
from app.core.ai_orders_v2_schema_attestation import (
    build_orders_v2_schema_attestation_candidate,
)
from app.core.ai_orders_v2_schema_evidence import (
    build_orders_v2_information_schema_evidence,
)


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
        self.calls.append(
            {"query": query, "job_config": job_config, "location": location}
        )
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


def _scopes(**changes):
    values = {
        "start_date": date(2026, 8, 12),
        "end_date": date(2026, 8, 13),
        "authorized_entity_ids": ("YS_TR",),
        "authorized_stores": ("Fulya",),
        "foreign_entity_id": "FOREIGN_REAL",
        "foreign_store": "Foreign Real Store",
        "foreign_entity_known_to_exist": True,
        "foreign_store_known_to_exist": True,
    }
    values.update(changes)
    return OrdersV2LiveProofScopes(**values)


def test_runner_executes_exact_three_bounded_controls() -> None:
    client = FakeClient(
        [
            [{"date": date(2026, 8, 13), "vendor_name": "Fulya", "orders": 2}],
            [],
            [],
        ]
    )
    artifact = run_orders_v2_live_cross_tenant_proof(
        client=client,
        schema_attestation=_attestation(),
        scopes=_scopes(),
        executed_at=datetime(2026, 8, 13, 21, 0, tzinfo=UTC),
    )

    assert len(client.calls) == 3
    assert all(call["location"] == "EU" for call in client.calls)
    assert all(
        call["job_config"].maximum_bytes_billed
        == LIVE_PROOF_MAXIMUM_BYTES_BILLED
        for call in client.calls
    )
    assert all(call["job_config"].use_query_cache is False for call in client.calls)
    assert all(job.timeouts == [LIVE_PROOF_TIMEOUT_SECONDS] for job in client.jobs)
    assert artifact.foreign_sentinel_match_count == 0
    assert artifact.promotion_eligible is False
    rendered = artifact.model_dump_json()
    assert "YS_TR" not in rendered
    assert "Fulya" not in rendered
    assert "FOREIGN_REAL" not in rendered
    assert "job-1" not in rendered


@pytest.mark.parametrize(
    "rowsets,match",
    [
        ([[], [], []], "positive control is empty"),
        (
            [
                [{"date": date(2026, 8, 13), "vendor_name": "Other", "orders": 1}],
                [],
                [],
            ],
            "foreign store",
        ),
        (
            [
                [{"date": date(2026, 8, 13), "vendor_name": "Fulya", "orders": 2}],
                [{"date": date(2026, 8, 13), "vendor_name": "Foreign", "orders": 1}],
                [],
            ],
            "leakage",
        ),
    ],
)
def test_runner_fails_closed_on_invalid_controls(rowsets, match) -> None:
    with pytest.raises(OrdersV2LiveProofError, match=match):
        run_orders_v2_live_cross_tenant_proof(
            client=FakeClient(rowsets),
            schema_attestation=_attestation(),
            scopes=_scopes(),
        )


def test_runner_rejects_unverified_or_overlapping_sentinels() -> None:
    for scopes in (
        _scopes(foreign_entity_known_to_exist=False),
        _scopes(foreign_store_known_to_exist=False),
        _scopes(foreign_entity_id="YS_TR"),
        _scopes(foreign_store="Fulya"),
    ):
        with pytest.raises(OrdersV2LiveProofError):
            run_orders_v2_live_cross_tenant_proof(
                client=FakeClient([]),
                schema_attestation=_attestation(),
                scopes=scopes,
            )
