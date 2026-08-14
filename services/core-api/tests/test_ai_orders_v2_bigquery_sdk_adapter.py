from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from google.cloud import bigquery

import app.core.ai_orders_v2_bigquery_sdk_adapter as adapter
from app.core.ai_orders_v2_bigquery_parameters import (
    orders_v2_bigquery_rest_parameters,
)
from app.core.ai_orders_v2_bigquery_sdk_adapter import (
    BIGQUERY_SDK_VERSION_SPEC,
    OrdersV2BigQuerySdkUnavailable,
    build_orders_v2_bigquery_job_config,
    build_orders_v2_bigquery_sdk_parameters,
    orders_v2_bigquery_sdk_adapter_fingerprint,
)


def valid_parameters() -> dict[str, object]:
    return {
        "start_date": "2026-08-01",
        "end_date": "2026-08-12",
        "entity_ids": ["TEST_ENTITY_TR"],
        "stores": ["Fulya", "Kartal Cumhuriyet"],
    }


def test_sdk_version_contract_matches_reviewed_optional_range() -> None:
    major, minor, *_ = bigquery.__version__.split(".")
    assert int(major) == 3
    assert int(minor) >= 42
    assert BIGQUERY_SDK_VERSION_SPEC == ">=3.42,<4"
    assert len(orders_v2_bigquery_sdk_adapter_fingerprint()) == 64


def test_real_sdk_parameters_match_network_free_planner_rest_shape() -> None:
    expected = orders_v2_bigquery_rest_parameters(valid_parameters())
    sdk_parameters = build_orders_v2_bigquery_sdk_parameters(
        valid_parameters()
    )

    assert len(sdk_parameters) == 4
    assert isinstance(sdk_parameters[0], bigquery.ScalarQueryParameter)
    assert isinstance(sdk_parameters[1], bigquery.ScalarQueryParameter)
    assert isinstance(sdk_parameters[2], bigquery.ArrayQueryParameter)
    assert isinstance(sdk_parameters[3], bigquery.ArrayQueryParameter)
    assert tuple(
        parameter.to_api_repr()
        for parameter in sdk_parameters
    ) == expected


def test_job_config_is_standard_sql_and_contains_only_reviewed_parameters() -> None:
    config = build_orders_v2_bigquery_job_config(valid_parameters())

    assert isinstance(config, bigquery.QueryJobConfig)
    assert config.use_legacy_sql is False
    assert len(config.query_parameters) == 4
    assert [parameter.name for parameter in config.query_parameters] == [
        "start_date",
        "end_date",
        "entity_ids",
        "stores",
    ]

    api = config.to_api_repr()
    query = api["query"]
    assert query["useLegacySql"] is False
    assert query["parameterMode"] == "NAMED"
    assert query["queryParameters"] == [
        parameter.to_api_repr()
        for parameter in config.query_parameters
    ]


def test_adapter_public_api_accepts_no_client_sql_project_or_type_override() -> None:
    for function in (
        build_orders_v2_bigquery_sdk_parameters,
        build_orders_v2_bigquery_job_config,
    ):
        parameters = inspect.signature(function).parameters
        assert tuple(parameters) == ("parameters",)
        for forbidden in (
            "client",
            "sql",
            "query",
            "project",
            "credentials",
            "location",
            "parameter_types",
            "array_type",
        ):
            assert forbidden not in parameters


def test_adapter_source_cannot_instantiate_client_or_submit_query() -> None:
    path = Path(adapter.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))

    forbidden_calls: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Attribute):
            name = function.attr
        elif isinstance(function, ast.Name):
            name = function.id
        else:
            continue
        if name in {
            "Client",
            "query",
            "query_and_wait",
            "run_query",
            "get_credentials",
            "default",
        }:
            forbidden_calls.append(name)

    assert forbidden_calls == []


def test_missing_optional_sdk_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_import(name: str):
        assert name == "google.cloud.bigquery"
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(adapter, "import_module", fail_import)

    with pytest.raises(OrdersV2BigQuerySdkUnavailable):
        build_orders_v2_bigquery_sdk_parameters(valid_parameters())

    with pytest.raises(OrdersV2BigQuerySdkUnavailable):
        build_orders_v2_bigquery_job_config(valid_parameters())
