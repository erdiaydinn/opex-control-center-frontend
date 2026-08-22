"""Governed Robot Authoring for Jarvis Adaptive Execution.

The authoring chain is deliberately non-executable:

adaptive repair -> structured candidate -> sandbox receipts -> registry candidate

Only canonical mission execution, capability, approval and commit-fence layers
may execute or activate a robot revision. This module never bypasses auth,
widens authorization, writes to production during verification or auto-publishes.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from enum import Enum
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .adaptive_execution_intelligence import (
    AdaptiveRepairProposal,
    DriftKind,
    ExecutionScope,
    RepairDisposition,
)

ROBOT_AUTHORING_CONTRACT = "eay-jarvis-robot-authoring-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RobotKind(str, Enum):
    API = "api"
    PLAYWRIGHT = "playwright"
    HYBRID = "hybrid"


class RobotAuthoringDisposition(str, Enum):
    HOLD = "HOLD"
    STRUCTURED_CANDIDATE = "STRUCTURED_CANDIDATE"


class SandboxEffectStatus(str, Enum):
    VERIFIED_EQUIVALENT = "VERIFIED_EQUIVALENT"
    VERIFIED_NOT_EQUIVALENT = "VERIFIED_NOT_EQUIVALENT"
    UNKNOWN = "UNKNOWN"


def _fingerprint(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RobotDefinition(BaseModel):
    """Current approved robot definition used only as authoring input."""

    model_config = ConfigDict(frozen=True)

    contract: str = ROBOT_AUTHORING_CONTRACT
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    objective_id: str = Field(min_length=1)
    robot_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    kind: RobotKind
    semantic_intent: str = Field(min_length=1)
    capability_ref: str = Field(min_length=1)
    manifest: tuple[tuple[str, str], ...] = Field(min_length=1)
    expected_outcome_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def manifest_is_unambiguous(self) -> RobotDefinition:
        keys: list[str] = []
        for key, value in self.manifest:
            if not key.strip() or not value.strip():
                raise ValueError("robot_manifest_keys_and_values_must_be_non_empty")
            keys.append(key)
        if len(keys) != len(set(keys)):
            raise ValueError("robot_manifest_keys_must_be_unique")
        return self


class StructuredRobotPatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str = Field(min_length=1)
    before: str = Field(min_length=1)
    after: str = Field(min_length=1)


class RobotAuthoringCandidate(BaseModel):
    """Tamper-evident robot revision that has no activation authority."""

    model_config = ConfigDict(frozen=True)

    contract: str = ROBOT_AUTHORING_CONTRACT
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    objective_id: str = Field(min_length=1)
    robot_id: str = Field(min_length=1)
    source_version: int = Field(ge=1)
    proposed_version: int = Field(ge=2)
    kind: RobotKind
    semantic_intent: str = Field(min_length=1)
    capability_ref: str = Field(min_length=1)
    repair_proposal_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_robot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    patches: tuple[StructuredRobotPatch, ...] = Field(min_length=1)
    candidate_manifest: tuple[tuple[str, str], ...] = Field(min_length=1)
    expected_outcome_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    grants_auth_bypass: bool = False
    grants_execution_authority: bool = False
    can_auto_publish: bool = False
    requires_sandbox_verification: bool = True
    requires_canonical_registration: bool = True

    @model_validator(mode="after")
    def candidate_is_sealed_and_non_authoritative(self) -> RobotAuthoringCandidate:
        if self.grants_auth_bypass or self.grants_execution_authority or self.can_auto_publish:
            raise ValueError("robot_authoring_candidate_cannot_grant_runtime_authority")
        if self.proposed_version != self.source_version + 1:
            raise ValueError("robot_authoring_candidate_version_must_increment_exactly_once")

        manifest_keys = [key for key, _ in self.candidate_manifest]
        patch_fields = [item.field for item in self.patches]
        if len(manifest_keys) != len(set(manifest_keys)):
            raise ValueError("robot_authoring_candidate_manifest_keys_must_be_unique")
        if len(patch_fields) != len(set(patch_fields)):
            raise ValueError("robot_authoring_candidate_patch_fields_must_be_unique")

        manifest = dict(self.candidate_manifest)
        if any(manifest.get(item.field) != item.after for item in self.patches):
            raise ValueError("robot_authoring_candidate_patch_manifest_mismatch")

        payload = _candidate_payload(
            tenant_id=self.tenant_id,
            company_id=self.company_id,
            objective_id=self.objective_id,
            robot_id=self.robot_id,
            source_version=self.source_version,
            proposed_version=self.proposed_version,
            kind=self.kind,
            semantic_intent=self.semantic_intent,
            capability_ref=self.capability_ref,
            repair_proposal_fingerprint=self.repair_proposal_fingerprint,
            source_robot_fingerprint=self.source_robot_fingerprint,
            patches=self.patches,
            candidate_manifest=self.candidate_manifest,
            expected_outcome_fingerprint=self.expected_outcome_fingerprint,
        )
        if _fingerprint(payload) != self.candidate_fingerprint:
            raise ValueError("robot_authoring_candidate_fingerprint_mismatch")
        return self


class RobotAuthoringResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract: str = ROBOT_AUTHORING_CONTRACT
    disposition: RobotAuthoringDisposition
    blockers: tuple[str, ...] = ()
    candidate: RobotAuthoringCandidate | None = None

    @model_validator(mode="after")
    def result_is_consistent(self) -> RobotAuthoringResult:
        if self.disposition is RobotAuthoringDisposition.HOLD and self.candidate is not None:
            raise ValueError("held_robot_authoring_result_cannot_contain_candidate")
        if (
            self.disposition is RobotAuthoringDisposition.STRUCTURED_CANDIDATE
            and self.candidate is None
        ):
            raise ValueError("structured_robot_authoring_result_requires_candidate")
        return self


class SandboxVerificationReceipt(BaseModel):
    """One independent, zero-production-write verification receipt."""

    model_config = ConfigDict(frozen=True)

    contract: str = ROBOT_AUTHORING_CONTRACT
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    objective_id: str = Field(min_length=1)
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_id: str = Field(min_length=1)
    network_policy: str = "deny-by-default"
    production_write_count: int = Field(ge=0)
    auth_bypass_observed: bool = False
    execution_authority_minted: bool = False
    effect_status: SandboxEffectStatus
    observed_outcome_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    receipt_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def receipt_is_tamper_evident(self) -> SandboxVerificationReceipt:
        payload = _sandbox_receipt_payload(
            tenant_id=self.tenant_id,
            company_id=self.company_id,
            objective_id=self.objective_id,
            candidate_fingerprint=self.candidate_fingerprint,
            environment_fingerprint=self.environment_fingerprint,
            verifier_id=self.verifier_id,
            network_policy=self.network_policy,
            production_write_count=self.production_write_count,
            auth_bypass_observed=self.auth_bypass_observed,
            execution_authority_minted=self.execution_authority_minted,
            effect_status=self.effect_status,
            observed_outcome_fingerprint=self.observed_outcome_fingerprint,
            evidence_refs=self.evidence_refs,
        )
        if _fingerprint(payload) != self.receipt_fingerprint:
            raise ValueError("sandbox_verification_receipt_fingerprint_mismatch")
        if (
            self.effect_status is SandboxEffectStatus.VERIFIED_EQUIVALENT
            and self.observed_outcome_fingerprint is None
        ):
            raise ValueError("equivalent_sandbox_receipt_requires_outcome_fingerprint")
        return self


class RobotRegistryCandidate(BaseModel):
    """Approval-required registry proposal; never an executable registry entry."""

    model_config = ConfigDict(frozen=True)

    contract: str = ROBOT_AUTHORING_CONTRACT
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    objective_id: str = Field(min_length=1)
    robot_id: str = Field(min_length=1)
    proposed_version: int = Field(ge=2)
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    sandbox_receipt_fingerprints: tuple[str, ...] = Field(min_length=2)
    independent_verifier_ids: tuple[str, ...] = Field(min_length=2)
    registry_candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_required: bool = True
    executable: bool = False
    production_activated: bool = False
    can_auto_publish: bool = False

    @model_validator(mode="after")
    def registry_candidate_is_sealed_and_non_executable(self) -> RobotRegistryCandidate:
        if (
            not self.approval_required
            or self.executable
            or self.production_activated
            or self.can_auto_publish
        ):
            raise ValueError("robot_registry_candidate_cannot_self_activate")
        if len(set(self.independent_verifier_ids)) < 2:
            raise ValueError("robot_registry_candidate_requires_two_independent_verifiers")
        if len(set(self.sandbox_receipt_fingerprints)) < 2:
            raise ValueError("robot_registry_candidate_requires_two_distinct_receipts")

        payload = _registry_candidate_payload(
            tenant_id=self.tenant_id,
            company_id=self.company_id,
            objective_id=self.objective_id,
            robot_id=self.robot_id,
            proposed_version=self.proposed_version,
            candidate_fingerprint=self.candidate_fingerprint,
            sandbox_receipt_fingerprints=self.sandbox_receipt_fingerprints,
            independent_verifier_ids=self.independent_verifier_ids,
        )
        if _fingerprint(payload) != self.registry_candidate_fingerprint:
            raise ValueError("robot_registry_candidate_fingerprint_mismatch")
        return self


_ALLOWED_PATCH_FIELDS: dict[DriftKind, frozenset[str]] = {
    DriftKind.OIDC_METADATA_CHANGE: frozenset(
        {"authorization_endpoint", "token_endpoint", "jwks_uri"}
    ),
    DriftKind.OIDC_KEY_ROTATION: frozenset({"jwks_uri"}),
    DriftKind.API_ENDPOINT_CHANGE: frozenset({"url", "operation_id", "method"}),
    DriftKind.API_SCHEMA_COMPATIBLE_CHANGE: frozenset(
        {"url", "operation_id", "method"}
    ),
    DriftKind.UI_SEMANTIC_RELOCATION: frozenset({"role", "label", "spatial_hint"}),
}
_URL_PATCH_FIELDS = frozenset(
    {"authorization_endpoint", "token_endpoint", "jwks_uri", "url"}
)


def robot_definition_fingerprint(robot: RobotDefinition) -> str:
    return _fingerprint(
        {
            "tenant_id": robot.tenant_id,
            "company_id": robot.company_id,
            "objective_id": robot.objective_id,
            "robot_id": robot.robot_id,
            "version": robot.version,
            "kind": robot.kind.value,
            "semantic_intent": robot.semantic_intent,
            "capability_ref": robot.capability_ref,
            "manifest": robot.manifest,
            "expected_outcome_fingerprint": robot.expected_outcome_fingerprint,
        }
    )


def author_repair_candidate(
    *,
    robot: RobotDefinition,
    repair_scope: ExecutionScope,
    proposal: AdaptiveRepairProposal,
) -> RobotAuthoringResult:
    """Turn only a safe repair proposal into an immutable robot revision."""

    if blocker := _scope_blocker(robot, repair_scope):
        return _hold(blocker)
    if proposal.disposition is not RepairDisposition.SANDBOX_VERIFY_CANDIDATE:
        return _hold("adaptive_repair_not_eligible_for_robot_authoring")
    if proposal.grants_auth_bypass or proposal.grants_execution_authority:
        return _hold("adaptive_repair_attempted_to_grant_forbidden_authority")

    allowed_fields = _ALLOWED_PATCH_FIELDS.get(proposal.drift_kind)
    if allowed_fields is None:
        return _hold("adaptive_repair_kind_not_authorable")

    adapter = dict(proposal.proposed_adapter)
    if not set(adapter).issubset(allowed_fields):
        return _hold("adaptive_repair_contains_unapproved_patch_field")
    if any(not str(value).strip() for value in adapter.values()):
        return _hold("adaptive_repair_contains_empty_patch_value")

    manifest = dict(robot.manifest)
    for field, value in adapter.items():
        if field in _URL_PATCH_FIELDS and (
            blocker := _trusted_https_url_blocker(
                str(value),
                repair_scope.trusted_origins,
            )
        ):
            return _hold(blocker)
        if field == "method":
            source_method = manifest.get("method")
            if source_method is None:
                return _hold("adaptive_repair_patch_field_missing_from_robot_manifest")
            if str(value).upper() != source_method.upper():
                return _hold("adaptive_repair_http_method_change_forbidden")

    patches: list[StructuredRobotPatch] = []
    for field in sorted(adapter):
        after = str(adapter[field])
        before = manifest.get(field)
        if before is None:
            return _hold("adaptive_repair_patch_field_missing_from_robot_manifest")
        if before == after:
            continue
        patches.append(StructuredRobotPatch(field=field, before=before, after=after))
        manifest[field] = after

    if not patches:
        return _hold("adaptive_repair_produced_no_robot_change")

    source_fingerprint = robot_definition_fingerprint(robot)
    candidate_manifest = tuple(sorted(manifest.items()))
    candidate_payload = _candidate_payload(
        tenant_id=robot.tenant_id,
        company_id=robot.company_id,
        objective_id=robot.objective_id,
        robot_id=robot.robot_id,
        source_version=robot.version,
        proposed_version=robot.version + 1,
        kind=robot.kind,
        semantic_intent=robot.semantic_intent,
        capability_ref=robot.capability_ref,
        repair_proposal_fingerprint=proposal.proposal_fingerprint,
        source_robot_fingerprint=source_fingerprint,
        patches=tuple(patches),
        candidate_manifest=candidate_manifest,
        expected_outcome_fingerprint=robot.expected_outcome_fingerprint,
    )
    candidate = RobotAuthoringCandidate(
        tenant_id=robot.tenant_id,
        company_id=robot.company_id,
        objective_id=robot.objective_id,
        robot_id=robot.robot_id,
        source_version=robot.version,
        proposed_version=robot.version + 1,
        kind=robot.kind,
        semantic_intent=robot.semantic_intent,
        capability_ref=robot.capability_ref,
        repair_proposal_fingerprint=proposal.proposal_fingerprint,
        source_robot_fingerprint=source_fingerprint,
        patches=tuple(patches),
        candidate_manifest=candidate_manifest,
        expected_outcome_fingerprint=robot.expected_outcome_fingerprint,
        candidate_fingerprint=_fingerprint(candidate_payload),
    )
    return RobotAuthoringResult(
        disposition=RobotAuthoringDisposition.STRUCTURED_CANDIDATE,
        candidate=candidate,
    )


def issue_sandbox_receipt(
    *,
    candidate: RobotAuthoringCandidate,
    environment_fingerprint: str,
    verifier_id: str,
    effect_status: SandboxEffectStatus,
    observed_outcome_fingerprint: str | None,
    evidence_refs: Sequence[str],
    network_policy: str = "deny-by-default",
    production_write_count: int = 0,
    auth_bypass_observed: bool = False,
    execution_authority_minted: bool = False,
) -> SandboxVerificationReceipt:
    """Seal one sandbox result without interpreting it as promotion authority."""

    if not _SHA256.fullmatch(environment_fingerprint):
        raise ValueError("sandbox_environment_fingerprint_invalid")
    if observed_outcome_fingerprint is not None and not _SHA256.fullmatch(
        observed_outcome_fingerprint
    ):
        raise ValueError("sandbox_outcome_fingerprint_invalid")
    evidence = tuple(dict.fromkeys(item.strip() for item in evidence_refs if item.strip()))
    if not evidence:
        raise ValueError("sandbox_verification_requires_evidence")

    payload = _sandbox_receipt_payload(
        tenant_id=candidate.tenant_id,
        company_id=candidate.company_id,
        objective_id=candidate.objective_id,
        candidate_fingerprint=candidate.candidate_fingerprint,
        environment_fingerprint=environment_fingerprint,
        verifier_id=verifier_id,
        network_policy=network_policy,
        production_write_count=production_write_count,
        auth_bypass_observed=auth_bypass_observed,
        execution_authority_minted=execution_authority_minted,
        effect_status=effect_status,
        observed_outcome_fingerprint=observed_outcome_fingerprint,
        evidence_refs=evidence,
    )
    return SandboxVerificationReceipt(
        tenant_id=candidate.tenant_id,
        company_id=candidate.company_id,
        objective_id=candidate.objective_id,
        candidate_fingerprint=candidate.candidate_fingerprint,
        environment_fingerprint=environment_fingerprint,
        verifier_id=verifier_id,
        network_policy=network_policy,
        production_write_count=production_write_count,
        auth_bypass_observed=auth_bypass_observed,
        execution_authority_minted=execution_authority_minted,
        effect_status=effect_status,
        observed_outcome_fingerprint=observed_outcome_fingerprint,
        evidence_refs=evidence,
        receipt_fingerprint=_fingerprint(payload),
    )


def build_registry_candidate(
    *,
    candidate: RobotAuthoringCandidate,
    receipts: Sequence[SandboxVerificationReceipt],
) -> RobotRegistryCandidate:
    """Admit only dual independent equivalent sandbox proof for review."""

    if len(receipts) < 2:
        raise ValueError("robot_registry_requires_two_sandbox_receipts")
    verifier_ids: list[str] = []
    receipt_fingerprints: list[str] = []
    for receipt in receipts:
        _validate_sandbox_receipt(candidate, receipt)
        verifier_ids.append(receipt.verifier_id)
        receipt_fingerprints.append(receipt.receipt_fingerprint)

    if len(set(verifier_ids)) < 2:
        raise ValueError("robot_registry_requires_two_independent_sandbox_verifiers")

    unique_receipts = tuple(sorted(set(receipt_fingerprints)))
    if len(unique_receipts) < 2:
        raise ValueError("robot_registry_requires_two_distinct_sandbox_receipts")
    unique_verifiers = tuple(sorted(set(verifier_ids)))
    payload = _registry_candidate_payload(
        tenant_id=candidate.tenant_id,
        company_id=candidate.company_id,
        objective_id=candidate.objective_id,
        robot_id=candidate.robot_id,
        proposed_version=candidate.proposed_version,
        candidate_fingerprint=candidate.candidate_fingerprint,
        sandbox_receipt_fingerprints=unique_receipts,
        independent_verifier_ids=unique_verifiers,
    )
    return RobotRegistryCandidate(
        tenant_id=candidate.tenant_id,
        company_id=candidate.company_id,
        objective_id=candidate.objective_id,
        robot_id=candidate.robot_id,
        proposed_version=candidate.proposed_version,
        candidate_fingerprint=candidate.candidate_fingerprint,
        sandbox_receipt_fingerprints=unique_receipts,
        independent_verifier_ids=unique_verifiers,
        registry_candidate_fingerprint=_fingerprint(payload),
    )


def _candidate_payload(
    *,
    tenant_id: str,
    company_id: str,
    objective_id: str,
    robot_id: str,
    source_version: int,
    proposed_version: int,
    kind: RobotKind,
    semantic_intent: str,
    capability_ref: str,
    repair_proposal_fingerprint: str,
    source_robot_fingerprint: str,
    patches: Sequence[StructuredRobotPatch],
    candidate_manifest: Sequence[tuple[str, str]],
    expected_outcome_fingerprint: str,
) -> dict[str, object]:
    return {
        "tenant_id": tenant_id,
        "company_id": company_id,
        "objective_id": objective_id,
        "robot_id": robot_id,
        "source_version": source_version,
        "proposed_version": proposed_version,
        "kind": kind.value,
        "semantic_intent": semantic_intent,
        "capability_ref": capability_ref,
        "repair_proposal_fingerprint": repair_proposal_fingerprint,
        "source_robot_fingerprint": source_robot_fingerprint,
        "patches": tuple((item.field, item.before, item.after) for item in patches),
        "candidate_manifest": tuple(candidate_manifest),
        "expected_outcome_fingerprint": expected_outcome_fingerprint,
        "grants_auth_bypass": False,
        "grants_execution_authority": False,
        "can_auto_publish": False,
    }


def _sandbox_receipt_payload(
    *,
    tenant_id: str,
    company_id: str,
    objective_id: str,
    candidate_fingerprint: str,
    environment_fingerprint: str,
    verifier_id: str,
    network_policy: str,
    production_write_count: int,
    auth_bypass_observed: bool,
    execution_authority_minted: bool,
    effect_status: SandboxEffectStatus,
    observed_outcome_fingerprint: str | None,
    evidence_refs: Sequence[str],
) -> dict[str, object]:
    return {
        "tenant_id": tenant_id,
        "company_id": company_id,
        "objective_id": objective_id,
        "candidate_fingerprint": candidate_fingerprint,
        "environment_fingerprint": environment_fingerprint,
        "verifier_id": verifier_id,
        "network_policy": network_policy,
        "production_write_count": production_write_count,
        "auth_bypass_observed": auth_bypass_observed,
        "execution_authority_minted": execution_authority_minted,
        "effect_status": effect_status.value,
        "observed_outcome_fingerprint": observed_outcome_fingerprint,
        "evidence_refs": tuple(evidence_refs),
    }


def _registry_candidate_payload(
    *,
    tenant_id: str,
    company_id: str,
    objective_id: str,
    robot_id: str,
    proposed_version: int,
    candidate_fingerprint: str,
    sandbox_receipt_fingerprints: Sequence[str],
    independent_verifier_ids: Sequence[str],
) -> dict[str, object]:
    return {
        "tenant_id": tenant_id,
        "company_id": company_id,
        "objective_id": objective_id,
        "robot_id": robot_id,
        "proposed_version": proposed_version,
        "candidate_fingerprint": candidate_fingerprint,
        "sandbox_receipt_fingerprints": tuple(sandbox_receipt_fingerprints),
        "independent_verifier_ids": tuple(independent_verifier_ids),
        "approval_required": True,
        "executable": False,
        "production_activated": False,
        "can_auto_publish": False,
    }


def _trusted_https_url_blocker(
    url: str,
    trusted_origins: frozenset[str],
) -> str | None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return "adaptive_repair_url_malformed"
    if parsed.scheme.lower() != "https":
        return "adaptive_repair_url_requires_https"
    if parsed.username or parsed.password:
        return "adaptive_repair_url_embedded_credentials_forbidden"
    if not parsed.hostname:
        return "adaptive_repair_url_malformed"

    suffix = "" if port in (None, 443) else f":{port}"
    origin = f"https://{parsed.hostname.lower()}{suffix}"
    normalized_trusted = {item.casefold().rstrip("/") for item in trusted_origins}
    if origin not in normalized_trusted:
        return "adaptive_repair_url_not_trusted"
    return None


def _scope_blocker(robot: RobotDefinition, repair_scope: ExecutionScope) -> str | None:
    if robot.tenant_id != repair_scope.tenant_id:
        return "robot_authoring_tenant_mismatch"
    if robot.company_id != repair_scope.company_id:
        return "robot_authoring_company_mismatch"
    if robot.objective_id != repair_scope.objective_id:
        return "robot_authoring_objective_mismatch"
    return None


def _validate_sandbox_receipt(
    candidate: RobotAuthoringCandidate,
    receipt: SandboxVerificationReceipt,
) -> None:
    if (
        receipt.tenant_id != candidate.tenant_id
        or receipt.company_id != candidate.company_id
        or receipt.objective_id != candidate.objective_id
    ):
        raise ValueError("sandbox_receipt_scope_mismatch")
    if receipt.candidate_fingerprint != candidate.candidate_fingerprint:
        raise ValueError("sandbox_receipt_candidate_mismatch")
    if receipt.network_policy != "deny-by-default":
        raise ValueError("sandbox_receipt_network_policy_not_fail_closed")
    if receipt.production_write_count != 0:
        raise ValueError("sandbox_receipt_contains_production_write")
    if receipt.auth_bypass_observed:
        raise ValueError("sandbox_receipt_observed_auth_bypass")
    if receipt.execution_authority_minted:
        raise ValueError("sandbox_receipt_minted_execution_authority")
    if receipt.effect_status is not SandboxEffectStatus.VERIFIED_EQUIVALENT:
        raise ValueError("sandbox_receipt_outcome_not_verified_equivalent")
    if receipt.observed_outcome_fingerprint != candidate.expected_outcome_fingerprint:
        raise ValueError("sandbox_receipt_business_outcome_mismatch")


def _hold(blocker: str) -> RobotAuthoringResult:
    return RobotAuthoringResult(
        disposition=RobotAuthoringDisposition.HOLD,
        blockers=(blocker,),
    )
