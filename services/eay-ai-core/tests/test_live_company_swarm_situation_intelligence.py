from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.company_source_adapter_registry import CompanySourceProtocol
from app.company_source_protocol_collectors import (
    CompanyReadProtocolProof,
    NormalizedCompanyReadResult,
    ProtocolBoundCompanySourceAdapter,
)
from app.global_lane_lease_broker import GlobalLaneLeaseAdmission
from app.live_company_reality import LiveSourceKind
from app.live_company_source_runtime import (
    ReadOnlySourceField,
    ReadOnlySourcePlan,
)
from app.multi_objective_swarm_runtime import MultiObjectiveExecutionRound
from app.parallel_mission_orchestration import (
    ParallelLaneDisposition,
    ParallelLaneResult,
    ParallelMissionRound,
)
from app.real_world_timeline import (
    TimelineAuthorityClass,
    TimelineEventKind,
    TimelineObjectKind,
    TimelineObjectQualifier,
    TimelineObjectRelation,
    build_timeline_event,
)
from app.situation_detection import (
    SituationAttention,
    detect_situations,
    situation_to_alert_candidate,
)
from app.swarm_execution_telemetry import build_swarm_execution_telemetry


NOW = datetime(2026, 8, 19, 9, 45, tzinfo=timezone.utc)
TENANT = "YS_TR"
OBJECT = "store://fulya"


def _plan(protocol_suffix: str = "orders") -> ReadOnlySourcePlan:
    return ReadOnlySourcePlan(
        binding_id=f"binding:{protocol_suffix}",
        tenant_id=TENANT,
        source_kind=LiveSourceKind.ORDERS,
        source_ref=f"source://{protocol_suffix}",
        schema_contract=f"schema:{protocol_suffix}",
        schema_version="v1",
        environment_ref="env://controlled-test",
        execution_identity_ref="identity://read-only-test",
        operation_ref=f"operation://{protocol_suffix}/read",
        requested_fields=("orders.count",),
        requested_at=NOW,
    )


def _field() -> ReadOnlySourceField:
    return ReadOnlySourceField(
        entity_id=OBJECT,
        field_name="orders.count",
        value=120,
        valid_from=NOW,
        confidence=0.99,
    )


class _Executor:
    def __init__(self, result: NormalizedCompanyReadResult):
        self.result = result
        self.calls = 0

    def execute(self, plan: ReadOnlySourcePlan) -> NormalizedCompanyReadResult:
        self.calls += 1
        return self.result


def _result(
    *,
    protocol: CompanySourceProtocol,
    plan: ReadOnlySourcePlan,
    statement_type: str | None = None,
    http_method: str | None = None,
    http_status: int | None = None,
    form_submit_detected: bool = False,
) -> NormalizedCompanyReadResult:
    proof = CompanyReadProtocolProof(
        protocol=protocol,
        operation_ref=plan.operation_ref,
        executed_at=NOW + timedelta(seconds=1),
        evidence_ref=f"proof://{protocol.value}/1",
        statement_type=statement_type,
        http_method=http_method,
        http_status=http_status,
        form_submit_detected=form_submit_detected,
    )
    return NormalizedCompanyReadResult(
        operation_ref=plan.operation_ref,
        observed_at=NOW + timedelta(seconds=2),
        source_receipt_ref=f"receipt://{protocol.value}/1",
        evidence_ref=f"evidence://{protocol.value}/1",
        fields=(_field(),),
        proof=proof,
    )


def test_bigquery_protocol_collector_accepts_only_select_and_stays_collection_only():
    plan = _plan("bigquery")
    result = _result(
        protocol=CompanySourceProtocol.BIGQUERY,
        plan=plan,
        statement_type="SELECT",
    )
    executor = _Executor(result)
    adapter = ProtocolBoundCompanySourceAdapter(
        protocol=CompanySourceProtocol.BIGQUERY,
        executor=executor,
    )
    batch = adapter.collect(plan)

    assert executor.calls == 1
    assert batch.operation_ref == plan.operation_ref
    assert batch.fields[0].value == 120
    assert batch.mutation_observed is False
    assert batch.raw_payload_retained is False
    assert batch.credential_material_retained is False


