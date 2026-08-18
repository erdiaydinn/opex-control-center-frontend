from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.resources import engine

from .repository import _set_tenant

ALLOWED_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/heic", "image/webp"})
MAX_EVIDENCE_BYTES = 26_214_400
DEFAULT_TRUSTED_STORAGE_HOSTS = frozenset({"field-evidence-store", "localhost"})


class FieldEvidenceUploadError(ValueError):
    pass


class FieldEvidenceStoreUnavailable(RuntimeError):
    pass


def _normalize_base_url(value: str, trusted_hosts: frozenset[str]) -> str:
    parsed = urlsplit(value.strip().rstrip("/"))
    hostname = (parsed.hostname or "").lower()
    allowed = {item.strip().lower() for item in trusted_hosts if item.strip()}
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or hostname not in allowed
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise FieldEvidenceStoreUnavailable("private Field evidence store configuration is invalid")
    return value.strip().rstrip("/")


def _read_token_file(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value)
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise FieldEvidenceStoreUnavailable(
            "private Field evidence store credential is unavailable"
        ) from exc
    if not token or len(token) > 8192 or any(character.isspace() for character in token):
        raise FieldEvidenceStoreUnavailable("private Field evidence store credential is invalid")
    return token


def storage_runtime_config() -> tuple[str, frozenset[str], str | None]:
    base_url = os.getenv("OPEX_FIELD_EVIDENCE_STORE_URL", "").strip()
    if not base_url:
        raise FieldEvidenceStoreUnavailable("private Field evidence store is not configured")
    extra_hosts = {
        value.strip().lower()
        for value in os.getenv("OPEX_FIELD_EVIDENCE_STORE_TRUSTED_HOSTS", "").split(",")
        if value.strip()
    }
    trusted_hosts = frozenset(set(DEFAULT_TRUSTED_STORAGE_HOSTS) | extra_hosts)
    normalized = _normalize_base_url(base_url, trusted_hosts)
    token = _read_token_file(os.getenv("OPEX_FIELD_EVIDENCE_STORE_TOKEN_FILE"))
    environment = os.getenv("OPEX_ENVIRONMENT", "development").strip().lower()
    if environment in {"staging", "production"} and token is None:
        raise FieldEvidenceStoreUnavailable(
            "staging/production private Field evidence store requires file-based credential"
        )
    return normalized, trusted_hosts, token


