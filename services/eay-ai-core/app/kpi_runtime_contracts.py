from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Mapping

from .kpi_activation_gate import (
    verify_duration_kpi_activation,
    verify_rate_kpi_activation,
)
from .kpi_aggregation_contracts import WeightedAverageContract
from .kpi_provenance import provenance_from_activation
from .kpi_putaway_contracts import PutawayQuantityContract, verify_putaway_activation
from .kpi_putaway_sla import PutawaySlaContract, resolve_putaway_sla_contract
from .kpi_rate_aggregation import RateAggregationContract
from .kpi_unit_contracts import DurationContract, RateContract


@dataclass(frozen=True)
class DurationRuntimeContract:
    unit: DurationContract
    aggregation: WeightedAverageContract


@dataclass(frozen=True)
class RateRuntimeContract:
    unit: RateContract
    aggregation: RateAggregationContract


@dataclass(frozen=True)
class PutawayRuntimeContract:
    sla_contracts: tuple[PutawaySlaContract, ...]
    quantity: PutawayQuantityContract = PutawayQuantityContract()


# Deliberately empty until production schema evidence also pins units/grain/policy.
# Adding a KPI to KPI_REGISTRY as executable without adding its reviewed runtime
# contract here will still fail closed in tool_execution.
DURATION_RUNTIME_CONTRACTS: dict[str, DurationRuntimeContract] = {}
RATE_RUNTIME_CONTRACTS: dict[str, RateRuntimeContract] = {}
PUTAWAY_RUNTIME_CONTRACTS: dict[str, PutawayRuntimeContract] = {}

DURATION_RUNTIME_METRICS = frozenset({"prep", "picking"})
RATE_RUNTIME_METRICS = frozenset({"otp"})
PUTAWAY_RUNTIME_METRICS = frozenset({"putaway"})


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
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object] | None:
    """Verify runtime-only KPI contracts after semantic + live schema verification.

    Rate KPIs require a pinned numerator/denominator aggregation contract, preventing
    average-of-percentages drift. Putaway additionally requires one reviewed SLA
    contract to cover the entire requested window.
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
        runtime = RATE_RUNTIME_CONTRACTS.get(metric)
        if runtime is None:
            raise ValueError(f"kpi_runtime_contract_required:{metric}")
        bundle = verify_rate_kpi_activation(
            metric=metric,
            semantic_verification=semantic_verification,
            schema_verification=schema_verification,
            rate_contract=runtime.unit,
            aggregation_contract=runtime.aggregation,
        )
        return _with_provenance(
            metric=metric,
            bundle=bundle,
            semantic_verification=semantic_verification,
            schema_verification=schema_verification,
        )

    if metric in PUTAWAY_RUNTIME_METRICS:
        runtime = PUTAWAY_RUNTIME_CONTRACTS.get(metric)
        if runtime is None:
            raise ValueError(f"kpi_runtime_contract_required:{metric}")
        if start_date is None or end_date is None:
            raise ValueError("kpi_runtime_date_window_required:putaway")
        start_sla = resolve_putaway_sla_contract(runtime.sla_contracts, as_of=start_date)
        end_sla = resolve_putaway_sla_contract(runtime.sla_contracts, as_of=end_date)
        if start_sla.fingerprint != end_sla.fingerprint:
            raise ValueError("putaway_runtime_query_spans_sla_versions")
        if start_sla.effective_from > start_date or (
            start_sla.effective_to is not None and start_sla.effective_to < end_date
        ):
            raise ValueError("putaway_runtime_sla_does_not_cover_query_window")
        bundle = verify_putaway_activation(
            semantic_verification=semantic_verification,
            schema_verification=schema_verification,
            sla_contracts=(start_sla,),
            as_of=end_date,
            quantity_contract=runtime.quantity,
        )
        return _with_provenance(
            metric=metric,
            bundle=bundle,
            semantic_verification=semantic_verification,
            schema_verification=schema_verification,
        )

    return None
