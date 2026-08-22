from datetime import UTC, datetime

from app.cyber_benchmark_intelligence import CyberBenchmarkEvidenceClass
from app.cyber_world_championship import (
    ChampionshipBaselineSystem,
    ChampionshipTrack,
    build_championship_run,
    build_default_arena,
    build_track_measurement,
    judge_world_championship,
)

NOW = datetime(2026, 8, 22, 5, 45, tzinfo=UTC)
ENV = "c" * 64


def _measurements(score: float):
    return tuple(
        build_track_measurement(
            track=track,
            score=score,
            sample_count=100,
            evidence_ref=f"championship-evidence:{track.value}:{score}",
        )
        for track in ChampionshipTrack
    )


def test_repository_baseline_measurement_cannot_support_verified_leader_claim():
    arena = build_default_arena(
        as_of=NOW,
        rotation_epoch="2026-08-evidence",
        sealed_ground_truth_ref="vault:cyber-world-championship:2026-08-evidence",
        task_count=1100,
    )
    challenger = build_championship_run(
        system_id="jarvis",
        system_version="2026.08",
        manifest=arena.blind_task_manifest,
        environment_fingerprint=ENV,
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
        measured_at=NOW,
        measurements=_measurements(1.0),
    )
    baselines = tuple(
        build_championship_run(
            system_id=system.value,
            system_version="2026.08",
            manifest=arena.blind_task_manifest,
            environment_fingerprint=ENV,
            evidence_class=(
                CyberBenchmarkEvidenceClass.REPOSITORY
                if system is ChampionshipBaselineSystem.CROWDSTRIKE_CHARLOTTE_AI
                else CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX
            ),
            measured_at=NOW,
            measurements=_measurements(0.8),
        )
        for system in ChampionshipBaselineSystem
    )
    verdict = judge_world_championship(
        arena=arena,
        challenger=challenger,
        baselines=baselines,
    )
    assert verdict.verified_leader_claim_allowed is False
    assert "cyber_championship_baseline_evidence_too_weak" in verdict.blockers
