"""Synthetic semantic proof harness for the blocked orders v2 candidate.

The harness exercises the intended conjunctive date + tenant + store semantics
against deterministic adversarial rows. It is deliberately labelled synthetic
and can never represent live BigQuery execution evidence.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.ai_orders_v2_bigquery_parameters import (
    orders_v2_bigquery_parameter_contract_fingerprint,
)
from app.core.ai_orders_v2_bigquery_sdk_adapter import (
    orders_v2_bigquery_sdk_adapter_fingerprint,
)
from app.core.ai_orders_v2_query_contract import (
    ORDERS_V2_CANDIDATE,
    validate_orders_v2_query_candidate,
    validate_orders_v2_runtime_parameters,
)

SYNTHETIC_PROOF_BLOCKER = "live_bigquery_cross_tenant_proof_missing"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


@dataclass(frozen=True)
class SyntheticOrderRow:
    partition_date_local: date
    entity_id: str
    vendor_name: str
    order_id: str


@dataclass(frozen=True)
class SyntheticProofCase:
    case_id: str
    start_date: date
    end_date: date
    entity_ids: tuple[str, ...]
    stores: tuple[str, ...]
    expected_order_ids: tuple[str, ...]


class OrdersV2SyntheticProofError(AssertionError):
    """The deterministic synthetic semantic matrix no longer holds."""


class OrdersV2SyntheticProofArtifact(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    proof_kind: Literal["synthetic_semantics_only"]
    candidate_template_fingerprint: str = Field(pattern=SHA256_PATTERN)
    parameter_contract_fingerprint: str = Field(pattern=SHA256_PATTERN)
    sdk_adapter_fingerprint: str = Field(pattern=SHA256_PATTERN)
    fixture_fingerprint: str = Field(pattern=SHA256_PATTERN)
    case_count: int = Field(ge=1)
    passed_case_ids: tuple[str, ...]
    live_bigquery_verified: Literal[False]
    production_blocker: Literal["live_bigquery_cross_tenant_proof_missing"]

    @property
    def proof_fingerprint(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def synthetic_orders_v2_fixture() -> tuple[SyntheticOrderRow, ...]:
    return (
        SyntheticOrderRow(
            date(2026, 8, 10),
            "TENANT_A",
            "Fulya",
            "A-F-1",
        ),
        SyntheticOrderRow(
            date(2026, 8, 10),
            "TENANT_A",
            "Fulya",
            "A-F-2",
        ),
        # Duplicate physical row proves COUNT(DISTINCT order_id) semantics.
        SyntheticOrderRow(
            date(2026, 8, 10),
            "TENANT_A",
            "Fulya",
            "A-F-2",
        ),
        SyntheticOrderRow(
            date(2026, 8, 10),
            "TENANT_B",
            "Fulya",
            "B-F-1",
        ),
        SyntheticOrderRow(
            date(2026, 8, 10),
            "TENANT_A",
            "Dicle",
            "A-D-1",
        ),
        SyntheticOrderRow(
            date(2026, 8, 10),
            "TENANT_B",
            "Dicle",
            "B-D-1",
        ),
        SyntheticOrderRow(
            date(2026, 7, 31),
            "TENANT_A",
            "Fulya",
            "A-F-OLD",
        ),
        # Exact string matching: this must not leak into a `Fulya` scope.
        SyntheticOrderRow(
            date(2026, 8, 10),
            "TENANT_A",
            "fulya",
            "A-f-lower",
        ),
    )


def synthetic_orders_v2_cases() -> tuple[SyntheticProofCase, ...]:
    return (
        SyntheticProofCase(
            case_id="tenant_a_fulya",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 12),
            entity_ids=("TENANT_A",),
            stores=("Fulya",),
            expected_order_ids=("A-F-1", "A-F-2"),
        ),
        SyntheticProofCase(
            case_id="tenant_b_fulya",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 12),
            entity_ids=("TENANT_B",),
            stores=("Fulya",),
            expected_order_ids=("B-F-1",),
        ),
        SyntheticProofCase(
            case_id="tenant_a_dicle",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 12),
            entity_ids=("TENANT_A",),
            stores=("Dicle",),
            expected_order_ids=("A-D-1",),
        ),
        SyntheticProofCase(
            case_id="explicit_multi_tenant_fulya",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 12),
            entity_ids=("TENANT_A", "TENANT_B"),
            stores=("Fulya",),
            expected_order_ids=("A-F-1", "A-F-2", "B-F-1"),
        ),
        SyntheticProofCase(
            case_id="date_exclusion",
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 10),
            entity_ids=("TENANT_A",),
            stores=("Fulya",),
            expected_order_ids=("A-F-1", "A-F-2"),
        ),
    )


def _fixture_fingerprint(rows: tuple[SyntheticOrderRow, ...]) -> str:
    payload = [
        {
            "partition_date_local": row.partition_date_local.isoformat(),
            "entity_id": row.entity_id,
            "vendor_name": row.vendor_name,
            "order_id": row.order_id,
        }
        for row in rows
    ]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evaluate_orders_v2_synthetic_scope(
    rows: tuple[SyntheticOrderRow, ...],
    *,
    start_date: date,
    end_date: date,
    entity_ids: tuple[str, ...],
    stores: tuple[str, ...],
) -> tuple[str, ...]:
    """Mirror only the candidate's deterministic filtering/distinct semantics."""

    validated = validate_orders_v2_runtime_parameters(
        {
            "start_date": start_date,
            "end_date": end_date,
            "entity_ids": entity_ids,
            "stores": stores,
        }
    )
    allowed_entities = set(validated["entity_ids"])
    allowed_stores = set(validated["stores"])
    start = validated["start_date"]
    end = validated["end_date"]
    if not isinstance(start, date) or not isinstance(end, date):
        raise OrdersV2SyntheticProofError("date preflight drift")

    selected = {
        row.order_id
        for row in rows
        if start <= row.partition_date_local <= end
        and row.entity_id in allowed_entities
        and row.vendor_name in allowed_stores
    }
    return tuple(sorted(selected))


