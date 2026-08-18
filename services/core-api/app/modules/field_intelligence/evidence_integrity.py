from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .schemas import EvidenceObjectClaim


class FieldEvidenceIntegrityError(ValueError):
    pass


def _canonical_fingerprint(payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_photo_receipt_binding(
    *,
    template_schema: dict[str, object],
    payload: dict[str, object],
    claims: tuple[EvidenceObjectClaim, ...],
) -> tuple[EvidenceObjectClaim, ...]:
    """Bind photo fields to opaque server-issued receipt UUIDs only."""
    fields = template_schema.get("fields") or []
    photo_keys = {
        str(field.get("key"))
        for field in fields
        if isinstance(field, dict) and field.get("type") == "photo"
    }
    by_field = {claim.field_key: claim for claim in claims}

    unknown = set(by_field) - photo_keys
    if unknown:
        raise FieldEvidenceIntegrityError(
            f"evidence object claim targets non-photo fields: {', '.join(sorted(unknown))}"
        )

    populated_photo_keys = {
        key for key in photo_keys if key in payload and payload[key] not in (None, "", [])
    }
    if populated_photo_keys != set(by_field):
        missing = sorted(populated_photo_keys - set(by_field))
        extra = sorted(set(by_field) - populated_photo_keys)
        detail = []
        if missing:
            detail.append(f"missing receipt claims for {', '.join(missing)}")
        if extra:
            detail.append(f"unexpected receipt claims for {', '.join(extra)}")
        raise FieldEvidenceIntegrityError("; ".join(detail) or "photo receipt binding mismatch")

    for field_key in sorted(populated_photo_keys):
        claim = by_field[field_key]
        if str(payload[field_key]) != str(claim.receipt_id):
            raise FieldEvidenceIntegrityError(
                f"photo field {field_key} must reference its server receipt UUID"
            )

    return tuple(sorted(claims, key=lambda item: item.field_key))


async def _device_authority_fingerprint(
    connection: AsyncConnection,
    *,
    tenant_id: str,
    device_id: str,
    trusted_device_ids: frozenset[str],
) -> str | None:
    if device_id in trusted_device_ids:
        return _canonical_fingerprint(
            {"authority": "injected_canonical_device_adapter", "device_id": device_id}
        )

    result = await connection.execute(
        text(
            """
            SELECT attestation_fingerprint
            FROM field_device_attestations
            WHERE tenant_id=CAST(:tenant_id AS UUID)
              AND device_id=:device_id
              AND verdict='trusted'
              AND (expires_at IS NULL OR expires_at >= CURRENT_TIMESTAMP)
            ORDER BY observed_at DESC, created_at DESC
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "device_id": device_id},
    )
    row = result.mappings().first()
    return str(row["attestation_fingerprint"]) if row is not None else None


async def verify_evidence_authority(
    connection: AsyncConnection,
    *,
    tenant_id: str,
    client_submission_id: str,
    device_id: str,
    captured_at: datetime,
    template_schema: dict[str, object],
    payload: dict[str, object],
    claims: tuple[EvidenceObjectClaim, ...],
    managed_device_required: bool,
    camera_only_photo: bool,
    trusted_device_ids: Iterable[str] = (),
    camera_attested_submission_ids: Iterable[str] = (),
) -> str:
    bound_claims = validate_photo_receipt_binding(
        template_schema=template_schema,
        payload=payload,
        claims=claims,
    )
    trusted_devices = frozenset(trusted_device_ids)
    camera_attested = frozenset(camera_attested_submission_ids)

    authority: dict[str, object] = {
        "device": None,
        "objects": [],
        "camera": [],
    }

    if managed_device_required:
        device_fingerprint = await _device_authority_fingerprint(
            connection,
            tenant_id=tenant_id,
            device_id=device_id,
            trusted_device_ids=trusted_devices,
        )
        if device_fingerprint is None:
            raise FieldEvidenceIntegrityError(
                "managed-device policy requires authoritative device attestation"
            )
        authority["device"] = device_fingerprint

    for claim in bound_claims:
        receipt_result = await connection.execute(
            text(
                """
                SELECT receipt_fingerprint, sha256, media_type, byte_size
                FROM field_evidence_object_receipts
                WHERE tenant_id=CAST(:tenant_id AS UUID)
                  AND receipt_id=CAST(:receipt_id AS UUID)
                  AND client_submission_id=CAST(:client_submission_id AS UUID)
                  AND field_key=:field_key
                  AND (expires_at IS NULL OR expires_at >= CURRENT_TIMESTAMP)
                """
            ),
            {
                "tenant_id": tenant_id,
                "receipt_id": str(claim.receipt_id),
                "client_submission_id": client_submission_id,
                "field_key": claim.field_key,
            },
        )
        receipt = receipt_result.mappings().first()
        if receipt is None:
            raise FieldEvidenceIntegrityError(
                f"server evidence object receipt missing, expired or misbound for {claim.field_key}"
            )
        if str(receipt["sha256"]) != claim.sha256:
            raise FieldEvidenceIntegrityError(
                f"evidence object hash mismatch for {claim.field_key}"
            )
        if str(receipt["media_type"]) != claim.media_type:
            raise FieldEvidenceIntegrityError(
                f"evidence object media type mismatch for {claim.field_key}"
            )
        if int(receipt["byte_size"]) != claim.byte_size:
            raise FieldEvidenceIntegrityError(
                f"evidence object byte size mismatch for {claim.field_key}"
            )

        cast_objects = authority["objects"]
        assert isinstance(cast_objects, list)
        cast_objects.append(
            {
                "field_key": claim.field_key,
                "receipt_id": str(claim.receipt_id),
                "receipt_fingerprint": str(receipt["receipt_fingerprint"]),
            }
        )

        if camera_only_photo:
            if claim.capture_session_id is None:
                raise FieldEvidenceIntegrityError(
                    f"camera-only policy requires capture session for {claim.field_key}"
                )

            if client_submission_id in camera_attested:
                capture_fingerprint = _canonical_fingerprint(
                    {
                        "authority": "injected_canonical_camera_adapter",
                        "submission_id": client_submission_id,
                        "receipt_id": str(claim.receipt_id),
                    }
                )
            else:
                attestation_result = await connection.execute(
                    text(
                        """
                        SELECT attestation_fingerprint
                        FROM field_capture_attestations
                        WHERE tenant_id=CAST(:tenant_id AS UUID)
                          AND receipt_id=CAST(:receipt_id AS UUID)
                          AND capture_session_id=CAST(:capture_session_id AS UUID)
                          AND device_id=:device_id
                          AND verdict='trusted'
                          AND (expires_at IS NULL OR expires_at >= CURRENT_TIMESTAMP)
                        ORDER BY observed_at DESC, created_at DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "receipt_id": str(claim.receipt_id),
                        "capture_session_id": str(claim.capture_session_id),
                        "device_id": device_id,
                    },
                )
                attestation = attestation_result.mappings().first()
                if attestation is None:
                    raise FieldEvidenceIntegrityError(
                        "camera-only policy requires authoritative capture attestation for"
                        f" {claim.field_key}"
                    )
                capture_fingerprint = str(attestation["attestation_fingerprint"])

            cast_camera = authority["camera"]
            assert isinstance(cast_camera, list)
            cast_camera.append(
                {
                    "field_key": claim.field_key,
                    "capture_session_id": str(claim.capture_session_id),
                    "attestation_fingerprint": capture_fingerprint,
                }
            )

    if camera_only_photo and not bound_claims:
        if client_submission_id not in camera_attested:
            raise FieldEvidenceIntegrityError(
                "camera-only policy requires authoritative capture attestation"
            )
        authority["camera"] = [
            {
                "submission_id": client_submission_id,
                "attestation_fingerprint": _canonical_fingerprint(
                    {
                        "authority": "injected_canonical_camera_adapter",
                        "submission_id": client_submission_id,
                    }
                ),
            }
        ]

    return _canonical_fingerprint(
        {
            "tenant_id": tenant_id,
            "client_submission_id": client_submission_id,
            "device_id": device_id,
            "captured_at": captured_at.isoformat(),
            "authority": authority,
        }
    )
