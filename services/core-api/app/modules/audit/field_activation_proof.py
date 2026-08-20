from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import UTC, datetime
from ipaddress import ip_address
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

AuditFieldCapability = Literal["photo_vision", "video_vision"]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RELEASE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_TRUSTED_FIELD_AUTHORITY_HOSTS = frozenset({"eay-audit-field-authority", "localhost"})


class AuditFieldActivationProof(BaseModel):
    """Opaque current-production field acceptance proof issued outside Audit runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(min_length=1, max_length=180)
    release_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    capability: AuditFieldCapability
    deployment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    field_uat_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    device_attestation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    private_storage_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    privacy_scanner_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    video_decoder_fingerprint: str | None = None

    def model_post_init(self, __context: object) -> None:
        del __context
        if self.video_decoder_fingerprint is not None and not _SHA256_RE.fullmatch(
            self.video_decoder_fingerprint
        ):
            raise ValueError("video_decoder_fingerprint must be lowercase SHA-256")
        if self.capability == "video_vision" and self.video_decoder_fingerprint is None:
            raise ValueError("video_vision activation requires video decoder acceptance")


class AuditFieldActivationProofUnavailable(RuntimeError):
    pass


class AuditFieldActivationProofVerifier(Protocol):
    async def require_current_activation(
        self,
        *,
        tenant_id: str,
        release_sha: str,
        capability: AuditFieldCapability,
    ) -> AuditFieldActivationProof: ...


class UnavailableAuditFieldActivationProofVerifier:
    async def require_current_activation(
        self,
        *,
        tenant_id: str,
        release_sha: str,
        capability: AuditFieldCapability,
    ) -> AuditFieldActivationProof:
        del tenant_id, release_sha, capability
        raise AuditFieldActivationProofUnavailable(
            "current production Audit field activation proof is unavailable"
        )


def _normalize_authority_url(
    value: str,
    *,
    trusted_hosts: frozenset[str] = DEFAULT_TRUSTED_FIELD_AUTHORITY_HOSTS,
) -> str:
    parsed = urlsplit(value.strip().rstrip("/"))
    hostname = (parsed.hostname or "").lower()
    try:
        loopback = ip_address(hostname).is_loopback
    except ValueError:
        loopback = False
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (hostname not in trusted_hosts and not loopback)
    ):
        raise ValueError("Audit field authority URL is invalid")
    return value.strip().rstrip("/")


def _read_token_file(path_value: str | None) -> str:
    if not path_value:
        raise AuditFieldActivationProofUnavailable(
            "Audit field authority credential file is not configured"
        )
    try:
        token = Path(path_value).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise AuditFieldActivationProofUnavailable(
            "Audit field authority credential is unavailable"
        ) from exc
    if len(token) < 32 or len(token) > 8192 or any(character.isspace() for character in token):
        raise AuditFieldActivationProofUnavailable("Audit field authority credential is invalid")
    return token


def _sealed_payload(body: dict[str, object]) -> bytes:
    payload = {key: value for key, value in body.items() if key != "seal"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class EAYAuditFieldActivationProofVerifier:
    """Challenge-bound adapter to an external field/UAT release authority."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        client: httpx.AsyncClient | None = None,
        trusted_hosts: frozenset[str] = DEFAULT_TRUSTED_FIELD_AUTHORITY_HOSTS,
    ) -> None:
        if len(token) < 32 or token != token.strip() or any(c.isspace() for c in token):
            raise ValueError("Audit field authority token is invalid")
        self.base_url = _normalize_authority_url(base_url, trusted_hosts=trusted_hosts)
        self.token = token
        self.client = client

    async def require_current_activation(
        self,
        *,
        tenant_id: str,
        release_sha: str,
        capability: AuditFieldCapability,
    ) -> AuditFieldActivationProof:
        if not tenant_id or len(tenant_id) > 180 or not _RELEASE_SHA_RE.fullmatch(release_sha):
            raise AuditFieldActivationProofUnavailable(
                "current production Audit field activation proof is unavailable"
            )
        challenge = secrets.token_hex(32)
        url = (
            self.base_url
            + "/v1/internal/audit-field-activation-proofs/"
            + quote(tenant_id, safe="")
            + "/"
            + quote(capability, safe="")
            + "/"
            + release_sha
        )
        owns_client = self.client is None
        active_client = self.client or httpx.AsyncClient(timeout=httpx.Timeout(5.0))
        try:
            response = await active_client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "X-EAY-Audit-Field-Challenge": challenge,
                },
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            raise AuditFieldActivationProofUnavailable(
                "current production Audit field activation proof is unavailable"
            ) from exc
        finally:
            if owns_client:
                await active_client.aclose()
        if response.status_code != 200:
            raise AuditFieldActivationProofUnavailable(
                "current production Audit field activation proof is unavailable"
            )
        try:
            body = response.json()
            expected_fields = {
                *AuditFieldActivationProof.model_fields,
                "challenge",
                "issued_at",
                "expires_at",
                "seal",
            }
            if not isinstance(body, dict) or set(body) != expected_fields:
                raise ValueError("field activation proof response shape mismatch")
            issued_at = datetime.fromisoformat(str(body["issued_at"]))
            expires_at = datetime.fromisoformat(str(body["expires_at"]))
            now = datetime.now(UTC)
            expected_seal = hmac.new(
                self.token.encode("utf-8"),
                _sealed_payload(body),
                hashlib.sha256,
            ).hexdigest()
            if (
                body["tenant_id"] != tenant_id
                or body["release_sha"] != release_sha
                or body["capability"] != capability
                or body["challenge"] != challenge
                or issued_at.tzinfo is None
                or expires_at.tzinfo is None
                or issued_at > now
                or expires_at <= now
                or (expires_at - issued_at).total_seconds() > 30
                or not hmac.compare_digest(str(body["seal"]), expected_seal)
            ):
                raise ValueError("field activation proof binding mismatch")
            proof_fields = {
                key: body[key] for key in AuditFieldActivationProof.model_fields
            }
            return AuditFieldActivationProof(**proof_fields)
        except (TypeError, ValueError) as exc:
            raise AuditFieldActivationProofUnavailable(
                "current production Audit field activation proof is unavailable"
            ) from exc


