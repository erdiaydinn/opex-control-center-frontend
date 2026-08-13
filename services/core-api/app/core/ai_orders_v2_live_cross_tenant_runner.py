"""Controlled live BigQuery runner for Orders V2 production evidence.

This is an explicit, non-HTTP acceptance tool. It executes only the frozen
Orders V2 SQL through the reviewed typed SDK adapter and returns the existing
privacy-minimized #53 evidence artifact. It never mutates policy state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol

from app.core.ai_orders_v2_bigquery_sdk_adapter import (
    build_orders_v2_bigquery_job_config,
)
from app.core.ai_orders_v2_live_cross_tenant_evidence import (
    OrdersV2LiveCrossTenantEvidence,
    build_orders_v2_live_cross_tenant_evidence_candidate,
)
from app.core.ai_orders_v2_query_contract import ORDERS_V2_SQL
from app.core.ai_orders_v2_schema_attestation import (
    OrdersV2SchemaAttestationArtifact,
)

LIVE_PROOF_TIMEOUT_SECONDS = 60
LIVE_PROOF_MAXIMUM_BYTES_BILLED = 1_000_000_000


class OrdersV2LiveProofError(RuntimeError):
    """A controlled live proof did not meet its fail-closed contract."""


class _QueryJob(Protocol):
    job_id: str

    def result(self, *, timeout: float | None = None) -> Any: ...


class _BigQueryClient(Protocol):
    project: str
    location: str | None

    def query(
        self,
        query: str,
        *,
        job_config: Any,
        location: str | None = None,
    ) -> _QueryJob: ...


@dataclass(frozen=True)
class OrdersV2LiveProofScopes:
    start_date: date
    end_date: date
    authorized_entity_ids: tuple[str, ...]
    authorized_stores: tuple[str, ...]
    foreign_entity_id: str
    foreign_store: str
    foreign_entity_known_to_exist: bool
    foreign_store_known_to_exist: bool

    def validate(self) -> None:
        if not self.foreign_entity_known_to_exist:
            raise OrdersV2LiveProofError("foreign entity existence is unproven")
        if not self.foreign_store_known_to_exist:
            raise OrdersV2LiveProofError("foreign store existence is unproven")
        if self.foreign_entity_id in self.authorized_entity_ids:
            raise OrdersV2LiveProofError("foreign entity is inside authorized scope")
        if self.foreign_store in self.authorized_stores:
            raise OrdersV2LiveProofError("foreign store is inside authorized scope")


def _canonical_rows(rows: Any) -> tuple[dict[str, object], ...]:
    materialized = tuple(rows)
    canonical: list[dict[str, object]] = []
    for row in materialized:
        values = dict(row.items()) if hasattr(row, "items") else dict(row)
        if set(values) != {"date", "vendor_name", "orders"}:
            raise OrdersV2LiveProofError("unexpected Orders V2 result columns")
        day = values["date"]
        vendor = values["vendor_name"]
        orders = values["orders"]
        if not isinstance(day, date) or isinstance(day, datetime):
            raise OrdersV2LiveProofError("unexpected Orders V2 date value")
        if not isinstance(vendor, str) or not vendor:
            raise OrdersV2LiveProofError("unexpected Orders V2 store value")
        if not isinstance(orders, int) or isinstance(orders, bool) or orders < 0:
            raise OrdersV2LiveProofError("unexpected Orders V2 order count")
        canonical.append(
            {"date": day.isoformat(), "vendor_name": vendor, "orders": orders}
        )
    canonical.sort(key=lambda item: (str(item["date"]), str(item["vendor_name"])))
    return tuple(canonical)


def _run_control(
    *,
    client: _BigQueryClient,
    location: str | None,
    parameters: dict[str, object],
) -> tuple[str, tuple[dict[str, object], ...]]:
    job_config = build_orders_v2_bigquery_job_config(parameters)
    job_config.maximum_bytes_billed = LIVE_PROOF_MAXIMUM_BYTES_BILLED
    job_config.use_query_cache = False
    try:
        job = client.query(
            ORDERS_V2_SQL,
            job_config=job_config,
            location=location,
        )
        rows = _canonical_rows(
            job.result(timeout=LIVE_PROOF_TIMEOUT_SECONDS)
        )
    except OrdersV2LiveProofError:
        raise
    except Exception as exc:
        raise OrdersV2LiveProofError("live BigQuery control failed") from exc

    job_id = str(getattr(job, "job_id", "") or "").strip()
    if not job_id:
        raise OrdersV2LiveProofError("BigQuery job id is missing")
    return job_id, rows


def run_orders_v2_live_cross_tenant_proof(
    *,
    client: _BigQueryClient,
    schema_attestation: OrdersV2SchemaAttestationArtifact,
    scopes: OrdersV2LiveProofScopes,
    executed_at: datetime | None = None,
) -> OrdersV2LiveCrossTenantEvidence:
    """Run positive, foreign-store and foreign-entity controls."""

    scopes.validate()
    if client.project != schema_attestation.project:
        raise OrdersV2LiveProofError("client project does not match attestation")
    if client.location != schema_attestation.location:
        raise OrdersV2LiveProofError("client location does not match attestation")

    shared = {
        "start_date": scopes.start_date,
        "end_date": scopes.end_date,
    }
    positive_job, positive_rows = _run_control(
        client=client,
        location=schema_attestation.location,
        parameters={
            **shared,
            "entity_ids": scopes.authorized_entity_ids,
            "stores": scopes.authorized_stores,
        },
    )
    if not positive_rows:
        raise OrdersV2LiveProofError("authorized positive control is empty")
    if any(
        str(row["vendor_name"]) not in scopes.authorized_stores
        for row in positive_rows
    ):
        raise OrdersV2LiveProofError("authorized control returned foreign store")

    foreign_store_job, foreign_store_rows = _run_control(
        client=client,
        location=schema_attestation.location,
        parameters={
            **shared,
            "entity_ids": scopes.authorized_entity_ids,
            "stores": (scopes.foreign_store,),
        },
    )
    foreign_entity_job, foreign_entity_rows = _run_control(
        client=client,
        location=schema_attestation.location,
        parameters={
            **shared,
            "entity_ids": (scopes.foreign_entity_id,),
            "stores": scopes.authorized_stores,
        },
    )
    foreign_matches = len(foreign_store_rows) + len(foreign_entity_rows)
    if foreign_matches:
        raise OrdersV2LiveProofError("cross-tenant leakage detected")

    job_ids = json.dumps(
        [positive_job, foreign_store_job, foreign_entity_job],
        separators=(",", ":"),
    )
    authorized_scope = json.dumps(
        {
            "entity_ids": list(scopes.authorized_entity_ids),
            "stores": list(scopes.authorized_stores),
            "start_date": scopes.start_date.isoformat(),
            "end_date": scopes.end_date.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    foreign_scope = json.dumps(
        {
            "foreign_entity_id": scopes.foreign_entity_id,
            "foreign_store": scopes.foreign_store,
            "existence_verified": True,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    canonical_rowset = json.dumps(
        positive_rows,
        sort_keys=True,
        separators=(",", ":"),
    )
    return build_orders_v2_live_cross_tenant_evidence_candidate(
        schema_attestation=schema_attestation,
        executed_at=executed_at or datetime.now(UTC),
        query_job_id=job_ids,
        authorized_scope_descriptor=authorized_scope,
        foreign_sentinel_scope_descriptor=foreign_scope,
        canonical_returned_rowset=canonical_rowset,
        foreign_sentinel_match_count=0,
    )
