from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings
from app.modules.field_intelligence.mobile_offline import (
    FieldOfflineSyncError,
    set_template_evidence_policy,
    sync_offline_batch,
)
from app.modules.field_intelligence.schemas import (
    EvidencePolicy,
    FieldScope,
    OfflineEvidenceEvent,
    OfflineSyncBatch,
)

TENANT_A = UUID("00000000-0000-0000-0000-00000000f201")
TENANT_B = UUID("00000000-0000-0000-0000-00000000f202")
MISSION_ID = UUID("00000000-0000-0000-0000-00000000f211")
TARGET_FINGERPRINT = "a" * 64
DEVICE_ID = "mobile-device-0001"


async def set_tenant_context(connection: AsyncConnection, tenant_id: UUID) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def seed_tenant(connection: AsyncConnection, tenant_id: UUID, slug: str) -> None:
    await set_tenant_context(connection, tenant_id)
    await connection.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name)
            VALUES (:tenant_id, :slug, :display_name)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"tenant_id": tenant_id, "slug": slug, "display_name": slug},
    )


async def seed_field_assignment(connection: AsyncConnection) -> None:
    await seed_tenant(connection, TENANT_A, "field-mobile-a")
    await connection.execute(
        text(
            """
            INSERT INTO field_locations (tenant_id, location_id, name, active)
            VALUES (:tenant_id, 'WH-001', 'Warehouse 001', TRUE)
            ON CONFLICT (tenant_id, location_id) DO NOTHING
            """
        ),
        {"tenant_id": TENANT_A},
    )
    await connection.execute(
        text(
            """
            INSERT INTO field_templates (
                tenant_id, template_id, version, status, name_i18n, schema, created_by
            ) VALUES (
                :tenant_id, 'mobile-proof', 1, 'active',
                CAST(:name_i18n AS JSONB), CAST(:schema AS JSONB), 'test-author'
            )
            ON CONFLICT (tenant_id, template_id, version) DO NOTHING
            """
        ),
        {
            "tenant_id": TENANT_A,
            "name_i18n": json.dumps({"en": "Mobile proof"}),
            "schema": json.dumps(
                {
                    "fields": [
                        {
                            "key": "lot",
                            "type": "text",
                            "label": {"values": {"en": "Lot"}},
                            "required": True,
                            "helper": None,
                            "options": [],
                            "unit": None,
                            "config": {},
                        }
                    ]
                }
            ),
        },
    )
    await connection.execute(
        text(
            """
            INSERT INTO field_missions (
                tenant_id, id, template_id, template_version, title_i18n, instructions_i18n,
                status, priority, selector, target_fingerprint, target_count,
                assigned_at, deadline_at, created_by
            ) VALUES (
                :tenant_id, :mission_id, 'mobile-proof', 1,
                CAST(:title_i18n AS JSONB), CAST(:instructions_i18n AS JSONB),
                'active', 'normal', CAST(:selector AS JSONB),
                :fingerprint, 1, CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP + interval '1 day', 'test-author'
            )
            ON CONFLICT (tenant_id, id) DO NOTHING
            """
        ),
        {
            "tenant_id": TENANT_A,
            "mission_id": MISSION_ID,
            "fingerprint": TARGET_FINGERPRINT,
            "title_i18n": json.dumps({"en": "Offline proof"}),
            "instructions_i18n": json.dumps({}),
            "selector": json.dumps({"include_location_ids": ["WH-001"]}),
        },
    )
    await connection.execute(
        text(
            """
            INSERT INTO field_mission_targets (tenant_id, mission_id, location_id, status)
            VALUES (:tenant_id, :mission_id, 'WH-001', 'unseen')
            ON CONFLICT (tenant_id, mission_id, location_id) DO NOTHING
            """
        ),
        {"tenant_id": TENANT_A, "mission_id": MISSION_ID},
    )


def event(
    *,
    sequence: int,
    submission_id: UUID | None = None,
    fingerprint: str = TARGET_FINGERPRINT,
    lot: str = "LOT-A",
) -> OfflineEvidenceEvent:
    return OfflineEvidenceEvent(
        client_submission_id=submission_id or uuid4(),
        mission_id=MISSION_ID,
        location_id="WH-001",
        device_id=DEVICE_ID,
        device_sequence=sequence,
        target_fingerprint=fingerprint,
        captured_at=datetime.now(UTC) - timedelta(minutes=2),
        payload={"lot": lot},
    )


