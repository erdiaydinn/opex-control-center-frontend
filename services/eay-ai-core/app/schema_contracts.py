from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Protocol

from .kpi_registry import get_kpi_definition
from .kpi_schema_evidence import KpiSchemaEvidence, verify_schema_evidence


@dataclass(frozen=True)
class ColumnContract:
    name: str
    field_type: str


@dataclass(frozen=True)
class TableSchemaContract:
    contract_id: str
    table_id: str
    required_columns: tuple[ColumnContract, ...]
    evidence_fingerprint: str | None = None

    @property
    def expected_fingerprint(self) -> str:
        return _fingerprint({column.name: column.field_type for column in self.required_columns})


class SchemaIntrospector(Protocol):
    def table_schema(self, table_id: str) -> Mapping[str, str]: ...


SCHEMA_CONTRACTS: dict[str, TableSchemaContract] = {
    "ops.orders.v1": TableSchemaContract(
        contract_id="ops.orders.v1",
        table_id="curated_data_shared_coredata_business.orders",
        required_columns=(
            ColumnContract("order_id", "STRING"),
            ColumnContract("partition_date_local", "DATE"),
            ColumnContract("vendor_name", "STRING"),
        ),
    ),
}


def _canonical_projection(schema: Mapping[str, str], names: set[str] | None = None) -> dict[str, str]:
    normalized = {str(name).lower(): str(field_type).upper() for name, field_type in schema.items()}
    if names is None:
        return dict(sorted(normalized.items()))
    return {name: normalized[name] for name in sorted(names) if name in normalized}


def _fingerprint(schema: Mapping[str, str]) -> str:
    payload = json.dumps(_canonical_projection(schema), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def schema_contract_from_reviewed_evidence(
    *,
    contract_id: str,
    expected_table: str,
    evidence: KpiSchemaEvidence,
    required_columns: tuple[str, ...],
) -> TableSchemaContract:
    """Create an immutable contract only from human-reviewed schema evidence.

    This helper deliberately does not mutate ``SCHEMA_CONTRACTS``. Activation remains a
    separate reviewed code change, while the evidence fingerprint permanently binds the
    resulting contract to the observation from which its BigQuery types were pinned.
    """

    if not contract_id.strip():
        raise ValueError("schema_contract_id_required")
    if not expected_table.strip():
        raise ValueError("schema_contract_expected_table_required")
    verified = verify_schema_evidence(
        evidence,
        expected_table=expected_table,
        required_columns=required_columns,
    )
    column_types = verified["column_types"]
    assert isinstance(column_types, dict)
    return TableSchemaContract(
        contract_id=contract_id,
        table_id=expected_table,
        required_columns=tuple(
            ColumnContract(name, str(column_types[name]).upper()) for name in required_columns
        ),
        evidence_fingerprint=str(verified["fingerprint"]),
    )


def get_schema_contract(contract_id: str) -> TableSchemaContract:
    contract = SCHEMA_CONTRACTS.get(contract_id)
    if contract is None:
        raise ValueError(f"unknown_schema_contract:{contract_id}")
    return contract


def verify_table_schema(contract: TableSchemaContract, observed_schema: Mapping[str, str]) -> dict[str, object]:
    expected = {column.name: column.field_type for column in contract.required_columns}
    observed = _canonical_projection(observed_schema)
    missing = sorted(set(expected) - set(observed))
    type_mismatches = {
        name: {"expected": expected[name], "observed": observed[name]}
        for name in sorted(set(expected) & set(observed))
        if observed[name] != expected[name]
    }
    selected_observed = _canonical_projection(observed, set(expected))
    observed_fingerprint = _fingerprint(selected_observed)
    expected_fingerprint = contract.expected_fingerprint
    if missing or type_mismatches or observed_fingerprint != expected_fingerprint:
        details = {
            "contract_id": contract.contract_id,
            "table_id": contract.table_id,
            "missing_columns": missing,
            "type_mismatches": type_mismatches,
            "expected_fingerprint": expected_fingerprint,
            "observed_fingerprint": observed_fingerprint,
            "evidence_fingerprint": contract.evidence_fingerprint,
        }
        raise ValueError("schema_contract_mismatch:" + json.dumps(details, sort_keys=True))
    return {
        "contract_id": contract.contract_id,
        "table_id": contract.table_id,
        "expected_fingerprint": expected_fingerprint,
        "observed_fingerprint": observed_fingerprint,
        "evidence_fingerprint": contract.evidence_fingerprint,
        "verified": True,
    }


def verify_kpi_schema(adapter: SchemaIntrospector, metric: str) -> dict[str, object]:
    definition = get_kpi_definition(metric)
    if not definition.schema_contract_id:
        raise ValueError(f"kpi_schema_contract_required:{metric}")
    contract = get_schema_contract(definition.schema_contract_id)
    if definition.source_table != contract.table_id:
        raise ValueError(f"kpi_schema_contract_table_mismatch:{metric}")
    introspect = getattr(adapter, "table_schema", None)
    if introspect is None or not callable(introspect):
        raise ValueError("schema_introspection_not_supported")
    observed = introspect(contract.table_id)
    return verify_table_schema(contract, observed)
