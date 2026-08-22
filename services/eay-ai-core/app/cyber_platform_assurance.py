"""Defensive, evidence-bound platform security assurance for EAY Jarvis.

Jarvis can continuously test EAY repository/sandbox/staging controls and can
perform explicitly authorized read-only production verification. This contract
never creates exploit payloads, captures credentials, mutates production,
automatically remediates, or grants execution authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

CYBER_PLATFORM_ASSURANCE_CONTRACT = "eay-cyber-platform-assurance-v1"

# Match credential/offensive material, not harmless semantic labels such as
# ``session-binding`` or ``secret-safe-observability``.
_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key|password|passwd|"
    r"secret(?:[_-]?(?:value|material|credential)|:)|"
    r"session(?:id|[_-]?(?:token|cookie|secret))(?:[-_: ]|$)|"
    r"cookie(?:[-_: ]|$)|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|"
    r"persistence[_-]?payload|ransomware[_-]?payload|shellcode)"
)


class SecurityStandard(str, Enum):
    OWASP_ASVS_5_0_0 = "owasp_asvs_5.0.0"
    NIST_CSF_2_0 = "nist_csf_2.0"
    EAY_SECURITY_BOUNDARY = "eay_security_boundary"


class SecurityAssuranceEnvironment(str, Enum):
    REPOSITORY = "repository"
    SANDBOX = "sandbox"
    STAGING = "staging"
    PRODUCTION_READ_ONLY = "production_read_only"


class SecurityProbeMode(str, Enum):
    STATIC_ANALYSIS = "static_analysis"
    CONTRACT_TEST = "contract_test"
    SANDBOX_ADVERSARIAL = "sandbox_adversarial"
    AUTHORIZED_READ_ONLY = "authorized_read_only"


class SecurityControlFamily(str, Enum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    TENANT_ISOLATION = "tenant_isolation"
    SECRET_HANDLING = "secret_handling"
    INPUT_BOUNDARY = "input_boundary"
    DATA_ACCESS = "data_access"
    SIDE_EFFECT_SAFETY = "side_effect_safety"
    AUDITABILITY = "auditability"
    SUPPLY_CHAIN = "supply_chain"
    CYBER_PRIORITY = "cyber_priority"
    INCIDENT_DISCLOSURE = "incident_disclosure"
    RECOVERY = "recovery"


class SecurityAssuranceStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class SecurityFindingSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityAssuranceTestCase(BaseModel):
    contract: str = CYBER_PLATFORM_ASSURANCE_CONTRACT
    test_id: str = Field(min_length=1)
    standards: tuple[SecurityStandard, ...] = Field(min_length=1)
    control_family: SecurityControlFamily
    probe_mode: SecurityProbeMode
    target_ref: str = Field(min_length=1)
    invariant_ref: str = Field(min_length=1)
    evidence_requirements: tuple[str, ...] = Field(min_length=1)
    destructive_actions_allowed: bool = False
    exploit_generation_allowed: bool = False
    credential_capture_allowed: bool = False
    production_mutation_allowed: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_security_test(self) -> SecurityAssuranceTestCase:
        if len(self.standards) != len(set(self.standards)):
            raise ValueError("cyber_assurance_standards_must_be_unique")
        if len(self.evidence_requirements) != len(set(self.evidence_requirements)):
            raise ValueError("cyber_assurance_evidence_requirements_must_be_unique")
        if self.destructive_actions_allowed:
            raise ValueError("cyber_assurance_destructive_action_forbidden")
        if self.exploit_generation_allowed:
            raise ValueError("cyber_assurance_exploit_generation_forbidden")
        if self.credential_capture_allowed:
            raise ValueError("cyber_assurance_credential_capture_forbidden")
        if self.production_mutation_allowed:
            raise ValueError("cyber_assurance_production_mutation_forbidden")
        if self.execution_authority_granted:
            raise ValueError("cyber_assurance_never_grants_execution_authority")
        _validate_refs(
            (
                self.test_id,
                self.target_ref,
                self.invariant_ref,
                *self.evidence_requirements,
            ),
            "cyber_assurance_unsafe_reference_forbidden",
        )
        _verify(self, "cyber_assurance_test_fingerprint_mismatch")
        return self


class SecurityAssurancePlan(BaseModel):
    contract: str = CYBER_PLATFORM_ASSURANCE_CONTRACT
    plan_id: str = Field(min_length=1)
    repository_ref: str = Field(min_length=1)
    revision_ref: str = Field(min_length=1)
    environment: SecurityAssuranceEnvironment
    tests: tuple[SecurityAssuranceTestCase, ...] = Field(min_length=1)
    exploit_generation_allowed: bool = False
    production_write_allowed: bool = False
    automatic_remediation_allowed: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_security_plan(self) -> SecurityAssurancePlan:
        if len({test.test_id for test in self.tests}) != len(self.tests):
            raise ValueError("cyber_assurance_duplicate_test_id")
        for test in self.tests:
            SecurityAssuranceTestCase.model_validate(test.model_dump(mode="json"))
        if self.environment is SecurityAssuranceEnvironment.PRODUCTION_READ_ONLY:
            forbidden = {
                SecurityProbeMode.SANDBOX_ADVERSARIAL,
                SecurityProbeMode.CONTRACT_TEST,
            }
            if any(test.probe_mode in forbidden for test in self.tests):
                raise ValueError("cyber_assurance_production_plan_must_be_read_only")
        if self.exploit_generation_allowed:
            raise ValueError("cyber_assurance_plan_exploit_generation_forbidden")
        if self.production_write_allowed:
            raise ValueError("cyber_assurance_plan_production_write_forbidden")
        if self.automatic_remediation_allowed:
            raise ValueError("cyber_assurance_plan_auto_remediation_forbidden")
        if self.execution_authority_granted:
            raise ValueError("cyber_assurance_plan_never_grants_execution_authority")
        _validate_refs(
            (self.plan_id, self.repository_ref, self.revision_ref),
            "cyber_assurance_plan_unsafe_reference_forbidden",
        )
        _verify(self, "cyber_assurance_plan_fingerprint_mismatch")
        return self


class SecurityAssuranceFinding(BaseModel):
    contract: str = CYBER_PLATFORM_ASSURANCE_CONTRACT
    finding_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_id: str = Field(min_length=1)
    test_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: SecurityAssuranceStatus
    severity: SecurityFindingSeverity
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    control_verified: bool = False
    remediation_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_security_finding(self) -> SecurityAssuranceFinding:
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("cyber_assurance_finding_evidence_refs_must_be_unique")
        if self.control_verified != (self.status is SecurityAssuranceStatus.PASS):
            raise ValueError("cyber_assurance_control_verified_requires_pass")
        if self.remediation_authority_granted:
            raise ValueError("cyber_assurance_finding_never_grants_remediation_authority")
        if self.execution_authority_granted:
            raise ValueError("cyber_assurance_finding_never_grants_execution_authority")
        _validate_refs(
            (self.finding_id, self.plan_id, self.test_id, *self.evidence_refs),
            "cyber_assurance_finding_unsafe_reference_forbidden",
        )
        _verify(self, "cyber_assurance_finding_fingerprint_mismatch")
        return self


_CASES: tuple[tuple[str, SecurityControlFamily, str, str, tuple[str, ...]], ...] = (
    (
        "authn-session-binding",
        SecurityControlFamily.AUTHENTICATION,
        "identity/session-binding",
        "authenticated-session-is-bound-to-the-exact-principal-and-context",
        ("test-receipt:authn", "evidence:session-binding"),
    ),
    (
        "authz-fail-closed",
        SecurityControlFamily.AUTHORIZATION,
        "policy/authorization-boundary",
        "missing-or-mismatched-authority-fails-before-tool-or-write-execution",
        ("test-receipt:authz", "evidence:deny-before-execution"),
    ),
    (
        "tenant-zero-leak",
        SecurityControlFamily.TENANT_ISOLATION,
        "data/tenant-boundary",
        "company-a-evidence-cannot-read-elevate-or-disclose-company-b",
        ("test-receipt:tenant-isolation", "evidence:cross-tenant-zero-leak"),
    ),
    (
        "secret-safe-observability",
        SecurityControlFamily.SECRET_HANDLING,
        "observability/logging",
        "credentials-and-sensitive-material-never-enter-memory-audit-or-traces",
        ("test-receipt:secret-safety", "evidence:redaction-boundary"),
    ),
    (
        "input-and-query-boundary",
        SecurityControlFamily.INPUT_BOUNDARY,
        "runtime/input-boundary",
        "model-controlled-input-cannot-expand-reviewed-query-or-tool-scope",
        ("test-receipt:input-boundary", "evidence:static-query-or-schema"),
    ),
    (
        "authoritative-data-read",
        SecurityControlFamily.DATA_ACCESS,
        "data/authoritative-read",
        "firm-company-claims-require-current-authoritative-company-evidence",
        ("test-receipt:data-truth", "evidence:live-company-receipt"),
    ),
    (
        "side-effect-integrity",
        SecurityControlFamily.SIDE_EFFECT_SAFETY,
        "runtime/side-effect-boundary",
        "writes-require-idempotency-effect-verification-and-reconciliation",
        ("test-receipt:side-effect", "evidence:verified-effect"),
    ),
    (
        "audit-tamper-evidence",
        SecurityControlFamily.AUDITABILITY,
        "audit/integrity",
        "security-and-execution-receipts-fail-closed-after-tampering",
        ("test-receipt:audit-integrity", "evidence:fingerprint-rejection"),
    ),
    (
        "supply-presence-not-exposure",
        SecurityControlFamily.SUPPLY_CHAIN,
        "software/supply-chain",
        "repository-or-build-presence-never-becomes-deployed-company-exposure",
        ("test-receipt:supply-chain", "evidence:deployment-attestation-boundary"),
    ),
    (
        "global-threat-not-company-risk",
        SecurityControlFamily.CYBER_PRIORITY,
        "cyber/priority-boundary",
        "global-threat-signals-never-confirm-company-risk-without-current-exposure",
        ("test-receipt:cyber-priority", "evidence:company-priority-receipt"),
    ),
    (
        "incident-need-to-know",
        SecurityControlFamily.INCIDENT_DISCLOSURE,
        "cyber/incident-disclosure",
        "incident-details-stay-company-bound-and-explicit-principal-scoped",
        ("test-receipt:incident-disclosure", "evidence:audience-policy"),
    ),
    (
        "recovery-no-blind-replay",
        SecurityControlFamily.RECOVERY,
        "runtime/recovery",
        "ambiguous-or-partial-side-effects-are-reconciled-before-any-retry",
        ("test-receipt:recovery", "evidence:no-blind-replay"),
    ),
)


def build_eay_platform_security_plan(
    *,
    plan_id: str,
    repository_ref: str,
    revision_ref: str,
    environment: SecurityAssuranceEnvironment = SecurityAssuranceEnvironment.REPOSITORY,
) -> SecurityAssurancePlan:
    tests = tuple(
        _build_test_case(
            test_id=test_id,
            control_family=family,
            target_ref=target,
            invariant_ref=invariant,
            evidence_requirements=evidence,
            environment=environment,
        )
        for test_id, family, target, invariant, evidence in _CASES
    )
    draft = {
        "contract": CYBER_PLATFORM_ASSURANCE_CONTRACT,
        "plan_id": plan_id,
        "repository_ref": repository_ref,
        "revision_ref": revision_ref,
        "environment": environment.value,
        "tests": [test.model_dump(mode="json") for test in tests],
        "exploit_generation_allowed": False,
        "production_write_allowed": False,
        "automatic_remediation_allowed": False,
        "execution_authority_granted": False,
    }
    return SecurityAssurancePlan.model_validate(_sealed(draft))


def record_security_assurance_finding(
    *,
    finding_id: str,
    plan: SecurityAssurancePlan,
    test_id: str,
    status: SecurityAssuranceStatus,
    severity: SecurityFindingSeverity,
    evidence_refs: tuple[str, ...],
) -> SecurityAssuranceFinding:
    plan = SecurityAssurancePlan.model_validate(plan.model_dump(mode="json"))
    tests = {test.test_id: test for test in plan.tests}
    if test_id not in tests:
        raise ValueError("cyber_assurance_finding_test_not_in_plan")
    test = tests[test_id]
    draft = {
        "contract": CYBER_PLATFORM_ASSURANCE_CONTRACT,
        "finding_id": finding_id,
        "plan_id": plan.plan_id,
        "plan_fingerprint": plan.fingerprint,
        "test_id": test.test_id,
        "test_fingerprint": test.fingerprint,
        "status": status.value,
        "severity": severity.value,
        "evidence_refs": list(evidence_refs),
        "control_verified": status is SecurityAssuranceStatus.PASS,
        "remediation_authority_granted": False,
        "execution_authority_granted": False,
    }
    return SecurityAssuranceFinding.model_validate(_sealed(draft))


def _build_test_case(
    *,
    test_id: str,
    control_family: SecurityControlFamily,
    target_ref: str,
    invariant_ref: str,
    evidence_requirements: tuple[str, ...],
    environment: SecurityAssuranceEnvironment,
) -> SecurityAssuranceTestCase:
    if environment is SecurityAssuranceEnvironment.PRODUCTION_READ_ONLY:
        mode = SecurityProbeMode.AUTHORIZED_READ_ONLY
    elif environment is SecurityAssuranceEnvironment.SANDBOX:
        mode = SecurityProbeMode.SANDBOX_ADVERSARIAL
    else:
        mode = SecurityProbeMode.CONTRACT_TEST
    draft = {
        "contract": CYBER_PLATFORM_ASSURANCE_CONTRACT,
        "test_id": test_id,
        "standards": [
            SecurityStandard.OWASP_ASVS_5_0_0.value,
            SecurityStandard.NIST_CSF_2_0.value,
            SecurityStandard.EAY_SECURITY_BOUNDARY.value,
        ],
        "control_family": control_family.value,
        "probe_mode": mode.value,
        "target_ref": target_ref,
        "invariant_ref": invariant_ref,
        "evidence_requirements": list(evidence_requirements),
        "destructive_actions_allowed": False,
        "exploit_generation_allowed": False,
        "credential_capture_allowed": False,
        "production_mutation_allowed": False,
        "execution_authority_granted": False,
    }
    return SecurityAssuranceTestCase.model_validate(_sealed(draft))


def _validate_refs(values: tuple[str, ...], error: str) -> None:
    for value in values:
        if _UNSAFE_REF.search(value):
            raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _sealed(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "fingerprint": _fingerprint(payload)}


def _verify(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_payload(model)):
        raise ValueError(error)


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
