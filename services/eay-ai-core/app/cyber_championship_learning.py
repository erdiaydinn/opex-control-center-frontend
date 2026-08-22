"""Anti-overfit learning queue for championship domains Jarvis actually loses."""

from __future__ import annotations

from datetime import datetime

from app.cyber_championship_execution import (
    BlindScoreReceipt,
    CompetitorKind,
    FailureSummary,
    RemediationQueueReceipt,
    SealedTaskBankReceipt,
    _seal_model,
    build_remediation_queue,
)

_REQUIRED_BASELINES = frozenset(
    {
        CompetitorKind.CROWDSTRIKE_CHARLOTTE_AI,
        CompetitorKind.GOOGLE_SECURITY_OPERATIONS_GEMINI,
        CompetitorKind.MICROSOFT_SECURITY_COPILOT,
    }
)


def build_lost_domain_remediation_queue(
    *,
    bank: SealedTaskBankReceipt,
    jarvis_score: BlindScoreReceipt,
    baseline_scores: tuple[BlindScoreReceipt, ...],
    jarvis_failure_summary: FailureSummary,
    created_at: datetime,
) -> RemediationQueueReceipt:
    bank = SealedTaskBankReceipt.model_validate(bank.model_dump(mode="json"))
    jarvis_score = BlindScoreReceipt.model_validate(jarvis_score.model_dump(mode="json"))
    jarvis_failure_summary = FailureSummary.model_validate(
        jarvis_failure_summary.model_dump(mode="json")
    )
    baselines = tuple(
        BlindScoreReceipt.model_validate(item.model_dump(mode="json"))
        for item in baseline_scores
    )
    if jarvis_score.competitor is not CompetitorKind.JARVIS:
        raise ValueError("championship_learning_requires_jarvis_score")
    baseline_ids = {item.competitor for item in baselines}
    if baseline_ids != _REQUIRED_BASELINES or len(baselines) != len(_REQUIRED_BASELINES):
        raise ValueError("championship_learning_requires_all_real_baselines")
    all_scores = (jarvis_score, *baselines)
    if any(item.bank_fingerprint != bank.fingerprint for item in all_scores):
        raise ValueError("championship_learning_cross_bank_scores_forbidden")
    if jarvis_failure_summary.run_fingerprint != jarvis_score.run_fingerprint:
        raise ValueError("championship_learning_failure_run_mismatch")

    jarvis_by_track = {item.track: item.score for item in jarvis_score.track_scores}
    baseline_by_track = {
        score.track: max(
            item.score
            for baseline in baselines
            for item in baseline.track_scores
            if item.track is score.track
        )
        for score in jarvis_score.track_scores
    }
    lost_tracks = {
        track
        for track, jarvis_value in jarvis_by_track.items()
        if jarvis_value < baseline_by_track[track]
    }
    filtered = tuple(
        aggregate
        for aggregate in jarvis_failure_summary.aggregates
        if aggregate.track in lost_tracks
    )
    filtered_summary = _seal_model(
        FailureSummary,
        {
            "contract": jarvis_failure_summary.contract,
            "run_fingerprint": jarvis_failure_summary.run_fingerprint,
            "evaluator_fingerprint": jarvis_failure_summary.evaluator_fingerprint,
            "aggregates": filtered,
            "contains_task_identifiers": False,
            "contains_ground_truth": False,
        },
    )
    return build_remediation_queue(
        bank=bank,
        summary=filtered_summary,
        created_at=created_at,
    )
