from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

from .kpi_activation_gate import (
    verify_duration_kpi_activation,
    verify_rate_kpi_activation,
)
from .kpi_aggregation_contracts import WeightedAverageContract
from .kpi_provenance import provenance_from_activation
from .kpi_unit_contracts import DurationContract, RateContract


@dataclass(frozen=True)
class DurationRuntimeContract:
    unit: DurationContract
    aggregation: WeightedAverageContract


# Deliberately empty until production schema evidence also pins units/grain.
# Adding a KPI to KPI_REGISTRY as executable without adding its reviewed runtime
# contract here will still fail closed in tool_execution.
DURATION_RUNTIME_CONTRACTS: dict[str, DurationRuntimeContract] = {}
RATE_RUNTIME_CONTRACTS: dict[str, RateContract] = {}

DURATION_RUNTIME_METRICS = frozenset({"prep", "picking"})
RATE_RUNTIME_METRICS = frozenset({"otp"})


def _with_provenance(
    *,
    metric: str,
    bundle: object,
    semantic_verification: Mapping[str, object],
    schema_verification: Mapping[str, object],
) -> dict[str, object]:
    result = asdict(bundle)
    result["activation_provenance_fingerprint"] = provenance_from_activation(
        metric=metric,
        semantic_verification=semantic_verification,
        schema_verification=schema_verification,
        runtime_activation=result,
    )
    return result


def verify_kpi_runtime_activation(
    *,
    metric: str,
    semantic_verification: Mapping[str, object],
    schema_verification: Mapping[str, object],
) -> dict[str, object] | None:
    """Verify runtime-only KPI contracts after semantic + live schema verification.

    Orders/count KPIs do not require unit/grain contracts. Duration and rate KPIs do.
    The runtime registries remain empty until reviewed production evidence pins the
    source unit/scale and aggregation grain, preventing a registry-only activation.
    """

    if metric in DURATION_RUNTIME_METRICS:
        runtime = DURATION_RUNTIME_CONTRACTS.get(metric)
        if runtime is None:
            raise ValueError(f"kpi_runtime_contract_required:{metric}")
        bundle = verify_duration_kpi_activation(
            metric=metric,
            semantic_verification=semantic_verification,
            schema_verification=schema_verification,
            unit_contract=runtime.unit,
            aggregation_contract=runtime.aggregation,
        )
        return _with_provenance(
            metric=metric,
            bundle=bundle,
            semantic_verification=semantic_verification,
            schema_verification=schema_verification,
        )

    if metric in RATE_RUNTIME_METRICS:
        contract = RATE_RUNTIME_CONTRACTS.get(metric)
        if contract is None:
            raise ValueError(f"kpi_runtime_contract_required:{metric}")
        bundle = verify_rate_kpi_activation(
            metric=metric,
            semantic_verification=semantic_verification,
            schema_verification=schema_verification,
            rate_contract=contract,
        )
        return _with_provenance(
            metric=metric,
            bundle=bundle,
            semantic_verification=semantic_verification,
            schema_verification=schema_verification,
        )

    return None
