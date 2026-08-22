"""Fail-closed workflow-drift repair planning for Jarvis Adaptive Execution."""

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
        if not all((self.tenant_id.strip(), self.company_id.strip(), self.objective_id.strip())):
            raise ValueError("tenant_id, company_id and objective_id must be non-empty")


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
        if self.grants_execution_authority or self.grants_auth_bypass:
            raise ValueError("adaptive repair cannot grant execution authority or auth bypass")


class AdaptiveExecutionRepairPlanner:
    """Classify drift and emit repair proposals without granting action authority."""

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
        self._scope(previous.tenant_id, previous.company_id)
        self._scope(current.tenant_id, current.company_id)
        if http_status in self._AUTH_FAILURES:
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                f"OIDC returned {http_status}; auth denial is not repairable drift",
            )
        if previous.issuer != current.issuer or current.issuer not in self.scope.trusted_issuers:
            return self._hold(
                DriftKind.SECURITY_BOUNDARY_CHANGE,
                "OIDC issuer/trust boundary changed",
            )

        endpoints = {
            "authorization_endpoint": current.authorization_endpoint,
            "token_endpoint": current.token_endpoint,
            "jwks_uri": current.jwks_uri,
        }
        for name, url in endpoints.items():
            if error := self._url_error(url, self.scope.trusted_origins):
                return self._hold(DriftKind.SECURITY_BOUNDARY_CHANGE, f"{name} {error}")
        for url in current.redirect_uris:
            if error := self._url_error(url, self.scope.allowed_redirect_origins):
                return self._hold(
                    DriftKind.SECURITY_BOUNDARY_CHANGE,
                    f"redirect_uri {error}",
                )

        if not current.scopes.issubset(self.scope.allowed_scopes):
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                "OIDC scope is outside approved scope set",
            )
        if not current.audiences.issubset(self.scope.allowed_audiences):
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                "OIDC audience is outside approved audience set",
            )
        if current.scopes - previous.scopes:
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                "OIDC scope expansion requires authorization review",
            )
        if current.scopes != previous.scopes:
            return self._review(DriftKind.AUTHORIZATION_CHANGE, "OIDC scope set changed")
        if current.audiences != previous.audiences:
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                "OIDC audience change requires authorization review",
            )
        if current.mfa_required and not previous.mfa_required:
            return self._hold(
                DriftKind.AUTH_POLICY_CHANGE,
                "new MFA/step-up must be satisfied normally",
            )
        if current.consent_required and not previous.consent_required:
            return self._hold(
                DriftKind.AUTH_POLICY_CHANGE,
                "new consent requirement must be satisfied normally",
            )
        if previous.policy_fingerprint and current.policy_fingerprint != previous.policy_fingerprint:
            return self._review(
                DriftKind.AUTH_POLICY_CHANGE,
                "authentication policy fingerprint changed",
            )

        changed = {
            name: url for name, url in endpoints.items() if url != getattr(previous, name)
        }
        if not changed:
            return self._proposal(
                DriftKind.NONE,
                RepairDisposition.NO_ACTION,
                ("OIDC metadata unchanged",),
                (),
                {},
                outcome=False,
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
                "verify HTTPS and trusted origin for discovered endpoints",
                "resolve JWKS dynamically and verify signature, issuer and audience",
                "run the existing approved auth flow in an authorized sandbox",
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
        self._scope(previous.tenant_id, previous.company_id)
        self._scope(current.tenant_id, current.company_id)
        if http_status in self._AUTH_FAILURES:
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                f"API returned {http_status}; auth denial cannot be routed around",
            )
        if previous.semantic_intent != current.semantic_intent:
            return self._hold(DriftKind.UNKNOWN, "semantic operation identity changed")
        if previous.method.upper() != current.method.upper():
            return self._hold(
                DriftKind.API_SCHEMA_BREAKING_CHANGE,
                "HTTP method changed; side-effect semantics may differ",
            )
        if error := self._url_error(current.url, self.scope.trusted_origins):
            return self._hold(
                DriftKind.SECURITY_BOUNDARY_CHANGE,
                f"API endpoint {error}",
            )
        if not current.required_scopes.issubset(self.scope.allowed_scopes):
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                "API scope is outside approved scope set",
            )
        if current.required_scopes - previous.required_scopes:
            return self._hold(
                DriftKind.AUTHORIZATION_CHANGE,
                "API requires additional privileges",
            )

        new_inputs = current.request_required_fields - previous.request_required_fields
        lost_outputs = previous.response_required_fields - current.response_required_fields
        if new_inputs or lost_outputs:
            reasons = tuple(
                filter(
                    None,
                    (
                        "new required request fields: " + ", ".join(sorted(new_inputs))
                        if new_inputs
                        else "",
                        "required response fields disappeared: "
                        + ", ".join(sorted(lost_outputs))
                        if lost_outputs
                        else "",
                    ),
                )
            )
            return self._proposal(
                DriftKind.API_SCHEMA_BREAKING_CHANGE,
                RepairDisposition.HOLD,
                reasons,
                (
                    "obtain a reviewed contract mapping",
                    "run contract and outcome tests before promotion",
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
                ("API contract unchanged",),
                (),
                {},
                outcome=False,
            )
        return self._proposal(
            DriftKind.API_ENDPOINT_CHANGE
            if endpoint_changed
            else DriftKind.API_SCHEMA_COMPATIBLE_CHANGE,
            RepairDisposition.SANDBOX_VERIFY_CANDIDATE,
            ("semantic API operation remains compatible inside the approved privilege boundary",),
            (
                "run schema/contract compatibility tests",
                "run in an authorized sandbox or read-only verification context",
                "verify expected response semantics and original business outcome",
                "promote only through canonical Jarvis execution/approval authority",
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
        self._scope(previous.tenant_id, previous.company_id)
        self._scope(current.tenant_id, current.company_id)
        if previous.semantic_intent != current.semantic_intent:
            return self._hold(
                DriftKind.UNKNOWN,
                "UI semantic intent changed; visual similarity is insufficient",
            )
        if previous.context_fingerprint != current.context_fingerprint:
            return self._review(DriftKind.UNKNOWN, "UI context changed around target")
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
                ("UI target unchanged",),
                (),
                {},
                outcome=False,
            )
        return self._proposal(
            DriftKind.UI_SEMANTIC_RELOCATION,
            RepairDisposition.SANDBOX_VERIFY_CANDIDATE,
            ("UI moved/relabelled while semantic intent and context stayed stable",),
            (
                "re-ground with accessibility/DOM semantics before vision/spatial fallback",
                "avoid coordinate-only repair",
                "sandbox replay the step",
                "verify expected state transition or business outcome",
            ),
            {
                "role": current.role,
                "label": current.label,
                "spatial_hint": current.spatial_hint,
            },
        )

    def _scope(self, tenant_id: str, company_id: str) -> None:
        if tenant_id != self.scope.tenant_id or company_id != self.scope.company_id:
            raise ValueError("cross-tenant/company adaptive repair is forbidden")

    @staticmethod
    def _origin(url: str) -> str:
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError:
            return ""
        if not parsed.scheme or not parsed.hostname:
            return ""
        default = (parsed.scheme == "https" and port in (None, 443)) or (
            parsed.scheme == "http" and port in (None, 80)
        )
        suffix = "" if default or port is None else f":{port}"
        return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}{suffix}"

    def _url_error(self, url: str, allowed: FrozenSet[str]) -> str | None:
        try:
            parsed = urlsplit(url)
        except ValueError:
            return "is malformed"
        if parsed.scheme.lower() != "https":
            return "must use HTTPS"
        if parsed.username or parsed.password:
            return "must not embed credentials"
        origin = self._origin(url)
        if not origin or origin not in allowed:
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

    def _review(self, kind: DriftKind, reason: str) -> AdaptiveRepairProposal:
        return self._proposal(
            kind,
            RepairDisposition.REVIEW_REQUIRED,
            (reason,),
            (
                "re-discover/re-ground in an authorized sandbox",
                "verify the original outcome",
                "require owner review before promotion",
            ),
            {},
        )

    def _proposal(
        self,
        kind: DriftKind,
        disposition: RepairDisposition,
        reasons: Iterable[str],
        verification: Iterable[str],
        adapter: Mapping[str, str],
        *,
        outcome: bool = True,
    ) -> AdaptiveRepairProposal:
        reasons_t = tuple(reasons)
        verification_t = tuple(verification)
        adapter_d = dict(sorted(adapter.items()))
        payload = {
            "tenant_id": self.scope.tenant_id,
            "company_id": self.scope.company_id,
            "objective_id": self.scope.objective_id,
            "drift_kind": kind.value,
            "disposition": disposition.value,
            "reasons": reasons_t,
            "verification": verification_t,
            "adapter": adapter_d,
            "execution_authority": False,
            "auth_bypass": False,
            "outcome": outcome,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return AdaptiveRepairProposal(
            drift_kind=kind,
            disposition=disposition,
            reasons=reasons_t,
            verification_requirements=verification_t,
            proposed_adapter=adapter_d,
            grants_execution_authority=False,
            grants_auth_bypass=False,
            requires_outcome_verification=outcome,
            proposal_fingerprint=fingerprint,
        )
