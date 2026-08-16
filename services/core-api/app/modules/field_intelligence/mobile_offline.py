from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.resources import engine

from .repository import (
    FieldRepositoryError,
    _set_tenant,
    _validate_evidence_payload,
    list_locations,
)
from .schemas import FieldScope, OfflineEvidenceEvent, OfflineSyncBatch


class FieldOfflineSyncError(ValueError):
    pass


def _event_fingerprint(event: OfflineEvidenceEvent) -> str:
    canonical = json.dumps(
        event.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _camera_policy_satisfied(
    *,
    event: OfflineEvidenceEvent,
    camera_attested_submission_ids: frozenset[str],
) -> bool:
    return str(event.client_submission_id) in camera_attested_submission_ids


async def _sync_one(
    *,
    tenant_id: str,
    actor_subject: str,
    event: OfflineEvidenceEvent,
    trusted_device_ids: frozenset[str],
    camera_attested_submission_ids: frozenset[str],
) -> dict[str, object]:
    payload_fingerprint = _event_fingerprint(event)

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)

        existing_result = await connection.execute(
            text(
                """
                SELECT id, client_submission_id, mission_id, location_id, device_id,
                       device_sequence, target_fingerprint, payload_fingerprint, evidence_id
                FROM field_offline_receipts
                WHERE tenant_id=CAST(:tenant_id AS UUID)
                  AND (
                    (device_id=:device_id AND device_sequence=:device_sequence)
                    OR client_submission_id=CAST(:client_submission_id AS UUID)
                  )
                ORDER BY received_at DESC
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "device_id": event.device_id,
                "device_sequence": event.device_sequence,
                "client_submission_id": str(event.client_submission_id),
            },
        )
        existing = existing_result.mappings().first()
        if existing is not None:
            exact = (
                str(existing["client_submission_id"]) == str(event.client_submission_id)
                and str(existing["mission_id"]) == str(event.mission_id)
                and existing["location_id"] == event.location_id
                and existing["device_id"] == event.device_id
                and int(existing["device_sequence"]) == event.device_sequence
                and existing["target_fingerprint"] == event.target_fingerprint
                and existing["payload_fingerprint"] == payload_fingerprint
            )
            if exact:
                return {
                    "client_submission_id": str(event.client_submission_id),
                    "device_sequence": event.device_sequence,
                    "decision": "idempotent_replay",
                    "evidence_id": str(existing["evidence_id"]),
                    "reason": "exact offline replay",
                }
            return {
                "client_submission_id": str(event.client_submission_id),
                "device_sequence": event.device_sequence,
                "decision": "conflict",
                "evidence_id": None,
                "reason": "device sequence or client submission id was already consumed by different evidence",
            }

        target_result = await connection.execute(
            text(
                """
                SELECT t.status AS target_status,
                       m.status AS mission_status,
                       m.target_fingerprint,
                       ft.schema AS template_schema,
                       ft.evidence_policy
                FROM field_mission_targets t
                JOIN field_missions m
                  ON m.tenant_id=t.tenant_id AND m.id=t.mission_id
                JOIN field_templates ft
                  ON ft.tenant_id=m.tenant_id
                 AND ft.template_id=m.template_id
                 AND ft.version=m.template_version
                WHERE t.tenant_id=CAST(:tenant_id AS UUID)
                  AND t.mission_id=CAST(:mission_id AS UUID)
                  AND t.location_id=:location_id
                FOR UPDATE OF t
                """
            ),
            {
                "tenant_id": tenant_id,
                "mission_id": str(event.mission_id),
                "location_id": event.location_id,
            },
        )
        target = target_result.mappings().first()
        if target is None:
            return {
                "client_submission_id": str(event.client_submission_id),
                "device_sequence": event.device_sequence,
                "decision": "stale_assignment",
                "evidence_id": None,
                "reason": "mission target no longer exists",
            }
        if target["mission_status"] != "active":
            return {
                "client_submission_id": str(event.client_submission_id),
                "device_sequence": event.device_sequence,
                "decision": "stale_assignment",
                "evidence_id": None,
                "reason": "mission is no longer active",
            }
        if target["target_fingerprint"] != event.target_fingerprint:
            return {
                "client_submission_id": str(event.client_submission_id),
                "device_sequence": event.device_sequence,
                "decision": "stale_assignment",
                "evidence_id": None,
                "reason": "mission target snapshot changed after offline capture",
            }
        if target["target_status"] in {"verified", "exempt"}:
            return {
                "client_submission_id": str(event.client_submission_id),
                "device_sequence": event.device_sequence,
                "decision": "stale_assignment",
                "evidence_id": None,
                "reason": "target no longer accepts evidence",
            }

        policy = dict(target["evidence_policy"] or {})
        if bool(policy.get("managed_device_required")) and event.device_id not in trusted_device_ids:
            return {
                "client_submission_id": str(event.client_submission_id),
                "device_sequence": event.device_sequence,
                "decision": "blocked",
                "evidence_id": None,
                "reason": "managed-device policy requires authoritative device attestation",
            }
        if bool(policy.get("camera_only_photo")) and not _camera_policy_satisfied(
            event=event,
            camera_attested_submission_ids=camera_attested_submission_ids,
        ):
            return {
                "client_submission_id": str(event.client_submission_id),
                "device_sequence": event.device_sequence,
                "decision": "blocked",
                "evidence_id": None,
                "reason": "camera-only policy requires authoritative capture attestation",
            }

        _validate_evidence_payload(dict(target["template_schema"]), event.payload)

        evidence_result = await connection.execute(
            text(
                """
                INSERT INTO field_evidence (
                    tenant_id, mission_id, location_id, actor_subject, device_id,
                    client_submission_id, fingerprint, payload, submitted_at
                ) VALUES (
                    CAST(:tenant_id AS UUID), CAST(:mission_id AS UUID), :location_id,
                    :actor_subject, :device_id, CAST(:client_submission_id AS UUID),
                    :fingerprint, CAST(:payload AS JSONB), :submitted_at
                )
                RETURNING id, submitted_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "mission_id": str(event.mission_id),
                "location_id": event.location_id,
                "actor_subject": actor_subject,
                "device_id": event.device_id,
                "client_submission_id": str(event.client_submission_id),
                "fingerprint": payload_fingerprint,
                "payload": json.dumps(event.payload, ensure_ascii=False, sort_keys=True),
                "submitted_at": event.captured_at,
            },
        )
        evidence = evidence_result.mappings().one()

        await connection.execute(
            text(
                """
                INSERT INTO field_offline_receipts (
                    tenant_id, mission_id, location_id, client_submission_id,
                    device_id, device_sequence, target_fingerprint, payload_fingerprint,
                    evidence_id, actor_subject, captured_at
                ) VALUES (
                    CAST(:tenant_id AS UUID), CAST(:mission_id AS UUID), :location_id,
                    CAST(:client_submission_id AS UUID), :device_id, :device_sequence,
                    :target_fingerprint, :payload_fingerprint, CAST(:evidence_id AS UUID),
                    :actor_subject, :captured_at
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "mission_id": str(event.mission_id),
                "location_id": event.location_id,
                "client_submission_id": str(event.client_submission_id),
                "device_id": event.device_id,
                "device_sequence": event.device_sequence,
                "target_fingerprint": event.target_fingerprint,
                "payload_fingerprint": payload_fingerprint,
                "evidence_id": str(evidence["id"]),
                "actor_subject": actor_subject,
                "captured_at": event.captured_at,
            },
        )
        await connection.execute(
            text(
                """
                UPDATE field_mission_targets
                SET status='submitted', updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=CAST(:tenant_id AS UUID)
                  AND mission_id=CAST(:mission_id AS UUID)
                  AND location_id=:location_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "mission_id": str(event.mission_id),
                "location_id": event.location_id,
            },
        )

        return {
            "client_submission_id": str(event.client_submission_id),
            "device_sequence": event.device_sequence,
            "decision": "accepted",
            "evidence_id": str(evidence["id"]),
            "reason": "offline evidence accepted exactly once",
        }


