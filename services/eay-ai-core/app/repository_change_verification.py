"""Evidence-bound repository change verification for Jarvis software engineering.

This module turns the SoftwareEngineeringProof completion checklist into a repo-aware,
sequential verification contract. Every stage binds the same repository, branch, base
SHA and candidate head SHA. Scope drift, wrong-head evidence, failed quality checks,
unresolved independent review findings or incomplete exact-head CI force HOLD.

The artifact never grants merge, execution, deployment or superiority authority.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import PurePosixPath

from pydantic import BaseModel, Field, model_validator

from .frontier_supremacy_intelligence import (
    SoftwareEngineeringAcceptance,
    SoftwareEngineeringProof,
    admit_software_engineering_completion,
)

REPOSITORY_CHANGE_VERIFICATION_CONTRACT = "eay-repository-change-verification-v1"
_SHA = r"^[0-9a-f]{40}$"
_DIGEST = r"^[0-9a-f]{64}$"
_REPO = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
_REF = r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,239}$"


class CodingVerificationDisposition(str, Enum):
    VERIFIED = "verified"
    HOLD = "hold"


class CodingVerificationStage(str, Enum):
    CHANGE_SCOPED = "change_scoped"
    PATCH_EVIDENCED = "patch_evidenced"
    QUALITY_VERIFIED = "quality_verified"
    INDEPENDENT_REVIEWED = "independent_reviewed"
    EXACT_HEAD_CI_VERIFIED = "exact_head_ci_verified"


def _seal(value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_path(path: str) -> str:
    candidate = path.replace("\\", "/").strip()
    if not candidate or candidate.startswith("/"):
        raise ValueError("repository_change_path_must_be_relative")
    parsed = PurePosixPath(candidate)
    if any(part in {"", ".", ".."} for part in parsed.parts):
        raise ValueError("repository_change_path_traversal_forbidden")
    return candidate


def _unique_paths(paths: tuple[str, ...], *, label: str) -> tuple[str, ...]:
    normalized = tuple(_validate_path(item) for item in paths)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label}_paths_must_be_unique")
    return normalized


class RepositoryChangeScope(BaseModel):
    contract: str = REPOSITORY_CHANGE_VERIFICATION_CONTRACT
    repository_full_name: str = Field(pattern=_REPO)
    branch_ref: str = Field(pattern=_REF)
    base_sha: str = Field(pattern=_SHA)
    candidate_head_sha: str = Field(pattern=_SHA)
    allowed_paths: tuple[str, ...] = Field(min_length=1)
    expected_changed_paths: tuple[str, ...] = ()
    scope_reason: str = Field(min_length=3)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def scope_is_exact_and_sealed(self) -> "RepositoryChangeScope":
        if self.base_sha == self.candidate_head_sha:
            raise ValueError("repository_change_base_and_candidate_must_differ")
        allowed = _unique_paths(self.allowed_paths, label="allowed")
        expected = _unique_paths(self.expected_changed_paths, label="expected")
        if not set(expected).issubset(set(allowed)):
            raise ValueError("repository_change_expected_path_outside_scope")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("repository_change_scope_evidence_refs_must_be_unique")
        payload = self.model_dump(mode="json", exclude={"fingerprint"})
        payload["allowed_paths"] = allowed
        payload["expected_changed_paths"] = expected
        if self.fingerprint != _seal(payload):
            raise ValueError("repository_change_scope_fingerprint_mismatch")
        return self

    @classmethod
    def seal(cls, **values: object) -> "RepositoryChangeScope":
        draft = dict(values)
        draft.setdefault("contract", REPOSITORY_CHANGE_VERIFICATION_CONTRACT)
        draft["allowed_paths"] = _unique_paths(tuple(draft["allowed_paths"]), label="allowed")
        draft["expected_changed_paths"] = _unique_paths(
            tuple(draft.get("expected_changed_paths", ())), label="expected"
        )
        payload = cls.model_construct(**draft, fingerprint="0" * 64).model_dump(
            mode="json", exclude={"fingerprint"}
        )
        return cls(**draft, fingerprint=_seal(payload))


class RepositoryPatchEvidence(BaseModel):
    repository_full_name: str = Field(pattern=_REPO)
    base_sha: str = Field(pattern=_SHA)
    candidate_head_sha: str = Field(pattern=_SHA)
    changed_paths: tuple[str, ...] = Field(min_length=1)
    additions: int = Field(ge=0)
    deletions: int = Field(ge=0)
    patch_sha256: str = Field(pattern=_DIGEST)
    repository_observation_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def patch_is_exact_and_sealed(self) -> "RepositoryPatchEvidence":
        changed = _unique_paths(self.changed_paths, label="changed")
        if self.additions + self.deletions <= 0:
            raise ValueError("repository_change_patch_must_have_diff")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("repository_change_patch_evidence_refs_must_be_unique")
        payload = self.model_dump(mode="json", exclude={"fingerprint"})
        payload["changed_paths"] = changed
        if self.fingerprint != _seal(payload):
            raise ValueError("repository_change_patch_fingerprint_mismatch")
        return self

    @classmethod
    def seal(cls, **values: object) -> "RepositoryPatchEvidence":
        draft = dict(values)
        draft["changed_paths"] = _unique_paths(tuple(draft["changed_paths"]), label="changed")
        payload = cls.model_construct(**draft, fingerprint="0" * 64).model_dump(
            mode="json", exclude={"fingerprint"}
        )
        return cls(**draft, fingerprint=_seal(payload))


class RepositoryQualityEvidence(BaseModel):
    repository_full_name: str = Field(pattern=_REPO)
    candidate_head_sha: str = Field(pattern=_SHA)
    compile_passed: bool
    tests_passed: bool
    static_analysis_passed: bool
    security_regression_passed: bool
    test_count: int = Field(ge=0)
    compile_evidence_ref: str = Field(min_length=1)
    test_evidence_ref: str = Field(min_length=1)
    static_analysis_evidence_ref: str = Field(min_length=1)
    security_evidence_ref: str = Field(min_length=1)
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def quality_is_sealed(self) -> "RepositoryQualityEvidence":
        payload = self.model_dump(mode="json", exclude={"fingerprint"})
        if self.fingerprint != _seal(payload):
            raise ValueError("repository_change_quality_fingerprint_mismatch")
        return self

    @classmethod
    def seal(cls, **values: object) -> "RepositoryQualityEvidence":
        draft = dict(values)
        payload = cls.model_construct(**draft, fingerprint="0" * 64).model_dump(
            mode="json", exclude={"fingerprint"}
        )
        return cls(**draft, fingerprint=_seal(payload))


class RepositoryIndependentReviewEvidence(BaseModel):
    repository_full_name: str = Field(pattern=_REPO)
    candidate_head_sha: str = Field(pattern=_SHA)
    reviewer_ref: str = Field(min_length=1)
    independent_evaluator: bool
    changed_files_reviewed: bool
    material_findings: int = Field(ge=0)
    unresolved_material_findings: int = Field(ge=0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def review_is_consistent_and_sealed(self) -> "RepositoryIndependentReviewEvidence":
        if self.unresolved_material_findings > self.material_findings:
            raise ValueError("repository_change_unresolved_findings_exceed_material_findings")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("repository_change_review_evidence_refs_must_be_unique")
        payload = self.model_dump(mode="json", exclude={"fingerprint"})
        if self.fingerprint != _seal(payload):
            raise ValueError("repository_change_review_fingerprint_mismatch")
        return self

    @classmethod
    def seal(cls, **values: object) -> "RepositoryIndependentReviewEvidence":
        draft = dict(values)
        payload = cls.model_construct(**draft, fingerprint="0" * 64).model_dump(
            mode="json", exclude={"fingerprint"}
        )
        return cls(**draft, fingerprint=_seal(payload))


class RepositoryExactHeadCIEvidence(BaseModel):
    repository_full_name: str = Field(pattern=_REPO)
    candidate_head_sha: str = Field(pattern=_SHA)
    merge_composition_sha: str | None = Field(default=None, pattern=_SHA)
    run_id: int = Field(gt=0)
    run_number: int = Field(gt=0)
    conclusion: str = Field(min_length=1)
    candidate_bound_to_run: bool
    required_jobs: tuple[str, ...] = Field(min_length=1)
    successful_jobs: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def ci_is_unique_and_sealed(self) -> "RepositoryExactHeadCIEvidence":
        if len(self.required_jobs) != len(set(self.required_jobs)):
            raise ValueError("repository_change_required_ci_jobs_must_be_unique")
        if len(self.successful_jobs) != len(set(self.successful_jobs)):
            raise ValueError("repository_change_successful_ci_jobs_must_be_unique")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("repository_change_ci_evidence_refs_must_be_unique")
        payload = self.model_dump(mode="json", exclude={"fingerprint"})
        if self.fingerprint != _seal(payload):
            raise ValueError("repository_change_ci_fingerprint_mismatch")
        return self

    @classmethod
    def seal(cls, **values: object) -> "RepositoryExactHeadCIEvidence":
        draft = dict(values)
        payload = cls.model_construct(**draft, fingerprint="0" * 64).model_dump(
            mode="json", exclude={"fingerprint"}
        )
        return cls(**draft, fingerprint=_seal(payload))


class RepositoryChangeVerification(BaseModel):
    contract: str = REPOSITORY_CHANGE_VERIFICATION_CONTRACT
    repository_full_name: str = Field(pattern=_REPO)
    branch_ref: str = Field(pattern=_REF)
    base_sha: str = Field(pattern=_SHA)
    candidate_head_sha: str = Field(pattern=_SHA)
    scope_fingerprint: str = Field(pattern=_DIGEST)
    patch_fingerprint: str | None = Field(default=None, pattern=_DIGEST)
    quality_fingerprint: str | None = Field(default=None, pattern=_DIGEST)
    review_fingerprint: str | None = Field(default=None, pattern=_DIGEST)
    ci_fingerprint: str | None = Field(default=None, pattern=_DIGEST)
    completed_stages: tuple[CodingVerificationStage, ...]
    disposition: CodingVerificationDisposition
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    test_count: int = Field(ge=0)
    merge_authority_granted: bool = False
    execution_authority_granted: bool = False
    deployment_authority_granted: bool = False
    superiority_claim_allowed: bool = False
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def final_artifact_is_sealed_and_non_authoritative(self) -> "RepositoryChangeVerification":
        if any(
            (
                self.merge_authority_granted,
                self.execution_authority_granted,
                self.deployment_authority_granted,
                self.superiority_claim_allowed,
            )
        ):
            raise ValueError("repository_change_verification_never_mints_authority_or_claim")
        if self.disposition is CodingVerificationDisposition.VERIFIED and self.blockers:
            raise ValueError("repository_change_verified_cannot_have_blockers")
        expected_stages = tuple(dict.fromkeys(self.completed_stages))
        if expected_stages != self.completed_stages:
            raise ValueError("repository_change_completed_stages_must_be_unique")
        payload = self.model_dump(mode="json", exclude={"fingerprint"})
        if self.fingerprint != _seal(payload):
            raise ValueError("repository_change_verification_fingerprint_mismatch")
        return self


def _identity_blockers(
    scope: RepositoryChangeScope,
    *,
    repository_full_name: str,
    candidate_head_sha: str,
    base_sha: str | None = None,
    label: str,
) -> list[str]:
    blockers: list[str] = []
    if repository_full_name != scope.repository_full_name:
        blockers.append(f"repository_change_{label}_repository_mismatch")
    if candidate_head_sha != scope.candidate_head_sha:
        blockers.append(f"repository_change_{label}_head_mismatch")
    if base_sha is not None and base_sha != scope.base_sha:
        blockers.append(f"repository_change_{label}_base_mismatch")
    return blockers


def verify_repository_change(
    *,
    scope: RepositoryChangeScope,
    patch: RepositoryPatchEvidence | None,
    quality: RepositoryQualityEvidence | None,
    review: RepositoryIndependentReviewEvidence | None,
    ci: RepositoryExactHeadCIEvidence | None,
) -> RepositoryChangeVerification:
    scope = RepositoryChangeScope.model_validate(scope.model_dump(mode="json"))
    blockers: list[str] = []
    stages: list[CodingVerificationStage] = [CodingVerificationStage.CHANGE_SCOPED]
    evidence_refs: list[str] = list(scope.evidence_refs)
    test_count = 0

    if patch is None:
        blockers.append("repository_change_patch_evidence_missing")
    else:
        patch = RepositoryPatchEvidence.model_validate(patch.model_dump(mode="json"))
        blockers.extend(
            _identity_blockers(
                scope,
                repository_full_name=patch.repository_full_name,
                candidate_head_sha=patch.candidate_head_sha,
                base_sha=patch.base_sha,
                label="patch",
            )
        )
        changed = set(patch.changed_paths)
        allowed = set(scope.allowed_paths)
        expected = set(scope.expected_changed_paths)
        unexpected = sorted(changed - allowed)
        missing = sorted(expected - changed)
        blockers.extend(f"repository_change_scope_violation:{path}" for path in unexpected)
        blockers.extend(f"repository_change_expected_path_missing:{path}" for path in missing)
        evidence_refs.extend((patch.repository_observation_ref, *patch.evidence_refs))
        if not blockers:
            stages.append(CodingVerificationStage.PATCH_EVIDENCED)

    patch_clean = CodingVerificationStage.PATCH_EVIDENCED in stages
    if quality is None:
        blockers.append("repository_change_quality_evidence_missing")
    else:
        quality = RepositoryQualityEvidence.model_validate(quality.model_dump(mode="json"))
        blockers.extend(
            _identity_blockers(
                scope,
                repository_full_name=quality.repository_full_name,
                candidate_head_sha=quality.candidate_head_sha,
                label="quality",
            )
        )
        quality_checks = {
            "repository_change_compile_not_green": quality.compile_passed,
            "repository_change_tests_not_green": quality.tests_passed,
            "repository_change_static_analysis_not_green": quality.static_analysis_passed,
            "repository_change_security_regression_not_green": quality.security_regression_passed,
            "repository_change_tests_not_exercised": quality.test_count > 0,
        }
        blockers.extend(code for code, passed in quality_checks.items() if not passed)
        test_count = quality.test_count
        evidence_refs.extend(
            (
                quality.compile_evidence_ref,
                quality.test_evidence_ref,
                quality.static_analysis_evidence_ref,
                quality.security_evidence_ref,
            )
        )
        if patch_clean and not any(code.startswith("repository_change_quality_") or code in {
            "repository_change_compile_not_green",
            "repository_change_tests_not_green",
            "repository_change_static_analysis_not_green",
            "repository_change_security_regression_not_green",
            "repository_change_tests_not_exercised",
        } for code in blockers):
            stages.append(CodingVerificationStage.QUALITY_VERIFIED)

    quality_clean = CodingVerificationStage.QUALITY_VERIFIED in stages
    if review is None:
        blockers.append("repository_change_independent_review_missing")
    else:
        review = RepositoryIndependentReviewEvidence.model_validate(review.model_dump(mode="json"))
        blockers.extend(
            _identity_blockers(
                scope,
                repository_full_name=review.repository_full_name,
                candidate_head_sha=review.candidate_head_sha,
                label="review",
            )
        )
        if not review.independent_evaluator:
            blockers.append("repository_change_independent_reviewer_required")
        if not review.changed_files_reviewed:
            blockers.append("repository_change_changed_files_not_reviewed")
        if review.unresolved_material_findings:
            blockers.append("repository_change_material_review_findings_unresolved")
        evidence_refs.extend(review.evidence_refs)
        if quality_clean and not any(
            code.startswith("repository_change_review_")
            or code in {
                "repository_change_independent_reviewer_required",
                "repository_change_changed_files_not_reviewed",
                "repository_change_material_review_findings_unresolved",
            }
            for code in blockers
        ):
            stages.append(CodingVerificationStage.INDEPENDENT_REVIEWED)

    review_clean = CodingVerificationStage.INDEPENDENT_REVIEWED in stages
    if ci is None:
        blockers.append("repository_change_exact_head_ci_missing")
    else:
        ci = RepositoryExactHeadCIEvidence.model_validate(ci.model_dump(mode="json"))
        blockers.extend(
            _identity_blockers(
                scope,
                repository_full_name=ci.repository_full_name,
                candidate_head_sha=ci.candidate_head_sha,
                label="ci",
            )
        )
        if not ci.candidate_bound_to_run:
            blockers.append("repository_change_ci_not_bound_to_candidate_head")
        if ci.conclusion.casefold() != "success":
            blockers.append("repository_change_exact_head_ci_not_green")
        missing_jobs = sorted(set(ci.required_jobs) - set(ci.successful_jobs))
        blockers.extend(f"repository_change_required_ci_job_not_green:{job}" for job in missing_jobs)
        evidence_refs.extend(ci.evidence_refs)
        if review_clean and not any(
            code.startswith("repository_change_ci_")
            or code.startswith("repository_change_required_ci_job_not_green:")
            or code == "repository_change_exact_head_ci_not_green"
            for code in blockers
        ):
            stages.append(CodingVerificationStage.EXACT_HEAD_CI_VERIFIED)

    unique_blockers = tuple(dict.fromkeys(blockers))
    disposition = (
        CodingVerificationDisposition.VERIFIED
        if not unique_blockers
        and stages[-1] is CodingVerificationStage.EXACT_HEAD_CI_VERIFIED
        else CodingVerificationDisposition.HOLD
    )
    payload = {
        "contract": REPOSITORY_CHANGE_VERIFICATION_CONTRACT,
        "repository_full_name": scope.repository_full_name,
        "branch_ref": scope.branch_ref,
        "base_sha": scope.base_sha,
        "candidate_head_sha": scope.candidate_head_sha,
        "scope_fingerprint": scope.fingerprint,
        "patch_fingerprint": patch.fingerprint if patch else None,
        "quality_fingerprint": quality.fingerprint if quality else None,
        "review_fingerprint": review.fingerprint if review else None,
        "ci_fingerprint": ci.fingerprint if ci else None,
        "completed_stages": [item.value for item in stages],
        "disposition": disposition.value,
        "blockers": unique_blockers,
        "evidence_refs": tuple(dict.fromkeys(evidence_refs)),
        "test_count": test_count,
        "merge_authority_granted": False,
        "execution_authority_granted": False,
        "deployment_authority_granted": False,
        "superiority_claim_allowed": False,
    }
    return RepositoryChangeVerification(**payload, fingerprint=_seal(payload))


def software_engineering_proof_from_verified_change(
    verification: RepositoryChangeVerification,
) -> SoftwareEngineeringProof:
    verification = RepositoryChangeVerification.model_validate(
        verification.model_dump(mode="json")
    )
    if verification.disposition is not CodingVerificationDisposition.VERIFIED:
        raise ValueError("repository_change_not_verified")
    return SoftwareEngineeringProof(
        exact_head_sha=verification.candidate_head_sha,
        changed_files_reviewed=True,
        compile_passed=True,
        tests_passed=True,
        static_analysis_passed=True,
        security_regression_passed=True,
        exact_head_ci_passed=True,
        test_count=verification.test_count,
        evidence_refs=verification.evidence_refs,
    )


def admit_verified_software_engineering_completion(
    verification: RepositoryChangeVerification,
) -> SoftwareEngineeringAcceptance:
    return admit_software_engineering_completion(
        software_engineering_proof_from_verified_change(verification)
    )
