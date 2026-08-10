from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .kpi_registry import KPI_REGISTRY, KpiDefinition
from .kpi_runtime_contracts import (
    DURATION_RUNTIME_CONTRACTS,
    DURATION_RUNTIME_METRICS,
    RATE_RUNTIME_CONTRACTS,
    RATE_RUNTIME_METRICS,
)


@dataclass(frozen=True)
class KpiReleaseGuardResult:
    executable_metrics: tuple[str, ...]
    duration_runtime_metrics: tuple[str, ...]
    rate_runtime_metrics: tuple[str, ...]
    passed: bool = True


def verify_kpi_registry_runtime_alignment(
    *,
    registry: Mapping[str, KpiDefinition] = KPI_REGISTRY,
    duration_contracts: Mapping[str, object] = DURATION_RUNTIME_CONTRACTS,
    rate_contracts: Mapping[str, object] = RATE_RUNTIME_CONTRACTS,
) -> KpiReleaseGuardResult:
    """Block releases that expose a runtime-sensitive KPI without its reviewed contract.

    This is intentionally independent of BigQuery availability. A future code review that
    flips Prep/Picking/OTP to executable must add the corresponding runtime contract in the
    same release, otherwise CI can fail before any production query is attempted.
    """

    executable = tuple(sorted(metric for metric, definition in registry.items() if definition.executable))

    missing_duration = sorted(
        metric for metric in executable if metric in DURATION_RUNTIME_METRICS and metric not in duration_contracts
    )
    missing_rate = sorted(
        metric for metric in executable if metric in RATE_RUNTIME_METRICS and metric not in rate_contracts
    )
    if missing_duration or missing_rate:
        blockers = []
        if missing_duration:
            blockers.append("duration=" + ",".join(missing_duration))
        if missing_rate:
            blockers.append("rate=" + ",".join(missing_rate))
        raise ValueError("kpi_release_runtime_contract_missing:" + ";".join(blockers))

    unknown_duration = sorted(set(duration_contracts) - set(DURATION_RUNTIME_METRICS))
    unknown_rate = sorted(set(rate_contracts) - set(RATE_RUNTIME_METRICS))
    if unknown_duration or unknown_rate:
        blockers = []
        if unknown_duration:
            blockers.append("duration=" + ",".join(unknown_duration))
        if unknown_rate:
            blockers.append("rate=" + ",".join(unknown_rate))
        raise ValueError("kpi_release_unregistered_runtime_contract:" + ";".join(blockers))

    return KpiReleaseGuardResult(
        executable_metrics=executable,
        duration_runtime_metrics=tuple(sorted(duration_contracts)),
        rate_runtime_metrics=tuple(sorted(rate_contracts)),
    )
