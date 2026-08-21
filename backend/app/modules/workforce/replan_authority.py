"""Intraday replan / what-if authority for roadmap 15/60.

Scenarios are hypotheses over immutable Workforce truth. They do not mutate the
current schedule, demand, capacity, DPI or optimizer proposal. KPI and cost deltas
are produced only from explicit versioned sensitivity/cost assumptions with
provenance; the engine never invents tenant KPI semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json

ZERO = Decimal("0")


class ReplanAuthorityError(ValueError):
    pass


def _decimal_text(value: Decimal) -> str:
    if value == ZERO:
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _hash(value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ScenarioShock:
    shock_id: str
    shock_type: str
    demand_delta_man_hours: Decimal = ZERO
    capacity_loss_man_hours: Decimal = ZERO
    source_ref: str = ""

    def __post_init__(self) -> None:
        if not self.shock_id.strip():
            raise ReplanAuthorityError("shock_id is required")
        if self.shock_type not in {"absence", "order_spike", "inbound_delay", "manual_hypothesis"}:
            raise ReplanAuthorityError(f"unsupported scenario shock: {self.shock_type}")
        if self.demand_delta_man_hours < ZERO or self.capacity_loss_man_hours < ZERO:
            raise ReplanAuthorityError("scenario shock deltas cannot be negative")
        if self.demand_delta_man_hours == ZERO and self.capacity_loss_man_hours == ZERO:
            raise ReplanAuthorityError("scenario shock must change demand or capacity")
        if self.shock_type == "absence" and self.capacity_loss_man_hours == ZERO:
            raise ReplanAuthorityError("absence shock requires capacity_loss_man_hours")
        if self.shock_type == "order_spike" and self.demand_delta_man_hours == ZERO:
            raise ReplanAuthorityError("order_spike shock requires demand_delta_man_hours")
        if self.shock_type == "inbound_delay" and self.demand_delta_man_hours == ZERO:
            raise ReplanAuthorityError("inbound_delay shock requires demand_delta_man_hours")
        if not self.source_ref.strip():
            raise ReplanAuthorityError("scenario shock requires source_ref provenance")

    def canonical(self) -> dict[str, str]:
        return {
            "shock_id": self.shock_id,
            "shock_type": self.shock_type,
            "demand_delta_man_hours": _decimal_text(self.demand_delta_man_hours),
            "capacity_loss_man_hours": _decimal_text(self.capacity_loss_man_hours),
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class KpiSensitivity:
    kpi_key: str
    delta_per_dpi_point: Decimal
    model_version: str
    source_ref: str

    def __post_init__(self) -> None:
        if not self.kpi_key.strip():
            raise ReplanAuthorityError("KPI sensitivity key is required")
        if not self.model_version.strip():
            raise ReplanAuthorityError("KPI sensitivity model_version is required")
        if not self.source_ref.strip():
            raise ReplanAuthorityError("KPI sensitivity requires source_ref provenance")

    def canonical(self) -> dict[str, str]:
        return {
            "kpi_key": self.kpi_key,
            "delta_per_dpi_point": _decimal_text(self.delta_per_dpi_point),
            "model_version": self.model_version,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class CostAssumption:
    incremental_cost_minor_units_per_man_hour: Decimal
    model_version: str
    source_ref: str

    def __post_init__(self) -> None:
        if self.incremental_cost_minor_units_per_man_hour < ZERO:
            raise ReplanAuthorityError("cost per man-hour cannot be negative")
        if not self.model_version.strip() or not self.source_ref.strip():
            raise ReplanAuthorityError("cost assumption requires version and provenance")

    def canonical(self) -> dict[str, str]:
        return {
            "incremental_cost_minor_units_per_man_hour": _decimal_text(
                self.incremental_cost_minor_units_per_man_hour
            ),
            "model_version": self.model_version,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class ReplanBaseline:
    demand_snapshot_fingerprint: str
    capacity_snapshot_fingerprint: str
    dpi_snapshot_fingerprint: str
    optimizer_proposal_fingerprint: str
    required_man_hours: Decimal
    effective_man_hours: Decimal
    demand_pressure_index: Decimal
    current_optimizer_cost_minor_units: int

    def __post_init__(self) -> None:
        for value, name in (
            (self.required_man_hours, "required_man_hours"),
            (self.effective_man_hours, "effective_man_hours"),
            (self.demand_pressure_index, "demand_pressure_index"),
        ):
            if value < ZERO:
                raise ReplanAuthorityError(f"{name} cannot be negative")
        if self.current_optimizer_cost_minor_units < 0:
            raise ReplanAuthorityError("current optimizer cost cannot be negative")
        for fingerprint, name in (
            (self.demand_snapshot_fingerprint, "demand_snapshot_fingerprint"),
            (self.capacity_snapshot_fingerprint, "capacity_snapshot_fingerprint"),
            (self.dpi_snapshot_fingerprint, "dpi_snapshot_fingerprint"),
            (self.optimizer_proposal_fingerprint, "optimizer_proposal_fingerprint"),
        ):
            if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
                raise ReplanAuthorityError(f"{name} must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class ReplanScenarioRequest:
    tenant_id: str
    location_id: str
    model_version: str
    baseline: ReplanBaseline
    shocks: tuple[ScenarioShock, ...]
    kpi_sensitivities: tuple[KpiSensitivity, ...]
    cost_assumption: CostAssumption

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not self.location_id.strip():
            raise ReplanAuthorityError("tenant_id and location_id are required")
        if not self.model_version.strip():
            raise ReplanAuthorityError("scenario model_version is required")
        if not self.shocks:
            raise ReplanAuthorityError("at least one scenario shock is required")
        shock_ids = [item.shock_id for item in self.shocks]
        if len(shock_ids) != len(set(shock_ids)):
            raise ReplanAuthorityError("scenario shock ids must be unique")
        kpi_keys = [item.kpi_key for item in self.kpi_sensitivities]
        if len(kpi_keys) != len(set(kpi_keys)):
            raise ReplanAuthorityError("KPI sensitivity keys must be unique")


@dataclass(frozen=True, slots=True)
class ReplanScenario:
    tenant_id: str
    location_id: str
    model_version: str
    input_fingerprint: str
    scenario_fingerprint: str
    baseline_dpi_snapshot_fingerprint: str
    baseline_optimizer_proposal_fingerprint: str
    baseline_required_man_hours: Decimal
    baseline_effective_man_hours: Decimal
    scenario_required_man_hours: Decimal
    scenario_effective_man_hours: Decimal
    baseline_gap_man_hours: Decimal
    scenario_gap_man_hours: Decimal
    gap_delta_man_hours: Decimal
    baseline_dpi: Decimal
    scenario_dpi: Decimal
    dpi_delta: Decimal
    predicted_kpi_deltas: dict[str, Decimal]
    estimated_scenario_cost_minor_units: int
    cost_delta_minor_units: int
    recommendation: str
    replan_required: bool
    automatic_apply_permitted: bool
    human_approval_required: bool
    shocks: tuple[dict[str, str], ...]
    assumptions: dict[str, object]

    def as_record(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "location_id": self.location_id,
            "model_version": self.model_version,
            "input_fingerprint": self.input_fingerprint,
            "scenario_fingerprint": self.scenario_fingerprint,
            "baseline_dpi_snapshot_fingerprint": self.baseline_dpi_snapshot_fingerprint,
            "baseline_optimizer_proposal_fingerprint": self.baseline_optimizer_proposal_fingerprint,
            "baseline_required_man_hours": _decimal_text(self.baseline_required_man_hours),
            "baseline_effective_man_hours": _decimal_text(self.baseline_effective_man_hours),
            "scenario_required_man_hours": _decimal_text(self.scenario_required_man_hours),
            "scenario_effective_man_hours": _decimal_text(self.scenario_effective_man_hours),
            "baseline_gap_man_hours": _decimal_text(self.baseline_gap_man_hours),
            "scenario_gap_man_hours": _decimal_text(self.scenario_gap_man_hours),
            "gap_delta_man_hours": _decimal_text(self.gap_delta_man_hours),
            "baseline_dpi": _decimal_text(self.baseline_dpi),
            "scenario_dpi": _decimal_text(self.scenario_dpi),
            "dpi_delta": _decimal_text(self.dpi_delta),
            "predicted_kpi_deltas": {
                key: _decimal_text(value) for key, value in sorted(self.predicted_kpi_deltas.items())
            },
            "estimated_scenario_cost_minor_units": self.estimated_scenario_cost_minor_units,
            "cost_delta_minor_units": self.cost_delta_minor_units,
            "recommendation": self.recommendation,
            "replan_required": self.replan_required,
            "automatic_apply_permitted": self.automatic_apply_permitted,
            "human_approval_required": self.human_approval_required,
            "shocks": list(self.shocks),
            "assumptions": self.assumptions,
        }


def _dpi(required: Decimal, effective: Decimal) -> Decimal:
    if required == ZERO:
        return ZERO
    if effective == ZERO:
        return Decimal("999")
    return required / effective


def build_replan_scenario(request: ReplanScenarioRequest) -> ReplanScenario:
    shocks = tuple(sorted(request.shocks, key=lambda item: item.shock_id))
    demand_delta = sum((item.demand_delta_man_hours for item in shocks), ZERO)
    capacity_loss = sum((item.capacity_loss_man_hours for item in shocks), ZERO)

    scenario_required = request.baseline.required_man_hours + demand_delta
    scenario_effective = max(request.baseline.effective_man_hours - capacity_loss, ZERO)
    baseline_gap = max(
        request.baseline.required_man_hours - request.baseline.effective_man_hours,
        ZERO,
    )
    scenario_gap = max(scenario_required - scenario_effective, ZERO)
    gap_delta = scenario_gap - baseline_gap
    scenario_dpi = _dpi(scenario_required, scenario_effective)
    dpi_delta = scenario_dpi - request.baseline.demand_pressure_index

    sensitivities = tuple(sorted(request.kpi_sensitivities, key=lambda item: item.kpi_key))
    predicted_kpi_deltas = {
        item.kpi_key: dpi_delta * item.delta_per_dpi_point for item in sensitivities
    }

    incremental_gap = max(scenario_gap - baseline_gap, ZERO)
    scenario_incremental_cost = int(
        (incremental_gap * request.cost_assumption.incremental_cost_minor_units_per_man_hour)
        .quantize(Decimal("1"))
    )
    estimated_scenario_cost = (
        request.baseline.current_optimizer_cost_minor_units + scenario_incremental_cost
    )
    cost_delta = estimated_scenario_cost - request.baseline.current_optimizer_cost_minor_units

    replan_required = scenario_gap > Decimal("0.01") or dpi_delta > Decimal("0.05")
    if replan_required:
        shock_types = {item.shock_type for item in shocks}
        if "absence" in shock_types and capacity_loss > ZERO:
            recommendation = "rerun_constraint_optimizer_for_capacity_loss"
        elif "order_spike" in shock_types:
            recommendation = "rerun_constraint_optimizer_for_demand_spike"
        elif "inbound_delay" in shock_types:
            recommendation = "resequence_intraday_work_and_rerun_optimizer"
        else:
            recommendation = "rerun_constraint_optimizer"
    else:
        recommendation = "keep_current_plan"

    automatic_apply_permitted = False
    human_approval_required = replan_required
    canonical_shocks = tuple(item.canonical() for item in shocks)
    assumptions: dict[str, object] = {
        "kpi_sensitivities": [item.canonical() for item in sensitivities],
        "cost_assumption": request.cost_assumption.canonical(),
        "predictions_are_scenario_estimates_not_observed_kpis": True,
    }
    input_payload = {
        "tenant_id": request.tenant_id,
        "location_id": request.location_id,
        "model_version": request.model_version,
        "baseline": {
            "demand_snapshot_fingerprint": request.baseline.demand_snapshot_fingerprint,
            "capacity_snapshot_fingerprint": request.baseline.capacity_snapshot_fingerprint,
            "dpi_snapshot_fingerprint": request.baseline.dpi_snapshot_fingerprint,
            "optimizer_proposal_fingerprint": request.baseline.optimizer_proposal_fingerprint,
            "required_man_hours": _decimal_text(request.baseline.required_man_hours),
            "effective_man_hours": _decimal_text(request.baseline.effective_man_hours),
            "demand_pressure_index": _decimal_text(request.baseline.demand_pressure_index),
            "current_optimizer_cost_minor_units": request.baseline.current_optimizer_cost_minor_units,
        },
        "shocks": list(canonical_shocks),
        "assumptions": assumptions,
    }
    input_fingerprint = _hash(input_payload)
    output_payload = {
        **input_payload,
        "input_fingerprint": input_fingerprint,
        "scenario_required_man_hours": _decimal_text(scenario_required),
        "scenario_effective_man_hours": _decimal_text(scenario_effective),
        "scenario_gap_man_hours": _decimal_text(scenario_gap),
        "dpi_delta": _decimal_text(dpi_delta),
        "predicted_kpi_deltas": {
            key: _decimal_text(value) for key, value in sorted(predicted_kpi_deltas.items())
        },
        "estimated_scenario_cost_minor_units": estimated_scenario_cost,
        "cost_delta_minor_units": cost_delta,
        "recommendation": recommendation,
        "replan_required": replan_required,
        "automatic_apply_permitted": automatic_apply_permitted,
    }
    scenario_fingerprint = _hash(output_payload)

    return ReplanScenario(
        tenant_id=request.tenant_id,
        location_id=request.location_id,
        model_version=request.model_version,
        input_fingerprint=input_fingerprint,
        scenario_fingerprint=scenario_fingerprint,
        baseline_dpi_snapshot_fingerprint=request.baseline.dpi_snapshot_fingerprint,
        baseline_optimizer_proposal_fingerprint=request.baseline.optimizer_proposal_fingerprint,
        baseline_required_man_hours=request.baseline.required_man_hours,
        baseline_effective_man_hours=request.baseline.effective_man_hours,
        scenario_required_man_hours=scenario_required,
        scenario_effective_man_hours=scenario_effective,
        baseline_gap_man_hours=baseline_gap,
        scenario_gap_man_hours=scenario_gap,
        gap_delta_man_hours=gap_delta,
        baseline_dpi=request.baseline.demand_pressure_index,
        scenario_dpi=scenario_dpi,
        dpi_delta=dpi_delta,
        predicted_kpi_deltas=predicted_kpi_deltas,
        estimated_scenario_cost_minor_units=estimated_scenario_cost,
        cost_delta_minor_units=cost_delta,
        recommendation=recommendation,
        replan_required=replan_required,
        automatic_apply_permitted=automatic_apply_permitted,
        human_approval_required=human_approval_required,
        shocks=canonical_shocks,
        assumptions=assumptions,
    )
