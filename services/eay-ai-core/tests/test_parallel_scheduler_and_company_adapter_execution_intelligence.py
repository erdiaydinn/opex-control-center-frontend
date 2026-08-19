from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.company_source_adapter_execution import (
    CompanySourceRuntimeBinding,
    execute_registered_company_read,
)
from app.company_source_adapter_registry import (
    AdapterAcceptance,
    CompanySourceAdapterDescriptor,
    CompanySourceAdapterRegistry,
    CompanySourceOperation,
    CompanySourceProtocol,
)
from app.live_company_reality import LiveSourceBindingPolicy, LiveSourceKind
from app.live_company_source_runtime import (
    ReadOnlySourceBatch,
    ReadOnlySourceField,
    ReadOnlySourcePlan,
)
from app.mission_execution import MissionExecutionKind, MissionExecutionSpec
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
from app.parallel_mission_orchestration import ParallelMissionLane, ParallelMissionPlan
from app.parallel_mission_scheduler import (
    LaneSchedulingClass,
    ParallelLaneSchedulingProfile,
    ParallelSchedulingPolicy,
    lane_preemption_allowed,
    schedule_parallel_wave,
)
from app.world_model import TruthClass

NOW = datetime(2026, 8, 19, 5, 0, tzinfo=timezone.utc)


def _lane(
    *,
    lane_id: str,
    priority: int = 50,
    side_effect: bool = False,
    resource_ref: str | None = None,
) -> ParallelMissionLane:
    step = MissionStep(
        step_id="step-1",
        description=f"advance {lane_id}",
        side_effect=side_effect,
        idempotency_key=(f"idem-{lane_id}-0123456789" if side_effect else None),
        effect_verifier_ref=("effect://authoritative" if side_effect else None),
    )
    definition = MissionDefinition(
        mission_id=f"mission-{lane_id}",
        objective=f"objective {lane_id}",
        tenant_id="YS_TR",
        steps=(step,),
    )
    spec = MissionExecutionSpec(
        step_id="step-1",
        kind=MissionExecutionKind.CAPABILITY,
        capability_ref=f"capability://{lane_id}",
    )
    return ParallelMissionLane(
        lane_id=lane_id,
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(spec,),
        priority=priority,
        exclusive_resource_refs=(() if resource_ref is None else (resource_ref,)),
    )


def test_scheduler_deadline_can_outrank_priority_without_creating_authority():
    background = _lane(lane_id="background", priority=95)
    urgent = _lane(lane_id="urgent", priority=40)
    plan = ParallelMissionPlan(
        objective_ref="objective://scheduler",
        tenant_id="YS_TR",
        lanes=(background, urgent),
        max_parallel_lanes=2,
    )
    wave = schedule_parallel_wave(
        plan=plan,
        profiles={
            "background": ParallelLaneSchedulingProfile(
                lane_id="background",
                scheduling_class=LaneSchedulingClass.RESEARCH,
            ),
            "urgent": ParallelLaneSchedulingProfile(
                lane_id="urgent",
                scheduling_class=LaneSchedulingClass.COMPANY_READ,
                deadline_at=NOW + timedelta(seconds=30),
            ),
        },
        policy=ParallelSchedulingPolicy(max_concurrency_weight=1),
        now=NOW,
    )
    assert wave.selected_lane_ids == ("urgent",)
    assert wave.deferred["background"] == ("parallel_weight_capacity_deferred",)
    assert wave.execution_authority_granted is False


def test_scheduler_deadline_never_overrides_same_resource_write_conflict():
    urgent_read = _lane(
        lane_id="urgent-read",
        priority=90,
        resource_ref="store://fulya/inventory",
    )
    write = _lane(
        lane_id="write",
        priority=80,
        side_effect=True,
        resource_ref="store://fulya/inventory",
    )
    plan = ParallelMissionPlan(
        objective_ref="objective://fulya",
        tenant_id="YS_TR",
        lanes=(urgent_read, write),
        max_parallel_lanes=2,
    )
    wave = schedule_parallel_wave(
        plan=plan,
        profiles={
            "urgent-read": ParallelLaneSchedulingProfile(
                lane_id="urgent-read",
                deadline_at=NOW + timedelta(seconds=10),
            ),
            "write": ParallelLaneSchedulingProfile(
                lane_id="write",
                scheduling_class=LaneSchedulingClass.EXECUTION,
                shedable=False,
                preemptible=False,
            ),
        },
        policy=ParallelSchedulingPolicy(max_concurrency_weight=4),
        now=NOW,
    )
    assert wave.selected_lane_ids == ("urgent-read",)
    assert wave.deferred["write"] == ("parallel_resource_conflict",)


