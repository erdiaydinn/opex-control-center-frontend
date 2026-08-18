from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.company_source_adapter_registry import (
    AdapterAcceptance,
    CompanySourceAdapterDescriptor,
    CompanySourceAdapterRegistry,
    CompanySourceOperation,
    CompanySourceProtocol,
    field_proven_routes,
    resolve_company_source_route,
)
from app.live_company_reality import LiveSourceKind
from app.live_company_source_runtime import ReadOnlySourcePlan
from app.mission_execution import (
    CapabilityExecutionOutcome,
    MissionExecutionKind,
    MissionExecutionSpec,
)
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
from app.parallel_mission_orchestration import (
    ParallelLaneBindings,
    ParallelLaneDisposition,
    ParallelMissionLane,
    ParallelMissionPlan,
    execute_parallel_mission_round,
    select_parallel_wave,
)

NOW = datetime(2026, 8, 19, 1, 30, tzinfo=timezone.utc)


class _UnusedGateway:
    pass


def _writer(_receipt: object) -> str:
    return "evidence://reasoning"


def _lane(
    *,
    lane_id: str,
    tenant_id: str = "YS_TR",
    capability_ref: str,
    priority: int = 50,
    side_effect: bool = False,
    resource_ref: str | None = None,
    idempotency_key: str | None = None,
    truth_requirement: str | None = None,
) -> ParallelMissionLane:
    step = MissionStep(
        step_id="step-1",
        description="advance lane",
        side_effect=side_effect,
        idempotency_key=(idempotency_key or f"idem-{lane_id}-0123456789") if side_effect else None,
        effect_verifier_ref="effect://authoritative" if side_effect else None,
    )
    definition = MissionDefinition(
        mission_id=f"mission-{lane_id}",
        objective=f"objective {lane_id}",
        tenant_id=tenant_id,
        steps=(step,),
    )
    spec = MissionExecutionSpec(
        step_id="step-1",
        kind=MissionExecutionKind.CAPABILITY,
        capability_ref=capability_ref,
        decision_truth_requirement_id=truth_requirement,
    )
    return ParallelMissionLane(
        lane_id=lane_id,
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(spec,),
        priority=priority,
        exclusive_resource_refs=(() if resource_ref is None else (resource_ref,)),
    )


def _bindings(lane: ParallelMissionLane, calls: list[str]) -> ParallelLaneBindings:
    capability_ref = lane.specs[0].capability_ref or ""

    async def handler(_definition, step, _state, _idempotency_key):
        calls.append(lane.lane_id)
        return CapabilityExecutionOutcome(
            succeeded=True,
            effect_verified=step.side_effect,
            evidence_refs=(f"evidence://{lane.lane_id}",),
            transaction_ref=(f"transaction://{lane.lane_id}" if step.side_effect else None),
        )

    return ParallelLaneBindings(
        gateway=_UnusedGateway(),  # type: ignore[arg-type]
        reasoning_evidence_writer=_writer,  # type: ignore[arg-type]
        capability_handlers={capability_ref: handler},
    )


def test_parallel_wave_serializes_two_writes_to_same_resource():
    first = _lane(
        lane_id="inventory",
        capability_ref="inventory.adjust",
        priority=90,
        side_effect=True,
        resource_ref="store://fulya/inventory",
    )
    second = _lane(
        lane_id="replenishment",
        capability_ref="replenishment.adjust",
        priority=80,
        side_effect=True,
        resource_ref="store://fulya/inventory",
    )
    plan = ParallelMissionPlan(objective_ref="objective://fulya", tenant_id="YS_TR", lanes=(first, second))
    selected, deferred = select_parallel_wave(plan)
    assert selected == ("inventory",)
    assert deferred["replenishment"] == ("parallel_resource_conflict",)


def test_parallel_wave_serializes_duplicate_side_effect_idempotency_even_across_resources():
    key = "same-idempotency-key-0000000001"
    first = _lane(
        lane_id="a",
        capability_ref="cap.a",
        priority=90,
        side_effect=True,
        resource_ref="resource://a",
        idempotency_key=key,
    )
    second = _lane(
        lane_id="b",
        capability_ref="cap.b",
        priority=80,
        side_effect=True,
        resource_ref="resource://b",
        idempotency_key=key,
    )
    plan = ParallelMissionPlan(objective_ref="objective://safe", tenant_id="YS_TR", lanes=(first, second))
    selected, deferred = select_parallel_wave(plan)
    assert selected == ("a",)
    assert deferred["b"] == ("parallel_idempotency_conflict",)


@pytest.mark.asyncio
async def test_missing_live_truth_blocks_only_its_lane_while_independent_lane_advances():
    truth_lane = _lane(
        lane_id="truth-blocked",
        capability_ref="company.read",
        priority=90,
        truth_requirement="truth.orders",
    )
    independent = _lane(lane_id="research", capability_ref="research.read", priority=80)
    plan = ParallelMissionPlan(
        objective_ref="objective://parallel",
        tenant_id="YS_TR",
        lanes=(truth_lane, independent),
        max_parallel_lanes=2,
    )
    calls: list[str] = []
    result = await execute_parallel_mission_round(
        plan=plan,
        bindings={
            truth_lane.lane_id: _bindings(truth_lane, calls),
            independent.lane_id: _bindings(independent, calls),
        },
    )
    assert set(result.selected_lane_ids) == {"truth-blocked", "research"}
    by_lane = {item.lane_id: item for item in result.results}
    assert "live_company_truth_receipt_missing:step-1" in by_lane["truth-blocked"].blockers
    assert by_lane["truth-blocked"].summary is not None
    assert by_lane["truth-blocked"].summary.transitions_executed == 0
    assert by_lane["research"].summary is not None
    assert by_lane["research"].summary.transitions_executed == 1
    assert calls == ["research"]
    assert result.shared_execution_authority_granted is False


