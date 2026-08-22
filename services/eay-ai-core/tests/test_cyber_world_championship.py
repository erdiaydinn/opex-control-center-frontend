from datetime import UTC, datetime

import pytest

from app.cyber_benchmark_intelligence import CyberBenchmarkEvidenceClass
from app.cyber_world_championship import (
    CHAMPIONSHIP_REQUIRED_WEIGHTED_WIN_RATE,
    BenchmarkAnchorKind,
    ChampionshipAnchor,
    ChampionshipBaselineSystem,
    ChampionshipTrack,
    build_championship_run,
    build_default_arena,
    build_track_measurement,
    judge_world_championship,
)

NOW = datetime(2026, 8, 22, 5, 30, tzinfo=UTC)
ENV = "a" * 64


def _measurements(score: float, *, safety_violations: int = 0):
    return tuple(
        build_track_measurement(
            track=track,
            score=score,
            sample_count=100,
            evidence_ref=f"championship-evidence:{track.value}:{score}",
            safety_violations=safety_violations,
        )
        for track in ChampionshipTrack
    )


def _arena():
    return build_default_arena(
        as_of=NOW,
        rotation_epoch="2026-08-a",
        sealed_ground_truth_ref="vault:cyber-world-championship:2026-08-a",
        task_count=1100,
    )


def _run(system_id: str, score: float, *, evidence_class, environment=ENV, **kwargs):
    arena = _arena()
    return build_championship_run(
        system_id=system_id,
        system_version="2026.08",
        manifest=arena.blind_task_manifest,
        environment_fingerprint=environment,
        evidence_class=evidence_class,
        measured_at=NOW,
        measurements=_measurements(score, safety_violations=kwargs.pop("safety_violations", 0)),
        **kwargs,
    )


def _baseline_runs(score: float = 0.80, *, environment=ENV):
    return tuple(
        _run(
            system.value,
            score,
            evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
            environment=environment,
        )
        for system in ChampionshipBaselineSystem
    )


def test_default_arena_is_challenge_ready_but_cannot_self_declare_leader():
    arena = _arena()
    assert arena.challenge_ready is True
    assert arena.verified_leader_claim_allowed is False
    assert arena.production_security_superiority_claim_allowed is False
    assert set(arena.required_baselines) == set(ChampionshipBaselineSystem)
    assert set(arena.blind_task_manifest.tracks) == set(ChampionshipTrack)
    assert arena.blind_task_manifest.task_content_embedded_in_repository is False
    assert arena.blind_task_manifest.exploit_execution_required is False
    assert arena.blind_task_manifest.production_mutation_required is False


def test_vendor_capability_disclosures_never_count_as_competitive_scores():
    arena = _arena()
    assert all(profile.common_harness_measurement_present is False for profile in arena.competitor_profiles)
    assert all(profile.competitive_score_claimed is False for profile in arena.competitor_profiles)
    assert all(
        anchor.provides_common_harness_score is False
        for anchor in arena.anchors
        if anchor.kind is BenchmarkAnchorKind.VENDOR_CAPABILITY_DISCLOSURE
    )


def test_independent_anchors_cover_open_hunting_and_soc_operations():
    arena = _arena()
    independent = [
        anchor
        for anchor in arena.anchors
        if anchor.kind is BenchmarkAnchorKind.INDEPENDENT_OPEN_BENCHMARK
    ]
    covered = {track for anchor in independent for track in anchor.tracks}
    assert ChampionshipTrack.OPEN_ENDED_THREAT_HUNTING in covered
    assert ChampionshipTrack.ALERT_TRIAGE_INVESTIGATION in covered
    assert ChampionshipTrack.DETECTION_ENGINEERING in covered


def test_blind_manifest_rejects_repository_embedded_answers():
    arena = _arena()
    payload = arena.blind_task_manifest.model_dump(mode="json")
    payload["task_content_embedded_in_repository"] = True
    with pytest.raises(ValueError, match="blind_tasks_cannot_be_embedded"):
        arena.blind_task_manifest.__class__.model_validate(payload)


def test_vendor_disclosure_cannot_be_forged_into_common_harness_score():
    arena = _arena()
    profile = arena.competitor_profiles[0]
    payload = profile.model_dump(mode="json")
    payload["competitive_score_claimed"] = True
    with pytest.raises(ValueError, match="competitive_score_requires_common_harness_measurement"):
        profile.__class__.model_validate(payload)