def test_protocol_collectors_fail_closed_on_mutating_bigquery_or_api_semantics():
    plan = _plan("bigquery")
    with pytest.raises(ValueError, match="company_source_bigquery_requires_select_statement"):
        CompanyReadProtocolProof(
            protocol=CompanySourceProtocol.BIGQUERY,
            operation_ref=plan.operation_ref,
            executed_at=NOW,
            evidence_ref="proof://bigquery/update",
            statement_type="UPDATE",
        )

    api_plan = _plan("internal-api")
    with pytest.raises(ValueError, match="company_source_internal_api_requires_get_or_head"):
        CompanyReadProtocolProof(
            protocol=CompanySourceProtocol.INTERNAL_API,
            operation_ref=api_plan.operation_ref,
            executed_at=NOW,
            evidence_ref="proof://api/post",
            http_method="POST",
            http_status=200,
        )


def test_browser_observation_rejects_form_submission():
    plan = _plan("browser")
    with pytest.raises(ValueError, match="company_source_browser_observation_form_submit_forbidden"):
        CompanyReadProtocolProof(
            protocol=CompanySourceProtocol.BROWSER_OBSERVATION,
            operation_ref=plan.operation_ref,
            executed_at=NOW,
            evidence_ref="proof://browser/form",
            http_method="GET",
            http_status=200,
            form_submit_detected=True,
        )


def _execution_round() -> MultiObjectiveExecutionRound:
    objective = ParallelMissionRound(
        objective_ref="objective://ops",
        tenant_id=TENANT,
        selected_lane_ids=("orders-read",),
        results=(
            ParallelLaneResult(
                lane_id="orders-read",
                disposition=ParallelLaneDisposition.DEFERRED,
                blockers=("live_company_truth_receipt_missing:read-orders",),
            ),
        ),
    )
    return MultiObjectiveExecutionRound(
        admission=GlobalLaneLeaseAdmission(
            selected=(),
            deferred={},
            issued_leases=(),
        ),
        objective_rounds=(objective,),
        deferred={
            "objective://inventory::write": ("global_lane_resource_lease_conflict:store://fulya",),
            "objective://ops::orders-read": ("live_company_truth_receipt_missing:read-orders",),
        },
        active_leases_after_round=(),
    )


def test_swarm_telemetry_aggregates_pressure_without_business_or_raw_blocker_values():
    snapshot = build_swarm_execution_telemetry(
        execution_round=_execution_round(),
        tenant_id=TENANT,
        observed_at=NOW,
    )

    assert snapshot.objective_count == 1
    assert snapshot.globally_deferred_lane_count == 2
    assert snapshot.operational_pressure_score > 0
    assert "global_lane_resource_lease_conflict" in snapshot.blocker_codes
    assert "live_company_truth_receipt_missing" in snapshot.blocker_codes
    assert all("store://fulya" not in item for item in snapshot.blocker_codes)
    assert snapshot.business_values_retained is False
    assert snapshot.execution_authority_granted is False