def configured_field_activation_proof_verifier() -> AuditFieldActivationProofVerifier:
    base_url = os.getenv("EAY_AUDIT_FIELD_AUTHORITY_URL", "").strip()
    token_file = os.getenv("EAY_AUDIT_FIELD_AUTHORITY_TOKEN_FILE", "").strip()
    if not base_url or not token_file:
        return UnavailableAuditFieldActivationProofVerifier()
    try:
        token = _read_token_file(token_file)
        return EAYAuditFieldActivationProofVerifier(base_url=base_url, token=token)
    except (AuditFieldActivationProofUnavailable, ValueError):
        return UnavailableAuditFieldActivationProofVerifier()


async def require_field_activation_for_production(
    *,
    tenant_id: str,
    capability: AuditFieldCapability,
    verifier: AuditFieldActivationProofVerifier | None = None,
) -> AuditFieldActivationProof | None:
    """Require external field/UAT authority only when this process is production."""

    environment = os.getenv("OPEX_ENVIRONMENT", "development").strip().lower()
    if environment != "production":
        return None
    release_sha = os.getenv("EAY_RELEASE_SHA", "").strip().lower()
    if not _RELEASE_SHA_RE.fullmatch(release_sha):
        raise AuditFieldActivationProofUnavailable("production release SHA is unavailable")
    active_verifier = verifier or configured_field_activation_proof_verifier()
    proof = await active_verifier.require_current_activation(
        tenant_id=tenant_id,
        release_sha=release_sha,
        capability=capability,
    )
    if (
        proof.tenant_id != tenant_id
        or proof.release_sha != release_sha
        or proof.capability != capability
    ):
        raise AuditFieldActivationProofUnavailable(
            "production Audit field activation proof identity mismatch"
        )
    return proof
