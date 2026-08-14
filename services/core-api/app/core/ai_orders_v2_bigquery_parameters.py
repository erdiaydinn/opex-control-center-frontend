"""Typed, network-free BigQuery parameter planning for orders v2.

This is intentionally not a BigQuery executor. It converts the already
validated `ops.kpi.orders.v2` runtime parameter object into a fixed typed plan
and REST-compatible parameter representation. Caller-selected parameter types,
arbitrary parameter names and unbounded arrays are outside the API surface.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from app.core.ai_orders_v2_query_contract import (
    ORDERS_V2_CANDIDATE,
    ORDERS_V2_PARAMETER_NAMES,
    ORDERS_V2_QUERY_ID,
    validate_orders_v2_query_candidate,
    validate_orders_v2_runtime_parameters,
)

ParameterMode = Literal["SCALAR", "ARRAY"]
BigQueryType = Literal["DATE", "STRING"]


@dataclass(frozen=True)
class BigQueryParameterContractEntry:
    name: str
    mode: ParameterMode
    value_type: BigQueryType


@dataclass(frozen=True)
class PlannedBigQueryParameter:
    name: str
    mode: ParameterMode
    value_type: BigQueryType
    value: date | tuple[str, ...]

    def rest_spec(self) -> dict[str, object]:
        """Return the canonical BigQuery REST query-parameter shape."""

        if self.mode == "SCALAR":
            if (
                self.value_type != "DATE"
                or not isinstance(self.value, date)
                or isinstance(self.value, datetime)
            ):
                raise ValueError("invalid_scalar_parameter_plan")
            return {
                "name": self.name,
                "parameterType": {"type": "DATE"},
                "parameterValue": {"value": self.value.isoformat()},
            }

        if (
            self.mode != "ARRAY"
            or self.value_type != "STRING"
            or not isinstance(self.value, tuple)
            or not self.value
            or not all(isinstance(item, str) for item in self.value)
        ):
            raise ValueError("invalid_array_parameter_plan")

        return {
            "name": self.name,
            "parameterType": {
                "type": "ARRAY",
                "arrayType": {"type": "STRING"},
            },
            "parameterValue": {
                "arrayValues": [
                    {"value": item}
                    for item in self.value
                ]
            },
        }


ORDERS_V2_BIGQUERY_PARAMETER_CONTRACT = (
    BigQueryParameterContractEntry(
        name="start_date",
        mode="SCALAR",
        value_type="DATE",
    ),
    BigQueryParameterContractEntry(
        name="end_date",
        mode="SCALAR",
        value_type="DATE",
    ),
    BigQueryParameterContractEntry(
        name="entity_ids",
        mode="ARRAY",
        value_type="STRING",
    ),
    BigQueryParameterContractEntry(
        name="stores",
        mode="ARRAY",
        value_type="STRING",
    ),
)


def orders_v2_bigquery_parameter_contract_fingerprint() -> str:
    """Bind the planner schema to the exact blocked query candidate."""

    payload = {
        "query_id": ORDERS_V2_QUERY_ID,
        "template_fingerprint": ORDERS_V2_CANDIDATE.template_fingerprint,
        "parameters": [
            {
                "name": entry.name,
                "mode": entry.mode,
                "value_type": entry.value_type,
            }
            for entry in ORDERS_V2_BIGQUERY_PARAMETER_CONTRACT
        ],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def plan_orders_v2_bigquery_parameters(
    parameters: Mapping[str, Any],
) -> tuple[PlannedBigQueryParameter, ...]:
    """Build the only accepted typed parameter plan for orders v2."""

    validate_orders_v2_query_candidate()
    validated = validate_orders_v2_runtime_parameters(parameters)

    if tuple(
        entry.name
        for entry in ORDERS_V2_BIGQUERY_PARAMETER_CONTRACT
    ) != ORDERS_V2_PARAMETER_NAMES:
        raise RuntimeError("orders_v2_parameter_contract_drift")

    start_date = validated["start_date"]
    end_date = validated["end_date"]
    entity_ids = validated["entity_ids"]
    stores = validated["stores"]

    if (
        not isinstance(start_date, date)
        or isinstance(start_date, datetime)
        or not isinstance(end_date, date)
        or isinstance(end_date, datetime)
    ):
        raise RuntimeError("orders_v2_date_plan_drift")
    if not isinstance(entity_ids, tuple) or not isinstance(stores, tuple):
        raise RuntimeError("orders_v2_array_plan_drift")

    return (
        PlannedBigQueryParameter(
            name="start_date",
            mode="SCALAR",
            value_type="DATE",
            value=start_date,
        ),
        PlannedBigQueryParameter(
            name="end_date",
            mode="SCALAR",
            value_type="DATE",
            value=end_date,
        ),
        PlannedBigQueryParameter(
            name="entity_ids",
            mode="ARRAY",
            value_type="STRING",
            value=entity_ids,
        ),
        PlannedBigQueryParameter(
            name="stores",
            mode="ARRAY",
            value_type="STRING",
            value=stores,
        ),
    )


def orders_v2_bigquery_rest_parameters(
    parameters: Mapping[str, Any],
) -> tuple[dict[str, object], ...]:
    """Render the typed plan without performing any network/client action."""

    return tuple(
        parameter.rest_spec()
        for parameter in plan_orders_v2_bigquery_parameters(parameters)
    )