def aggregate_orders_v2_synthetic_scope(
    rows: tuple[SyntheticOrderRow, ...],
    *,
    start_date: date,
    end_date: date,
    entity_ids: tuple[str, ...],
    stores: tuple[str, ...],
) -> tuple[tuple[date, str, int], ...]:
    """Mirror candidate GROUP BY date/vendor + COUNT(DISTINCT order_id)."""

    validated = validate_orders_v2_runtime_parameters(
        {
            "start_date": start_date,
            "end_date": end_date,
            "entity_ids": entity_ids,
            "stores": stores,
        }
    )
    allowed_entities = set(validated["entity_ids"])
    allowed_stores = set(validated["stores"])
    start = validated["start_date"]
    end = validated["end_date"]
    if not isinstance(start, date) or not isinstance(end, date):
        raise OrdersV2SyntheticProofError("date preflight drift")

    grouped: dict[tuple[date, str], set[str]] = defaultdict(set)
    for row in rows:
        if (
            start <= row.partition_date_local <= end
            and row.entity_id in allowed_entities
            and row.vendor_name in allowed_stores
        ):
            grouped[(row.partition_date_local, row.vendor_name)].add(row.order_id)

    result = [
        (row_date, store, len(order_ids))
        for (row_date, store), order_ids in grouped.items()
    ]
    return tuple(
        sorted(
            result,
            key=lambda item: (-item[0].toordinal(), -item[2], item[1]),
        )
    )


def run_orders_v2_synthetic_cross_tenant_proof() -> OrdersV2SyntheticProofArtifact:
    """Run the deterministic matrix and return a non-promoting proof artifact."""

    validate_orders_v2_query_candidate()
    rows = synthetic_orders_v2_fixture()
    cases = synthetic_orders_v2_cases()

    passed: list[str] = []
    for case in cases:
        actual = evaluate_orders_v2_synthetic_scope(
            rows,
            start_date=case.start_date,
            end_date=case.end_date,
            entity_ids=case.entity_ids,
            stores=case.stores,
        )
        if actual != case.expected_order_ids:
            raise OrdersV2SyntheticProofError(
                f"synthetic proof failed: {case.case_id}"
            )
        passed.append(case.case_id)

    return OrdersV2SyntheticProofArtifact(
        proof_kind="synthetic_semantics_only",
        candidate_template_fingerprint=(
            ORDERS_V2_CANDIDATE.template_fingerprint
        ),
        parameter_contract_fingerprint=(
            orders_v2_bigquery_parameter_contract_fingerprint()
        ),
        sdk_adapter_fingerprint=(
            orders_v2_bigquery_sdk_adapter_fingerprint()
        ),
        fixture_fingerprint=_fixture_fingerprint(rows),
        case_count=len(cases),
        passed_case_ids=tuple(passed),
        live_bigquery_verified=False,
        production_blocker=SYNTHETIC_PROOF_BLOCKER,
    )
