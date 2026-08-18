from pathlib import Path

import pytest

from app.sre.observability import (
    TelemetryEvent,
    load_observability_contract,
    load_profiles,
    validate_telemetry_event,
)

ROOT = Path(__file__).resolve().parents[3]


def test_unified_observability_requires_signal_families_and_safe_dimensions() -> None:
    contract = load_observability_contract(
        ROOT / "docs/governance/eay_observability_contract.json"
    )
    assert {
        "logs",
        "traces",
        "metrics",
        "audit",
        "ai_tool_calls",
        "business_workflow_health",
    } <= set(contract["required_signals"])

    validate_telemetry_event(
        contract,
        TelemetryEvent(
            signal="traces",
            service="budget",
            environment="staging",
            workflow="invoice",
            operation="post",
            result="ok",
            dimensions={"tenant_safe_hash": "abc"},
        ),
    )
    with pytest.raises(ValueError, match="sensitive telemetry"):
        validate_telemetry_event(
            contract,
            TelemetryEvent(
                signal="traces",
                service="budget",
                environment="staging",
                workflow="invoice",
                operation="post",
                result="ok",
                dimensions={"tenant_safe_hash": "abc", "raw_secret": "x"},
            ),
        )
    with pytest.raises(ValueError, match="required telemetry dimensions"):
        validate_telemetry_event(
            contract,
            TelemetryEvent(
                signal="metrics",
                service="inventory",
                environment="staging",
                workflow="count",
                operation="submit",
                result="ok",
                dimensions={},
            ),
        )


def test_load_profiles_cover_production_shapes_without_synthetic_acceptance() -> None:
    profiles = load_profiles(
        ROOT / "docs/governance/eay_production_shape_load_profiles.json"
    )
    by_key = {profile["key"]: profile for profile in profiles}
    assert by_key["portal_3000"]["concurrency"] == 3000
    assert by_key["inventory_400_terminals"]["concurrency"] == 400
    assert by_key["academy_1200_media"]["concurrency"] == 1200
    assert all(
        profile["evidence_class"] not in {"SYNTHETIC", "REPOSITORY"}
        for profile in profiles
    )
