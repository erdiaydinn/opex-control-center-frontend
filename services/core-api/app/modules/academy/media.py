import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from fastapi import HTTPException, status

from app.core.security import Principal


class AcademyMediaUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class AcademyMediaConfig:
    cdn_base_url: str
    signing_secret: bytes
    token_ttl_seconds: int


def load_media_config() -> AcademyMediaConfig:
    base_url = os.getenv("OPEX_ACADEMY_MEDIA_CDN_BASE_URL", "").strip().rstrip("/")
    secret_file = os.getenv("OPEX_ACADEMY_MEDIA_SIGNING_SECRET_FILE", "").strip()
    try:
        ttl = int(os.getenv("OPEX_ACADEMY_MEDIA_TOKEN_TTL_SECONDS", "120"))
    except ValueError as exc:
        raise AcademyMediaUnavailable("Academy media token TTL is invalid") from exc

    if not base_url.startswith("https://"):
        raise AcademyMediaUnavailable("Academy media CDN base URL must use HTTPS")
    if not 30 <= ttl <= 300:
        raise AcademyMediaUnavailable("Academy media token TTL must be between 30 and 300 seconds")
    if not secret_file:
        raise AcademyMediaUnavailable("Academy media signing secret file is not configured")

    try:
        secret = Path(secret_file).read_bytes().strip()
    except OSError as exc:
        raise AcademyMediaUnavailable("Academy media signing secret cannot be read") from exc
    if len(secret) < 32:
        raise AcademyMediaUnavailable("Academy media signing secret must contain at least 32 bytes")

    return AcademyMediaConfig(base_url, secret, ttl)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode_b64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def issue_playback_token(
    config: AcademyMediaConfig,
    principal: Principal,
    *,
    media_id: UUID,
    content_version_id: UUID,
    delivery_key: str,
    now: int | None = None,
) -> tuple[str, int]:
    issued_at = int(time.time() if now is None else now)
    expires_at = issued_at + config.token_ttl_seconds
    payload = {
        "v": 1,
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "media_id": str(media_id),
        "content_version_id": str(content_version_id),
        "delivery_key_sha256": hashlib.sha256(delivery_key.encode("utf-8")).hexdigest(),
        "iat": issued_at,
        "exp": expires_at,
        "nonce": secrets.token_urlsafe(12),
    }
    encoded = _b64url(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = _b64url(
        hmac.new(config.signing_secret, encoded.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{encoded}.{signature}", expires_at


def verify_playback_token(
    config: AcademyMediaConfig,
    token: str,
    *,
    tenant_id: UUID,
    subject: str,
    media_id: UUID,
    content_version_id: UUID,
    delivery_key: str,
    now: int | None = None,
) -> dict[str, object]:
    try:
        encoded, signature = token.split(".", 1)
        expected = _b64url(
            hmac.new(config.signing_secret, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature mismatch")
        payload = json.loads(_decode_b64url(encoded))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid playback token") from exc

    current = int(time.time() if now is None else now)
    expected_delivery_hash = hashlib.sha256(delivery_key.encode("utf-8")).hexdigest()
    checks = {
        "v": 1,
        "tenant_id": str(tenant_id),
        "subject": subject,
        "media_id": str(media_id),
        "content_version_id": str(content_version_id),
        "delivery_key_sha256": expected_delivery_hash,
    }
    if any(payload.get(key) != value for key, value in checks.items()):
        raise ValueError("Playback token scope mismatch")
    if not isinstance(payload.get("exp"), int) or current >= payload["exp"]:
        raise ValueError("Playback token expired")
    if not isinstance(payload.get("iat"), int) or payload["iat"] > current + 30:
        raise ValueError("Playback token issued-at is invalid")
    return payload


def build_playback_url(
    config: AcademyMediaConfig,
    *,
    delivery_key: str,
    manifest_path: str | None,
    token: str,
    delivery_mode: str,
) -> str:
    if delivery_mode == "hls":
        manifest = manifest_path or "master.m3u8"
    elif delivery_mode == "dash":
        manifest = manifest_path or "manifest.mpd"
    else:
        manifest = manifest_path or "document"
    safe_delivery_key = "/".join(quote(part, safe="") for part in delivery_key.split("/") if part)
    safe_manifest = "/".join(quote(part, safe="") for part in manifest.split("/") if part)
    encoded_token = quote(token, safe="")
    return f"{config.cdn_base_url}/{safe_delivery_key}/{safe_manifest}?eay_token={encoded_token}"


def media_unavailable_http(exc: AcademyMediaUnavailable) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Academy media delivery is not configured for this environment",
    )