def _event(
    event_id: str,
    event_type: str,
    authority: TimelineAuthorityClass,
    *,
    confidence: float = 0.95,
    observed_at: datetime = NOW,
):
    if authority is TimelineAuthorityClass.VERIFIED_EXTERNAL:
        kind = TimelineEventKind.EXTERNAL_CONTEXT
    elif authority is TimelineAuthorityClass.AMBIENT_UNTRUSTED:
        kind = TimelineEventKind.AMBIENT_OBSERVATION
    else:
        kind = TimelineEventKind.COMPANY_ASSERTION
    return build_timeline_event(
        event_id=event_id,
        event_type=event_type,
        event_kind=kind,
        source_ref=f"source://{event_id}",
        tenant_id=TENANT,
        occurred_at=observed_at - timedelta(seconds=2),
        observed_at=observed_at,
        data_ref=f"data://{event_id}",
        authority_class=authority,
        confidence=confidence,
        object_relations=(
            TimelineObjectRelation(
                object_ref=OBJECT,
                object_kind=TimelineObjectKind.LOCATION,
                qualifier=TimelineObjectQualifier.AFFECTED,
            ),
        ),
        evidence_refs=(f"evidence://{event_id}",),
    )


def test_verified_cross_domain_timeline_plus_swarm_pressure_creates_noncausal_situation():
    telemetry = build_swarm_execution_telemetry(
        execution_round=_execution_round(),
        tenant_id=TENANT,
        observed_at=NOW,
    )
    events = (
        _event(
            "orders-spike",
            "eay.company.orders.spike",
            TimelineAuthorityClass.VERIFIED_COMPANY,
        ),
        _event(
            "weather-rain",
            "eay.external.weather.rain",
            TimelineAuthorityClass.VERIFIED_EXTERNAL,
        ),
        _event(
            "otp-risk",
            "eay.company.otp.degraded",
            TimelineAuthorityClass.GOVERNED_OPERATIONAL,
        ),
    )
    situations = detect_situations(
        events=events,
        telemetry=telemetry,
        tenant_id=TENANT,
        now=NOW,
    )

    assert len(situations) == 1
    situation = situations[0]
    assert situation.object_ref == OBJECT
    assert set(situation.domains) == {"orders", "otp", "weather"}
    assert situation.strong_authority_event_count == 3
    assert situation.attention in {SituationAttention.SURFACE, SituationAttention.ESCALATE}
    assert situation.actionable_attention is True
    assert situation.causal_claim_proven is False
    assert situation.truth_authority_granted is False
    assert situation.replanning_authority_granted is False
    assert situation.execution_authority_granted is False

    alert = situation_to_alert_candidate(situation)
    assert alert.fingerprint == f"situation:{TENANT}:{OBJECT}"
    assert f"situation-candidate://{situation.fingerprint}" in alert.evidence_refs


def test_ambient_only_evidence_cannot_create_actionable_situation():
    telemetry = build_swarm_execution_telemetry(
        execution_round=_execution_round(),
        tenant_id=TENANT,
        observed_at=NOW,
    )
    events = tuple(
        _event(
            f"ambient-{index}",
            f"eay.ambient.topic{index}.signal",
            TimelineAuthorityClass.AMBIENT_UNTRUSTED,
        )
        for index in range(1, 4)
    )

    assert detect_situations(
        events=events,
        telemetry=telemetry,
        tenant_id=TENANT,
        now=NOW,
    ) == ()


def test_tampered_swarm_telemetry_fails_before_situation_detection():
    telemetry = build_swarm_execution_telemetry(
        execution_round=_execution_round(),
        tenant_id=TENANT,
        observed_at=NOW,
    )
    tampered = telemetry.model_copy(update={"operational_pressure_score": 1.0})

    with pytest.raises(ValueError, match="swarm_telemetry_fingerprint_mismatch"):
        detect_situations(
            events=(
                _event(
                    "orders-spike",
                    "eay.company.orders.spike",
                    TimelineAuthorityClass.VERIFIED_COMPANY,
                ),
                _event(
                    "weather-rain",
                    "eay.external.weather.rain",
                    TimelineAuthorityClass.VERIFIED_EXTERNAL,
                ),
                _event(
                    "otp-risk",
                    "eay.company.otp.degraded",
                    TimelineAuthorityClass.GOVERNED_OPERATIONAL,
                ),
            ),
            telemetry=tampered,
            tenant_id=TENANT,
            now=NOW,
        )
