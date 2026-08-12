from __future__ import annotations

import pytest

import app.core.jarvis_safety_policy as safety
from app.core.ai_tool_authorization import TOOL_REQUIRED_SCOPES


def test_safety_registry_exactly_covers_authorized_tools() -> None:
    assert set(safety.TOOL_SAFETY_POLICIES) == set(TOOL_REQUIRED_SCOPES)


def test_current_tools_are_read_only_and_noncritical() -> None:
    for policy in safety.TOOL_SAFETY_POLICIES.values():
        assert policy.side_effect_class in {"none", "read"}
        assert policy.risk_class != "critical"
        assert policy.requires_human_approval is False


def test_execution_envelope_is_server_owned_and_deterministic() -> None:
    first = safety.execution_envelope(
        "ops_kpi_query",
        arguments={"metric": "orders"},
    )
    second = safety.execution_envelope(
        "ops_kpi_query",
        arguments={"metric": "orders"},
    )

    assert first == second
    assert first.maximum_bytes_billed == 250 * 1024 * 1024
    assert first.timeout_ms == 20_000
    assert first.max_rows == 500
    assert first.side_effect_class == "read"
    assert len(first.safety_policy_fingerprint) == 64


def test_regulatory_tool_has_tighter_result_budget() -> None:
    envelope = safety.execution_envelope(
        "regulatory_impact_query",
        arguments={"topic": "food labeling"},
    )
    assert envelope.risk_class == "medium"
    assert envelope.data_sensitivity == "confidential"
    assert envelope.max_rows == 250


def test_unknown_tool_fails_closed() -> None:
    with pytest.raises(safety.JarvisSafetyPolicyDenied):
        safety.execution_envelope(  # type: ignore[arg-type]
            "unknown_tool",
            arguments={},
        )


def test_argument_depth_is_bounded() -> None:
    nested: dict[str, object] = {"value": "ok"}
    for _ in range(10):
        nested = {"nested": nested}

    with pytest.raises(safety.JarvisSafetyPolicyDenied, match="depth"):
        safety.execution_envelope(
            "ops_kpi_query",
            arguments=nested,
        )


def test_argument_node_count_is_bounded() -> None:
    arguments = {"values": list(range(1200))}
    with pytest.raises(safety.JarvisSafetyPolicyDenied, match="complexity"):
        safety.execution_envelope(
            "ops_kpi_query",
            arguments=arguments,
        )


def test_argument_string_budget_counts_keys_and_values() -> None:
    arguments = {"payload": "x" * (64 * 1024)}
    with pytest.raises(safety.JarvisSafetyPolicyDenied, match="text size"):
        safety.execution_envelope(
            "ops_kpi_query",
            arguments=arguments,
        )


def test_policy_models_forbid_unreviewed_fields() -> None:
    with pytest.raises(ValueError):
        safety.ToolSafetyPolicy.model_validate(
            {
                "risk_class": "low",
                "data_sensitivity": "internal",
                "side_effect_class": "read",
                "requires_human_approval": False,
                "maximum_bytes_billed": 1,
                "timeout_ms": 1000,
                "max_rows": 1,
                "max_argument_depth": 1,
                "max_argument_nodes": 1,
                "max_argument_string_bytes": 1,
                "unreviewed": True,
            }
        )
