from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.repository_change_verification import (
    CodingVerificationDisposition,
    CodingVerificationStage,
    RepositoryChangeScope,
    RepositoryChangeVerification,
    RepositoryExactHeadCIEvidence,
    RepositoryIndependentReviewEvidence,
    RepositoryPatchEvidence,
    RepositoryQualityEvidence,
    admit_verified_software_engineering_completion,
    software_engineering_proof_from_verified_change,
    verify_repository_change,
)

REPO = "erdiaydinn/opex-control-center-frontend"
BASE = "a" * 40
HEAD = "b" * 40
OTHER = "c" * 40
PATCH_DIGEST = "d" * 64


def scope(**overrides) -> RepositoryChangeScope:
    values = dict(
        repository_full_name=REPO,
        branch_ref="product/jarvis-general-intelligence-v1",
        base_sha=BASE,
        candidate_head_sha=HEAD,
        allowed_paths=(
            "services/eay-ai-core/app/repository_change_verification.py",
            "services/eay-ai-core/tests/test_repository_change_verification_intelligence.py",
        ),
        expected_changed_paths=(
            "services/eay-ai-core/app/repository_change_verification.py",
        ),
        scope_reason="Add exact-head software change verification authority",
        evidence_refs=("github://scope/pr-169",),
    )
    values.update(overrides)
    return RepositoryChangeScope.seal(**values)


def patch(**overrides) -> RepositoryPatchEvidence:
    values = dict(
        repository_full_name=REPO,
        base_sha=BASE,
        candidate_head_sha=HEAD,
        changed_paths=(
            "services/eay-ai-core/app/repository_change_verification.py",
            "services/eay-ai-core/tests/test_repository_change_verification_intelligence.py",
        ),
        additions=500,
        deletions=0,
        patch_sha256=PATCH_DIGEST,
        repository_observation_ref="github://compare/base...head",
        evidence_refs=("github://commit/head",),
    )
    values.update(overrides)
    return RepositoryPatchEvidence.seal(**values)


def quality(**overrides) -> RepositoryQualityEvidence:
    values = dict(
        repository_full_name=REPO,
        candidate_head_sha=HEAD,
        compile_passed=True,
        tests_passed=True,
        static_analysis_passed=True,
        security_regression_passed=True,
        test_count=1263,
        compile_evidence_ref="ci://compile/1034",
        test_evidence_ref="ci://tests/1034",
        static_analysis_evidence_ref="ci://static/1034",
        security_evidence_ref="ci://security/1034",
    )
    values.update(overrides)
    return RepositoryQualityEvidence.seal(**values)


def review(**overrides) -> RepositoryIndependentReviewEvidence:
    values = dict(
        repository_full_name=REPO,
        candidate_head_sha=HEAD,
        reviewer_ref="reviewer://independent/frontier-critic",
        independent_evaluator=True,
        changed_files_reviewed=True,
        material_findings=2,
        unresolved_material_findings=0,
        evidence_refs=("review://head/independent",),
    )
    values.update(overrides)
    return RepositoryIndependentReviewEvidence.seal(**values)


def ci(**overrides) -> RepositoryExactHeadCIEvidence:
    values = dict(
        repository_full_name=REPO,
        candidate_head_sha=HEAD,
        merge_composition_sha="e" * 40,
        run_id=32531596085,
        run_number=1034,
        conclusion="success",
        candidate_bound_to_run=True,
        required_jobs=("Jarvis intelligence", "PostgreSQL authority"),
        successful_jobs=("Jarvis intelligence", "PostgreSQL authority"),
        evidence_refs=("github-actions://run/1034",),
    )
    values.update(overrides)
    return RepositoryExactHeadCIEvidence.seal(**values)


def verified(**overrides) -> RepositoryChangeVerification:
    values = dict(scope=scope(), patch=patch(), quality=quality(), review=review(), ci=ci())
    values.update(overrides)
    return verify_repository_change(**values)


def test_full_repository_change_chain_reaches_verified_and_existing_completion_gate() -> None:
    result = verified()
    assert result.disposition is CodingVerificationDisposition.VERIFIED
    assert result.blockers == ()
    assert result.completed_stages == (
        CodingVerificationStage.CHANGE_SCOPED,
        CodingVerificationStage.PATCH_EVIDENCED,
        CodingVerificationStage.QUALITY_VERIFIED,
        CodingVerificationStage.INDEPENDENT_REVIEWED,
        CodingVerificationStage.EXACT_HEAD_CI_VERIFIED,
    )
    assert result.test_count == 1263
    assert result.merge_authority_granted is False
    assert result.execution_authority_granted is False
    assert result.deployment_authority_granted is False
    assert result.superiority_claim_allowed is False

    proof = software_engineering_proof_from_verified_change(result)
    assert proof.exact_head_sha == HEAD
    assert proof.exact_head_ci_passed is True
    assert proof.test_count == 1263
    acceptance = admit_verified_software_engineering_completion(result)
    assert acceptance.completion_ready is True
    assert acceptance.blockers == ()


