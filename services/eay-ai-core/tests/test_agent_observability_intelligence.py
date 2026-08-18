from datetime import datetime, timezone

import pytest

from app.agent_observability import (
    AgentDiagnosticTrace,
    DiagnosticReplayDisposition,
    build_agent_diagnostic_trace,
    build_diagnostic_replay_plan,
)
from app.intelligence_router import (
    IntelligenceTask,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
)
from app.mission_execution import (
    MissionExecutionKind,
    MissionExecutionSpec,
    MissionExecutionSummary,
)
from app.mission_runtime import (
    MissionDefinition,
    MissionStatus,
    MissionStep,
    StepStatus,
    new_checkpoint,
    record_step_result,
)


NOW = datetime(2026, 8, 18, 8, 35, tzinfo=timezone.utc)


def _definition():
    return MissionDefinition(
        mission_id="mission-observe-1",
        objective="Do not persist this business objective: barcode 8691234567890",
        tenant_id="tenant://YS_TR",
        steps=(
            MissionStep(
                step_id="reason",
                description="Analyze sensitive stock context",
            ),
            MissionStep(
                step_id="adjust",
                description="Apply one bounded adjustment",
                depends_on=("reason",),
                side_effect=True,
                required_permission="inventory.adjust",
                idempotency_key="idem://observe-1",
                effect_verifier_ref="verifier://inventory/readback",
            ),
        ),
    )


def _specs():
    return (
        MissionExecutionSpec(
            step_id="reason",
            kind=MissionExecutionKind.REASONING,
            intelligence_task=IntelligenceTask(
                task_id="task://inventory/reasoning",
                complexity=TaskComplexity.HARD,
                risk=TaskRisk.MEDIUM,
                privacy=PrivacyLevel.CONFIDENTIAL,
            ),
            prompt="PASSWORD=secret OTP=482731 barcode=8691234567890",
        ),
        MissionExecutionSpec(
            step_id="adjust",
            kind=MissionExecutionKind.CAPABILITY,
            capability_ref="carsiportal.inventory.adjust_stock.v1",
        ),
    )


def _ambiguous_summary():
    definition = _definition()
    checkpoint = new_checkpoint(definition, now=NOW)
    checkpoint = record_step_result(
        definition,
        checkpoint,
        step_id="reason",
        succeeded=True,
        evidence_refs=("evidence://reasoning/1",),
        now=NOW,
    )
    checkpoint = record_step_result(
        definition,
        checkpoint,
        step_id="adjust",
        succeeded=False,
        evidence_refs=("transaction://unknown/1", "readback://timeout/1"),
        error="authoritative_readback_timeout",
        ambiguous_outcome=True,
        now=NOW,
    )
    return MissionExecutionSummary(
        checkpoint=checkpoint,
        transitions_executed=2,
        reasoning_engine_ids=("openai-gpt-5.6",),
        capability_refs=("carsiportal.inventory.adjust_stock.v1",),
        blockers=("capability_outcome_ambiguous:carsiportal.inventory.adjust_stock.v1",),
    )


def test_trace_reconstructs_control_flow_without_prompts_objectives_or_secret_values():
    trace = build_agent_diagnostic_trace(
        definition=_definition(),
        specs=_specs(),
        summary=_ambiguous_summary(),
    )
    serialized = trace.model_dump_json()

    assert trace.mission_status is MissionStatus.HALTED
    assert len(trace.spans) == 2
    assert trace.spans[0].status is StepStatus.SUCCEEDED
    assert trace.spans[0].reasoning_task_ref == "task://inventory/reasoning"
    assert trace.spans[1].capability_ref == "carsiportal.inventory.adjust_stock.v1"
    assert trace.spans[1].ambiguous_outcome is True
    assert trace.authoritative_audit_replaced is False
    assert trace.executable_replay_allowed is False
    assert "PASSWORD=secret" not in serialized
    assert "482731" not in serialized
    assert "8691234567890" not in serialized
    assert "Do not persist this business objective" not in serialized


def test_ambiguous_write_diagnostic_replay_requires_reconciliation_and_never_executes():
    trace = build_agent_diagnostic_trace(
        definition=_definition(),
        specs=_specs(),
        summary=_ambiguous_summary(),
    )
    replay = build_diagnostic_replay_plan(trace)

    assert replay.executable is False
    assert replay.mutation_allowed is False
    assert replay.requires_fresh_authorization_for_any_future_write is True
    assert replay.steps[0].disposition is DiagnosticReplayDisposition.REASONING_REEVALUATION_ALLOWED
    assert replay.steps[1].disposition is DiagnosticReplayDisposition.AMBIGUOUS_EFFECT_RECONCILIATION_REQUIRED
    assert replay.steps[1].side_effect_replay_allowed is False
    assert "transaction://unknown/1" in replay.steps[1].evidence_refs


def test_even_successful_write_is_never_replayed_from_diagnostic_trace():
    definition = _definition()
    checkpoint = new_checkpoint(definition, now=NOW)
    checkpoint = record_step_result(
        definition,
        checkpoint,
        step_id="reason",
        succeeded=True,
        evidence_refs=("evidence://reasoning/ok",),
        now=NOW,
    )
    checkpoint = record_step_result(
        definition,
        checkpoint,
        step_id="adjust",
        succeeded=True,
        evidence_refs=("transaction://applied/1", "readback://stock/24"),
        now=NOW,
    )
    trace = build_agent_diagnostic_trace(
        definition=definition,
        specs=_specs(),
        summary=MissionExecutionSummary(
            checkpoint=checkpoint,
            transitions_executed=2,
            capability_refs=("carsiportal.inventory.adjust_stock.v1",),
        ),
    )
    replay = build_diagnostic_replay_plan(trace)

    assert trace.mission_status is MissionStatus.COMPLETED
    assert replay.steps[1].disposition is DiagnosticReplayDisposition.SIDE_EFFECT_REPLAY_FORBIDDEN
    assert replay.steps[1].side_effect_replay_allowed is False


def test_trace_rejects_mission_tenant_and_definition_drift():
    summary = _ambiguous_summary()
    wrong_tenant = summary.model_copy(
        update={"checkpoint": summary.checkpoint.model_copy(update={"tenant_id": "tenant://OTHER"})}
    )
    with pytest.raises(ValueError, match="agent_observability_tenant_identity_mismatch"):
        build_agent_diagnostic_trace(definition=_definition(), specs=_specs(), summary=wrong_tenant)

    wrong_fingerprint = summary.model_copy(
        update={
            "checkpoint": summary.checkpoint.model_copy(
                update={"definition_fingerprint": "0" * 64}
            )
        }
    )
    with pytest.raises(ValueError, match="agent_observability_definition_drift"):
        build_agent_diagnostic_trace(definition=_definition(), specs=_specs(), summary=wrong_fingerprint)


def test_trace_model_cannot_be_promoted_to_executable_or_authoritative_audit():
    trace = build_agent_diagnostic_trace(
        definition=_definition(),
        specs=_specs(),
        summary=_ambiguous_summary(),
    )
    payload = trace.model_dump(mode="python")
    payload["authoritative_audit_replaced"] = True
    with pytest.raises(ValueError, match="agent_observability_never_replaces_authoritative_audit"):
        AgentDiagnosticTrace.model_validate(payload)

    payload = trace.model_dump(mode="python")
    payload["executable_replay_allowed"] = True
    with pytest.raises(ValueError, match="agent_observability_never_allows_executable_replay"):
        AgentDiagnosticTrace.model_validate(payload)
