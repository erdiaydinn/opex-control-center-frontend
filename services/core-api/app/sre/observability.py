"""Master 45 observability and Master 46 production-shape load contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TelemetryEvent:
    signal: str
    service: str
    environment: str
    workflow: str
    operation: str
    result: str
    dimensions: Mapping[str, str]


def load_observability_contract(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported observability schema")

    required = data.get("required_signals", [])
    if not isinstance(required, list) or not required:
        raise ValueError("observability required signals are missing")
    if len(set(required)) != len(required):
        raise ValueError("duplicate required signal")

    required_dimensions = data.get("required_dimensions", [])
    if not isinstance(required_dimensions, list) or not required_dimensions:
        raise ValueError("observability required dimensions are missing")
    return data


def validate_telemetry_event(
    contract: dict[str, object],
    event: TelemetryEvent,
) -> None:
    if event.signal not in contract["required_signals"]:
        raise ValueError("unregistered telemetry signal")
    authority_dimensions = (
        event.service,
        event.environment,
        event.workflow,
        event.operation,
        event.result,
    )
    if not all(value.strip() for value in authority_dimensions):
        raise ValueError("telemetry authority dimensions required")

    forbidden = {str(value) for value in contract["forbidden_dimensions"]}
    if forbidden & set(event.dimensions):
        raise ValueError("sensitive telemetry dimension forbidden")

    required_dimensions = {str(value) for value in contract["required_dimensions"]}
    required_event_dimensions = required_dimensions - {
        "service",
        "environment",
        "workflow",
        "operation",
        "result",
    }
    if not required_event_dimensions <= set(event.dimensions):
        raise ValueError("required telemetry dimensions missing")


def load_profiles(path: Path) -> tuple[dict[str, object], ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported load profile schema")

    profiles = tuple(data.get("profiles", ()))
    keys = [str(profile.get("key", "")) for profile in profiles]
    if not profiles or len(keys) != len(set(keys)):
        raise ValueError("duplicate or missing load profile")

    forbidden = {"SYNTHETIC", "REPOSITORY"}
    if any(profile.get("evidence_class") in forbidden for profile in profiles):
        raise ValueError("production-shape profile cannot be synthetic")
    return profiles
