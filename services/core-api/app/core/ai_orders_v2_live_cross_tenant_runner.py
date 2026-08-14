"""Controlled live BigQuery runner for Orders V2 production evidence.

This is an explicit, non-HTTP acceptance tool. It executes only the frozen
Orders V2 SQL through the reviewed typed SDK adapter and returns the existing
privacy-minimized #53 evidence artifact. Authorized entity/store scope is
accepted only from existing server-authoritative Platform Core objects; the
operator may choose only the proof window and controlled foreign sentinels.
It never mutates policy state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol
from uuid import UUID

from app.core.ai_data_scope import ai_data_scope_fingerprint
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
from app.core.ai_tenant_query_context import (
    AiTenantQueryContextRecord,
    ai_tenant_query_context_fingerprint,
)
from app.core.ai_tool_authorization import AiToolCapability

LIVE_PROOF_TIMEOUT_SECONDS = 60
LIVE_PROOF_MAXIMUM_BYTES_BILLED = 1_000_000_000
LIVE_PROOF_MAX_AUTHORIZED_STORES = 200


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
class OrdersV2LiveProofWindow:
    start_date: date
    end_date: date


@dataclass(frozen=True)
class OrdersV2LiveProofSentinels:
    foreign_entity_id: str
    foreign_store: str
    foreign_entity_known_to_exist: bool
    foreign_store_known_to_exist: bool


def _validate_authority(
    *,
    capability: AiToolCapability,
    tenant_query_context: AiTenantQueryContextRecord,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if capability.tool != "ops_kpi_query":
        raise OrdersV2LiveProofError("live proof requires ops_kpi_query capability")

    expected_scope_fingerprint = ai_data_scope_fingerprint(capability.data_scope)
    if capability.data_scope_fingerprint != expected_scope_fingerprint:
        raise OrdersV2LiveProofError("data scope authority fingerprint mismatch")

    expected_context_fingerprint = ai_tenant_query_context_fingerprint(
        tenant_query_context.context
    )
    if tenant_query_context.record_fingerprint != expected_context_fingerprint:
        raise OrdersV2LiveProofError("tenant query context fingerprint mismatch")

    if str(capability.tenant_id) != tenant_query_context.tenant_id:
        raise OrdersV2LiveProofError("capability and tenant query context mismatch")

    entity_ids = tuple(tenant_query_context.context.entity_ids)
    stores = tuple(capability.data_scope.store_names)
    if not entity_ids:
        raise OrdersV2LiveProofError("authoritative entity scope is empty")
    if not stores:
        raise OrdersV2LiveProofError("authoritative store scope is empty")
    if len(stores) > LIVE_PROOF_MAX_AUTHORIZED_STORES:
        raise OrdersV2LiveProofError(
            "authoritative store scope exceeds reviewed Orders V2 parameter bound"
        )
    return entity_ids, stores


def _validate_sentinels(
    *,
    sentinels: OrdersV2LiveProofSentinels,
    authorized_entity_ids: tuple[str, ...],
    authorized_stores: tuple[str, ...],
) -> None:
    if not sentinels.foreign_entity_known_to_exist:
        raise OrdersV2LiveProofError("foreign entity existence is unproven")
    if not sentinels.foreign_store_known_to_exist:
        raise OrdersV2LiveProofError("foreign store existence is unproven")

    entity_keys = {value.casefold() for value in authorized_entity_ids}
    store_keys = {value.casefold() for value in authorized_stores}
    if sentinels.foreign_entity_id.casefold() in entity_keys:
        raise OrdersV2LiveProofError("foreign entity is inside authorized scope")
    if sentinels.foreign_store.casefold() in store_keys:
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
        rows = _canonical_rows(job.result(timeout=LIVE_PROOF_TIMEOUT_SECONDS))
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
    capability: AiToolCapability,
    tenant_query_context: AiTenantQueryContextRecord,
    window: OrdersV2LiveProofWindow,
    sentinels: OrdersV2LiveProofSentinels,
    executed_at: datetime | None = None,
) -> OrdersV2LiveCrossTenantEvidence:
    """Run positive, foreign-store and foreign-entity controls.

    Security-sensitive positive scope is derived only from the existing
    server-authoritative capability and tenant query-context records. The
    operator cannot pass entity_ids or stores into this function.
    """

    authorized_entity_ids, authorized_stores = _validate_authority(
        capability=capability,
        tenant_query_context=tenant_query_context,
    )
    _validate_sentinels(
        sentinels=sentinels,
        authorized_entity_ids=authorized_entity_ids,
        authorized_stores=authorized_stores,
    )

    if client.project != schema_attestation.project:
        raise OrdersV2LiveProofError("client project does not match attestation")
    if client.location != schema_attestation.location:
        raise OrdersV2LiveProofError("client location does not match attestation")

    shared = {
        "start_date": window.start_date,
        "end_date": window.end_date,
    }
    positive_job, positive_rows = _run_control(
        client=client,
        location=schema_attestation.location,
        parameters={
            **shared,
            "entity_ids": authorized_entity_ids,
            "stores": authorized_stores,
        },
    )
    if not positive_rows:
        raise OrdersV2LiveProofError("authorized positive control is empty")
    if any(
        str(row["vendor_name"]).casefold()
        not in {store.casefold() for store in authorized_stores}
        for row in positive_rows
    ):
        raise OrdersV2LiveProofError("authorized control returned foreign store")

    foreign_store_job, foreign_store_rows = _run_control(
        client=client,
        location=schema_attestation.location,
        parameters={
            **shared,
            "entity_ids": authorized_entity_ids,
            "stores": (sentinels.foreign_store,),
        },
    )
    foreign_entity_job, foreign_entity_rows = _run_control(
        client=client,
        location=schema_attestation.location,
        parameters={
            **shared,
            "entity_ids": (sentinels.foreign_entity_id,),
            "stores": authorized_stores,
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
            "tenant_id": str(UUID(tenant_query_context.tenant_id)),
            "data_scope_fingerprint": capability.data_scope_fingerprint,
            "tenant_query_context_fingerprint": tenant_query_context.record_fingerprint,
            "entity_ids": list(authorized_entity_ids),
            "stores": list(authorized_stores),
            "start_date": window.start_date.isoformat(),
            "end_date": window.end_date.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    foreign_scope = json.dumps(
        {
            "foreign_entity_id": sentinels.foreign_entity_id,
            "foreign_store": sentinels.foreign_store,
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
