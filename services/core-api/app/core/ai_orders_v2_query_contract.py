"""Blocked candidate contract for tenant-safe `ops.kpi.orders.v2`.

This module is deliberately *not* an execution adapter and does not make the
query production-ready. It freezes the intended SQL shape so schema evidence,
BigQuery array-parameter support and cross-tenant proof can be reviewed against
one exact candidate rather than an informal query string.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlglot import exp, parse
from sqlglot.errors import ParseError

ORDERS_V2_QUERY_ID = "ops.kpi.orders.v2"
ORDERS_SOURCE_TABLE = "curated_data_shared_coredata_business.orders"
ORDERS_V2_PARAMETER_NAMES = (
    "start_date",
    "end_date",
    "entity_ids",
    "stores",
)
ORDERS_V2_BLOCKERS = (
    "orders_tenant_discriminator_schema_evidence_missing",
    "bigquery_array_parameter_adapter_not_reviewed",
    "cross_tenant_query_proof_missing",
)

ORDERS_V2_SQL = """
SELECT
  DATE(partition_date_local) AS date,
  vendor_name,
  COUNT(DISTINCT order_id) AS orders
FROM `curated_data_shared_coredata_business.orders`
WHERE DATE(partition_date_local) BETWEEN @start_date AND @end_date
  AND entity.id IN UNNEST(@entity_ids)
  AND vendor_name IN UNNEST(@stores)
