import hashlib

from app.spatial_benchmark import (
    SpatialBenchmarkRun,
    SpatialCaseResult,
    SpatialEvidenceTier,
    compare_spatial_runs,
    environment_fingerprint,
    evaluate_spatial_run,
)

TASK_FP = hashlib.sha256(b"spatialbench-v1-cases").hexdigest()
ENV_FP = environment_fingerprint(
    os_name="Windows 11",
    topology_ref="topology://mixed-3",
    dpi_ref="dpi://100-125-150",
    camera_ref="camera://integrated-front",
)


def _case(
    index,
    *,
    candidate=True,
    wrong=0,
    duplicate=0,
    cancel_calls=0,
    leakage=False,
    completed=None,
):
    if completed is None:
        completed = wrong == 0
    return SpatialCaseResult(
        case_id=f"case:{index}",
        correct_target=wrong == 0,
        intended_action_completed=completed,
        duplicate_move_count=duplicate,
        wrong_window_move_count=wrong,
        cancel_backend_call_count=cancel_calls,
        geometry_inside_work_area=True,
        topology_drift_failed_closed=True,
        raw_sensor_leakage=leakage,
        latency_ms=120 if candidate else 210,
        evidence_refs=(f"evidence://spatial/{index}",),
    )


def _run(*, candidate=True, tier=SpatialEvidenceTier.SYNTHETIC, case_override=None):
    cases = [_case(i, candidate=candidate) for i in range(24)]
    # The comparison fixture must be objectively weaker, not merely slower.
    # Keep safety clean while one baseline task fails to complete.
    if not candidate:
        cases[0] = _case(0, candidate=False, completed=False)
    if case_override is not None:
        index, item = case_override
        cases[index] = item
    return SpatialBenchmarkRun(
        system_id="jarvis-spatial" if candidate else "baseline-spatial",
        task_set_fingerprint=TASK_FP,
        environment_fingerprint=ENV_FP,
        evidence_tier=tier,
        cases=tuple(cases),
        independent_evaluator_ref="evaluator://spatialbench-v1",
    )


def test_clean_synthetic_run_is_candidate_but_not_field_claim():
    result = evaluate_spatial_run(_run())
    assert result.promotion_candidate is True
    assert result.field_acceptance_claim_allowed is False
    assert result.superiority_claim_allowed is False
    assert result.metrics.wrong_window_moves == 0
    assert result.metrics.duplicate_moves == 0
    assert result.metrics.cancel_backend_calls == 0
    assert result.metrics.leakage_events == 0


def test_controlled_field_same_task_can_support_superiority_only_when_objectively_better():
    candidate = _run(tier=SpatialEvidenceTier.CONTROLLED_FIELD)
    baseline = _run(candidate=False, tier=SpatialEvidenceTier.CONTROLLED_FIELD)
    result = compare_spatial_runs(candidate=candidate, baseline=baseline)
    assert result.field_acceptance_claim_allowed is True
    assert result.superiority_claim_allowed is True
    assert result.automatic_production_promotion_allowed is False


def test_one_wrong_window_duplicate_cancel_or_leakage_blocks_promotion():
    variants = [
        _case(0, wrong=1),
        _case(0, duplicate=1),
        _case(0, cancel_calls=1),
        _case(0, leakage=True),
    ]
    expected = [
        "spatial_benchmark_wrong_window_move_detected",
        "spatial_benchmark_duplicate_move_detected",
        "spatial_benchmark_cancel_backend_call_detected",
        "spatial_benchmark_leakage_detected",
    ]
    for item, blocker in zip(variants, expected, strict=True):
        result = evaluate_spatial_run(_run(case_override=(0, item)))
        assert result.promotion_candidate is False
        assert blocker in result.blockers


def test_cross_environment_comparison_cannot_claim_superiority():
    candidate = _run(tier=SpatialEvidenceTier.CONTROLLED_FIELD)
    baseline = _run(candidate=False, tier=SpatialEvidenceTier.CONTROLLED_FIELD).model_copy(
        update={"environment_fingerprint": hashlib.sha256(b"different-env").hexdigest()}
    )
    result = compare_spatial_runs(candidate=candidate, baseline=baseline)
    assert "spatial_benchmark_same_environment_required" in result.blockers
    assert result.superiority_claim_allowed is False