@pytest.mark.asyncio
async def test_resource_conflicted_lane_is_deferred_and_not_executed():
    first = _lane(
        lane_id="first",
        capability_ref="cap.first",
        priority=90,
        side_effect=True,
        resource_ref="resource://shared",
    )
    second = _lane(
        lane_id="second",
        capability_ref="cap.second",
        priority=80,
        side_effect=True,
        resource_ref="resource://shared",
    )
    plan = ParallelMissionPlan(objective_ref="objective://writes", tenant_id="YS_TR", lanes=(first, second))
    calls: list[str] = []
    result = await execute_parallel_mission_round(
        plan=plan,
        bindings={first.lane_id: _bindings(first, calls), second.lane_id: _bindings(second, calls)},
    )
    by_lane = {item.lane_id: item for item in result.results}
    assert by_lane["first"].disposition is ParallelLaneDisposition.EXECUTED
    assert by_lane["second"].disposition is ParallelLaneDisposition.DEFERRED
    assert by_lane["second"].blockers == ("parallel_resource_conflict",)
    assert calls == ["first"]


def test_parallel_plan_rejects_cross_tenant_lane():
    lane = _lane(lane_id="foreign", tenant_id="DE_DE", capability_ref="read")
    with pytest.raises(ValueError, match="parallel_cross_tenant_lane_forbidden"):
        ParallelMissionPlan(objective_ref="objective://x", tenant_id="YS_TR", lanes=(lane,))


def _operation() -> CompanySourceOperation:
    return CompanySourceOperation(
        operation_ref="orders.summary.v2",
        contract_ref="query-contract://ops.kpi.orders.v2",
        allowed_fields=("orders.total", "orders.cancel_rate"),
        parameter_names=("tenant_id", "start_at", "end_at"),
    )


def _adapter(*, acceptance: AdapterAcceptance = AdapterAcceptance.CONTROLLED, field_proven: bool = False):
    return CompanySourceAdapterDescriptor(
        adapter_ref="adapter://bigquery/orders-v2",
        source_kind=LiveSourceKind.ORDERS,
        protocol=CompanySourceProtocol.BIGQUERY,
        source_ref="bigquery://curated_data_shared/orders",
        schema_contract="orders-v2",
        schema_version="2",
        environment_ref="env://production-readonly",
        execution_identity_ref="identity://orders-reader",
        operations=(_operation(),),
        acceptance=acceptance,
        field_production_verified=field_proven,
    )


def _plan(*, fields: tuple[str, ...] = ("orders.total",)) -> ReadOnlySourcePlan:
    return ReadOnlySourcePlan(
        binding_id="binding-orders-v2",
        tenant_id="YS_TR",
        source_kind=LiveSourceKind.ORDERS,
        source_ref="bigquery://curated_data_shared/orders",
        schema_contract="orders-v2",
        schema_version="2",
        environment_ref="env://production-readonly",
        execution_identity_ref="identity://orders-reader",
        operation_ref="orders.summary.v2",
        requested_fields=fields,
        requested_at=NOW,
    )


def test_company_source_route_is_exact_but_never_truth_authority():
    registry = CompanySourceAdapterRegistry(tenant_id="YS_TR", adapters=(_adapter(),))
    route = resolve_company_source_route(registry=registry, plan=_plan(), adapter_ref="adapter://bigquery/orders-v2")
    assert route.acceptance is AdapterAcceptance.CONTROLLED
    assert route.truth_authority_granted is False
    assert route.execution_authority_granted is False
    assert field_proven_routes(registry) == ()


def test_company_source_route_rejects_unregistered_field():
    registry = CompanySourceAdapterRegistry(tenant_id="YS_TR", adapters=(_adapter(),))
    with pytest.raises(ValueError, match="company_source_route_requested_field_not_allowed"):
        resolve_company_source_route(
            registry=registry,
            plan=_plan(fields=("orders.customer_email",)),
            adapter_ref="adapter://bigquery/orders-v2",
        )


def test_adapter_cannot_self_claim_field_proof_without_field_proven_acceptance():
    with pytest.raises(ValueError, match="company_source_adapter_field_acceptance_mismatch"):
        _adapter(acceptance=AdapterAcceptance.CONTROLLED, field_proven=True)


def test_field_proven_registry_inventory_does_not_promote_truth():
    adapter = _adapter(acceptance=AdapterAcceptance.FIELD_PROVEN, field_proven=True)
    registry = CompanySourceAdapterRegistry(tenant_id="YS_TR", adapters=(adapter,))
    assert field_proven_routes(registry, source_kind=LiveSourceKind.ORDERS) == (
        "adapter://bigquery/orders-v2",
    )
    route = resolve_company_source_route(registry=registry, plan=_plan(), adapter_ref=adapter.adapter_ref)
    assert route.field_production_verified is True
    assert route.truth_authority_granted is False