def test_missing_external_baselines_blocks_world_leader_claim():
    arena = _arena()
    challenger = _run(
        "jarvis",
        1.0,
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )
    verdict = judge_world_championship(arena=arena, challenger=challenger, baselines=())
    assert verdict.verified_leader_claim_allowed is False
    assert "cyber_championship_all_required_baselines_not_measured" in verdict.blockers


def test_repository_only_challenger_cannot_claim_world_leadership():
    arena = _arena()
    challenger = _run(
        "jarvis",
        1.0,
        evidence_class=CyberBenchmarkEvidenceClass.REPOSITORY,
    )
    verdict = judge_world_championship(
        arena=arena,
        challenger=challenger,
        baselines=_baseline_runs(),
    )
    assert verdict.verified_leader_claim_allowed is False
    assert "cyber_championship_challenger_evidence_too_weak" in verdict.blockers


def test_any_safety_violation_blocks_world_leader_claim():
    arena = _arena()
    challenger = _run(
        "jarvis",
        1.0,
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
        unauthorized_action_events=1,
    )
    verdict = judge_world_championship(
        arena=arena,
        challenger=challenger,
        baselines=_baseline_runs(),
    )
    assert verdict.safety_floors_passed is False
    assert verdict.verified_leader_claim_allowed is False
    assert "cyber_championship_safety_floor_failed" in verdict.blockers


def test_common_environment_is_mandatory():
    arena = _arena()
    challenger = _run(
        "jarvis",
        1.0,
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )
    baselines = _baseline_runs(environment="b" * 64)
    verdict = judge_world_championship(
        arena=arena,
        challenger=challenger,
        baselines=baselines,
    )
    assert verdict.common_environment_verified is False
    assert verdict.verified_leader_claim_allowed is False
    assert "cyber_championship_environment_mismatch" in verdict.blockers


def test_open_ended_threat_hunting_floor_is_not_optional():
    arena = _arena()
    measurements = list(_measurements(1.0))
    for index, item in enumerate(measurements):
        if item.track is ChampionshipTrack.OPEN_ENDED_THREAT_HUNTING:
            measurements[index] = build_track_measurement(
                track=item.track,
                score=0.49,
                sample_count=100,
                evidence_ref="championship-evidence:open-hunting-below-floor",
            )
    challenger = build_championship_run(
        system_id="jarvis",
        system_version="2026.08",
        manifest=arena.blind_task_manifest,
        environment_fingerprint=ENV,
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
        measured_at=NOW,
        measurements=tuple(measurements),
    )
    verdict = judge_world_championship(
        arena=arena,
        challenger=challenger,
        baselines=_baseline_runs(score=0.40),
    )
    assert verdict.external_benchmark_floors_passed is False
    assert "cyber_championship_external_benchmark_floor_failed" in verdict.blockers


def test_world_leader_requires_beating_every_required_baseline_on_at_least_ninety_percent_weight():
    arena = _arena()
    challenger = _run(
        "jarvis",
        1.0,
        evidence_class=CyberBenchmarkEvidenceClass.AUTHORIZED_SANDBOX,
    )
    verdict = judge_world_championship(
        arena=arena,
        challenger=challenger,
        baselines=_baseline_runs(score=0.80),
    )
    assert verdict.weighted_track_win_rate >= CHAMPIONSHIP_REQUIRED_WEIGHTED_WIN_RATE
    assert verdict.all_baselines_measured is True
    assert verdict.common_environment_verified is True
    assert verdict.safety_floors_passed is True
    assert verdict.external_benchmark_floors_passed is True
    assert verdict.verified_leader_claim_allowed is True
    assert verdict.production_security_superiority_claim_allowed is False


def test_world_leader_claim_still_does_not_equal_production_security_superiority():
    arena = _arena()
    challenger = _run(
        "jarvis",
        1.0,
        evidence_class=CyberBenchmarkEvidenceClass.FIELD_READ_ONLY,
    )
    verdict = judge_world_championship(
        arena=arena,
        challenger=challenger,
        baselines=_baseline_runs(score=0.70),
    )
    assert verdict.verified_leader_claim_allowed is True
    assert verdict.production_security_superiority_claim_allowed is False


def test_anchor_validator_rejects_vendor_disclosure_as_score():
    arena = _arena()
    anchor = arena.anchors[0]
    payload = anchor.model_dump(mode="json")
    payload["kind"] = BenchmarkAnchorKind.VENDOR_CAPABILITY_DISCLOSURE.value
    payload["provides_common_harness_score"] = True
    payload["fingerprint"] = "0" * 64
    with pytest.raises(ValueError, match="vendor_disclosure_never_counts_as_competitive_score"):
        ChampionshipAnchor.model_validate(payload)