GROUP BY 1,2
ORDER BY 1 DESC,3 DESC
""".strip()

_PARAMETER_RE = re.compile(r"@([A-Za-z_][A-Za-z0-9_]*)")
_WHITESPACE_RE = re.compile(r"\s+")
_CONTROL_WHITESPACE = frozenset({"\t", "\r", "\n"})


class OrdersV2QueryContractError(ValueError):
    """The candidate query or its bounded parameters violate the contract."""


@dataclass(frozen=True)
class OrdersV2QueryCandidate:
    query_id: str
    source_table: str
    sql: str
    parameter_names: tuple[str, ...]
    tenant_discriminator_expression: str
    tenant_parameter: str
    store_expression: str
    store_parameter: str
    schema_evidence_fingerprint: str | None
    array_parameter_adapter_fingerprint: str | None
    cross_tenant_proof_fingerprint: str | None
    blockers: tuple[str, ...]

    @property
    def template_fingerprint(self) -> str:
        """Match the frozen AI Core QueryTemplate fingerprint algorithm."""

        payload = {
            "query_id": self.query_id,
            "sql": self.sql,
            "parameter_names": list(self.parameter_names),
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @property
    def security_fingerprint(self) -> str:
        payload = {
            "query_id": self.query_id,
            "source_table": self.source_table,
            "template_fingerprint": self.template_fingerprint,
            "tenant_discriminator_expression": (
                self.tenant_discriminator_expression
            ),
            "tenant_parameter": self.tenant_parameter,
            "store_expression": self.store_expression,
            "store_parameter": self.store_parameter,
            "schema_evidence_fingerprint": self.schema_evidence_fingerprint,
            "array_parameter_adapter_fingerprint": (
                self.array_parameter_adapter_fingerprint
            ),
            "cross_tenant_proof_fingerprint": (
                self.cross_tenant_proof_fingerprint
            ),
            "blockers": list(self.blockers),
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


ORDERS_V2_CANDIDATE = OrdersV2QueryCandidate(
    query_id=ORDERS_V2_QUERY_ID,
    source_table=ORDERS_SOURCE_TABLE,
    sql=ORDERS_V2_SQL,
    parameter_names=ORDERS_V2_PARAMETER_NAMES,
    # Candidate only. This expression is NOT treated as reviewed production
    # schema evidence until an authoritative schema-evidence slice proves it.
    tenant_discriminator_expression="entity.id",
    tenant_parameter="entity_ids",
    store_expression="vendor_name",
    store_parameter="stores",
    schema_evidence_fingerprint=None,
    array_parameter_adapter_fingerprint=None,
    cross_tenant_proof_fingerprint=None,
    blockers=ORDERS_V2_BLOCKERS,
)


def _normalized_sql(sql: str) -> str:
    return _WHITESPACE_RE.sub(" ", sql.strip()).lower()


def _normalized_table_name(table: exp.Table) -> str:
    rendered = table.sql(dialect="bigquery")
    return rendered.replace("`", "").strip().lower()


def validate_orders_v2_query_candidate(
    candidate: OrdersV2QueryCandidate = ORDERS_V2_CANDIDATE,
) -> str:
    """Validate the fixed candidate SQL shape and return its fingerprint.

    This is a structural candidate gate, not schema evidence. Production
    promotion remains impossible while any explicit blocker exists.
    """

    if candidate.query_id != ORDERS_V2_QUERY_ID:
        raise OrdersV2QueryContractError("unexpected_query_id")
    if candidate.source_table != ORDERS_SOURCE_TABLE:
        raise OrdersV2QueryContractError("unexpected_source_table")
    if candidate.parameter_names != ORDERS_V2_PARAMETER_NAMES:
        raise OrdersV2QueryContractError("unexpected_parameter_contract")
    if not candidate.blockers:
        raise OrdersV2QueryContractError(
            "candidate_must_remain_blocked_without_review_evidence"
        )
    if any(
        value is not None
        for value in (
            candidate.schema_evidence_fingerprint,
            candidate.array_parameter_adapter_fingerprint,
            candidate.cross_tenant_proof_fingerprint,
        )
    ):
        raise OrdersV2QueryContractError(
            "candidate_review_evidence_must_be_promoted_separately"
        )

    sql = candidate.sql
    normalized = _normalized_sql(sql)
    if not sql or ";" in sql or "--" in sql or "/*" in sql:
        raise OrdersV2QueryContractError("unsafe_sql_surface")

    try:
        statements = parse(sql, read="bigquery")
    except ParseError as exc:
        raise OrdersV2QueryContractError("invalid_bigquery_sql") from exc

    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise OrdersV2QueryContractError("single_select_required")

    tree = statements[0]
    if tree.find(exp.Union) is not None:
        raise OrdersV2QueryContractError("set_operations_forbidden")
    if tree.find(exp.Or) is not None:
        raise OrdersV2QueryContractError("or_predicates_forbidden")
    if tree.find(exp.Star) is not None:
        raise OrdersV2QueryContractError("select_star_forbidden")

    tables = {
        _normalized_table_name(table)
        for table in tree.find_all(exp.Table)
    }
    if tables != {ORDERS_SOURCE_TABLE.lower()}:
        raise OrdersV2QueryContractError("source_table_mismatch")

    parameters = tuple(_PARAMETER_RE.findall(sql))
    if set(parameters) != set(ORDERS_V2_PARAMETER_NAMES):
        raise OrdersV2QueryContractError("parameter_set_mismatch")
    if any(parameters.count(name) != 1 for name in ORDERS_V2_PARAMETER_NAMES):
        raise OrdersV2QueryContractError("parameter_must_appear_exactly_once")

    if "stores_empty" in normalized or "entity_ids_empty" in normalized:
        raise OrdersV2QueryContractError("empty_scope_bypass_forbidden")

    required_fragments = (
        "date(partition_date_local) between @start_date and @end_date",
        "entity.id in unnest(@entity_ids)",
        "vendor_name in unnest(@stores)",
    )
    if any(fragment not in normalized for fragment in required_fragments):
        raise OrdersV2QueryContractError("mandatory_predicate_missing")

    if re.search(
        r"entity\.id\s*(?:=|in)\s*['\"]",
        normalized,
    ):
        raise OrdersV2QueryContractError("literal_tenant_filter_forbidden")

    return candidate.template_fingerprint


def _canonical_nonempty_string_list(
    value: Any,
    *,
    name: str,
    max_items: int,
    allow_spaces: bool,
) -> tuple[str, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or not 1 <= len(value) <= max_items
    ):
        raise OrdersV2QueryContractError(f"{name}_must_be_nonempty_array")

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, str):
            raise OrdersV2QueryContractError(f"{name}_must_contain_text")
        item = raw.strip()
        if (
            not item
            or "*" in item
            or "%" in item
            or any(char in item for char in _CONTROL_WHITESPACE)
            or (not allow_spaces and any(char.isspace() for char in item))
        ):
            raise OrdersV2QueryContractError(f"{name}_contains_unsafe_value")
        folded = item.casefold()
        if folded in seen:
            raise OrdersV2QueryContractError(f"{name}_contains_duplicates")
        seen.add(folded)
        normalized.append(item)

    return tuple(normalized)


def validate_orders_v2_runtime_parameters(
    parameters: Mapping[str, Any],
) -> dict[str, object]:
    """Preflight the future executor parameter object without executing SQL."""

    if set(parameters) != set(ORDERS_V2_PARAMETER_NAMES):
        raise OrdersV2QueryContractError("runtime_parameter_set_mismatch")

    start = parameters["start_date"]
    end = parameters["end_date"]
    if isinstance(start, str):
        try:
            start = date.fromisoformat(start)
        except ValueError as exc:
            raise OrdersV2QueryContractError("invalid_start_date") from exc
    if isinstance(end, str):
        try:
            end = date.fromisoformat(end)
        except ValueError as exc:
            raise OrdersV2QueryContractError("invalid_end_date") from exc
    if (
        not isinstance(start, date)
        or isinstance(start, datetime)
        or not isinstance(end, date)
        or isinstance(end, datetime)
    ):
        raise OrdersV2QueryContractError("date_parameters_required")
    if end < start:
        raise OrdersV2QueryContractError("end_date_before_start_date")
    if (end - start).days > 366:
        raise OrdersV2QueryContractError("date_window_too_large")

    entity_ids = _canonical_nonempty_string_list(
        parameters["entity_ids"],
        name="entity_ids",
        max_items=16,
        allow_spaces=False,
    )
    stores = _canonical_nonempty_string_list(
        parameters["stores"],
        name="stores",
        max_items=200,
        allow_spaces=True,
    )

    return {
        "start_date": start,
        "end_date": end,
        "entity_ids": entity_ids,
        "stores": stores,
    }
