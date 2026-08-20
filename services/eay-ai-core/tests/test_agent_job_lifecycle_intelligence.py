from datetime import UTC, datetime

import pytest

from app.agent_job_lifecycle import (
    AgentEffectState,
    AgentJobStatus,
    acknowledge_agent_job_cancellation,
    mark_agent_job_running,
    new_agent_job,
    record_child_result,
    request_agent_job_cancellation,
)

NOW = datetime(2026, 8, 20, 13, 0, tzinfo=UTC)


def job():
    return new_agent_job(
        job_id="job-1",
        objective_ref="objective://research",
        tenant_id="YS_TR",
        root_agent_id="jarvis-root",
        child_agent_ids=("research-a", "research-b"),
    )


def test_all_admitted_children_must_finish_before_fan_in_completion():
    running = mark_agent_job_running(job())
    one = record_child_result(
        running,
        child_agent_id="research-a",
        observed_cancellation_epoch=0,
        evidence_refs=("evidence://a",),
        effect_state=AgentEffectState.NO_EFFECT,
        now=NOW,
    )
    assert one.status is AgentJobStatus.RUNNING
    complete = record_child_result(
        one,
        child_agent_id="research-b",
        observed_cancellation_epoch=0,
        evidence_refs=("evidence://b",),
        effect_state=AgentEffectState.NO_EFFECT,
        now=NOW,
    )
    assert complete.status is AgentJobStatus.COMPLETED
    assert complete.terminal_at == NOW


def test_root_cancel_increments_epoch_and_rejects_late_child_result():
    cancelled = request_agent_job_cancellation(mark_agent_job_running(job()), now=NOW)
    assert cancelled.cancellation_epoch == 1
    with pytest.raises(ValueError, match="stale_cancellation_epoch"):
        record_child_result(
            cancelled,
            child_agent_id="research-a",
            observed_cancellation_epoch=0,
            evidence_refs=("evidence://late",),
            effect_state=AgentEffectState.NO_EFFECT,
            now=NOW,
        )
    with pytest.raises(ValueError, match="cancelled_tree_rejects_late_result"):
        record_child_result(
            cancelled,
            child_agent_id="research-a",
            observed_cancellation_epoch=1,
            evidence_refs=("evidence://late",),
            effect_state=AgentEffectState.NO_EFFECT,
            now=NOW,
        )


def test_cancel_requires_every_child_ack_and_preserves_unknown_effect_blocker():
    cancelling = request_agent_job_cancellation(mark_agent_job_running(job()), now=NOW)
    first = acknowledge_agent_job_cancellation(
        cancelling,
        child_agent_id="research-a",
        cancellation_epoch=1,
        effect_state=AgentEffectState.NO_EFFECT,
        evidence_refs=("evidence://cancel/a",),
        now=NOW,
    )
    assert first.status is AgentJobStatus.CANCEL_REQUESTED
    unknown = acknowledge_agent_job_cancellation(
        first,
        child_agent_id="research-b",
        cancellation_epoch=1,
        effect_state=AgentEffectState.UNKNOWN_EFFECT,
        evidence_refs=("evidence://cancel/b",),
        now=NOW,
    )
    assert unknown.status is AgentJobStatus.RECONCILIATION_REQUIRED
    assert unknown.terminal_at is None


def test_clean_cancel_becomes_terminal_only_after_all_descendants_ack():
    state = request_agent_job_cancellation(mark_agent_job_running(job()), now=NOW)
    for child in ("research-a", "research-b"):
        state = acknowledge_agent_job_cancellation(
            state,
            child_agent_id=child,
            cancellation_epoch=1,
            effect_state=AgentEffectState.RECONCILED_NO_EFFECT,
            evidence_refs=(f"evidence://cancel/{child}",),
            now=NOW,
        )
    assert state.status is AgentJobStatus.CANCELLED
    assert state.terminal_at == NOW


def test_child_result_replay_is_idempotent_but_conflicting_replay_is_rejected():
    running = mark_agent_job_running(job())
    accepted = record_child_result(
        running,
        child_agent_id="research-a",
        observed_cancellation_epoch=0,
        evidence_refs=("evidence://a",),
        effect_state=AgentEffectState.NO_EFFECT,
        now=NOW,
    )
    replay = record_child_result(
        accepted,
        child_agent_id="research-a",
        observed_cancellation_epoch=0,
        evidence_refs=("evidence://a",),
        effect_state=AgentEffectState.NO_EFFECT,
        now=NOW,
    )
    assert replay == accepted
    with pytest.raises(ValueError, match="child_result_conflict"):
        record_child_result(
            accepted,
            child_agent_id="research-a",
            observed_cancellation_epoch=0,
            evidence_refs=("evidence://forged",),
            effect_state=AgentEffectState.NO_EFFECT,
            now=NOW,
        )


def test_snapshot_tamper_is_detected_before_transition():
    running = mark_agent_job_running(job())
    payload = running.model_dump(mode="json")
    payload["tenant_id"] = "tenant-b"
    with pytest.raises(ValueError, match="fingerprint_mismatch"):
        request_agent_job_cancellation(type(running).model_validate(payload), now=NOW)
