"""Fail-closed adaptive execution repair planning for Jarvis.

This module lets Jarvis recognize bounded workflow drift (OIDC metadata, API
contracts and semantic UI relocation) without creating an authentication,
authorization or execution bypass. It only produces repair proposals; the
canonical Jarvis mission/execution authority remains responsible for permits,
side effects and verified effect receipts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import FrozenSet, Iterable, Mapping
from urllib.parse import urlsplit


class DriftKind(str, Enum):
    NONE = "NONE"
    OIDC_METADATA_CHANGE = "OIDC_METADATA_CHANGE"
    OIDC_KEY_ROTATION = "OIDC_KEY_ROTATION"
    API_ENDPOINT_CHANGE = "API_ENDPOINT_CHANGE"
    API_SCHEMA_COMPATIBLE_CHANGE = "API_SCHEMA_COMPATIBLE_CHANGE"
    API_SCHEMA_BREAKING_CHANGE = "API_SCHEMA_BREAKING_CHANGE"
    UI_SEMANTIC_RELOCATION = "UI_SEMANTIC_RELOCATION"
    AUTH_POLICY_CHANGE = "AUTH_POLICY_CHANGE"
    AUTHORIZATION_CHANGE = "AUTHORIZATION_CHANGE"
    SECURITY_BOUNDARY_CHANGE = "SECURITY_BOUNDARY_CHANGE"
    UNKNOWN = "UNKNOWN"


class RepairDisposition(str, Enum):
    NO_ACTION = "NO_ACTION"
    SANDBOX_VERIFY_CANDIDATE = "SANDBOX_VERIFY_CANDIDATE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    HOLD = "HOLD"


@dataclass(frozen=True)
class ExecutionScope:
    tenant_id: str
    company_id: str
    objective_id: str
    trusted_origins: FrozenSet[str]
    trusted_issuers: FrozenSet[str]
    allowed_scopes: FrozenSet[str]
    allowed_audiences: FrozenSet[str]
    allowed_redirect_origins: FrozenSet[str]

    def __post_init__(self) -> None:
        for value, name in (
            (self.tenant_id, "tenant_id"),
            (self.company_id, "company_id"),
            (self.objective_id, "objective_id"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")


@dataclass(frozen=True)
class OidcMetadataSnapshot:
    tenant_id: str
    company_id: str
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    scopes: FrozenSet[str]
    audiences: FrozenSet[str]
    redirect_uris: FrozenSet[str] = frozenset()
    mfa_required: bool = False
    consent_required: bool = False
    policy_fingerprint: str = ""


@dataclass(frozen=True)
class ApiOperationSnapshot:
    tenant_id: str
    company_id: str
    semantic_intent: str
    method: str
    url: str
    operation_id: str
    required_scopes: FrozenSet[str]
    request_required_fields: FrozenSet[str] = frozenset()
    response_required_fields: FrozenSet[str] = frozenset()
    schema_fingerprint: str = ""


@dataclass(frozen=True)
class UiTargetSnapshot:
    tenant_id: str
    company_id: str
    semantic_intent: str
    role: str
    label: str
    context_fingerprint: str
    stable_attributes: tuple[tuple[str, str], ...] = ()
    spatial_hint: str = ""


@dataclass(frozen=True)
class AdaptiveRepairProposal:
    drift_kind: DriftKind
    disposition: RepairDisposition
    reasons: tuple[str, ...]
    verification_requirements: tuple[str, ...]
    proposed_adapter: Mapping[str, str]
    grants_execution_authority: bool = False
    grants_auth_bypass: bool = False
    requires_outcome_verification: bool = True
    proposal_fingerprint: str = ""

    def __post_init__(self) -> None:
        if self.grants_execution_authority:
            raise ValueError("adaptive repair may never grant execution authority")
        if self.grants_auth_bypass:
            raise ValueError("adaptive repair may never grant an auth bypass")


class AdaptiveExecutionRepairPlanner:
    """Produces bounded repair proposals and fails closed on security drift."""

    _AUTH_FAILURES = frozenset({401, 403})

    def __init__(self, scope: ExecutionScope) -> None:
        self.scope = scope

    def assess_oidc_drift(
        self,
        previous: OidcMetadataSnapshot,
        current: OidcMetadataSnapshot,
        *,
        http_status: int | None = None,
    ) -> AdaptiveRepairProposal:
        self._require_scope(previous.tenant_id, previous.company_id)
        self._require_scope(current.tenant_id, current.company_id)

        if http_status in self._AUTH_FAILURES:
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                f"OIDC flow returned {http_status}; authentication/authorization failure is not repairable drift",
            )

        if previous.issuer != current.issuer:
            return self._hold(
                DriftKind.SECURITY_BOUNDARY_CHANGE,
                "OIDC issuer changed; automatic trust migration is forbidden",
            )
        if current.issuer not in self.scope.trusted_issuers:
            return self._hold(
                DriftKind.SECURITY_BOUNDARY_CHANGE,
                "OIDC issuer is outside the configured trust set",
            )

        endpoint_urls = {
            "authorization_endpoint": current.authorization_endpoint,
            "token_endpoint": current.token_endpoint,
            "jwks_uri": current.jwks_uri,
        }
        for name, url in endpoint_urls.items():
            invalid = self._url_security_error(url, self.scope.trusted_origins)
            if invalid:
                return self._hold(
                    DriftKind.SECURITY_BOUNDARY_CHANGE,
                    f"{name} {invalid}",
                )

        for redirect_uri in current.redirect_uris:
            invalid = self._url_security_error(
                redirect_uri, self.scope.allowed_redirect_origins
            )
            if invalid:
                return self._hold(
                    DriftKind.SECURITY_BOUNDARY_CHANGE,
                    f"redirect_uri {invalid}",
                )

        if not current.scopes.issubset(self.scope.allowed_scopes):
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                "OIDC metadata requests scopes outside the approved scope set",
            )
        if not current.audiences.issubset(self.scope.allowed_audiences):
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                "OIDC audience moved outside the approved audience set",
            )
        if current.scopes - previous.scopes:
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                "OIDC scope expansion requires explicit authorization review",
            )
        if current.audiences != previous.audiences:
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                "OIDC audience change requires explicit authorization review",
            )
        if current.mfa_required and not previous.mfa_required:
            return self._hold(
                DriftKind.AUTH_POLICY_CHANGE,
                "new MFA/step-up requirement must be satisfied normally, never bypassed",
            )
        if current.consent_required and not previous.consent_required:
            return self._hold(
                DriftKind.AUTH_POLICY_CHANGE,
                "new consent requirement must be satisfied normally, never bypassed",
            )
        if (
            previous.policy_fingerprint
            and current.policy_fingerprint != previous.policy_fingerprint
        ):
            return self._proposal(
                DriftKind.AUTH_POLICY_CHANGE,
                RepairDisposition.REVIEW_REQUIRED,
                ("authentication policy fingerprint changed",),
                (
                    "re-run OIDC discovery from the trusted issuer",
                    "re-run authenticated sandbox sign-in without bypassing policy challenges",
                    "require human review before adapter promotion",
                ),
                {},
            )

        changed = {
            name: url
            for name, url in endpoint_urls.items()
            if url != getattr(previous, name)
        }
        if not changed:
            return self._proposal(
                DriftKind.NONE,
                RepairDisposition.NO_ACTION,
                ("OIDC security-relevant metadata is unchanged",),
                (),
                {},
                requires_outcome_verification=False,
            )

        kind = (
            DriftKind.OIDC_KEY_ROTATION
            if set(changed) == {"jwks_uri"}
            else DriftKind.OIDC_METADATA_CHANGE
        )
        return self._proposal(
            kind,
            RepairDisposition.SANDBOX_VERIFY_CANDIDATE,
            ("trusted OIDC metadata changed without trust or privilege expansion",),
            (
                "re-run OIDC discovery from the exact trusted issuer",
                "verify TLS and trusted origin for every discovered endpoint",
                "resolve JWKS dynamically and verify token signature/issuer/audience",
                "run authenticated sandbox flow with the existing approved scopes",
                "verify the original business outcome before promotion",
            ),
            changed,
        )

    def assess_api_drift(
        self,
        previous: ApiOperationSnapshot,
        current: ApiOperationSnapshot,
        *,
        http_status: int | None = None,
    ) -> AdaptiveRepairProposal:
        self._require_scope(previous.tenant_id, previous.company_id)
        self._require_scope(current.tenant_id, current.company_id)

        if http_status in self._AUTH_FAILURES:
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                f"API returned {http_status}; Jarvis must not route around an auth/authz denial",
            )
        if previous.semantic_intent != current.semantic_intent:
            return self._hold(
                DriftKind.UNKNOWN,
                "semantic operation identity changed; automatic substitution is unsafe",
            )
        if previous.method.upper() != current.method.upper():
            return self._hold(
                DriftKind.API_SCHEMA_BREAKING_CHANGE,
                "HTTP method changed; side-effect semantics may have changed",
            )

        invalid = self._url_security_error(current.url, self.scope.trusted_origins)
        if invalid:
            return self._hold(
                DriftKind.SECURITY_BOUNDARY_CHANGE, f"API endpoint {invalid}"
            )

        if not current.required_scopes.issubset(self.scope.allowed_scopes):
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                "API operation requires scopes outside the approved scope set",
            )
        if current.required_scopes - previous.required_scopes:
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                "API operation requires additional privileges",
            )

        newly_required_inputs = (
            current.request_required_fields - previous.request_required_fields
        )
        missing_required_outputs = (
            previous.response_required_fields - current.response_required_fields
        )
        if newly_required_inputs or missing_required_outputs:
            reasons = []
            if newly_required_inputs:
                reasons.append(
                    "new required request fields: "
                    + ", ".join(sorted(newly_required_inputs))
                )
            if missing_required_outputs:
                reasons.append(
                    "previously required response fields disappeared: "
                    + ", ".join(sorted(missing_required_outputs))
                )
            return self._proposal(
                DriftKind.API_SCHEMA_BREAKING_CHANGE,
                RepairDisposition.HOLD,
                tuple(reasons),
                (
                    "obtain a reviewed contract mapping",
                    "run contract and outcome tests before a new adapter can be promoted",
                ),
                {},
            )

        endpoint_changed = (
            previous.url != current.url or previous.operation_id != current.operation_id
        )
        schema_changed = previous.schema_fingerprint != current.schema_fingerprint
        if not endpoint_changed and not schema_changed:
            return self._proposal(
                DriftKind.NONE,
                RepairDisposition.NO_ACTION,
                ("API operation contract is unchanged",),
                (),
                {},
                requires_outcome_verification=False,
            )

        drift_kind = (
            DriftKind.API_ENDPOINT_CHANGE
            if endpoint_changed
            else DriftKind.API_SCHEMA_COMPATIBLE_CHANGE
        )
        return self._proposal(
            drift_kind,
            RepairDisposition.SANDBOX_VERIFY_CANDIDATE,
            ("semantic API operation remains compatible within the approved privilege boundary",),
            (
                "run schema/contract compatibility tests",
                "run the operation in an authorized sandbox or read-only verification context",
                "verify expected response semantics and original business outcome",
                "promote only through the canonical Jarvis execution/approval authority",
            ),
            {
                "url": current.url,
                "operation_id": current.operation_id,
                "method": current.method.upper(),
            },
        )

    def assess_ui_drift(
        self,
        previous: UiTargetSnapshot,
        current: UiTargetSnapshot,
    ) -> AdaptiveRepairProposal:
        self._require_scope(previous.tenant_id, previous.company_id)
        self._require_scope(current.tenant_id, current.company_id)

        if previous.semantic_intent != current.semantic_intent:
            return self._hold(
                DriftKind.UNKNOWN,
                "UI target semantic intent changed; visual similarity is insufficient authority",
            )
        if previous.context_fingerprint != current.context_fingerprint:
            return self._proposal(
                DriftKind.UNKNOWN,
                RepairDisposition.REVIEW_REQUIRED,
                ("UI context changed around the target",),
                (
                    "re-ground the target using semantic role, label, ancestors and task context",
                    "require sandbox replay and outcome verification",
                ),
                {},
            )

        unchanged = (
            previous.role == current.role
            and previous.label == current.label
            and previous.stable_attributes == current.stable_attributes
            and previous.spatial_hint == current.spatial_hint
        )
        if unchanged:
            return self._proposal(
                DriftKind.NONE,
                RepairDisposition.NO_ACTION,
                ("semantic UI target is unchanged",),
                (),
                {},
                requires_outcome_verification=False,
            )

        return self._proposal(
            DriftKind.UI_SEMANTIC_RELOCATION,
            RepairDisposition.SANDBOX_VERIFY_CANDIDATE,
            ("UI target moved or was relabeled while semantic intent and context stayed stable",),
            (
                "re-ground using accessibility/DOM semantics before vision or spatial fallback",
                "avoid coordinate-only repair",
                "sandbox replay the step",
                "verify the expected state transition or business outcome",
            ),
            {
                "role": current.role,
                "label": current.label,
                "spatial_hint": current.spatial_hint,
            },
        )

    def _require_scope(self, tenant_id: str, company_id: str) -> None:
        if tenant_id != self.scope.tenant_id or company_id != self.scope.company_id:
            raise ValueError("cross-tenant/company adaptive repair is forbidden")

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.hostname:
            return ""
        port = parsed.port
        default_port = (parsed.scheme == "https" and port in (None, 443)) or (
            parsed.scheme == "http" and port in (None, 80)
        )
        suffix = "" if default_port or port is None else f":{port}"
        return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}{suffix}"

    def _url_security_error(
        self, url: str, allowed_origins: FrozenSet[str]
    ) -> str | None:
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https":
            return "must use HTTPS"
        if parsed.username or parsed.password:
            return "must not embed credentials"
        origin = self._origin(url)
        if not origin or origin not in allowed_origins:
            return f"origin {origin or '<invalid>'} is not trusted"
        return None

    def _hold(self, kind: DriftKind, reason: str) -> AdaptiveRepairProposal:
        return self._proposal(
            kind,
            RepairDisposition.HOLD,
            (reason,),
            ("stop automatic repair and require explicit security/owner review",),
            {},
        )

    def _proposal(
        self,
        kind: DriftKind,
        disposition: RepairDisposition,
        reasons: Iterable[str],
        verification_requirements: Iterable[str],
        proposed_adapter: Mapping[str, str],
        *,
        requires_outcome_verification: bool = True,
    ) -> AdaptiveRepairProposal:
        reasons_tuple = tuple(reasons)
        verification_tuple = tuple(verification_requirements)
        adapter = dict(sorted(proposed_adapter.items()))
        payload = {
            "tenant_id": self.scope.tenant_id,
            "company_id": self.scope.company_id,
            "objective_id": self.scope.objective_id,
            "drift_kind": kind.value,
            "disposition": disposition.value,
            "reasons": reasons_tuple,
            "verification_requirements": verification_tuple,
            "proposed_adapter": adapter,
            "grants_execution_authority": False,
            "grants_auth_bypass": False,
            "requires_outcome_verification": requires_outcome_verification,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return AdaptiveRepairProposal(
            drift_kind=kind,
            disposition=disposition,
            reasons=reasons_tuple,
            verification_requirements=verification_tuple,
            proposed_adapter=adapter,
            grants_execution_authority=False,
            grants_auth_bypass=False,
            requires_outcome_verification=requires_outcome_verification,
            proposal_fingerprint=fingerprint,
        )
