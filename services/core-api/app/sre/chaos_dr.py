"""Master 47 chaos and Master 48 disaster-recovery acceptance authority."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChaosResult:
    scenario: str
    environment: str
    measured: bool
    passed_invariants: tuple[str, ...]
    provenance: str


@dataclass(frozen=True)
class DrResult:
    environment: str
    restore_passed: bool
    rpo_seconds: int | None
    rto_seconds: int | None
    provenance: str


def load_chaos_dr_contract(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported chaos/DR schema")
    if len(data.get("chaos_scenarios", [])) != 14:
        raise ValueError("Master 47 requires all fourteen chaos scenarios")
    if data["dr"].get("environment") != "MANAGED_STAGING_REQUIRED":
        raise ValueError("DR environment weakened")
    if data["dr"].get("rpo_seconds") != "MEASURED_REQUIRED":
        raise ValueError("DR RPO measurement requirement weakened")
    if data["dr"].get("rto_seconds") != "MEASURED_REQUIRED":
        raise ValueError("DR RTO measurement requirement weakened")
    return data


def chaos_result_accepted(
    contract: dict[str, object],
    result: ChaosResult,
) -> bool:
    forbidden_environments = {"ci", "repository", "synthetic"}
    return (
        result.scenario in contract["chaos_scenarios"]
        and result.environment.casefold() not in forbidden_environments
        and result.measured
        and set(contract["required_invariants"]) <= set(result.passed_invariants)
        and bool(result.provenance.strip())
    )


def dr_result_accepted(result: DrResult) -> bool:
    forbidden_environments = {"ci", "repository", "synthetic"}
    return (
        result.environment.casefold() not in forbidden_environments
        and result.restore_passed
        and result.rpo_seconds is not None
        and result.rto_seconds is not None
        and result.rpo_seconds >= 0
        and result.rto_seconds >= 0
        and bool(result.provenance.strip())
    )
