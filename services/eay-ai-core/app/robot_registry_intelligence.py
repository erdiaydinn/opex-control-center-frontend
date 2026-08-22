"""Passive loader/compiler for approved versions in the Jarvis Robot Registry.

This module cannot activate a registry version and cannot execute a plan. It
validates the persistent artifact fingerprint and scope, then compiles the
approved manifest into the existing API or Playwright capability-plan types.
Mission execution, authorization, idempotency and effect verification remain
separate canonical authorities.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .playwright_computer_runtime import (
    BrowserAction,
    BrowserActionKind,
    BrowserLocator,
    LocatorKind,
    PlaywrightSessionConfig,
)
from .playwright_mission_adapter import PlaywrightCapabilityPlan
from .robot_authoring_intelligence import RobotKind

ROBOT_REGISTRY_INTELLIGENCE_CONTRACT = "eay-jarvis-robot-registry-intelligence-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_MANIFEST_FIELDS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "jwt",
        "password",
        "passwd",
        "refresh_token",
        "secret",
        "token",
    }
)
_API_FIELDS = frozenset({"method", "url", "operation_id"})
_PLAYWRIGHT_FIELDS = frozenset(
    {
        "start_url",
        "action_kind",
        "action_id",
        "commit_action_id",
        "role",
        "label",
        "locator_kind",
        "locator_value",
        "spatial_hint",
        "timeout_ms",
        "settle_ms",
    }
)
_API_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"})


class CompiledPlanKind(str, Enum):
    API = "api"
    PLAYWRIGHT = "playwright"


class ApprovedRobotVersion(BaseModel):
    """Combined active registry pointer + immutable approved version artifact."""

    model_config = ConfigDict(frozen=True)

    contract: str = ROBOT_REGISTRY_INTELLIGENCE_CONTRACT
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    objective_id: str = Field(min_length=1)
    robot_id: str = Field(min_length=1)
    robot_version: int = Field(ge=1)
    parent_version: int | None = Field(default=None, ge=1)
    parent_version_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    kind: RobotKind
    semantic_intent: str = Field(min_length=1)
    capability_ref: str = Field(min_length=1)
    manifest: tuple[tuple[str, str], ...] = Field(min_length=1)
    expected_outcome_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_robot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    registry_candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_evidence_ref: str = Field(min_length=1)
    version_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation: int = Field(ge=1)
    registry_state: str = "active"
    active_version_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def artifact_is_active_sealed_and_unambiguous(self) -> ApprovedRobotVersion:
        if self.registry_state != "active":
            raise ValueError("robot_registry_loader_requires_active_registry")
        if self.active_version_fingerprint != self.version_fingerprint:
            raise ValueError("robot_registry_loader_active_fingerprint_mismatch")
        if (self.parent_version is None) != (self.parent_version_fingerprint is None):
            raise ValueError("robot_registry_loader_parent_fields_must_be_paired")
        keys = [key for key, _ in self.manifest]
        if len(keys) != len(set(keys)) or any(not key.strip() for key in keys):
            raise ValueError("robot_registry_loader_manifest_keys_must_be_unique")
        if any(not value.strip() for _, value in self.manifest):
            raise ValueError("robot_registry_loader_manifest_values_must_be_non_empty")
        if _version_fingerprint(self) != self.version_fingerprint:
            raise ValueError("robot_registry_loader_version_fingerprint_mismatch")
        return self


class RobotCompilationScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    objective_id: str = Field(min_length=1)
    allowed_hosts: frozenset[str] = Field(min_length=1)
    application_id: str = Field(min_length=1)
    tenant_scope_ref: str = Field(min_length=1)
    auth_context_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def hosts_are_normalized(self) -> RobotCompilationScope:
        normalized = frozenset(item.casefold().rstrip(".") for item in self.allowed_hosts)
        if not normalized or any(not item for item in normalized):
            raise ValueError("robot_compiler_allowed_hosts_required")
        object.__setattr__(self, "allowed_hosts", normalized)
        return self


class ApiCapabilityPlan(BaseModel):
    """Passive API call description. It is not direct-call authorization."""

    model_config = ConfigDict(frozen=True)

    contract: str = ROBOT_REGISTRY_INTELLIGENCE_CONTRACT
    capability_ref: str = Field(min_length=1)
    method: str = Field(min_length=1)
    url: str = Field(min_length=8)
    operation_id: str = Field(min_length=1)
    expected_outcome_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    side_effect_possible: bool
    direct_api_execution_authorized: bool = False

    @model_validator(mode="after")
    def never_grants_direct_execution(self) -> ApiCapabilityPlan:
        if self.direct_api_execution_authorized:
            raise ValueError("robot_api_plan_cannot_grant_direct_execution")
        return self


class CompiledRobotPlan(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    contract: str = ROBOT_REGISTRY_INTELLIGENCE_CONTRACT
    tenant_id: str
    company_id: str
    objective_id: str
    robot_id: str
    robot_version: int
    generation: int
    kind: CompiledPlanKind
    version_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_evidence_ref: str
    api_plan: ApiCapabilityPlan | None = None
    playwright_plan: PlaywrightCapabilityPlan | None = None
    execution_authority_granted: bool = False
    production_activation_granted: bool = False

    @model_validator(mode="after")
    def exactly_one_passive_plan(self) -> CompiledRobotPlan:
        if self.execution_authority_granted or self.production_activation_granted:
            raise ValueError("robot_compiler_cannot_grant_runtime_authority")
        if (self.api_plan is None) == (self.playwright_plan is None):
            raise ValueError("robot_compiler_requires_exactly_one_plan")
        if self.kind is CompiledPlanKind.API and self.api_plan is None:
            raise ValueError("robot_compiler_api_kind_requires_api_plan")
        if self.kind is CompiledPlanKind.PLAYWRIGHT and self.playwright_plan is None:
            raise ValueError("robot_compiler_playwright_kind_requires_browser_plan")
        return self


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _version_fingerprint(version: ApprovedRobotVersion) -> str:
    return _sha(
        {
            "tenant_id": version.tenant_id,
            "company_id": version.company_id,
            "objective_id": version.objective_id,
            "robot_id": version.robot_id,
            "robot_version": version.robot_version,
            "parent_version": version.parent_version,
            "parent_version_fingerprint": version.parent_version_fingerprint,
            "kind": version.kind.value,
            "semantic_intent": version.semantic_intent,
            "capability_ref": version.capability_ref,
            "manifest": dict(version.manifest),
            "expected_outcome_fingerprint": version.expected_outcome_fingerprint,
            "source_robot_fingerprint": version.source_robot_fingerprint,
            "candidate_fingerprint": version.candidate_fingerprint,
            "registry_candidate_fingerprint": version.registry_candidate_fingerprint,
            "approval_evidence_ref": version.approval_evidence_ref,
        }
    )


def calculate_version_fingerprint(
    *,
    tenant_id: str,
    company_id: str,
    objective_id: str,
    robot_id: str,
    robot_version: int,
    parent_version: int | None,
    parent_version_fingerprint: str | None,
    kind: RobotKind,
    semantic_intent: str,
    capability_ref: str,
    manifest: dict[str, str],
    expected_outcome_fingerprint: str,
    source_robot_fingerprint: str,
    candidate_fingerprint: str,
    registry_candidate_fingerprint: str,
    approval_evidence_ref: str,
) -> str:
    """Public deterministic helper matching the Core API persistence contract."""

    return _sha(
        {
            "tenant_id": tenant_id,
            "company_id": company_id,
            "objective_id": objective_id,
            "robot_id": robot_id,
            "robot_version": robot_version,
            "parent_version": parent_version,
            "parent_version_fingerprint": parent_version_fingerprint,
            "kind": kind.value,
            "semantic_intent": semantic_intent,
            "capability_ref": capability_ref,
            "manifest": manifest,
            "expected_outcome_fingerprint": expected_outcome_fingerprint,
            "source_robot_fingerprint": source_robot_fingerprint,
            "candidate_fingerprint": candidate_fingerprint,
            "registry_candidate_fingerprint": registry_candidate_fingerprint,
            "approval_evidence_ref": approval_evidence_ref,
        }
    )


def compile_approved_robot(
    *,
    version: ApprovedRobotVersion,
    scope: RobotCompilationScope,
) -> CompiledRobotPlan:
    """Compile an active, approved robot artifact without executing it."""

    _validate_scope(version, scope)
    manifest = dict(version.manifest)
    sensitive = {key.casefold() for key in manifest} & _SENSITIVE_MANIFEST_FIELDS
    if sensitive:
        raise ValueError("robot_compiler_manifest_contains_sensitive_field")

    if version.kind is RobotKind.API:
        plan = _compile_api(version, manifest, scope)
        return CompiledRobotPlan(
            tenant_id=version.tenant_id,
            company_id=version.company_id,
            objective_id=version.objective_id,
            robot_id=version.robot_id,
            robot_version=version.robot_version,
            generation=version.generation,
            kind=CompiledPlanKind.API,
            version_fingerprint=version.version_fingerprint,
            approval_evidence_ref=version.approval_evidence_ref,
            api_plan=plan,
        )
    if version.kind is RobotKind.PLAYWRIGHT:
        plan = _compile_playwright(version, manifest, scope)
        return CompiledRobotPlan(
            tenant_id=version.tenant_id,
            company_id=version.company_id,
            objective_id=version.objective_id,
            robot_id=version.robot_id,
            robot_version=version.robot_version,
            generation=version.generation,
            kind=CompiledPlanKind.PLAYWRIGHT,
            version_fingerprint=version.version_fingerprint,
            approval_evidence_ref=version.approval_evidence_ref,
            playwright_plan=plan,
        )
    raise ValueError("robot_compiler_hybrid_plan_requires_explicit_composition")


def _validate_scope(version: ApprovedRobotVersion, scope: RobotCompilationScope) -> None:
    if version.tenant_id != scope.tenant_id:
        raise ValueError("robot_compiler_tenant_mismatch")
    if version.company_id != scope.company_id:
        raise ValueError("robot_compiler_company_mismatch")
    if version.objective_id != scope.objective_id:
        raise ValueError("robot_compiler_objective_mismatch")


def _compile_api(
    version: ApprovedRobotVersion,
    manifest: dict[str, str],
    scope: RobotCompilationScope,
) -> ApiCapabilityPlan:
    if set(manifest) != _API_FIELDS:
        raise ValueError("robot_compiler_api_manifest_not_exact")
    method = manifest["method"].upper()
    if method not in _API_METHODS:
        raise ValueError("robot_compiler_api_method_not_allowed")
    _require_trusted_https(manifest["url"], scope.allowed_hosts)
    return ApiCapabilityPlan(
        capability_ref=version.capability_ref,
        method=method,
        url=manifest["url"],
        operation_id=manifest["operation_id"],
        expected_outcome_fingerprint=version.expected_outcome_fingerprint,
        side_effect_possible=method not in {"GET", "HEAD"},
    )


def _compile_playwright(
    version: ApprovedRobotVersion,
    manifest: dict[str, str],
    scope: RobotCompilationScope,
) -> PlaywrightCapabilityPlan:
    if not set(manifest).issubset(_PLAYWRIGHT_FIELDS):
        raise ValueError("robot_compiler_playwright_manifest_contains_unapproved_field")
    required = {"start_url", "action_kind", "action_id", "commit_action_id"}
    if not required.issubset(manifest):
        raise ValueError("robot_compiler_playwright_manifest_missing_required_field")
    if manifest["action_kind"] != BrowserActionKind.CLICK.value:
        raise ValueError("robot_compiler_playwright_v1_only_compiles_click")
    if manifest["commit_action_id"] != manifest["action_id"]:
        raise ValueError("robot_compiler_playwright_v1_commit_must_match_single_action")
    _require_trusted_https(manifest["start_url"], scope.allowed_hosts)
    locator = _compile_locator(manifest)
    timeout_ms = _bounded_int(manifest.get("timeout_ms", "15000"), 100, 60000, "timeout")
    settle_ms = _bounded_int(manifest.get("settle_ms", "750"), 0, 10000, "settle")
    action = BrowserAction(
        action_id=manifest["action_id"],
        kind=BrowserActionKind.CLICK,
        locator=locator,
        timeout_ms=timeout_ms,
        settle_ms=settle_ms,
    )
    session = PlaywrightSessionConfig(
        application_id=scope.application_id,
        tenant_scope_ref=scope.tenant_scope_ref,
        auth_context_ref=scope.auth_context_ref,
        allowed_hosts=scope.allowed_hosts,
    )
    return PlaywrightCapabilityPlan(
        capability_ref=version.capability_ref,
        session_config=session,
        start_url=manifest["start_url"],
        actions=(action,),
        commit_action_id=manifest["commit_action_id"],
    )


def _compile_locator(manifest: dict[str, str]) -> BrowserLocator:
    role = manifest.get("role")
    label = manifest.get("label")
    locator_kind = manifest.get("locator_kind")
    locator_value = manifest.get("locator_value")
    if role:
        if not label:
            raise ValueError("robot_compiler_role_locator_requires_label")
        return BrowserLocator(
            kind=LocatorKind.ROLE,
            value=role,
            accessible_name=label,
        )
    if label:
        return BrowserLocator(kind=LocatorKind.LABEL, value=label)
    if locator_kind and locator_value:
        try:
            kind = LocatorKind(locator_kind)
        except ValueError as exc:
            raise ValueError("robot_compiler_locator_kind_not_allowed") from exc
        if kind is LocatorKind.CSS:
            raise ValueError("robot_compiler_registry_does_not_compile_css_locator")
        return BrowserLocator(kind=kind, value=locator_value)
    raise ValueError("robot_compiler_playwright_semantic_locator_required")


def _require_trusted_https(url: str, allowed_hosts: frozenset[str]) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme != "https"
        or not host
        or host not in allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("robot_compiler_url_not_trusted_https")


def _bounded_int(raw: str, minimum: int, maximum: int, name: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"robot_compiler_{name}_must_be_integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"robot_compiler_{name}_out_of_bounds")
    return value