async def _authorize_upload(
    *,
    tenant_id: str,
    mission_id: str,
    location_id: str,
    field_key: str,
) -> None:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT 1
                FROM field_mission_targets target
                JOIN field_missions mission
                  ON mission.tenant_id=target.tenant_id AND mission.id=target.mission_id
                JOIN field_templates template
                  ON template.tenant_id=mission.tenant_id
                 AND template.template_id=mission.template_id
                 AND template.version=mission.template_version
                WHERE target.tenant_id=CAST(:tenant_id AS UUID)
                  AND target.mission_id=CAST(:mission_id AS UUID)
                  AND target.location_id=:location_id
                  AND mission.status='active'
                  AND target.status NOT IN ('verified','exempt')
                  AND EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(template.schema->'fields') field
                    WHERE field->>'key'=:field_key AND field->>'type'='photo'
                  )
                """
            ),
            {
                "tenant_id": tenant_id,
                "mission_id": mission_id,
                "location_id": location_id,
                "field_key": field_key,
            },
        )
        if result.first() is None:
            raise FieldEvidenceUploadError(
                "photo upload is not authorized for this active Field target"
            )


async def _existing_receipt(
    *,
    tenant_id: str,
    client_submission_id: str,
    field_key: str,
) -> dict[str, object] | None:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT receipt_id, sha256, media_type, byte_size, received_at
                FROM field_evidence_object_receipts
                WHERE tenant_id=CAST(:tenant_id AS UUID)
                  AND client_submission_id=CAST(:client_submission_id AS UUID)
                  AND field_key=:field_key
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "client_submission_id": client_submission_id,
                "field_key": field_key,
            },
        )
        row = result.mappings().first()
        if row is None:
            return None
        return {
            "receipt_id": str(row["receipt_id"]),
            "sha256": str(row["sha256"]),
            "media_type": str(row["media_type"]),
            "byte_size": int(row["byte_size"]),
            "received_at": row["received_at"],
        }


async def upload_private_evidence_object(
    *,
    tenant_id: str,
    actor_subject: str,
    mission_id: str,
    location_id: str,
    client_submission_id: str,
    field_key: str,
    media_type: str,
    expected_sha256: str,
    content: bytes,
    client: httpx.AsyncClient | None = None,
    base_url: str | None = None,
    trusted_hosts: frozenset[str] | None = None,
    token: str | None = None,
) -> dict[str, object]:
    try:
        UUID(client_submission_id)
        UUID(mission_id)
    except ValueError as exc:
        raise FieldEvidenceUploadError("invalid Field upload identity") from exc
    if not field_key or len(field_key) > 120:
        raise FieldEvidenceUploadError("invalid Field photo key")
    normalized_media_type = media_type.split(";", 1)[0].strip().lower()
    if normalized_media_type not in ALLOWED_MEDIA_TYPES:
        raise FieldEvidenceUploadError("unsupported Field evidence media type")
    if not content or len(content) > MAX_EVIDENCE_BYTES:
        raise FieldEvidenceUploadError("Field evidence object size is invalid")
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if expected_sha256 != actual_sha256:
        raise FieldEvidenceUploadError("Field evidence object hash mismatch")

    await _authorize_upload(
        tenant_id=tenant_id,
        mission_id=mission_id,
        location_id=location_id,
        field_key=field_key,
    )
    existing = await _existing_receipt(
        tenant_id=tenant_id,
        client_submission_id=client_submission_id,
        field_key=field_key,
    )
    if existing is not None:
        if (
            existing["sha256"] == actual_sha256
            and existing["media_type"] == normalized_media_type
            and existing["byte_size"] == len(content)
        ):
            return {**existing, "idempotent_replay": True}
        raise FieldEvidenceUploadError("Field photo identity was already used for different bytes")

    if base_url is None:
        configured_url, configured_hosts, configured_token = storage_runtime_config()
        base_url = configured_url
        trusted_hosts = configured_hosts
        token = configured_token
    else:
        trusted_hosts = trusted_hosts or DEFAULT_TRUSTED_STORAGE_HOSTS
        base_url = _normalize_base_url(base_url, trusted_hosts)

    receipt_id = uuid4()
    headers = {
        "Content-Type": normalized_media_type,
        "X-EAY-Field-Object-SHA256": actual_sha256,
        "X-EAY-Field-Object-Bytes": str(len(content)),
        "X-EAY-Field-Tenant": tenant_id,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=httpx.Timeout(20.0))
    try:
        response = await active_client.put(
            f"{base_url}/v1/private/field-evidence/{receipt_id}",
            headers=headers,
            content=content,
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        raise FieldEvidenceStoreUnavailable("private Field evidence store is unavailable") from exc
    finally:
        if owns_client:
            await active_client.aclose()
    if response.status_code not in {200, 201}:
        raise FieldEvidenceStoreUnavailable("private Field evidence store rejected the object")
    try:
        storage_body = response.json()
    except ValueError as exc:
        raise FieldEvidenceStoreUnavailable(
            "private Field evidence store returned invalid receipt"
        ) from exc
    storage_receipt = storage_body.get("receipt") if isinstance(storage_body, dict) else None
    if not isinstance(storage_receipt, str) or not storage_receipt or len(storage_receipt) > 1000:
        raise FieldEvidenceStoreUnavailable("private Field evidence store returned invalid receipt")
    storage_receipt_hash = hashlib.sha256(storage_receipt.encode("utf-8")).hexdigest()
    receipt_fingerprint = hashlib.sha256(
        (
            f"{tenant_id}|{receipt_id}|{client_submission_id}|{mission_id}|{location_id}|"
            f"{field_key}|{actual_sha256}|{normalized_media_type}|{len(content)}|"
            f"{storage_receipt_hash}"
        ).encode()
    ).hexdigest()

    try:
        async with engine.begin() as connection:
            await _set_tenant(connection, tenant_id)
            result = await connection.execute(
                text(
                    """
                    INSERT INTO field_evidence_object_receipts (
                        tenant_id, receipt_id, receipt_fingerprint, storage_provider,
                        sha256, media_type, byte_size, client_submission_id,
                        mission_id, location_id, field_key, actor_subject,
                        storage_receipt_hash, expires_at
                    ) VALUES (
                        CAST(:tenant_id AS UUID), CAST(:receipt_id AS UUID), :receipt_fingerprint,
                        'private_gateway', :sha256, :media_type, :byte_size,
                        CAST(:client_submission_id AS UUID), CAST(:mission_id AS UUID),
                        :location_id, :field_key, :actor_subject, :storage_receipt_hash,
                        CURRENT_TIMESTAMP + interval '24 hours'
                    )
                    RETURNING received_at
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "receipt_id": str(receipt_id),
                    "receipt_fingerprint": receipt_fingerprint,
                    "sha256": actual_sha256,
                    "media_type": normalized_media_type,
                    "byte_size": len(content),
                    "client_submission_id": client_submission_id,
                    "mission_id": mission_id,
                    "location_id": location_id,
                    "field_key": field_key,
                    "actor_subject": actor_subject,
                    "storage_receipt_hash": storage_receipt_hash,
                },
            )
            received_at = result.scalar_one()
    except IntegrityError as exc:
        raise FieldEvidenceUploadError("Field evidence receipt collision") from exc

    return {
        "receipt_id": str(receipt_id),
        "sha256": actual_sha256,
        "media_type": normalized_media_type,
        "byte_size": len(content),
        "received_at": received_at,
        "idempotent_replay": False,
    }