def test_offline_batch_rejects_browser_authority_and_duplicate_sequence() -> None:
    first = event(sequence=1)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OfflineEvidenceEvent(**first.model_dump(mode="python"), tenant_id=str(TENANT_A))
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OfflineEvidenceEvent(**first.model_dump(mode="python"), trusted_device=True)
    with pytest.raises(ValidationError, match="duplicate device sequence"):
        OfflineSyncBatch(
            events=(first, first.model_copy(update={"client_submission_id": uuid4()}))
        )


@pytest.mark.asyncio
async def test_offline_sync_is_idempotent_detects_conflict_stale_and_policy_blocks() -> None:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await seed_field_assignment(connection)
            await seed_tenant(connection, TENANT_B, "field-mobile-b")

        scope = FieldScope(unrestricted=True)
        first = event(sequence=1)
        accepted = await sync_offline_batch(
            tenant_id=str(TENANT_A),
            actor_subject="worker-a",
            scope=scope,
            batch=OfflineSyncBatch(events=(first,)),
        )
        assert accepted["outcomes"][0]["decision"] == "accepted"
        evidence_id = accepted["outcomes"][0]["evidence_id"]

        replay = await sync_offline_batch(
            tenant_id=str(TENANT_A),
            actor_subject="worker-a",
            scope=scope,
            batch=OfflineSyncBatch(events=(first,)),
        )
        assert replay["outcomes"][0] == {
            "client_submission_id": str(first.client_submission_id),
            "device_sequence": 1,
            "decision": "idempotent_replay",
            "evidence_id": evidence_id,
            "reason": "exact offline replay",
        }

        collision = event(sequence=1, lot="DIFFERENT")
        conflict = await sync_offline_batch(
            tenant_id=str(TENANT_A),
            actor_subject="worker-a",
            scope=scope,
            batch=OfflineSyncBatch(events=(collision,)),
        )
        assert conflict["outcomes"][0]["decision"] == "conflict"

        stale = await sync_offline_batch(
            tenant_id=str(TENANT_A),
            actor_subject="worker-a",
            scope=scope,
            batch=OfflineSyncBatch(events=(event(sequence=2, fingerprint="b" * 64),)),
        )
        assert stale["outcomes"][0]["decision"] == "stale_assignment"

        policy = await set_template_evidence_policy(
            tenant_id=str(TENANT_A),
            actor_subject="manager-a",
            template_id="mobile-proof",
            template_version=1,
            policy=EvidencePolicy(camera_only_photo=True, managed_device_required=True),
        )
        assert policy["camera_only_photo"] is True
        assert policy["managed_device_required"] is True

        restricted = event(sequence=3)
        blocked_device = await sync_offline_batch(
            tenant_id=str(TENANT_A),
            actor_subject="worker-a",
            scope=scope,
            batch=OfflineSyncBatch(events=(restricted,)),
        )
        assert blocked_device["outcomes"][0]["decision"] == "blocked"
        assert "device attestation" in blocked_device["outcomes"][0]["reason"]

        blocked_camera = await sync_offline_batch(
            tenant_id=str(TENANT_A),
            actor_subject="worker-a",
            scope=scope,
            batch=OfflineSyncBatch(events=(restricted,)),
            trusted_device_ids={DEVICE_ID},
        )
        assert blocked_camera["outcomes"][0]["decision"] == "blocked"
        assert "capture attestation" in blocked_camera["outcomes"][0]["reason"]

        attested = await sync_offline_batch(
            tenant_id=str(TENANT_A),
            actor_subject="worker-a",
            scope=scope,
            batch=OfflineSyncBatch(events=(restricted,)),
            trusted_device_ids={DEVICE_ID},
            camera_attested_submission_ids={str(restricted.client_submission_id)},
        )
        assert attested["outcomes"][0]["decision"] == "accepted"

        with pytest.raises(FieldOfflineSyncError, match="already defined"):
            await set_template_evidence_policy(
                tenant_id=str(TENANT_A),
                actor_subject="manager-b",
                template_id="mobile-proof",
                template_version=1,
                policy=EvidencePolicy(),
            )

        async with engine.begin() as connection:
            await set_tenant_context(connection, TENANT_B)
            assert await connection.scalar(text("SELECT count(*) FROM field_offline_receipts")) == 0
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM field_template_evidence_policies")
                )
                == 0
            )

        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await set_tenant_context(connection, TENANT_A)
                await connection.execute(
                    text(
                        """
                        UPDATE field_template_evidence_policies
                        SET managed_device_required=FALSE
                        WHERE tenant_id=:tenant_id
                          AND template_id='mobile-proof'
                          AND template_version=1
                        """
                    ),
                    {"tenant_id": TENANT_A},
                )
    finally:
        await engine.dispose()
