from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import time
from urllib.parse import quote

from fastapi import HTTPException, status


class AcademyMediaUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class AcademyMediaConfig:
    cdn_base_url: str
    playback_signing_key: str
    token_ttl_seconds: int

    @classmethod
    def from_env(cls) -> "AcademyMediaConfig":
        return cls(
            cdn_base_url=os.getenv("OPEX_ACADEMY_CDN_BASE_URL", "").strip().rstrip("/"),
            playback_signing_key=os.getenv("OPEX_ACADEMY_PLAYBACK_SIGNING_KEY", "").strip(),
            token_ttl_seconds=max(60, int(os.getenv("OPEX_ACADEMY_PLAYBACK_TOKEN_TTL_SECONDS", "300"))),
        )

    @property
    def configured(self) -> bool:
        return bool(self.cdn_base_url and self.playback_signing_key)


def _b64url(data: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode_b64url(value: str) -> bytes:
    import base64

    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def issue_playback_token(
    config: AcademyMediaConfig,
    *,
    tenant_id: str,
    subject: str,
    media_id: str,
    delivery_key: str,
    now: int | None = None,
) -> tuple[str, dict[str, object]]:
    if not config.configured:
        raise AcademyMediaUnavailable("Academy media delivery is not configured")
    issued_at = int(time.time() if now is None else now)
    payload = {
        "aud": "eay-academy-media",
        "tenant_id": tenant_id,
        "subject": subject,
        "media_id": media_id,
        "delivery_key": delivery_key,
        "iat": issued_at,
        "exp": issued_at + config.token_ttl_seconds,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    encoded_payload = _b64url(canonical)
    signature = hmac.new(
        config.playback_signing_key.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{encoded_payload}.{_b64url(signature)}", payload


def verify_playback_token(
    config: AcademyMediaConfig,
    token: str,
    *,
    expected_tenant_id: str,
    expected_subject: str,
    expected_media_id: str,
    now: int | None = None,
) -> dict[str, object]:
    if not config.configured:
        raise AcademyMediaUnavailable("Academy media delivery is not configured")
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Malformed Academy playback token") from exc
    expected_signature = hmac.new(
        config.playback_signing_key.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256
    ).digest()
    supplied_signature = _decode_b64url(encoded_signature)
    if not hmac.compare_digest(expected_signature, supplied_signature):
        raise ValueError("Invalid Academy playback signature")
    payload = json.loads(_decode_b64url(encoded_payload))
    if payload.get("aud") != "eay-academy-media":
        raise ValueError("Invalid Academy playback audience")
    if payload.get("tenant_id") != expected_tenant_id:
        raise ValueError("Academy playback tenant mismatch")
    if payload.get("subject") != expected_subject:
        raise ValueError("Academy playback subject mismatch")
    if payload.get("media_id") != expected_media_id:
        raise ValueError("Academy playback media mismatch")
    current = int(time.time() if now is None else now)
    if int(payload.get("exp", 0)) < current:
        raise ValueError("Academy playback token expired")
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
