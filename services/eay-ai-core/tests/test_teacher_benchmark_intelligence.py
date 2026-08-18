import hashlib

from app.teacher_benchmark import (
    TeacherBenchmarkRun,
    TeacherCaseResult,
    TeachingEvidenceTier,
    compare_teacher_runs,
)

TASK_FP = hashlib.sha256(b"teacher-task-set").hexdigest()
ENV_FP = hashlib.sha256(b"teacher-env").hexdigest()


def _case(index, *, candidate=False, leak=False, privacy=False, grounded=True):
    if candidate:
        return TeacherCaseResult(
            case_id=f"case:{index}",
            pretest_score=0.40,
            posttest_score=0.90,
            delayed_score=0.88,
            transfer_score=0.84,
            misconception_repair_score=0.86,
            source_grounded=grounded,
            answer_leakage=leak,
            privacy_violation=privacy,
            evidence_refs=(f"eval://candidate/{index}",),
        )
    return TeacherCaseResult(
        case_id=f"case:{index}",
        pretest_score=0.40,
        posttest_score=0.80,
        delayed_score=0.80,
        transfer_score=0.78,
        misconception_repair_score=0.79,
        source_grounded=True,
        evidence_refs=(f"eval://baseline/{index}",),
    )


def _run(system, *, candidate=False, tier=TeachingEvidenceTier.SYNTHETIC, count=20, **case_kwargs):
    return TeacherBenchmarkRun(
        system_id=system,
        task_set_fingerprint=TASK_FP,
        environment_fingerprint=ENV_FP,
        evidence_tier=tier,
        cases=tuple(_case(i, candidate=candidate, **case_kwargs) for i in range(count)),
        independent_evaluator_ref="evaluator://independent-v1",
    )


def test_synthetic_superior_candidate_can_be_promotion_candidate_but_not_claim_field_superiority():
    result = compare_teacher_runs(
        candidate=_run("jarvis-teacher", candidate=True),
        baseline=_run("baseline-teacher"),
    )
    assert result.promotion_candidate is True
    assert result.superiority_claim_allowed is False
    assert result.automatic_strategy_promotion_allowed is False
    assert result.blockers == ()


def test_controlled_field_superiority_can_support_claim_but_not_auto_promotion():
    result = compare_teacher_runs(
        candidate=_run("jarvis-teacher", candidate=True, tier=TeachingEvidenceTier.CONTROLLED_FIELD),
        baseline=_run("baseline-teacher", tier=TeachingEvidenceTier.CONTROLLED_FIELD),
    )
    assert result.promotion_candidate is True
    assert result.superiority_claim_allowed is True
    assert result.automatic_strategy_promotion_allowed is False


def test_privacy_violation_or_answer_leakage_blocks_teacher_promotion():
    leak_cases = list(_run("jarvis", candidate=True).cases)
    leak_cases[0] = _case(0, candidate=True, leak=True)
    leak_run = _run("jarvis", candidate=True).model_copy(update={"cases": tuple(leak_cases)})
    leak = compare_teacher_runs(candidate=leak_run, baseline=_run("baseline"))
    assert "teacher_benchmark_answer_leakage" in leak.blockers
    assert leak.promotion_candidate is False

    privacy_cases = list(_run("jarvis", candidate=True).cases)
    privacy_cases[0] = _case(0, candidate=True, privacy=True)
    privacy_run = _run("jarvis", candidate=True).model_copy(update={"cases": tuple(privacy_cases)})
    privacy = compare_teacher_runs(candidate=privacy_run, baseline=_run("baseline"))
    assert "teacher_benchmark_privacy_violation" in privacy.blockers
    assert privacy.promotion_candidate is False


def test_same_task_environment_and_minimum_sample_are_required():
    changed_env = _run("jarvis", candidate=True).model_copy(
        update={"environment_fingerprint": hashlib.sha256(b"other-env").hexdigest()}
    )
    mismatch = compare_teacher_runs(candidate=changed_env, baseline=_run("baseline"))
    assert "teacher_benchmark_same_task_environment_required" in mismatch.blockers

    small = compare_teacher_runs(
        candidate=_run("jarvis", candidate=True, count=5),
        baseline=_run("baseline", count=5),
    )
    assert "teacher_benchmark_minimum_case_count_not_met" in small.blockers


def test_source_grounding_floor_is_strict():
    cases = list(_run("jarvis", candidate=True).cases)
    cases[0] = _case(0, candidate=True, grounded=False)
    candidate = _run("jarvis", candidate=True).model_copy(update={"cases": tuple(cases)})
    result = compare_teacher_runs(candidate=candidate, baseline=_run("baseline"))
    assert result.candidate.source_grounding_rate == 0.95
    assert "teacher_benchmark_source_grounding_below_floor" in result.blockers
