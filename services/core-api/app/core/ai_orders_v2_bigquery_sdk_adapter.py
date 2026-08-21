"""Google BigQuery SDK adapter for the blocked orders v2 candidate.

This module creates typed SDK parameter objects and a QueryJobConfig only. It
does not instantiate a BigQuery client, submit a query, resolve credentials or
perform any network action. The optional BigQuery dependency is required only
when this adapter is explicitly used.
"""

from __future__ import annotations

import hashlib
import json
from importlib import import_module
from typing import Any, Protocol

from app.core.ai_orders_v2_bigquery_parameters import (
    PlannedBigQueryParameter,
    orders_v2_bigquery_parameter_contract_fingerprint,
    plan_orders_v2_bigquery_parameters,
)

BIGQUERY_SDK_VERSION_SPEC = ">=3.42,<4"


class OrdersV2BigQuerySdkAdapterError(RuntimeError):
    """Base fail-closed SDK adapter error."""


class OrdersV2BigQuerySdkUnavailable(OrdersV2BigQuerySdkAdapterError):
    """The optional BigQuery SDK is not installed or importable."""


class _BigQueryModule(Protocol):
    ScalarQueryParameter: Any
    ArrayQueryParameter: Any
    QueryJobConfig: Any


def _load_bigquery_module() -> _BigQueryModule:
    try:
        module = import_module("google.cloud.bigquery")
    except (ImportError, ModuleNotFoundError) as exc:
        raise OrdersV2BigQuerySdkUnavailable(
            "google-cloud-bigquery optional dependency is unavailable"
        ) from exc

    for required in (
        "ScalarQueryParameter",
        "ArrayQueryParameter",
        "QueryJobConfig",
    ):
        if not hasattr(module, required):
            raise OrdersV2BigQuerySdkUnavailable(
                "google-cloud-bigquery SDK surface is incomplete"
            )

    return module  # type: ignore[return-value]


def orders_v2_bigquery_sdk_adapter_fingerprint() -> str:
    """Bind adapter review evidence to the exact typed planner contract."""

    payload = {
        "adapter": "google-cloud-bigquery-query-parameters-v1",
        "sdk_version_spec": BIGQUERY_SDK_VERSION_SPEC,
        "parameter_contract_fingerprint": (
            orders_v2_bigquery_parameter_contract_fingerprint()
        ),
        "scalar_class": "google.cloud.bigquery.ScalarQueryParameter",
        "array_class": "google.cloud.bigquery.ArrayQueryParameter",
        "job_config_class": "google.cloud.bigquery.QueryJobConfig",
        "use_legacy_sql": False,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sdk_parameter_from_plan(
    bigquery: _BigQueryModule,
    parameter: PlannedBigQueryParameter,
) -> Any:
    if parameter.mode == "SCALAR" and parameter.value_type == "DATE":
        return bigquery.ScalarQueryParameter(
            parameter.name,
            "DATE",
            parameter.value,
        )

    if parameter.mode == "ARRAY" and parameter.value_type == "STRING":
        if not isinstance(parameter.value, tuple) or not parameter.value:
            raise OrdersV2BigQuerySdkAdapterError(
                "invalid ARRAY<STRING> parameter plan"
            )
        return bigquery.ArrayQueryParameter(
            parameter.name,
            "STRING",
            list(parameter.value),
        )

    raise OrdersV2BigQuerySdkAdapterError(
        "unsupported BigQuery parameter plan"
    )


def build_orders_v2_bigquery_sdk_parameters(
    parameters: dict[str, object],
) -> tuple[Any, ...]:
    """Convert the validated fixed plan into real BigQuery SDK parameters."""

    bigquery = _load_bigquery_module()
    plan = plan_orders_v2_bigquery_parameters(parameters)
    return tuple(
        _sdk_parameter_from_plan(bigquery, parameter)
        for parameter in plan
    )


def build_orders_v2_bigquery_job_config(
    parameters: dict[str, object],
) -> Any:
    """Build a Standard SQL QueryJobConfig without submitting a query."""

    bigquery = _load_bigquery_module()
    plan = plan_orders_v2_bigquery_parameters(parameters)
    query_parameters = [
        _sdk_parameter_from_plan(bigquery, parameter)
        for parameter in plan
    ]
    return bigquery.QueryJobConfig(
        use_legacy_sql=False,
        query_parameters=query_parameters,
    )
