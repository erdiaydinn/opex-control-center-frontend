from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime

import pytest

from app.core.ai_orders_v2_query_contract import (
    ORDERS_SOURCE_TABLE,
    ORDERS_V2_BLOCKERS,
    ORDERS_V2_CANDIDATE,
    ORDERS_V2_PARAMETER_NAMES,
    OrdersV2QueryContractError,
    validate_orders_v2_query_candidate,
    validate_orders_v2_runtime_parameters,
)
from app.core.ai_query_contract_policy import AI_QUERY_CONTRACT_POLICIES


def test_candidate_is_exact_versioned_and_explicitly_blocked() -> None:
    fingerprint = validate_orders_v2_query_candidate()

    assert ORDERS_V2_CANDIDATE.query_id == "ops.kpi.orders.v2"
    assert ORDERS_V2_CANDIDATE.source_table == ORDERS_SOURCE_TABLE
    assert ORDERS_V2_CANDIDATE.parameter_names == ORDERS_V2_PARAMETER_NAMES
    assert ORDERS_V2_CANDIDATE.tenant_discriminator_expression == "entity.id"
    assert ORDERS_V2_CANDIDATE.tenant_parameter == "entity_ids"
    assert ORDERS_V2_CANDIDATE.store_expression == "vendor_name"
    assert ORDERS_V2_CANDIDATE.store_parameter == "stores"
    assert ORDERS_V2_CANDIDATE.blockers == ORDERS_V2_BLOCKERS
    assert ORDERS_V2_CANDIDATE.schema_evidence_fingerprint is None
    assert ORDERS_V2_CANDIDATE.array_parameter_adapter_fingerprint is None
    assert ORDERS_V2_CANDIDATE.cross_tenant_proof_fingerprint is None
    assert len(fingerprint) == 64
    assert fingerprint == ORDERS_V2_CANDIDATE.template_fingerprint
    assert len(ORDERS_V2_CANDIDATE.security_fingerprint) == 64

    active = AI_QUERY_CONTRACT_POLICIES["ops_kpi_query"]
    assert active.contract_id == "ops.kpi.orders.v1"
    assert active.production_ready is False


@pytest.mark.parametrize(
    "mutate_sql",
    [
        lambda sql: sql.replace(
            "  AND entity.id IN UNNEST(@entity_ids)\n",
            "",
        ),
        lambda sql: sql.replace(
            "  AND vendor_name IN UNNEST(@stores)",
            "  AND (vendor_name IN UNNEST(@stores) OR TRUE)",
        ),
        lambda sql: sql.replace(
            "entity.id IN UNNEST(@entity_ids)",
            "entity.id = 'YS_TR'",
        ),
        lambda sql: sql.replace(
            "vendor_name IN UNNEST(@stores)",
            "(@stores_empty OR vendor_name IN UNNEST(@stores))",
        ),
        lambda sql: sql.replace(
            ORDERS_SOURCE_TABLE,
            "curated_data_shared.orders",
        ),
        lambda sql: sql.replace(
            "GROUP BY 1,2",
            "  AND @debug_flag\nGROUP BY 1,2",
        ),
        lambda sql: sql + "\nUNION ALL SELECT CURRENT_DATE(), 'X', 1",
        lambda sql: sql + "; SELECT 1",
        lambda sql: sql.replace(
            (
                "DATE(partition_date_local) AS date,\n"
                "  vendor_name,\n"
                "  COUNT(DISTINCT order_id) AS orders"
            ),
            "*",
        ),
    ],
)
def test_candidate_rejects_structural_bypasses(
    mutate_sql: Callable[[str], str],
) -> None:
    candidate = replace(
        ORDERS_V2_CANDIDATE,
        sql=mutate_sql(ORDERS_V2_CANDIDATE.sql),
    )

    with pytest.raises(OrdersV2QueryContractError):
        validate_orders_v2_query_candidate(candidate)


def test_candidate_requires_exact_parameter_contract_and_blockers() -> None:
    with pytest.raises(
        OrdersV2QueryContractError,
        match="unexpected_parameter_contract",
    ):
        validate_orders_v2_query_candidate(
            replace(
                ORDERS_V2_CANDIDATE,
                parameter_names=(
                    "start_date",
                    "end_date",
                    "stores",
                ),
            )
        )

    with pytest.raises(
        OrdersV2QueryContractError,
        match="candidate_must_remain_blocked",
    ):
        validate_orders_v2_query_candidate(
            replace(
                ORDERS_V2_CANDIDATE,
                blockers=(),
            )
        )

    with pytest.raises(
        OrdersV2QueryContractError,
        match="promoted_separately",
    ):
        validate_orders_v2_query_candidate(
            replace(
                ORDERS_V2_CANDIDATE,
                schema_evidence_fingerprint="a" * 64,
            )
        )


