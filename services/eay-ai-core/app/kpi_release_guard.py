from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .kpi_registry import KPI_REGISTRY, KpiDefinition
from .kpi_result_validation import KPI_RESULT_CONTRACTS
from .kpi_runtime_contracts import (
    DURATION_RUNTIME_CONTRACTS,
    DURATION_RUNTIME_METRICS,
    PUTAWAY_RUNTIME_CONTRACTS,
    PUTAWAY_RUNTIME_METRICS,
    RATE_RUNTIME_CONTRACTS,
    RATE_RUNTIME_METRICS,
)

RESULT_CONTRACT_REQUIRED_METRICS = frozenset({"nsfr", "pfr", "refund"})


@dataclass(frozen=True)
class KpiReleaseGuardResult:
    executable_metrics: tuple[str, ...]
    duration_runtime_metrics: tuple[str, ...]
    rate_runtime_metrics: tuple[str, ...]
    putaway_runtime_metrics: tuple[str, ...]
    result_contract_metrics: tuple[str, ...]
    passed: bool = True


def _registry_activation_intent(definition: KpiDefinition) -> bool:
    """Return true as soon as a registry entry is being prepared for activation.

    Runtime/result contract safety must be checked *before* the newer promotion and
    registry-binding fingerprints are sealed. Otherwise adding stricter promotion
    fields can accidentally hide an incomplete activation from the release guard simply
    because ``definition.executable`` remains false until the final review step.
    """

    return (
        definition.review_state == "reviewed"
        and bool(definition.query_id)
        and bool(definition.schema_contract_id)
        and bool(definition.semantic_contract_id)
    )


def verify_kpi_registry_runtime_alignment(
    *,
    registry: Mapping[str, KpiDefinition] = KPI_REGISTRY,
    duration_contracts: Mapping[str, object] = DURATION_RUNTIME_CONTRACTS,
    rate_contracts: Mapping[str, object] = RATE_RUNTIME_CONTRACTS,
    putaway_contracts: Mapping[str, object] = PUTAWAY_RUNTIME_CONTRACTS,
    result_contracts: Mapping[str, object] = KPI_RESULT_CONTRACTS,
) -> KpiReleaseGuardResult:
    """Block releases that prepare a governed KPI without all runtime/result contracts.

    This is intentionally independent of BigQuery availability and of final registry
    promotion sealing. A code review that starts activating Prep/Picking/OTP/Putaway or
    the NSFR family must add the corresponding runtime and post-query result contracts
    in the same release. The guard evaluates activation intent rather than only the final
    ``executable`` property so stricter promotion gates can never mask missing safety
    contracts.
    """

    activation_candidates = tuple(
        sorted(metric for metric, definition in registry.items() if _registry_activation_intent(definition))
    )
    executable = tuple(sorted(metric for metric, definition in registry.items() if definition.executable))

    missing_duration = sorted(
        metric
        for metric in activation_candidates
        if metric in DURATION_RUNTIME_METRICS and metric not in duration_contracts
    )
    missing_rate = sorted(
        metric
        for metric in activation_candidates
        if metric in RATE_RUNTIME_METRICS and metric not in rate_contracts
    )
    missing_putaway = sorted(
        metric
        for metric in activation_candidates
        if metric in PUTAWAY_RUNTIME_METRICS and metric not in putaway_contracts
    )
    missing_result = sorted(
        metric
        for metric in activation_candidates
        if metric in RESULT_CONTRACT_REQUIRED_METRICS and metric not in result_contracts
    )
    if missing_duration or missing_rate or missing_putaway or missing_result:
        blockers = []
        if missing_duration:
            blockers.append("duration=" + ",".join(missing_duration))
        if missing_rate:
            blockers.append("rate=" + ",".join(missing_rate))
        if missing_putaway:
            blockers.append("putaway=" + ",".join(missing_putaway))
        if missing_result:
            blockers.append("result=" + ",".join(missing_result))
        raise ValueError("kpi_release_runtime_contract_missing:" + ";".join(blockers))

    unknown_duration = sorted(set(duration_contracts) - set(DURATION_RUNTIME_METRICS))
    unknown_rate = sorted(set(rate_contracts) - set(RATE_RUNTIME_METRICS))
    unknown_putaway = sorted(set(putaway_contracts) - set(PUTAWAY_RUNTIME_METRICS))
    unknown_result = sorted(set(result_contracts) - set(RESULT_CONTRACT_REQUIRED_METRICS))
    if unknown_duration or unknown_rate or unknown_putaway or unknown_result:
        blockers = []
        if unknown_duration:
            blockers.append("duration=" + ",".join(unknown_duration))
        if unknown_rate:
            blockers.append("rate=" + ",".join(unknown_rate))
        if unknown_putaway:
            blockers.append("putaway=" + ",".join(unknown_putaway))
        if unknown_result:
            blockers.append("result=" + ",".join(unknown_result))
        raise ValueError("kpi_release_unregistered_runtime_contract:" + ";".join(blockers))

    return KpiReleaseGuardResult(
        executable_metrics=executable,
        duration_runtime_metrics=tuple(sorted(duration_contracts)),
        rate_runtime_metrics=tuple(sorted(rate_contracts)),
        putaway_runtime_metrics=tuple(sorted(putaway_contracts)),
        result_contract_metrics=tuple(sorted(result_contracts)),
    )
