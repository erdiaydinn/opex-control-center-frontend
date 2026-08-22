"""PostgreSQL adapter for authenticated Jarvis agent jobs.

All statements retain an explicit tenant predicate in addition to FORCE RLS.
Create/replay and cancellation/event append execute inside the tenant transaction
provided by ``get_tenant_session``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

GENESIS_HASH = "0" * 64


def _hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class AgentJobRecord:
    id: UUID
    tenant_id: UUID
    requested_by: str
    objective_ref: str
    status: str
    version: int
    cancellation_epoch: int
    required_child_count: int
    completed_child_count: int
    effect_state: str
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None


class PostgresAgentJobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        requested_by: str,
        idempotency_key: str,
        objective_ref: str,
        required_child_count: int,
    ) -> tuple[AgentJobRecord, bool]:
        fingerprint = _hash({
            "tenant_id": str(tenant_id),
            "requested_by": requested_by,
            "objective_ref": objective_ref,
            "required_child_count": required_child_count,
        })
        inserted = await self.session.execute(
            text("""
                INSERT INTO jarvis_agent_jobs (
                    tenant_id, requested_by, idempotency_key, request_fingerprint,
                    objective_ref, required_child_count
                ) VALUES (
                    :tenant_id, :requested_by, :idempotency_key, :fingerprint,
                    :objective_ref, :required_child_count
                )
                ON CONFLICT (tenant_id, requested_by, idempotency_key) DO NOTHING
                RETURNING *
            """),
            {
                "tenant_id": tenant_id,
                "requested_by": requested_by,
                "idempotency_key": idempotency_key,
                "fingerprint": fingerprint,
                "objective_ref": objective_ref,
                "required_child_count": required_child_count,
            },
        )
        row = inserted.mappings().first()
        created = row is not None
        if row is None:
            existing = await self.session.execute(
                text("""
                    SELECT * FROM jarvis_agent_jobs
                    WHERE tenant_id = :tenant_id AND requested_by = :requested_by
                      AND idempotency_key = :idempotency_key
                    FOR UPDATE
                """),
                {
                    "tenant_id": tenant_id,
                    "requested_by": requested_by,
                    "idempotency_key": idempotency_key,
                },
            )
            row = existing.mappings().first()
            if row is None:
                raise RuntimeError("agent_job_idempotency_resolution_failed")
            if row["request_fingerprint"] != fingerprint:
                raise ValueError("agent_job_idempotency_payload_conflict")
        if created:
            event_hash = _hash({
                "job_id": str(row["id"]),
                "sequence": 1,
                "event_type": "created",
                "actor_ref": requested_by,
                "cancellation_epoch": 0,
                "previous_event_hash": GENESIS_HASH,
            })
            await self.session.execute(
                text("""
                    INSERT INTO jarvis_agent_job_events (
                        tenant_id, job_id, sequence, event_type, actor_ref,
                        cancellation_epoch, previous_event_hash, event_hash
                    ) VALUES (
                        :tenant_id, :job_id, 1, 'created', :actor_ref,
                        0, :previous_hash, :event_hash
                    )
                """),
                {
                    "tenant_id": tenant_id,
                    "job_id": row["id"],
                    "actor_ref": requested_by,
                    "previous_hash": GENESIS_HASH,
                    "event_hash": event_hash,
                },
            )
            await self.session.execute(
                text("""
                    UPDATE jarvis_agent_jobs SET last_event_hash = :event_hash
                    WHERE tenant_id = :tenant_id AND id = :job_id
                """),
                {"tenant_id": tenant_id, "job_id": row["id"], "event_hash": event_hash},
            )
        return self._record(row), created

    async def get(self, *, tenant_id: UUID, job_id: UUID) -> AgentJobRecord | None:
        result = await self.session.execute(
            text("SELECT * FROM jarvis_agent_jobs WHERE tenant_id = :tenant_id AND id = :job_id"),
            {"tenant_id": tenant_id, "job_id": job_id},
        )
        row = result.mappings().first()
        return self._record(row) if row else None

    async def events(
        self, *, tenant_id: UUID, job_id: UUID, after_sequence: int, limit: int
    ) -> tuple[dict[str, object], ...]:
        exists = await self.get(tenant_id=tenant_id, job_id=job_id)
        if exists is None:
            return ()
        result = await self.session.execute(
            text("""
                SELECT sequence, event_type, actor_ref, cancellation_epoch,
                       evidence_refs, event_hash, occurred_at
                FROM jarvis_agent_job_events
                WHERE tenant_id = :tenant_id AND job_id = :job_id
                  AND sequence > :after_sequence
                ORDER BY sequence ASC LIMIT :limit
            """),
            {
                "tenant_id": tenant_id,
                "job_id": job_id,
                "after_sequence": after_sequence,
                "limit": limit,
            },
        )
        return tuple(dict(row) for row in result.mappings().all())

    async def cancel(
        self, *, tenant_id: UUID, job_id: UUID, requested_by: str
    ) -> AgentJobRecord | None:
        current_result = await self.session.execute(
            text("""
                SELECT * FROM jarvis_agent_jobs
                WHERE tenant_id = :tenant_id AND id = :job_id FOR UPDATE
            """),
            {"tenant_id": tenant_id, "job_id": job_id},
        )
        current = current_result.mappings().first()
        if current is None:
            return None
        if current["status"] in {"cancel_requested", "cancelled", "completed", "failed"}:
            return self._record(current)
        next_epoch = int(current["cancellation_epoch"]) + 1
        next_version = int(current["version"]) + 1
        updated_result = await self.session.execute(
            text("""
                UPDATE jarvis_agent_jobs
                SET status = 'cancel_requested', cancellation_epoch = :next_epoch,
                    version = :next_version, updated_at = CURRENT_TIMESTAMP
                WHERE tenant_id = :tenant_id AND id = :job_id
                  AND version = :expected_version
                RETURNING *
            """),
            {
                "tenant_id": tenant_id,
                "job_id": job_id,
                "next_epoch": next_epoch,
                "next_version": next_version,
                "expected_version": current["version"],
            },
        )
        updated = updated_result.mappings().first()
        if updated is None:
            raise RuntimeError("agent_job_optimistic_version_conflict")
        event_hash = _hash({
            "job_id": str(job_id),
            "sequence": next_version,
            "event_type": "cancel_requested",
            "actor_ref": requested_by,
            "cancellation_epoch": next_epoch,
            "previous_event_hash": current["last_event_hash"],
        })
        await self.session.execute(
            text("""
                INSERT INTO jarvis_agent_job_events (
                    tenant_id, job_id, sequence, event_type, actor_ref,
                    cancellation_epoch, previous_event_hash, event_hash
                ) VALUES (
                    :tenant_id, :job_id, :sequence, 'cancel_requested', :actor_ref,
                    :epoch, :previous_hash, :event_hash
                )
            """),
            {
                "tenant_id": tenant_id,
                "job_id": job_id,
                "sequence": next_version,
                "actor_ref": requested_by,
                "epoch": next_epoch,
                "previous_hash": current["last_event_hash"],
                "event_hash": event_hash,
            },
        )
        await self.session.execute(
            text("""
                UPDATE jarvis_agent_jobs SET last_event_hash = :event_hash
                WHERE tenant_id = :tenant_id AND id = :job_id AND version = :version
            """),
            {
                "tenant_id": tenant_id,
                "job_id": job_id,
                "version": next_version,
                "event_hash": event_hash,
            },
        )
        return self._record(updated)

    @staticmethod
    def _record(row) -> AgentJobRecord:
        return AgentJobRecord(
            id=row["id"], tenant_id=row["tenant_id"], requested_by=row["requested_by"],
            objective_ref=row["objective_ref"], status=row["status"], version=row["version"],
            cancellation_epoch=row["cancellation_epoch"],
            required_child_count=row["required_child_count"],
            completed_child_count=row["completed_child_count"],
            effect_state=row["effect_state"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            terminal_at=row["terminal_at"],
        )