def test_overload_sheds_low_priority_research_but_keeps_non_shedable_write():
    write = _lane(
        lane_id="write",
        priority=70,
        side_effect=True,
        resource_ref="resource://inventory-adjustment",
    )
    research = _lane(lane_id="research", priority=20)
    plan = ParallelMissionPlan(
        objective_ref="objective://overload",
        tenant_id="YS_TR",
        lanes=(write, research),
    )
    wave = schedule_parallel_wave(
        plan=plan,
        profiles={
            "write": ParallelLaneSchedulingProfile(
                lane_id="write",
                scheduling_class=LaneSchedulingClass.EXECUTION,
                shedable=False,
                preemptible=False,
            ),
            "research": ParallelLaneSchedulingProfile(
                lane_id="research",
                scheduling_class=LaneSchedulingClass.RESEARCH,
                shedable=True,
                preemptible=True,
            ),
        },
        policy=ParallelSchedulingPolicy(
            overload_mode=True,
            overload_shed_priority_below=40,
        ),
        now=NOW,
    )
    assert wave.selected_lane_ids == ("write",)
    assert wave.deferred["research"] == ("parallel_overload_shed",)


def test_pending_side_effect_profile_cannot_be_shedable_or_preemptible():
    write = _lane(
        lane_id="write",
        side_effect=True,
        resource_ref="resource://critical",
    )
    plan = ParallelMissionPlan(
        objective_ref="objective://safe",
        tenant_id="YS_TR",
        lanes=(write,),
    )
    with pytest.raises(ValueError, match="pending_side_effect_cannot_be_shedable"):
        schedule_parallel_wave(
            plan=plan,
            profiles={"write": ParallelLaneSchedulingProfile(lane_id="write")},
            policy=ParallelSchedulingPolicy(),
            now=NOW,
        )

    safe_profile = ParallelLaneSchedulingProfile(
        lane_id="write",
        scheduling_class=LaneSchedulingClass.EXECUTION,
        shedable=False,
        preemptible=False,
    )
    assert lane_preemption_allowed(lane=write, profile=safe_profile) is False


def test_scheduler_cost_budget_sheds_background_work_deterministically():
    first = _lane(lane_id="first", priority=80)
    second = _lane(lane_id="second", priority=70)
    plan = ParallelMissionPlan(
        objective_ref="objective://budget",
        tenant_id="YS_TR",
        lanes=(second, first),
    )
    wave = schedule_parallel_wave(
        plan=plan,
        profiles={
            "first": ParallelLaneSchedulingProfile(lane_id="first", estimated_cost_units=7),
            "second": ParallelLaneSchedulingProfile(lane_id="second", estimated_cost_units=7),
        },
        policy=ParallelSchedulingPolicy(max_round_cost_units=10),
        now=NOW,
    )
    assert wave.selected_lane_ids == ("first",)
    assert wave.deferred["second"] == ("parallel_cost_budget_shed",)
    assert wave.total_cost_units == 7


class _RecordingOrdersAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def collect(self, plan: ReadOnlySourcePlan) -> ReadOnlySourceBatch:
        self.calls += 1
        return ReadOnlySourceBatch(
            binding_id=plan.binding_id,
            tenant_id=plan.tenant_id,
            source_kind=plan.source_kind,
            source_ref=plan.source_ref,
            schema_contract=plan.schema_contract,
            schema_version=plan.schema_version,
            environment_ref=plan.environment_ref,
            execution_identity_ref=plan.execution_identity_ref,
            operation_ref=plan.operation_ref,
            observed_at=NOW + timedelta(seconds=2),
            source_receipt_ref="source-receipt://orders/001",
            evidence_ref="evidence://orders-read/001",
            fields=(
                ReadOnlySourceField(
                    entity_id="tenant:YS_TR",
                    field_name="orders.total",
                    value=1234,
                    valid_from=NOW,
                    confidence=0.99,
                ),
            ),
        )


def _orders_operation() -> CompanySourceOperation:
    return CompanySourceOperation(
        operation_ref="orders.summary.v2",
        contract_ref="query-contract://ops.kpi.orders.v2",
        allowed_fields=("orders.total", "orders.cancel_rate"),
        parameter_names=("tenant_id", "start_at", "end_at"),
    )


def _orders_descriptor(
    *,
    acceptance: AdapterAcceptance = AdapterAcceptance.CONTROLLED,
    protocol: CompanySourceProtocol = CompanySourceProtocol.BIGQUERY,
) -> CompanySourceAdapterDescriptor:
    return CompanySourceAdapterDescriptor(
        adapter_ref="adapter://bigquery/orders-v2",
        source_kind=LiveSourceKind.ORDERS,
        protocol=protocol,
        source_ref="bigquery://curated_data_shared/orders",
        schema_contract="orders-v2",
        schema_version="2",
        environment_ref="env://production-readonly",
        execution_identity_ref="identity://orders-reader",
        operations=(_orders_operation(),),
        acceptance=acceptance,
        field_production_verified=(acceptance is AdapterAcceptance.FIELD_PROVEN),
    )


