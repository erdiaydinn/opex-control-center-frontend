"""Credential-gated runner ports for real cyber championship competitors.

The repository intentionally does not embed vendor credentials, fabricate vendor
scores or guess private product APIs.  A real common-harness runner is admitted
only after an organization-owned authorization receipt proves the required
identity/resource bindings.  The runner never receives sealed ground truth.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.cyber_championship_execution import (
    CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
    ChampionshipSandboxAuthorization,
    CompetitorKind,
    SealedTaskBankReceipt,
    SystemExecutionReceipt,
)


class RunnerAuthorityStatus(str, Enum):
    READY = "ready"
    MISSING_ORGANIZATION_ACCESS = "missing_organization_access"
    MISSING_SCOPED_CREDENTIAL = "missing_scoped_credential"
    MISSING_RESOURCE_BINDING = "missing_resource_binding"
    NOT_AUTHORIZED_FOR_COMPETITION = "not_authorized_for_competition"


class CompetitorAdapterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    competitor: CompetitorKind
    adapter_id: str = Field(min_length=1)
    official_authority_refs: tuple[str, ...] = Field(min_length=1)
    required_identity_binding_names: tuple[str, ...] = Field(min_length=1)
    required_resource_binding_names: tuple[str, ...] = Field(min_length=1)
    read_only_competition_only: bool = True
    ground_truth_visible_to_adapter: bool = False

    @model_validator(mode="after")
    def adapter_is_bounded(self) -> CompetitorAdapterSpec:
        if self.competitor is CompetitorKind.JARVIS:
            raise ValueError("vendor_adapter_cannot_target_jarvis")
        if not self.read_only_competition_only or self.ground_truth_visible_to_adapter:
            raise ValueError("vendor_adapter_authority_boundary_violated")
        _unique(self.official_authority_refs, "vendor_adapter_authority_refs_duplicate")
        _unique(
            self.required_identity_binding_names,
            "vendor_adapter_identity_bindings_duplicate",
        )
        _unique(
            self.required_resource_binding_names,
            "vendor_adapter_resource_bindings_duplicate",
        )
        return self


class CompetitorRunnerAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    competitor: CompetitorKind
    organization_ref: str = Field(min_length=1)
    identity_binding_refs: tuple[str, ...] = Field(min_length=1)
    resource_binding_refs: tuple[str, ...] = Field(min_length=1)
    authorization_evidence_ref: str = Field(min_length=1)
    authorized_at: datetime
    expires_at: datetime
    competition_use_authorized: bool
    read_only_scope_verified: bool
    credentials_embedded_in_receipt: bool = False
    production_mutation_authority: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def authorization_is_safe(self) -> CompetitorRunnerAuthorization:
        _aware(self.authorized_at, "competitor_auth_time_requires_timezone")
        _aware(self.expires_at, "competitor_auth_expiry_requires_timezone")
        if self.expires_at <= self.authorized_at:
            raise ValueError("competitor_auth_expiry_invalid")
        if self.competitor is CompetitorKind.JARVIS:
            raise ValueError("competitor_auth_vendor_required")
        if (
            not self.competition_use_authorized
            or not self.read_only_scope_verified
            or self.credentials_embedded_in_receipt
            or self.production_mutation_authority
        ):
            raise ValueError("competitor_auth_boundary_not_satisfied")
        _unique(self.identity_binding_refs, "competitor_auth_identity_refs_duplicate")
        _unique(self.resource_binding_refs, "competitor_auth_resource_refs_duplicate")
        _verify(self, "competitor_auth_fingerprint_mismatch")
        return self


class CompetitorRunnerPort(Protocol):
    """External credentialed runner. Ground truth is deliberately absent."""

    def run_common_harness(
        self,
        *,
        adapter: CompetitorAdapterSpec,
        authorization: CompetitorRunnerAuthorization,
        bank: SealedTaskBankReceipt,
        sandbox: ChampionshipSandboxAuthorization,
    ) -> SystemExecutionReceipt: ...


def default_competitor_adapter_specs() -> tuple[CompetitorAdapterSpec, ...]:
    return (
        CompetitorAdapterSpec(
            competitor=CompetitorKind.CROWDSTRIKE_CHARLOTTE_AI,
            adapter_id="crowdstrike-charlotte-ai-common-harness-v1",
            official_authority_refs=(
                "https://developer.crowdstrike.com/docs/openapi/",
                "https://www.crowdstrike.com/en-us/platform/charlotte-ai/",
            ),
            required_identity_binding_names=(
                "falcon_tenant",
                "falcon_scoped_api_identity",
            ),
            required_resource_binding_names=("authorized_falcon_workspace",),
        ),
        CompetitorAdapterSpec(
            competitor=CompetitorKind.GOOGLE_SECURITY_OPERATIONS_GEMINI,
            adapter_id="google-secops-gemini-common-harness-v1",
            official_authority_refs=(
                "https://cloud.google.com/chronicle/docs/soar/investigate/gemini",
                "https://cloud.google.com/iam/docs/workload-identity-federation",
            ),
            required_identity_binding_names=(
                "google_workload_identity",
                "secops_authorized_principal",
            ),
            required_resource_binding_names=("google_secops_customer",),
        ),
        CompetitorAdapterSpec(
            competitor=CompetitorKind.MICROSOFT_SECURITY_COPILOT,
            adapter_id="microsoft-security-copilot-common-harness-v1",
            official_authority_refs=(
                "https://learn.microsoft.com/en-us/copilot/security/",
                "https://learn.microsoft.com/en-us/entra/identity-platform/",
            ),
            required_identity_binding_names=(
                "entra_tenant",
                "security_copilot_scoped_identity",
            ),
            required_resource_binding_names=("security_copilot_resource",),
        ),
    )


def assess_runner_authority(
    *,
    adapter: CompetitorAdapterSpec,
    authorization: CompetitorRunnerAuthorization | None,
    now: datetime,
) -> tuple[RunnerAuthorityStatus, tuple[str, ...]]:
    _aware(now, "competitor_authority_check_time_requires_timezone")
    if authorization is None:
        return (
            RunnerAuthorityStatus.MISSING_ORGANIZATION_ACCESS,
            ("competitor_organization_authorization_receipt_missing",),
        )
    authorization = CompetitorRunnerAuthorization.model_validate(
        authorization.model_dump(mode="json")
    )
    if authorization.competitor is not adapter.competitor:
        return (
            RunnerAuthorityStatus.MISSING_RESOURCE_BINDING,
            ("competitor_authorization_adapter_binding_mismatch",),
        )
    if now >= authorization.expires_at:
        return (
            RunnerAuthorityStatus.MISSING_SCOPED_CREDENTIAL,
            ("competitor_authorization_expired",),
        )
    if not authorization.competition_use_authorized:
        return (
            RunnerAuthorityStatus.NOT_AUTHORIZED_FOR_COMPETITION,
            ("competitor_competition_use_not_authorized",),
        )
    return RunnerAuthorityStatus.READY, ()


def execute_real_competitor_run(
    *,
    adapter: CompetitorAdapterSpec,
    authorization: CompetitorRunnerAuthorization,
    bank: SealedTaskBankReceipt,
    sandbox: ChampionshipSandboxAuthorization,
    runner: CompetitorRunnerPort,
    now: datetime,
) -> SystemExecutionReceipt:
    status, blockers = assess_runner_authority(
        adapter=adapter,
        authorization=authorization,
        now=now,
    )
    if status is not RunnerAuthorityStatus.READY:
        raise ValueError(blockers[0])
    receipt = runner.run_common_harness(
        adapter=adapter,
        authorization=authorization,
        bank=bank,
        sandbox=sandbox,
    )
    receipt = SystemExecutionReceipt.model_validate(receipt.model_dump(mode="json"))
    if receipt.competitor is not adapter.competitor:
        raise ValueError("competitor_runner_receipt_system_mismatch")
    if receipt.task_set_fingerprint != bank.task_set_fingerprint:
        raise ValueError("competitor_runner_task_set_mismatch")
    if receipt.environment_fingerprint != sandbox.environment_fingerprint:
        raise ValueError("competitor_runner_environment_mismatch")
    if receipt.sandbox_fingerprint != sandbox.fingerprint:
        raise ValueError("competitor_runner_sandbox_mismatch")
    if receipt.tasks_attempted != bank.task_count:
        raise ValueError("competitor_runner_incomplete_task_bank")
    return receipt


def _unique(values: tuple[Any, ...], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    value = model.model_dump(mode="json")
    value.pop("fingerprint", None)
    return value


def _verify(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_payload(model)):
        raise ValueError(error)


def _fingerprint(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