async def sync_offline_batch(
    *,
    tenant_id: str,
    actor_subject: str,
    scope: FieldScope,
    batch: OfflineSyncBatch,
    trusted_device_ids: Iterable[str] = (),
    camera_attested_submission_ids: Iterable[str] = (),
) -> dict[str, object]:
    allowed_locations = await list_locations(tenant_id, scope)
    allowed_ids = {str(item["location_id"]) for item in allowed_locations}
    unauthorized = sorted({event.location_id for event in batch.events} - allowed_ids)
    if unauthorized:
        raise FieldOfflineSyncError(
            "offline batch contains locations outside authorized Field scope"
        )

    trusted = frozenset(trusted_device_ids)
    camera_attested = frozenset(camera_attested_submission_ids)
    outcomes: list[dict[str, object]] = []
    for event in sorted(batch.events, key=lambda item: (item.device_id, item.device_sequence)):
        try:
            outcome = await _sync_one(
                tenant_id=tenant_id,
                actor_subject=actor_subject,
                event=event,
                trusted_device_ids=trusted,
                camera_attested_submission_ids=camera_attested,
            )
        except IntegrityError:
            outcome = {
                "client_submission_id": str(event.client_submission_id),
                "device_sequence": event.device_sequence,
                "decision": "retry_required",
                "evidence_id": None,
                "reason": "concurrent replay collision; retry the exact event",
            }
        except FieldRepositoryError as exc:
            outcome = {
                "client_submission_id": str(event.client_submission_id),
                "device_sequence": event.device_sequence,
                "decision": "invalid",
                "evidence_id": None,
                "reason": str(exc),
            }
        outcomes.append(outcome)

    return {
        "count": len(outcomes),
        "outcomes": outcomes,
        "device_authority": "canonical_attestation_required_for_managed_policy",
        "camera_authority": "canonical_capture_attestation_required_for_camera_only_policy",
    }
