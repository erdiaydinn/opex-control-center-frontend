"""Governed open-source cyber-defense source registry for EAY Jarvis.

The registry is intentionally not an auto-install list. It classifies upstream
projects by defensive value and the *maximum* environment in which EAY may use
them. Repository discovery never grants execution, network, credential, data,
or production authority.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.cyber_defense_school import CyberDefenseDomain

CYBER_OPEN_SOURCE_REGISTRY_CONTRACT = "eay-cyber-open-source-registry-v1"


class OpenSourceTrustTier(str, Enum):
    FOUNDATION = "foundation"
    PRIMARY_PROJECT = "primary_project"
    HIGH_SIGNAL_COMMUNITY = "high_signal_community"
    DUAL_USE_RESEARCH = "dual_use_research"


class OpenSourceUseMode(str, Enum):
    REFERENCE_ONLY = "reference_only"
    READ_ONLY_CORPUS = "read_only_corpus"
    CI_ISOLATED = "ci_isolated"
    AUTHORIZED_SANDBOX_ONLY = "authorized_sandbox_only"


class OpenSourceRiskClass(str, Enum):
    PASSIVE_DEFENSE = "passive_defense"
    ACTIVE_VALIDATION = "active_validation"
    DUAL_USE = "dual_use"


class OpenSourceAdmission(str, Enum):
    REFERENCE_ADMITTED = "reference_admitted"
    INGESTION_REVIEW_REQUIRED = "ingestion_review_required"
    CI_REVIEW_REQUIRED = "ci_review_required"
    SANDBOX_AUTHORITY_REQUIRED = "sandbox_authority_required"
    ADMITTED_READ_ONLY = "admitted_read_only"
    ADMITTED_CI_ISOLATED = "admitted_ci_isolated"
    ADMITTED_SANDBOX = "admitted_sandbox"


class CyberOpenSourceRepository(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_OPEN_SOURCE_REGISTRY_CONTRACT
    repo: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    canonical_url: str = Field(pattern=r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    trust_tier: OpenSourceTrustTier
    domains: tuple[CyberDefenseDomain, ...] = Field(min_length=1)
    use_mode: OpenSourceUseMode
    risk_class: OpenSourceRiskClass
    rationale: str = Field(min_length=8, max_length=280)
    upstream_pin_required: bool = True
    license_review_required: bool = True
    security_review_required: bool = True
    server_side_only: bool = True
    content_vendoring_permitted: bool = False
    production_execution_permitted: bool = False
    production_mutation_permitted: bool = False
    credential_access_permitted: bool = False
    offensive_execution_permitted: bool = False
    unrestricted_network_permitted: bool = False

    @model_validator(mode="after")
    def enforce_defensive_boundary(self) -> CyberOpenSourceRepository:
        if self.canonical_url != f"https://github.com/{self.repo}":
            raise ValueError("cyber_open_source_canonical_url_mismatch")
        if len(self.domains) != len(set(self.domains)):
            raise ValueError("cyber_open_source_domains_must_be_unique")
        if not (
            self.upstream_pin_required
            and self.license_review_required
            and self.security_review_required
            and self.server_side_only
        ):
            raise ValueError("cyber_open_source_governance_controls_mandatory")
        if any(
            (
                self.content_vendoring_permitted,
                self.production_execution_permitted,
                self.production_mutation_permitted,
                self.credential_access_permitted,
                self.offensive_execution_permitted,
                self.unrestricted_network_permitted,
            )
        ):
            raise ValueError("cyber_open_source_never_grants_privileged_authority")
        if self.risk_class is OpenSourceRiskClass.DUAL_USE:
            if self.use_mode is not OpenSourceUseMode.AUTHORIZED_SANDBOX_ONLY:
                raise ValueError("cyber_open_source_dual_use_must_be_sandbox_only")
        if self.use_mode is OpenSourceUseMode.AUTHORIZED_SANDBOX_ONLY:
            if self.risk_class is OpenSourceRiskClass.PASSIVE_DEFENSE:
                raise ValueError("cyber_open_source_passive_source_not_sandbox_only")
        return self

    @property
    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        return _sha256(payload)


class CyberOpenSourceRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_OPEN_SOURCE_REGISTRY_CONTRACT
    registry_id: str = Field(min_length=1)
    repositories: tuple[CyberOpenSourceRepository, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def registry_is_unique_and_governed(self) -> CyberOpenSourceRegistry:
        repos = tuple(item.repo.lower() for item in self.repositories)
        if len(repos) != len(set(repos)):
            raise ValueError("cyber_open_source_repositories_must_be_unique")
        for item in self.repositories:
            CyberOpenSourceRepository.model_validate(item.model_dump(mode="json"))
        return self

    @property
    def fingerprint(self) -> str:
        return _sha256(self.model_dump(mode="json"))


class OpenSourceAdmissionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repo: str
    admission: OpenSourceAdmission
    repository_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    pinned_commit_sha: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")
    blockers: tuple[str, ...] = ()
    execution_authority_granted: bool = False
    production_authority_granted: bool = False

    @model_validator(mode="after")
    def decision_never_mints_authority(self) -> OpenSourceAdmissionDecision:
        if self.execution_authority_granted or self.production_authority_granted:
            raise ValueError("cyber_open_source_admission_never_grants_authority")
        return self


def load_registry(path: str | Path) -> CyberOpenSourceRegistry:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return CyberOpenSourceRegistry.model_validate(payload)


def assess_repository_admission(
    repository: CyberOpenSourceRepository,
    *,
    pinned_commit_sha: str | None = None,
    license_review_passed: bool = False,
    security_review_passed: bool = False,
    isolated_runner_verified: bool = False,
    sandbox_authorized: bool = False,
) -> OpenSourceAdmissionDecision:
    """Return the maximum defensible admission for one upstream repository.

    Discovery/reference use is immediately allowed. Any content ingestion or
    execution requires an immutable 40-hex upstream commit pin plus explicit
    license/security review. CI tools additionally require an isolated runner;
    dual-use tooling additionally requires an authorized sandbox.
    """

    blockers: list[str] = []
    if pinned_commit_sha is None:
        blockers.append("immutable_upstream_commit_pin_required")
    elif not _is_commit_sha(pinned_commit_sha):
        blockers.append("immutable_upstream_commit_pin_invalid")
    if not license_review_passed:
        blockers.append("license_review_required")
    if not security_review_passed:
        blockers.append("security_review_required")

    if repository.use_mode is OpenSourceUseMode.REFERENCE_ONLY:
        return _decision(repository, OpenSourceAdmission.REFERENCE_ADMITTED, pinned_commit_sha, ())

    if blockers:
        requested = (
            OpenSourceAdmission.INGESTION_REVIEW_REQUIRED
            if repository.use_mode is OpenSourceUseMode.READ_ONLY_CORPUS
            else OpenSourceAdmission.CI_REVIEW_REQUIRED
            if repository.use_mode is OpenSourceUseMode.CI_ISOLATED
            else OpenSourceAdmission.SANDBOX_AUTHORITY_REQUIRED
        )
        return _decision(repository, requested, pinned_commit_sha, tuple(blockers))

    if repository.use_mode is OpenSourceUseMode.READ_ONLY_CORPUS:
        return _decision(repository, OpenSourceAdmission.ADMITTED_READ_ONLY, pinned_commit_sha, ())

    if repository.use_mode is OpenSourceUseMode.CI_ISOLATED:
        if not isolated_runner_verified:
            return _decision(
                repository,
                OpenSourceAdmission.CI_REVIEW_REQUIRED,
                pinned_commit_sha,
                ("isolated_runner_verification_required",),
            )
        return _decision(repository, OpenSourceAdmission.ADMITTED_CI_ISOLATED, pinned_commit_sha, ())

    if not isolated_runner_verified:
        blockers.append("isolated_runner_verification_required")
    if not sandbox_authorized:
        blockers.append("security_guardian_sandbox_authority_required")
    if blockers:
        return _decision(
            repository,
            OpenSourceAdmission.SANDBOX_AUTHORITY_REQUIRED,
            pinned_commit_sha,
            tuple(blockers),
        )
    return _decision(repository, OpenSourceAdmission.ADMITTED_SANDBOX, pinned_commit_sha, ())


def _decision(
    repository: CyberOpenSourceRepository,
    admission: OpenSourceAdmission,
    pinned_commit_sha: str | None,
    blockers: tuple[str, ...],
) -> OpenSourceAdmissionDecision:
    return OpenSourceAdmissionDecision(
        repo=repository.repo,
        admission=admission,
        repository_fingerprint=repository.fingerprint,
        pinned_commit_sha=pinned_commit_sha if _is_commit_sha(pinned_commit_sha) else None,
        blockers=blockers,
    )


def _is_commit_sha(value: str | None) -> bool:
    if value is None or len(value) != 40:
        return False
    return all(character in "0123456789abcdef" for character in value)


def _sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
