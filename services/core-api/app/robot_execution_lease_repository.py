"""PostgreSQL authority for exact-version Jarvis robot execution leases.

A lease pins one mission to the active Robot Registry version and generation.
The repository never approves a robot and never executes a capability. Callers
that mint a final commit permit must invoke ``validate_current`` in the SAME
PostgreSQL transaction before burning that permit, so a concurrent registry
activation/rollback cannot race past the generation check.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .robot_registry_repository import RobotRegistryIdentity

GENESIS_HASH = "0" * 64


def _canonical(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )


def _sha(value: dict[str, Any] | str) -> str:
    serialized = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RobotExecutionLeaseRecord:
    identity: RobotRegistryIdentity
    lease_id: str
    mission_id: str
    robot_version: int
    registry_generation: int
    version_fingerprint: str
    approval_evidence_ref: str
    lease_generation: int
    state: str
    canary: bool
    baseline_version: int | None
    baseline_version_fingerprint: str | None
    request_fingerprint: str
    idempotency_key: str
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    revocation_reason: str | None
    last_sequence: int
    last_event_hash: str
    updated_at: datetime


@dataclass(frozen=True)
class RobotExecutionLeaseReceiptRecord:
    sequence: int
    lease_generation: int
    receipt_type: str
    receipt_fingerprint: str
    payload_json: str
    payload_hash: str
    previous_event_hash: str
    event_hash: str
    occurred_at: datetime


def _identity_payload(identity: RobotRegistryIdentity) -> dict[str, str]:
    return {
        "tenant_id": str(identity.tenant_id),
        "company_id": identity.company_id,
        "objective_id": identity.objective_id,
        "robot_id": identity.robot_id,
    }


class PostgresRobotExecutionLeaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _params(identity: RobotRegistryIdentity) -> dict[str, object]:
        return {
            "tenant_id": identity.tenant_id,
            "company_id": identity.company_id,
            "objective_id": identity.objective_id,
            "robot_id": identity.robot_id,
        }

    async def issue(
        self,
        *,
        identity: RobotRegistryIdentity,
        mission_id: str,
        expected_robot_version: int,
        expected_registry_generation: int,
        expected_version_fingerprint: str,
        approval_evidence_ref: str,
        issued_at: datetime,
        expires_at: datetime,
        idempotency_key: str,
        canary: bool = False,
        baseline_version: int | None = None,
        baseline_version_fingerprint: str | None = None,
    ) -> tuple[RobotExecutionLeaseRecord, RobotExecutionLeaseReceiptRecord, bool]:
        if not mission_id.strip() or not approval_evidence_ref.strip() or not idempotency_key.strip():
            raise ValueError("robot_execution_lease_required_field_missing")
        if expires_at <= issued_at:
            raise ValueError("robot_execution_lease_expiry_must_follow_issue")
        if canary:
            if (
                baseline_version is None
                or baseline_version_fingerprint is None
                or baseline_version >= expected_robot_version
            ):
                raise ValueError("robot_execution_canary_requires_older_baseline")
        elif baseline_version is not None or baseline_version_fingerprint is not None:
            raise ValueError("robot_execution_non_canary_cannot_claim_baseline")

        registry = await self._active_registry_for_share(identity)
        if registry is None:
            raise ValueError("robot_execution_registry_not_active")
        if (
            registry["active_version"] != expected_robot_version
            or registry["generation"] != expected_registry_generation
            or registry["active_version_fingerprint"] != expected_version_fingerprint
        ):
            raise ValueError("robot_execution_registry_pin_mismatch")

        if canary:
            baseline = await self.session.execute(
                text(
                    """
                    SELECT version_fingerprint FROM jarvis_robot_versions
                    WHERE tenant_id = :tenant_id AND company_id = :company_id
                      AND objective_id = :objective_id AND robot_id = :robot_id
                      AND robot_version = :baseline_version
                    """
                ),
                {**self._params(identity), "baseline_version": baseline_version},
            )
            baseline_row = baseline.mappings().first()
            if (
                baseline_row is None
                or baseline_row["version_fingerprint"] != baseline_version_fingerprint
            ):
                raise ValueError("robot_execution_canary_baseline_mismatch")

        request_payload = {
            **_identity_payload(identity),
            "mission_id": mission_id,
            "robot_version": expected_robot_version,
            "registry_generation": expected_registry_generation,
            "version_fingerprint": expected_version_fingerprint,
            "approval_evidence_ref": approval_evidence_ref,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "canary": canary,
            "baseline_version": baseline_version,
            "baseline_version_fingerprint": baseline_version_fingerprint,
        }
        request_fingerprint = _sha(request_payload)
        lease_id = _sha(
            {
                **_identity_payload(identity),
                "mission_id": mission_id,
                "idempotency_key": idempotency_key,
                "request_fingerprint": request_fingerprint,
            }
        )

        existing_result = await self.session.execute(
            text(
                """
                SELECT * FROM jarvis_robot_execution_leases
                WHERE tenant_id = :tenant_id AND company_id = :company_id
                  AND objective_id = :objective_id AND robot_id = :robot_id
                  AND idempotency_key = :idempotency_key
                FOR UPDATE
                """
            ),
            {**self._params(identity), "idempotency_key": idempotency_key},
        )
        existing = existing_result.mappings().first()
        if existing is not None:
            record = self._record(existing)
            if record.request_fingerprint != request_fingerprint:
                raise ValueError("robot_execution_lease_idempotency_payload_conflict")
            receipt = await self._first_receipt(identity.tenant_id, record.lease_id)
            if receipt is None:
                raise RuntimeError("robot_execution_lease_issue_receipt_missing")
            return record, receipt, False

        await self.session.execute(
            text(
                """
                INSERT INTO jarvis_robot_execution_leases (
                    tenant_id, company_id, objective_id, robot_id, lease_id,
                    mission_id, robot_version, registry_generation,
                    version_fingerprint, approval_evidence_ref, lease_generation,
                    state, canary, baseline_version, baseline_version_fingerprint,
                    request_fingerprint, idempotency_key, issued_at, expires_at,
                    updated_at
                ) VALUES (
                    :tenant_id, :company_id, :objective_id, :robot_id, :lease_id,
                    :mission_id, :robot_version, :registry_generation,
                    :version_fingerprint, :approval_evidence_ref, 1,
                    'active', :canary, :baseline_version, :baseline_version_fingerprint,
                    :request_fingerprint, :idempotency_key, :issued_at, :expires_at,
                    :issued_at
                )
                """
            ),
            {
                **self._params(identity),
                "lease_id": lease_id,
                "mission_id": mission_id,
                "robot_version": expected_robot_version,
                "registry_generation": expected_registry_generation,
                "version_fingerprint": expected_version_fingerprint,
                "approval_evidence_ref": approval_evidence_ref,
                "canary": canary,
                "baseline_version": baseline_version,
                "baseline_version_fingerprint": baseline_version_fingerprint,
                "request_fingerprint": request_fingerprint,
                "idempotency_key": idempotency_key,
                "issued_at": issued_at,
                "expires_at": expires_at,
            },
        )
        record = await self.get(identity.tenant_id, lease_id, for_update=True)
        if record is None:
            raise RuntimeError("robot_execution_lease_missing_after_insert")
        receipt = await self._append_receipt(
            record=record,
            receipt_type="issued",
            occurred_at=issued_at,
            payload={
                "lease_id": lease_id,
                "robot_version": expected_robot_version,
                "registry_generation": expected_registry_generation,
                "version_fingerprint": expected_version_fingerprint,
                "mission_id": mission_id,
            },
        )
        refreshed = await self.get(identity.tenant_id, lease_id)
        if refreshed is None:
            raise RuntimeError("robot_execution_lease_missing_after_receipt")
        return refreshed, receipt, True

    async def validate_current(
        self,
        *,
        tenant_id: UUID,
        lease_id: str,
        checked_at: datetime,
        record_validation_receipt: bool = True,
    ) -> RobotExecutionLeaseRecord:
        """Lock lease + registry so a permit can be burned safely in this transaction."""

        record = await self.get(tenant_id, lease_id, for_update=True)
        if record is None:
            raise ValueError("robot_execution_lease_not_found")
        if record.state != "active":
            raise ValueError("robot_execution_lease_not_active")
        registry = await self._active_registry_for_share(record.identity)
        reason: str | None = None
        if checked_at >= record.expires_at:
            reason = "robot_execution_lease_expired"
        elif registry is None:
            reason = "robot_execution_registry_not_active"
        elif (
            registry["generation"] != record.registry_generation
            or registry["active_version"] != record.robot_version
            or registry["active_version_fingerprint"] != record.version_fingerprint
        ):
            reason = "robot_execution_registry_generation_or_version_changed"

        if reason is not None:
            revoked = await self._revoke_locked(record, reason=reason, occurred_at=checked_at)
            raise ValueError(reason + ":" + revoked.lease_id)

        if record_validation_receipt:
            await self._append_receipt(
                record=record,
                receipt_type="validated",
                occurred_at=checked_at,
                payload={
                    "lease_id": record.lease_id,
                    "robot_version": record.robot_version,
                    "registry_generation": record.registry_generation,
                    "version_fingerprint": record.version_fingerprint,
                },
            )
            refreshed = await self.get(tenant_id, lease_id, for_update=True)
            if refreshed is None:
                raise RuntimeError("robot_execution_lease_missing_after_validation")
            return refreshed
        return record

    async def complete(
        self,
        *,
        tenant_id: UUID,
        lease_id: str,
        completed_at: datetime,
        completion_evidence_ref: str,
    ) -> RobotExecutionLeaseRecord:
        if not completion_evidence_ref.strip():
            raise ValueError("robot_execution_lease_completion_requires_evidence")
        record = await self.validate_current(
            tenant_id=tenant_id,
            lease_id=lease_id,
            checked_at=completed_at,
            record_validation_receipt=False,
        )
        updated = await self.session.execute(
            text(
                """
                UPDATE jarvis_robot_execution_leases
                SET state = 'completed', updated_at = :completed_at
                WHERE tenant_id = :tenant_id AND lease_id = :lease_id
                  AND state = 'active' AND lease_generation = :lease_generation
                RETURNING *
                """
            ),
            {
                "tenant_id": tenant_id,
                "lease_id": lease_id,
                "lease_generation": record.lease_generation,
                "completed_at": completed_at,
            },
        )
        row = updated.mappings().first()
        if row is None:
            raise ValueError("robot_execution_lease_stale_generation")
        completed = self._record(row)
        await self._append_receipt(
            record=completed,
            receipt_type="completed",
            occurred_at=completed_at,
            payload={
                "lease_id": lease_id,
                "completion_evidence_ref": completion_evidence_ref,
            },
        )
        result = await self.get(tenant_id, lease_id)
        if result is None:
            raise RuntimeError("robot_execution_lease_missing_after_completion")
        return result

    async def get(
        self,
        tenant_id: UUID,
        lease_id: str,
        *,
        for_update: bool = False,
    ) -> RobotExecutionLeaseRecord | None:
        suffix = " FOR UPDATE" if for_update else ""
        result = await self.session.execute(
            text(
                "SELECT * FROM jarvis_robot_execution_leases "
                "WHERE tenant_id = :tenant_id AND lease_id = :lease_id" + suffix
            ),
            {"tenant_id": tenant_id, "lease_id": lease_id},
        )
        row = result.mappings().first()
        return None if row is None else self._record(row)

    async def list_receipts(
        self, *, tenant_id: UUID, lease_id: str
    ) -> tuple[RobotExecutionLeaseReceiptRecord, ...]:
        result = await self.session.execute(
            text(
                """
                SELECT * FROM jarvis_robot_execution_lease_receipts
                WHERE tenant_id = :tenant_id AND lease_id = :lease_id
                ORDER BY sequence
                """
            ),
            {"tenant_id": tenant_id, "lease_id": lease_id},
        )
        return tuple(self._receipt(row) for row in result.mappings().all())

    async def _active_registry_for_share(self, identity: RobotRegistryIdentity):
        result = await self.session.execute(
            text(
                """
                SELECT state, active_version, active_version_fingerprint, generation
                FROM jarvis_robot_registries
                WHERE tenant_id = :tenant_id AND company_id = :company_id
                  AND objective_id = :objective_id AND robot_id = :robot_id
                  AND state = 'active'
                FOR SHARE
                """
            ),
            self._params(identity),
        )
        return result.mappings().first()

    async def _revoke_locked(
        self,
        record: RobotExecutionLeaseRecord,
        *,
        reason: str,
        occurred_at: datetime,
    ) -> RobotExecutionLeaseRecord:
        next_generation = record.lease_generation + 1
        updated = await self.session.execute(
            text(
                """
                UPDATE jarvis_robot_execution_leases
                SET state = 'revoked', lease_generation = :next_generation,
                    revoked_at = :occurred_at, revocation_reason = :reason,
                    updated_at = :occurred_at
                WHERE tenant_id = :tenant_id AND lease_id = :lease_id
                  AND state = 'active' AND lease_generation = :expected_generation
                RETURNING *
                """
            ),
            {
                "tenant_id": record.identity.tenant_id,
                "lease_id": record.lease_id,
                "next_generation": next_generation,
                "expected_generation": record.lease_generation,
                "occurred_at": occurred_at,
                "reason": reason,
            },
        )
        row = updated.mappings().first()
        if row is None:
            raise ValueError("robot_execution_lease_stale_generation")
        revoked = self._record(row)
        await self._append_receipt(
            record=revoked,
            receipt_type="revoked",
            occurred_at=occurred_at,
            payload={"lease_id": record.lease_id, "reason": reason},
        )
        result = await self.get(record.identity.tenant_id, record.lease_id, for_update=True)
        if result is None:
            raise RuntimeError("robot_execution_lease_missing_after_revocation")
        return result

    async def _append_receipt(
        self,
        *,
        record: RobotExecutionLeaseRecord,
        receipt_type: str,
        occurred_at: datetime,
        payload: dict[str, Any],
    ) -> RobotExecutionLeaseReceiptRecord:
        current = await self.get(record.identity.tenant_id, record.lease_id, for_update=True)
        if current is None:
            raise RuntimeError("robot_execution_lease_missing_for_receipt")
        sequence = current.last_sequence + 1
        payload_json = _canonical(payload)
        payload_hash = _sha(payload_json)
        receipt_fingerprint = _sha(
            {
                "tenant_id": str(current.identity.tenant_id),
                "lease_id": current.lease_id,
                "sequence": sequence,
                "lease_generation": current.lease_generation,
                "receipt_type": receipt_type,
                "payload_hash": payload_hash,
            }
        )
        event_hash = _sha(
            {
                "tenant_id": str(current.identity.tenant_id),
                "lease_id": current.lease_id,
                "sequence": sequence,
                "lease_generation": current.lease_generation,
                "receipt_type": receipt_type,
                "receipt_fingerprint": receipt_fingerprint,
                "payload_hash": payload_hash,
                "previous_event_hash": current.last_event_hash,
            }
        )
        await self.session.execute(
            text(
                """
                INSERT INTO jarvis_robot_execution_lease_receipts (
                    tenant_id, lease_id, sequence, lease_generation, receipt_type,
                    receipt_fingerprint, payload_json, payload_hash,
                    previous_event_hash, event_hash, occurred_at
                ) VALUES (
                    :tenant_id, :lease_id, :sequence, :lease_generation, :receipt_type,
                    :receipt_fingerprint, :payload_json, :payload_hash,
                    :previous_event_hash, :event_hash, :occurred_at
                )
                """
            ),
            {
                "tenant_id": current.identity.tenant_id,
                "lease_id": current.lease_id,
                "sequence": sequence,
                "lease_generation": current.lease_generation,
                "receipt_type": receipt_type,
                "receipt_fingerprint": receipt_fingerprint,
                "payload_json": payload_json,
                "payload_hash": payload_hash,
                "previous_event_hash": current.last_event_hash,
                "event_hash": event_hash,
                "occurred_at": occurred_at,
            },
        )
        result = await self.session.execute(
            text(
                """
                UPDATE jarvis_robot_execution_leases
                SET last_sequence = :sequence, last_event_hash = :event_hash,
                    updated_at = GREATEST(updated_at, :occurred_at)
                WHERE tenant_id = :tenant_id AND lease_id = :lease_id
                  AND last_sequence = :expected_sequence
                """
            ),
            {
                "tenant_id": current.identity.tenant_id,
                "lease_id": current.lease_id,
                "sequence": sequence,
                "event_hash": event_hash,
                "occurred_at": occurred_at,
                "expected_sequence": current.last_sequence,
            },
        )
        if result.rowcount != 1:
            raise RuntimeError("robot_execution_lease_receipt_sequence_conflict")
        return RobotExecutionLeaseReceiptRecord(
            sequence=sequence,
            lease_generation=current.lease_generation,
            receipt_type=receipt_type,
            receipt_fingerprint=receipt_fingerprint,
            payload_json=payload_json,
            payload_hash=payload_hash,
            previous_event_hash=current.last_event_hash,
            event_hash=event_hash,
            occurred_at=occurred_at,
        )

    async def _first_receipt(
        self, tenant_id: UUID, lease_id: str
    ) -> RobotExecutionLeaseReceiptRecord | None:
        result = await self.session.execute(
            text(
                """
                SELECT * FROM jarvis_robot_execution_lease_receipts
                WHERE tenant_id = :tenant_id AND lease_id = :lease_id
                ORDER BY sequence LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "lease_id": lease_id},
        )
        row = result.mappings().first()
        return None if row is None else self._receipt(row)

    @staticmethod
    def _record(row) -> RobotExecutionLeaseRecord:
        return RobotExecutionLeaseRecord(
            identity=RobotRegistryIdentity(
                tenant_id=row["tenant_id"],
                company_id=row["company_id"],
                objective_id=row["objective_id"],
                robot_id=row["robot_id"],
            ),
            lease_id=row["lease_id"],
            mission_id=row["mission_id"],
            robot_version=row["robot_version"],
            registry_generation=row["registry_generation"],
            version_fingerprint=row["version_fingerprint"],
            approval_evidence_ref=row["approval_evidence_ref"],
            lease_generation=row["lease_generation"],
            state=row["state"],
            canary=row["canary"],
            baseline_version=row["baseline_version"],
            baseline_version_fingerprint=row["baseline_version_fingerprint"],
            request_fingerprint=row["request_fingerprint"],
            idempotency_key=row["idempotency_key"],
            issued_at=row["issued_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
            revocation_reason=row["revocation_reason"],
            last_sequence=row["last_sequence"],
            last_event_hash=row["last_event_hash"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _receipt(row) -> RobotExecutionLeaseReceiptRecord:
        return RobotExecutionLeaseReceiptRecord(
            sequence=row["sequence"],
            lease_generation=row["lease_generation"],
            receipt_type=row["receipt_type"],
            receipt_fingerprint=row["receipt_fingerprint"],
            payload_json=row["payload_json"],
            payload_hash=row["payload_hash"],
            previous_event_hash=row["previous_event_hash"],
            event_hash=row["event_hash"],
            occurred_at=row["occurred_at"],
        )