def valid_parameters() -> dict[str, object]:
    return {
        "start_date": "2026-08-01",
        "end_date": "2026-08-12",
        "entity_ids": ["TEST_ENTITY_TR"],
        "stores": ["Fulya", "Kartal Cumhuriyet"],
    }


def test_runtime_preflight_requires_nonempty_bounded_authority_arrays() -> None:
    validated = validate_orders_v2_runtime_parameters(
        valid_parameters()
    )

    assert validated == {
        "start_date": date(2026, 8, 1),
        "end_date": date(2026, 8, 12),
        "entity_ids": ("TEST_ENTITY_TR",),
        "stores": ("Fulya", "Kartal Cumhuriyet"),
    }

    for field in ("entity_ids", "stores"):
        parameters = valid_parameters()
        parameters[field] = []
        with pytest.raises(OrdersV2QueryContractError):
            validate_orders_v2_runtime_parameters(parameters)

        parameters = valid_parameters()
        parameters[field] = ["*"]
        with pytest.raises(OrdersV2QueryContractError):
            validate_orders_v2_runtime_parameters(parameters)

        parameters = valid_parameters()
        parameters[field] = ["A", "a"]
        with pytest.raises(OrdersV2QueryContractError):
            validate_orders_v2_runtime_parameters(parameters)


def test_runtime_preflight_rejects_datetime_and_control_whitespace() -> None:
    for field in ("start_date", "end_date"):
        parameters = valid_parameters()
        parameters[field] = datetime(2026, 8, 1, 12, 30)
        with pytest.raises(
            OrdersV2QueryContractError,
            match="date_parameters_required",
        ):
            validate_orders_v2_runtime_parameters(parameters)

    entity_whitespace = valid_parameters()
    entity_whitespace["entity_ids"] = ["TEST ENTITY"]
    with pytest.raises(OrdersV2QueryContractError):
        validate_orders_v2_runtime_parameters(entity_whitespace)

    for unsafe_store in ("Fulya\nInjected", "Fulya\tInjected", "Fulya\rInjected"):
        store_control = valid_parameters()
        store_control["stores"] = [unsafe_store]
        with pytest.raises(OrdersV2QueryContractError):
            validate_orders_v2_runtime_parameters(store_control)

    spaced_store = valid_parameters()
    spaced_store["stores"] = ["Kartal Cumhuriyet"]
    validated = validate_orders_v2_runtime_parameters(spaced_store)
    assert validated["stores"] == ("Kartal Cumhuriyet",)


def test_runtime_preflight_keeps_frozen_window_and_store_bounds() -> None:
    reversed_window = valid_parameters()
    reversed_window["start_date"] = "2026-08-12"
    reversed_window["end_date"] = "2026-08-01"
    with pytest.raises(
        OrdersV2QueryContractError,
        match="end_date_before_start_date",
    ):
        validate_orders_v2_runtime_parameters(reversed_window)

    too_long = valid_parameters()
    too_long["start_date"] = "2025-01-01"
    too_long["end_date"] = "2026-08-12"
    with pytest.raises(
        OrdersV2QueryContractError,
        match="date_window_too_large",
    ):
        validate_orders_v2_runtime_parameters(too_long)

    too_many_stores = valid_parameters()
    too_many_stores["stores"] = [
        f"Store-{index}"
        for index in range(201)
    ]
    with pytest.raises(OrdersV2QueryContractError):
        validate_orders_v2_runtime_parameters(too_many_stores)

    too_many_entities = valid_parameters()
    too_many_entities["entity_ids"] = [
        f"ENTITY_{index}"
        for index in range(17)
    ]
    with pytest.raises(OrdersV2QueryContractError):
        validate_orders_v2_runtime_parameters(too_many_entities)


def test_runtime_preflight_rejects_missing_or_extra_parameters() -> None:
    missing = valid_parameters()
    del missing["entity_ids"]
    with pytest.raises(
        OrdersV2QueryContractError,
        match="runtime_parameter_set_mismatch",
    ):
        validate_orders_v2_runtime_parameters(missing)

    extra = valid_parameters()
    extra["stores_empty"] = False
    with pytest.raises(
        OrdersV2QueryContractError,
        match="runtime_parameter_set_mismatch",
    ):
        validate_orders_v2_runtime_parameters(extra)
