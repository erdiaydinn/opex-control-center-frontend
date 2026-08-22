from datetime import UTC, datetime

import app.cyber_championship_execution as execution
from app.cyber_championship_execution import (
    BlindScoreReceipt,
    ChampionshipTrack,
    CompetitorKind,
    FailureAggregate,
    FailureClass,
    FailureSummary,
    SealedTaskBankReceipt,
    TrackScore,
)
from app.cyber_championship_learning import build_lost_domain_remediation_queue

NOW = datetime(2026, 8, 22, 6, 0, tzinfo=UTC)


def _bank():
    return execution._seal_model(
        SealedTaskBankReceipt,
        {
            "contract": execution.CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "bank_id": "independent-bank-loss-test",
            "rotation_epoch": "rotation-loss-001",
            "task_set_fingerprint": "1" * 64,
            "public_manifest_sha256": "2" * 64,
            "sealed_ground_truth_sha256": "3" * 64,
            "task_count": 110,
            "tracks": tuple(ChampionshipTrack),
            "independent_provider_ref": "evidence://independent-evaluator/loss-test",
            "sealed_storage_ref": "sealed://evaluator-vault/loss-test",
            "evaluator_key_id": "evaluator-key-loss-test",
            "issued_at": NOW,
            "expires_at": datetime(2026, 8, 29, 6, 0, tzinfo=UTC),
            "ground_truth_embedded_in_repository": False,
            "ground_truth_visible_to_competitors": False,
            "bank_mutable_after_issue": False,
        },
    )


def _score(bank, competitor, *, hunting, api):
    values = []
    for track in ChampionshipTrack:
        score = 0.99
        if track is ChampionshipTrack.OPEN_ENDED_THREAT_HUNTING:
            score = hunting
        if track is ChampionshipTrack.API_TENANT_SECURITY:
            score = api
        values.append(
            TrackScore(
                track=track,
                score=score,
                sample_count=10,
                failure_count=0 if score == 1.0 else 1,
                safety_violation_count=0,
            )
        )
    return execution._seal_model(
        BlindScoreReceipt,
        {
            "contract": execution.CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "competitor": competitor,
            "run_fingerprint": (str(list(CompetitorKind).index(competitor) + 4) * 64)[:64],
            "evaluator_fingerprint": (str(list(CompetitorKind).index(competitor) + 5) * 64)[:64],
            "bank_fingerprint": bank.fingerprint,
            "track_scores": tuple(values),
            "overall_score": sum(item.score for item in values) / len(values),
            "safety_floor_passed": True,
            "blind_scoring_verified": True,
        },
    )


def test_training_queue_contains_only_domains_jarvis_loses():
    bank = _bank()
    jarvis = _score(bank, CompetitorKind.JARVIS, hunting=0.80, api=1.00)
    baselines = (
        _score(bank, CompetitorKind.CROWDSTRIKE_CHARLOTTE_AI, hunting=0.90, api=0.98),
        _score(bank, CompetitorKind.GOOGLE_SECURITY_OPERATIONS_GEMINI, hunting=0.95, api=0.97),
        _score(bank, CompetitorKind.MICROSOFT_SECURITY_COPILOT, hunting=0.91, api=0.99),
    )
    summary = execution._seal_model(
        FailureSummary,
        {
            "contract": execution.CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "run_fingerprint": jarvis.run_fingerprint,
            "evaluator_fingerprint": jarvis.evaluator_fingerprint,
            "aggregates": (
                FailureAggregate(
                    track=ChampionshipTrack.OPEN_ENDED_THREAT_HUNTING,
                    failure_class=FailureClass.DETECTION_MISS,
                    count=3,
                ),
                FailureAggregate(
                    track=ChampionshipTrack.API_TENANT_SECURITY,
                    failure_class=FailureClass.FALSE_POSITIVE,
                    count=1,
                ),
            ),
            "contains_task_identifiers": False,
            "contains_ground_truth": False,
        },
    )

    queue = build_lost_domain_remediation_queue(
        bank=bank,
        jarvis_score=jarvis,
        baseline_scores=baselines,
        jarvis_failure_summary=summary,
        created_at=NOW,
    )

    assert len(queue.items) == 1
    assert queue.items[0].track is ChampionshipTrack.OPEN_ENDED_THREAT_HUNTING
    assert queue.items[0].failure_class is FailureClass.DETECTION_MISS
    assert queue.items[0].sealed_task_content_allowed is False
    assert queue.items[0].automatic_production_weight_update_allowed is False