def test_scope_violation_and_missing_expected_file_force_hold() -> None:
    outside = RepositoryPatchEvidence.seal(
        repository_full_name=REPO,
        base_sha=BASE,
        candidate_head_sha=HEAD,
        changed_paths=("services/core-api/app/main.py",),
        additions=5,
        deletions=1,
        patch_sha256=PATCH_DIGEST,
        repository_observation_ref="github://compare/outside",
        evidence_refs=("github://outside",),
    )
    result = verified(patch=outside)
    assert result.disposition is CodingVerificationDisposition.HOLD
    assert "repository_change_scope_violation:services/core-api/app/main.py" in result.blockers
    assert any(code.startswith("repository_change_expected_path_missing:") for code in result.blockers)
    assert result.completed_stages == (CodingVerificationStage.CHANGE_SCOPED,)


def test_wrong_head_at_every_downstream_stage_fails_closed() -> None:
    cases = (
        ("patch", patch(candidate_head_sha=OTHER), "repository_change_patch_head_mismatch"),
        ("quality", quality(candidate_head_sha=OTHER), "repository_change_quality_head_mismatch"),
        ("review", review(candidate_head_sha=OTHER), "repository_change_review_head_mismatch"),
        ("ci", ci(candidate_head_sha=OTHER), "repository_change_ci_head_mismatch"),
    )
    for key, evidence, blocker in cases:
        result = verified(**{key: evidence})
        assert result.disposition is CodingVerificationDisposition.HOLD
        assert blocker in result.blockers


@pytest.mark.parametrize(
    ("field", "blocker"),
    (
        ("compile_passed", "repository_change_compile_not_green"),
        ("tests_passed", "repository_change_tests_not_green"),
        ("static_analysis_passed", "repository_change_static_analysis_not_green"),
        ("security_regression_passed", "repository_change_security_regression_not_green"),
    ),
)
def test_each_quality_gate_is_mandatory(field: str, blocker: str) -> None:
    result = verified(quality=quality(**{field: False}))
    assert result.disposition is CodingVerificationDisposition.HOLD
    assert blocker in result.blockers
    assert CodingVerificationStage.QUALITY_VERIFIED not in result.completed_stages


def test_tests_must_actually_execute() -> None:
    result = verified(quality=quality(test_count=0))
    assert result.disposition is CodingVerificationDisposition.HOLD
    assert "repository_change_tests_not_exercised" in result.blockers


@pytest.mark.parametrize(
    ("overrides", "blocker"),
    (
        ({"independent_evaluator": False}, "repository_change_independent_reviewer_required"),
        ({"changed_files_reviewed": False}, "repository_change_changed_files_not_reviewed"),
        ({"unresolved_material_findings": 1}, "repository_change_material_review_findings_unresolved"),
    ),
)
def test_independent_review_cannot_be_skipped_or_leave_material_findings(
    overrides: dict[str, object], blocker: str
) -> None:
    result = verified(review=review(**overrides))
    assert result.disposition is CodingVerificationDisposition.HOLD
    assert blocker in result.blockers
    assert CodingVerificationStage.INDEPENDENT_REVIEWED not in result.completed_stages


def test_exact_head_ci_requires_candidate_binding_success_and_every_required_job() -> None:
    not_bound = verified(ci=ci(candidate_bound_to_run=False))
    assert "repository_change_ci_not_bound_to_candidate_head" in not_bound.blockers

    failed = verified(ci=ci(conclusion="failure"))
    assert "repository_change_exact_head_ci_not_green" in failed.blockers

    missing_job = verified(ci=ci(successful_jobs=("Jarvis intelligence",)))
    assert "repository_change_required_ci_job_not_green:PostgreSQL authority" in missing_job.blockers
    assert missing_job.disposition is CodingVerificationDisposition.HOLD


def test_missing_stage_evidence_produces_hold_not_synthetic_success() -> None:
    result = verify_repository_change(
        scope=scope(), patch=patch(), quality=None, review=None, ci=None
    )
    assert result.disposition is CodingVerificationDisposition.HOLD
    assert "repository_change_quality_evidence_missing" in result.blockers
    assert "repository_change_independent_review_missing" in result.blockers
    assert "repository_change_exact_head_ci_missing" in result.blockers
    assert result.completed_stages == (
        CodingVerificationStage.CHANGE_SCOPED,
        CodingVerificationStage.PATCH_EVIDENCED,
    )
    with pytest.raises(ValueError, match="repository_change_not_verified"):
        software_engineering_proof_from_verified_change(result)


def test_path_traversal_and_duplicate_scope_paths_are_rejected() -> None:
    with pytest.raises(ValueError, match="repository_change_path_traversal_forbidden"):
        scope(allowed_paths=("../secret.txt",))
    with pytest.raises(ValueError, match="allowed_paths_must_be_unique"):
        scope(allowed_paths=("app/a.py", "app/a.py"), expected_changed_paths=())


def test_patch_and_final_artifact_are_tamper_evident_and_replay_deterministic() -> None:
    original_patch = patch()
    tampered_patch = original_patch.model_dump(mode="json")
    tampered_patch["additions"] += 1
    with pytest.raises(ValidationError, match="repository_change_patch_fingerprint_mismatch"):
        RepositoryPatchEvidence.model_validate(tampered_patch)

    one = verified()
    two = verified()
    assert one.fingerprint == two.fingerprint
    tampered_final = one.model_dump(mode="json")
    tampered_final["test_count"] += 1
    with pytest.raises(ValidationError, match="repository_change_verification_fingerprint_mismatch"):
        RepositoryChangeVerification.model_validate(tampered_final)
