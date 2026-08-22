from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.company_read_mission_bridge import (
    CompanyReadMissionBinding,
    build_company_read_capability_handler,
)
from app.company_source_adapter_execution import CompanySourceRuntimeBinding
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
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
from app.world_model import TruthClass

NOW = datetime(2026, 8, 19, 7, 15, tzinfo=timezone.utc)


class _RecordingAdapter:
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
            observed_at=NOW + timedelta(seconds=1),
            source_receipt_ref="source-receipt://orders/001",
            evidence_ref="evidence://orders/001",
            fields=(
                ReadOnlySourceField(
                    entity_id="tenant:YS_TR",
                    field_name="orders.total",
                    value=123,
                    valid_from=NOW,
                    confidence=0.99,
                ),
            ),
        )


def _registry() -> CompanySourceAdapterRegistry:
    operation = CompanySourceOperation(
        operation_ref="orders.summary.v2",
        contract_ref="query-contract://ops.kpi.orders.v2",
        allowed_fields=("orders.total",),
        parameter_names=("tenant_id",),
    )
    adapter = CompanySourceAdapterDescriptor(
        adapter_ref="adapter://bigquery/orders-v2",
        source_kind=LiveSourceKind.ORDERS,
        protocol=CompanySourceProtocol.BIGQUERY,
        source_ref="bigquery://curated_data_shared/orders",
        schema_contract="orders-v2",
        schema_version="2",
        environment_ref="env://production-readonly",
        execution_identity_ref="identity://orders-reader",
        operations=(operation,),
        acceptance=AdapterAcceptance.CONTROLLED,
    )
    return CompanySourceAdapterRegistry(tenant_id="YS_TR", adapters=(adapter,))


def _plan(*, fields: tuple[str, ...] = ("orders.total",)) -> ReadOnlySourcePlan:
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


def _policy() -> LiveSourceBindingPolicy:
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
        allowed_fields=("orders.total",),
    )


def _definition(*, side_effect: bool = False) -> tuple[MissionDefinition, MissionStep]:
    step = MissionStep(
        step_id="read-orders",
        description="read governed orders summary",
        side_effect=side_effect,
        idempotency_key=("idem-read-orders-00000001" if side_effect else None),
        effect_verifier_ref=("effect://forbidden" if side_effect else None),
    )
    definition = MissionDefinition(
        mission_id="mission-orders-read",
        objective="read orders",
        tenant_id="YS_TR",
        steps=(step,),
    )
    return definition, step


@pytest.mark.asyncio
async def test_company_read_bridge_collects_off_mission_path_without_truth_promotion():
    adapter = _RecordingAdapter()
    evidence_receipts = []
    binding = CompanyReadMissionBinding(
        capability_ref="company.orders.read",
        registry=_registry(),
        plan=_plan(),
        policy=_policy(),
        adapter_ref="adapter://bigquery/orders-v2",
        runtime_bindings={
            "adapter://bigquery/orders-v2": CompanySourceRuntimeBinding(
                adapter_ref="adapter://bigquery/orders-v2",
                protocol=CompanySourceProtocol.BIGQUERY,
                collector=adapter,
            )
        },
        evidence_writer=lambda receipt: evidence_receipts.append(receipt) or "evidence-store://orders/001",
    )
    handler = build_company_read_capability_handler(binding)
    definition, step = _definition()
    state = new_checkpoint(definition, now=NOW).steps[0]
    outcome = await handler(definition, step, state, "")

    assert adapter.calls == 1
    assert outcome.succeeded is True
    assert outcome.effect_verified is False
    assert outcome.transaction_ref is None
    assert "evidence-store://orders/001" in outcome.evidence_refs
    assert "source-receipt://orders/001" in outcome.evidence_refs
    assert len(evidence_receipts) == 1
    assert evidence_receipts[0].truth_promoted is False
    assert evidence_receipts[0].execution_authority_granted is False


@pytest.mark.asyncio
async def test_company_read_bridge_rejects_side_effect_before_collector():
    adapter = _RecordingAdapter()
    binding = CompanyReadMissionBinding(
        capability_ref="company.orders.read",
        registry=_registry(),
        plan=_plan(),
        policy=_policy(),
        adapter_ref="adapter://bigquery/orders-v2",
        runtime_bindings={
            "adapter://bigquery/orders-v2": CompanySourceRuntimeBinding(
                adapter_ref="adapter://bigquery/orders-v2",
                protocol=CompanySourceProtocol.BIGQUERY,
                collector=adapter,
            )
        },
        evidence_writer=lambda _receipt: "evidence-store://orders/001",
    )
    handler = build_company_read_capability_handler(binding)
    definition, step = _definition(side_effect=True)
    state = new_checkpoint(definition, now=NOW).steps[0]

    with pytest.raises(ValueError, match="company_read_bridge_forbids_side_effect_step"):
        await handler(definition, step, state, "idem")
    assert adapter.calls == 0


@pytest.mark.asyncio
async def test_unregistered_field_fails_before_collector_even_through_bridge():
    adapter = _RecordingAdapter()
    binding = CompanyReadMissionBinding(
        capability_ref="company.orders.read",
        registry=_registry(),
        plan=_plan(fields=("orders.customer_email",)),
        policy=_policy(),
        adapter_ref="adapter://bigquery/orders-v2",
        runtime_bindings={
            "adapter://bigquery/orders-v2": CompanySourceRuntimeBinding(
                adapter_ref="adapter://bigquery/orders-v2",
                protocol=CompanySourceProtocol.BIGQUERY,
                collector=adapter,
            )
        },
        evidence_writer=lambda _receipt: "evidence-store://orders/001",
    )
    handler = build_company_read_capability_handler(binding)
    definition, step = _definition()
    state = new_checkpoint(definition, now=NOW).steps[0]

    with pytest.raises(ValueError, match="company_source_route_requested_field_not_allowed"):
        await handler(definition, step, state, "")
    assert adapter.calls == 0
