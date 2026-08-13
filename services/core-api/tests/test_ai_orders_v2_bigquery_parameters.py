from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import replace
from datetime import date, datetime

import pytest

from app.core.ai_orders_v2_bigquery_parameters import (
    ORDERS_V2_BIGQUERY_PARAMETER_CONTRACT,
    BigQueryParameterContractEntry,
    PlannedBigQueryParameter,
    orders_v2_bigquery_parameter_contract_fingerprint,
    orders_v2_bigquery_rest_parameters,
    plan_orders_v2_bigquery_parameters,
)
from app.core.ai_orders_v2_query_contract import (
    ORDERS_V2_CANDIDATE,
    OrdersV2QueryContractError,
)


def valid_parameters() -> dict[str, object]:
    return {
        "start_date": "2026-08-01",
        "end_date": "2026-08-12",
        "entity_ids": ["TEST_ENTITY_TR"],
        "stores": ["Fulya", "Kartal Cumhuriyet"],
    }


def test_parameter_contract_is_exact_and_bound_to_candidate() -> None:
    assert (
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
    ) == ORDERS_V2_BIGQUERY_PARAMETER_CONTRACT

    fingerprint = orders_v2_bigquery_parameter_contract_fingerprint()
    assert len(fingerprint) == 64
    assert len(ORDERS_V2_CANDIDATE.template_fingerprint) == 64


def test_planner_emits_only_fixed_date_and_array_string_types() -> None:
    plan = plan_orders_v2_bigquery_parameters(valid_parameters())

    assert plan == (
        PlannedBigQueryParameter(
            name="start_date",
            mode="SCALAR",
            value_type="DATE",
            value=date(2026, 8, 1),
        ),
        PlannedBigQueryParameter(
            name="end_date",
            mode="SCALAR",
            value_type="DATE",
            value=date(2026, 8, 12),
        ),
        PlannedBigQueryParameter(
            name="entity_ids",
            mode="ARRAY",
            value_type="STRING",
            value=("TEST_ENTITY_TR",),
        ),
        PlannedBigQueryParameter(
            name="stores",
            mode="ARRAY",
            value_type="STRING",
            value=("Fulya", "Kartal Cumhuriyet"),
        ),
    )


def test_rest_parameter_shape_is_explicit_and_nonempty() -> None:
    specs = orders_v2_bigquery_rest_parameters(valid_parameters())

    assert specs == (
        {
            "name": "start_date",
            "parameterType": {"type": "DATE"},
            "parameterValue": {"value": "2026-08-01"},
        },
        {
            "name": "end_date",
            "parameterType": {"type": "DATE"},
            "parameterValue": {"value": "2026-08-12"},
        },
        {
            "name": "entity_ids",
            "parameterType": {
                "type": "ARRAY",
                "arrayType": {"type": "STRING"},
            },
            "parameterValue": {
                "arrayValues": [{"value": "TEST_ENTITY_TR"}]
            },
        },
        {
            "name": "stores",
            "parameterType": {
                "type": "ARRAY",
                "arrayType": {"type": "STRING"},
            },
            "parameterValue": {
                "arrayValues": [
                    {"value": "Fulya"},
                    {"value": "Kartal Cumhuriyet"},
                ]
            },
        },
    )


def test_planner_api_exposes_no_caller_selected_type_contract() -> None:
    parameters = inspect.signature(
        plan_orders_v2_bigquery_parameters
    ).parameters
    assert tuple(parameters) == ("parameters",)

    for forbidden in (
        "types",
        "parameter_types",
        "array_type",
        "value_type",
        "query_id",
        "sql",
    ):
        assert forbidden not in parameters

    smuggled = valid_parameters()
    smuggled["parameter_types"] = {
        "entity_ids": "STRING",
    }
    with pytest.raises(
        OrdersV2QueryContractError,
        match="runtime_parameter_set_mismatch",
    ):
        plan_orders_v2_bigquery_parameters(smuggled)


def test_planner_rejects_empty_nested_heterogeneous_and_mapping_arrays() -> None:
    unsafe_values = (
        [],
        [["TEST_ENTITY_TR"]],
        ["TEST_ENTITY_TR", 123],
        {"0": "TEST_ENTITY_TR"},
    )

    for field in ("entity_ids", "stores"):
        for unsafe in unsafe_values:
            parameters = valid_parameters()
            parameters[field] = unsafe
            with pytest.raises(OrdersV2QueryContractError):
                plan_orders_v2_bigquery_parameters(parameters)


def test_planned_parameter_defense_in_depth_rejects_manual_type_confusion() -> None:
    with pytest.raises(ValueError, match="invalid_scalar_parameter_plan"):
        PlannedBigQueryParameter(
            name="start_date",
            mode="SCALAR",
            value_type="DATE",
            value=datetime(2026, 8, 1, 12, 0),
        ).rest_spec()

    for invalid in (
        (),
        ("A", 1),
    ):
        with pytest.raises(ValueError, match="invalid_array_parameter_plan"):
            PlannedBigQueryParameter(
                name="stores",
                mode="ARRAY",
                value_type="STRING",
                value=invalid,  # type: ignore[arg-type]
            ).rest_spec()


def test_parameter_contract_fingerprint_changes_when_schema_changes() -> None:
    original = orders_v2_bigquery_parameter_contract_fingerprint()

    changed = replace(
        ORDERS_V2_BIGQUERY_PARAMETER_CONTRACT[-1],
        mode="SCALAR",
    )
    payload = (
        *ORDERS_V2_BIGQUERY_PARAMETER_CONTRACT[:-1],
        changed,
    )

    encoded = json.dumps(
        {
            "query_id": ORDERS_V2_CANDIDATE.query_id,
            "template_fingerprint": (
                ORDERS_V2_CANDIDATE.template_fingerprint
            ),
            "parameters": [
                {
                    "name": entry.name,
                    "mode": entry.mode,
                    "value_type": entry.value_type,
                }
                for entry in payload
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    changed_fingerprint = hashlib.sha256(encoded).hexdigest()

    assert changed_fingerprint != original