def _orders_registry(
    *,
    acceptance: AdapterAcceptance = AdapterAcceptance.CONTROLLED,
    protocol: CompanySourceProtocol = CompanySourceProtocol.BIGQUERY,
) -> CompanySourceAdapterRegistry:
    return CompanySourceAdapterRegistry(
        tenant_id="YS_TR",
        adapters=(_orders_descriptor(acceptance=acceptance, protocol=protocol),),
    )


def _orders_plan(*, fields: tuple[str, ...] = ("orders.total",)) -> ReadOnlySourcePlan:
    return ReadOnlySourcePlan(
        binding_id="orders-live-v2",
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


def _orders_policy() -> LiveSourceBindingPolicy:
    return LiveSourceBindingPolicy(
        binding_id="orders-live-v2",
        tenant_id="YS_TR",
        source_kind=LiveSourceKind.ORDERS,
        source_ref="bigquery://curated_data_shared/orders",
        schema_contract="orders-v2",
        schema_version="2",
        environment_ref="env://production-readonly",
        execution_identity_ref="identity://orders-reader",
        verifier_ref="verifier://orders-independent-readback",
        truth_class=TruthClass.VERIFIED_COMPANY,
        max_observation_age_seconds=60,
        max_attestation_age_seconds=60,
        allowed_fields=("orders.total", "orders.cancel_rate"),
    )


def _runtime(adapter: _RecordingOrdersAdapter, *, protocol=CompanySourceProtocol.BIGQUERY):
    return {
        "adapter://bigquery/orders-v2": CompanySourceRuntimeBinding(
            adapter_ref="adapter://bigquery/orders-v2",
            protocol=protocol,
            collector=adapter,
        )
    }


def test_controlled_registered_company_read_collects_but_never_promotes_truth():
    adapter = _RecordingOrdersAdapter()
    receipt = execute_registered_company_read(
        registry=_orders_registry(),
        plan=_orders_plan(),
        policy=_orders_policy(),
        adapter_ref="adapter://bigquery/orders-v2",
        runtime_bindings=_runtime(adapter),
    )
    assert adapter.calls == 1
    assert receipt.collection.batch.fields[0].value == 1234
    assert receipt.truth_promoted is False
    assert receipt.execution_authority_granted is False
    assert receipt.route.truth_authority_granted is False


def test_unregistered_field_is_rejected_before_collector_call():
    adapter = _RecordingOrdersAdapter()
    with pytest.raises(ValueError, match="company_source_route_requested_field_not_allowed"):
        execute_registered_company_read(
            registry=_orders_registry(),
            plan=_orders_plan(fields=("orders.customer_email",)),
            policy=_orders_policy(),
            adapter_ref="adapter://bigquery/orders-v2",
            runtime_bindings=_runtime(adapter),
        )
    assert adapter.calls == 0


def test_repository_only_adapter_cannot_be_executed():
    adapter = _RecordingOrdersAdapter()
    with pytest.raises(ValueError, match="company_source_execution_adapter_not_controlled"):
        execute_registered_company_read(
            registry=_orders_registry(acceptance=AdapterAcceptance.REPOSITORY_ONLY),
            plan=_orders_plan(),
            policy=_orders_policy(),
            adapter_ref="adapter://bigquery/orders-v2",
            runtime_bindings=_runtime(adapter),
        )
    assert adapter.calls == 0


def test_runtime_protocol_mismatch_fails_before_collector_call():
    adapter = _RecordingOrdersAdapter()
    with pytest.raises(ValueError, match="company_source_execution_runtime_protocol_mismatch"):
        execute_registered_company_read(
            registry=_orders_registry(protocol=CompanySourceProtocol.BIGQUERY),
            plan=_orders_plan(),
            policy=_orders_policy(),
            adapter_ref="adapter://bigquery/orders-v2",
            runtime_bindings=_runtime(adapter, protocol=CompanySourceProtocol.INTERNAL_API),
        )
    assert adapter.calls == 0


def test_field_proven_adapter_still_returns_collection_not_truth():
    adapter = _RecordingOrdersAdapter()
    receipt = execute_registered_company_read(
        registry=_orders_registry(acceptance=AdapterAcceptance.FIELD_PROVEN),
        plan=_orders_plan(),
        policy=_orders_policy(),
        adapter_ref="adapter://bigquery/orders-v2",
        runtime_bindings=_runtime(adapter),
    )
    assert receipt.route.field_production_verified is True
    assert receipt.collection.truth_promoted is False
    assert receipt.truth_promoted is False
