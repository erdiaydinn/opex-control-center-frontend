from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.core.resources import close_resources, engine
from app.modules.field_intelligence.evidence_integrity import (
    FieldEvidenceIntegrityError,
    verify_evidence_authority,
)
from app.modules.field_intelligence.evidence_object_upload import (
    FieldEvidenceStoreUnavailable,
    storage_runtime_config,
    upload_private_evidence_object,
)
from app.modules.field_intelligence.repository import _set_tenant
from app.modules.field_intelligence.schemas import EvidenceObjectClaim


@pytest.mark.asyncio
async def test_private_photo_receipt_is_bound_to_exact_submission_and_field() -> None:
    database_url = os.getenv("OPEX_MIGRATION_DATABASE_URL")
    if not database_url or "postgresql" not in database_url:
        pytest.skip("PostgreSQL migration identity is required")

    import asyncpg

    dsn = database_url.replace("postgresql+asyncpg://", "postgresql://")
    tenant_id = uuid4()
    mission_id = uuid4()
    submission_id = uuid4()
    location_id = f"store-{uuid4().hex[:8]}"
    photo_bytes = b"synthetic-private-photo-bytes"
    sha256 = hashlib.sha256(photo_bytes).hexdigest()
    template_schema = {
        "fields": [
            {
                "key": "photo",
                "type": "photo",
                "label": {"values": {"en": "Photo"}},
                "required": True,
                "options": [],
                "config": {},
            }
        ]
    }

    connection = await asyncpg.connect(dsn)
    try:
        await connection.execute(
            "INSERT INTO tenants (id, slug, display_name) VALUES ($1, $2, $3)",
            tenant_id,
            f"upload-{tenant_id.hex[:8]}",
            "Upload Test",
        )
        await connection.execute(
            """
            INSERT INTO field_locations (tenant_id, location_id, name, active)
            VALUES ($1, $2, 'Photo Store', TRUE)
            """,
            tenant_id,
            location_id,
        )
        await connection.execute(
            """
            INSERT INTO field_templates (
                tenant_id, template_id, version, name_i18n, schema, status, created_by
            ) VALUES ($1, 'photo-check', 1, '{"en":"Photo check"}'::jsonb, $2::jsonb, 'active',
            'author')
            """,
            tenant_id,
            __import__("json").dumps(template_schema),
        )
        await connection.execute(
            """
            INSERT INTO field_missions (
                tenant_id, id, template_id, template_version, title_i18n, instructions_i18n,
                priority, status, assigned_at, deadline_at, selector,
                target_fingerprint, target_count, created_by
            ) VALUES (
                $1, $2, 'photo-check', 1, '{"en":"Photo check"}'::jsonb, '{}'::jsonb,
                'normal', 'active', CURRENT_TIMESTAMP - interval '1 hour',
                CURRENT_TIMESTAMP + interval '1 hour', '{"all_active_locations":true}'::jsonb,
                repeat('c',64), 1, 'mission-author'
            )
            """,
            tenant_id,
            mission_id,
        )
        await connection.execute(
            """
            INSERT INTO field_mission_targets (
                tenant_id, mission_id, location_id, status
            ) VALUES ($1, $2, $3, 'unseen')
            """,
            tenant_id,
            mission_id,
            location_id,
        )
    finally:
        await connection.close()

    observed: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["headers"] = dict(request.headers)
        observed["body"] = request.content
        return httpx.Response(201, json={"receipt": "opaque-storage-receipt-001"})

    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            receipt = await upload_private_evidence_object(
                tenant_id=str(tenant_id),
                actor_subject="field-worker",
                mission_id=str(mission_id),
                location_id=location_id,
                client_submission_id=str(submission_id),
                field_key="photo",
                media_type="image/jpeg",
                expected_sha256=sha256,
                content=photo_bytes,
                client=client,
                base_url="http://field-evidence-store",
                trusted_hosts=frozenset({"field-evidence-store"}),
            )

        assert observed["body"] == photo_bytes
        assert str(observed["url"]).startswith(
            "http://field-evidence-store/v1/private/field-evidence/"
        )
        assert observed["headers"]["x-eay-field-object-sha256"] == sha256
        assert receipt["sha256"] == sha256
        assert receipt["media_type"] == "image/jpeg"
        assert receipt["byte_size"] == len(photo_bytes)
        assert receipt["idempotent_replay"] is False

        claim = EvidenceObjectClaim(
            receipt_id=receipt["receipt_id"],
            field_key="photo",
            sha256=sha256,
            media_type="image/jpeg",
            byte_size=len(photo_bytes),
        )
        async with engine.begin() as db:
            await _set_tenant(db, str(tenant_id))
            fingerprint = await verify_evidence_authority(
                db,
                tenant_id=str(tenant_id),
                client_submission_id=str(submission_id),
                device_id="device-photo-001",
                captured_at=datetime(2026, 8, 17, 7, 30, tzinfo=UTC),
                template_schema=template_schema,
                payload={"photo": receipt["receipt_id"]},
                claims=(claim,),
                managed_device_required=False,
                camera_only_photo=False,
            )
        assert len(fingerprint) == 64

        async with engine.begin() as db:
            await _set_tenant(db, str(tenant_id))
            with pytest.raises(FieldEvidenceIntegrityError, match="misbound"):
                await verify_evidence_authority(
                    db,
                    tenant_id=str(tenant_id),
                    client_submission_id=str(uuid4()),
                    device_id="device-photo-001",
                    captured_at=datetime(2026, 8, 17, 7, 31, tzinfo=UTC),
                    template_schema=template_schema,
                    payload={"photo": receipt["receipt_id"]},
                    claims=(claim,),
                    managed_device_required=False,
                    camera_only_photo=False,
                )
    finally:
        await close_resources()


def test_production_private_storage_config_fails_closed_without_runtime_endpoint(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEX_ENVIRONMENT", "production")
    monkeypatch.delenv("OPEX_FIELD_EVIDENCE_STORE_URL", raising=False)
    monkeypatch.delenv("OPEX_FIELD_EVIDENCE_STORE_TOKEN_FILE", raising=False)
    with pytest.raises(FieldEvidenceStoreUnavailable, match="not configured"):
        storage_runtime_config()
