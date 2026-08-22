"""PostgreSQL authority for restart-safe Jarvis epistemic canary rollouts.

AI-core creates sealed snapshots and receipts. This adapter persists them with explicit
rollout identity predicates, FORCE-RLS protection, append-only receipt history, a hash
chain, and generation/version compare-and-swap fencing.
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

GENESIS_HASH = "0" * 64
FINGERPRINT_FIELDS = {
    "activation": "activation_fingerprint",
    "health_observation": "observation_fingerprint",
    "health_verdict": "verdict_fingerprint",
    "rollback": "rollback_fingerprint",
    "promotion_evidence": "evidence_fingerprint",
    "promotion_approval": "approval_fingerprint",
    "promotion_review": "receipt_fingerprint",
}
ACTIVE_RECEIPTS = frozenset(FINGERPRINT_FIELDS) - {"activation", "rollback"}


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value: dict[str, Any] | str) -> str:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("epistemic_payload_must_be_object")
    return json.dumps(
        parsed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )


@dataclass(frozen=True)
class EpistemicRolloutIdentity:
    tenant_id: UUID
    company_id: str
    problem_class: str
    rollout_id: str


@dataclass(frozen=True)
class EpistemicRolloutRecord:
    identity: EpistemicRolloutIdentity
    generation: int
    state: str
    version: int
    candidate_fingerprint: str
    baseline_fingerprint: str
    baseline_profile_fingerprint: str
    selected_profile_fingerprint: str
    activation_fingerprint: str
    rollback_fingerprint: str | None
    snapshot_fingerprint: str
    snapshot_payload_json: str
    snapshot_payload_hash: str
    last_sequence: int
    last_event_hash: str

    def verified_snapshot_payload(self) -> dict[str, Any]:
        if _sha(self.snapshot_payload_json) != self.snapshot_payload_hash:
            raise ValueError("epistemic_snapshot_payload_hash_mismatch")
        payload = json.loads(self.snapshot_payload_json)
        if payload.get("snapshot_fingerprint") != self.snapshot_fingerprint:
            raise ValueError("epistemic_snapshot_fingerprint_payload_mismatch")
        return payload


@dataclass(frozen=True)
class EpistemicReceiptRecord:
    sequence: int
    generation: int
    receipt_type: str
    receipt_fingerprint: str
    payload_json: str
    payload_hash: str
    idempotency_key: str | None
    previous_event_hash: str
    event_hash: str

    def verified_payload(self) -> dict[str, Any]:
        if _sha(self.payload_json) != self.payload_hash:
            raise ValueError("epistemic_receipt_payload_hash_mismatch")
        return json.loads(self.payload_json)


def _identity_payload(identity: EpistemicRolloutIdentity) -> dict[str, str]:
    return {
        "tenant_id": str(identity.tenant_id),
        "company_id": identity.company_id,
        "problem_class": identity.problem_class,
        "rollout_id": identity.rollout_id,
    }


def _validate_snapshot(
    identity: EpistemicRolloutIdentity,
    generation: int,
    state: str,
    fingerprint: str,
    payload_json: str,
) -> None:
    payload = json.loads(payload_json)
    if payload.get("snapshot_fingerprint") != fingerprint:
        raise ValueError("epistemic_snapshot_fingerprint_payload_mismatch")
    if payload.get("identity") != _identity_payload(identity):
        raise ValueError("epistemic_snapshot_identity_payload_mismatch")
    if payload.get("generation") != generation or payload.get("state") != state:
        raise ValueError("epistemic_snapshot_state_generation_mismatch")


def _validate_receipt(
    identity: EpistemicRolloutIdentity,
    generation: int,
    receipt_type: str,
    fingerprint: str,
    payload_json: str,
) -> None:
    payload = json.loads(payload_json)
    field = FINGERPRINT_FIELDS.get(receipt_type)
    if field is None or payload.get(field) != fingerprint:
        raise ValueError("epistemic_receipt_fingerprint_payload_mismatch")
    expected_identity = _identity_payload(identity)
    embedded = payload.get("identity")
    if embedded is not None:
        if embedded != expected_identity:
            raise ValueError("epistemic_receipt_identity_payload_mismatch")
    elif any(payload.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("epistemic_receipt_identity_payload_mismatch")
    embedded_generation = (
        payload.get("resulting_generation")
        if receipt_type == "rollback"
        else payload.get("generation")
    )
    if embedded_generation is not None and embedded_generation != generation:
        raise ValueError("epistemic_receipt_generation_payload_mismatch")


def _event_hash(
    identity: EpistemicRolloutIdentity,
    *,
    sequence: int,
    generation: int,
    receipt_type: str,
    receipt_fingerprint: str,
    payload_hash: str,
    previous_event_hash: str,
) -> str:
    return _sha(
        _canonical(
            {
                **_identity_payload(identity),
                "sequence": sequence,
                "generation": generation,
                "receipt_type": receipt_type,
                "receipt_fingerprint": receipt_fingerprint,
                "payload_hash": payload_hash,
                "previous_event_hash": previous_event_hash,
            }
        )
    )


class PostgresEpistemicRolloutRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _params(identity: EpistemicRolloutIdentity) -> dict[str, object]:
        return {
            "tenant_id": identity.tenant_id,
            "company_id": identity.company_id,
            "problem_class": identity.problem_class,
            "rollout_id": identity.rollout_id,
        }

    async def activate(
        self,
        *,
        identity: EpistemicRolloutIdentity,
        generation: int,
        candidate_fingerprint: str,
        baseline_fingerprint: str,
        baseline_profile_fingerprint: str,
        activation_fingerprint: str,
        snapshot_fingerprint: str,
        snapshot_payload: dict[str, Any] | str,
        receipt_payload: dict[str, Any] | str,
        occurred_at: datetime,
    ) -> tuple[EpistemicRolloutRecord, EpistemicReceiptRecord, bool]:
        snapshot_json = _canonical(snapshot_payload)
        receipt_json = _canonical(receipt_payload)
        _validate_snapshot(identity, generation, "active", snapshot_fingerprint, snapshot_json)
        _validate_receipt(
            identity,
            generation,
            "activation",
            activation_fingerprint,
            receipt_json,
        )
        inserted = await self.session.execute(
            text(
                """
                INSERT INTO jarvis_epistemic_rollouts (
                    tenant_id, company_id, problem_class, rollout_id,
                    generation, state, version, candidate_fingerprint,
                    baseline_fingerprint, baseline_profile_fingerprint,
                    selected_profile_fingerprint, activation_fingerprint,
                    snapshot_fingerprint, snapshot_payload_json, snapshot_payload_hash,
                    created_at, updated_at
                ) VALUES (
                    :tenant_id, :company_id, :problem_class, :rollout_id,
                    :generation, 'active', 0, :candidate, :baseline, :baseline_profile,
                    :candidate, :activation, :snapshot, :snapshot_json, :snapshot_hash,
                    :occurred_at, :occurred_at
                )
                ON CONFLICT (tenant_id, company_id, problem_class, rollout_id) DO NOTHING
                RETURNING *
                """
            ),
            {
                **self._params(identity),
                "generation": generation,
                "candidate": candidate_fingerprint,
                "baseline": baseline_fingerprint,
                "baseline_profile": baseline_profile_fingerprint,
                "activation": activation_fingerprint,
                "snapshot": snapshot_fingerprint,
                "snapshot_json": snapshot_json,
                "snapshot_hash": _sha(snapshot_json),
                "occurred_at": occurred_at,
            },
        )
        if inserted.mappings().first() is None:
            current = await self._lock(identity)
            receipts = await self.list_receipts(identity=identity)
            match = next(
                (item for item in receipts if item.receipt_fingerprint == activation_fingerprint),
                None,
            )
            if (
                current is None
                or current.generation != generation
                or current.state != "active"
                or current.activation_fingerprint != activation_fingerprint
                or current.snapshot_fingerprint != snapshot_fingerprint
                or current.snapshot_payload_hash != _sha(snapshot_json)
                or match is None
                or match.receipt_type != "activation"
                or match.payload_hash != _sha(receipt_json)
            ):
                raise ValueError("epistemic_activation_replay_conflict")
            return current, match, False
        current, receipt, _ = await self.append_receipt(
            identity=identity,
            generation=generation,
            expected_version=0,
            receipt_type="activation",
            receipt_fingerprint=activation_fingerprint,
            receipt_payload=receipt_json,
            occurred_at=occurred_at,
            _allow_activation=True,
        )
        return current, receipt, True

    async def get(
        self,
        *,
        identity: EpistemicRolloutIdentity,
    ) -> EpistemicRolloutRecord | None:
        result = await self.session.execute(
            text(
                """
                SELECT * FROM jarvis_epistemic_rollouts
                WHERE tenant_id = :tenant_id
                  AND company_id = :company_id
                  AND problem_class = :problem_class
                  AND rollout_id = :rollout_id
                """
            ),
            self._params(identity),
        )
        row = result.mappings().first()
        return self._rollout(row) if row else None

    async def append_receipt(
        self,
        *,
        identity: EpistemicRolloutIdentity,
        generation: int,
        expected_version: int,
        receipt_type: str,
        receipt_fingerprint: str,
        receipt_payload: dict[str, Any] | str,
        occurred_at: datetime,
        idempotency_key: str | None = None,
        _allow_activation: bool = False,
    ) -> tuple[EpistemicRolloutRecord, EpistemicReceiptRecord, bool]:
        allowed = ACTIVE_RECEIPTS | ({"activation"} if _allow_activation else set())
        if receipt_type not in allowed:
            raise ValueError("epistemic_receipt_type_not_appendable")
        current = await self._lock(identity)
        if current is None or current.state != "active":
            raise ValueError("epistemic_rollout_not_active")
        if current.generation != generation:
            raise ValueError("epistemic_rollout_generation_conflict")
        payload_json = _canonical(receipt_payload)
        _validate_receipt(
            identity,
            generation,
            receipt_type,
            receipt_fingerprint,
            payload_json,
        )
        history = await self.list_receipts(identity=identity)
        existing = next(
            (item for item in history if item.receipt_fingerprint == receipt_fingerprint),
            None,
        )
        if existing is not None:
            if (
                existing.generation != generation
                or existing.receipt_type != receipt_type
                or existing.payload_hash != _sha(payload_json)
                or existing.idempotency_key != idempotency_key
            ):
                raise ValueError("epistemic_receipt_replay_conflict")
            return current, existing, False
        if current.version != expected_version:
            raise ValueError("epistemic_rollout_version_conflict")
        receipt = await self._insert_receipt(
            current=current,
            generation=generation,
            receipt_type=receipt_type,
            receipt_fingerprint=receipt_fingerprint,
            payload_json=payload_json,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
        )
        updated = await self.session.execute(
            text(
                """
                UPDATE jarvis_epistemic_rollouts
                SET version = version + 1,
                    last_sequence = :sequence,
                    last_event_hash = :event_hash,
                    updated_at = :occurred_at
                WHERE tenant_id = :tenant_id
                  AND company_id = :company_id
                  AND problem_class = :problem_class
                  AND rollout_id = :rollout_id
                  AND generation = :generation
                  AND version = :expected_version
                RETURNING *
                """
            ),
            {
                **self._params(identity),
                "sequence": receipt.sequence,
                "event_hash": receipt.event_hash,
                "occurred_at": occurred_at,
                "generation": generation,
                "expected_version": expected_version,
            },
        )
        row = updated.mappings().first()
        if row is None:
            raise RuntimeError("epistemic_receipt_compare_and_swap_conflict")
        return self._rollout(row), receipt, True

    async def apply_rollback(
        self,
        *,
        identity: EpistemicRolloutIdentity,
        source_generation: int,
        resulting_generation: int,
        expected_version: int,
        activation_fingerprint: str,
        baseline_fingerprint: str,
        baseline_profile_fingerprint: str,
        rollback_fingerprint: str,
        snapshot_fingerprint: str,
        snapshot_payload: dict[str, Any] | str,
        idempotency_key: str,
        receipt_payload: dict[str, Any] | str,
        occurred_at: datetime,
    ) -> tuple[EpistemicRolloutRecord, EpistemicReceiptRecord, bool]:
        if resulting_generation != source_generation + 1:
            raise ValueError("epistemic_rollback_generation_must_increment_once")
        current = await self._lock(identity)
        if current is None:
            raise ValueError("epistemic_rollout_not_found")
        snapshot_json = _canonical(snapshot_payload)
        payload_json = _canonical(receipt_payload)
        _validate_snapshot(
            identity,
            resulting_generation,
            "rolled_back",
            snapshot_fingerprint,
            snapshot_json,
        )
        _validate_receipt(
            identity,
            resulting_generation,
            "rollback",
            rollback_fingerprint,
            payload_json,
        )
        history = await self.list_receipts(identity=identity)
        existing = next(
            (item for item in history if item.receipt_fingerprint == rollback_fingerprint),
            None,
        )
        if current.state == "rolled_back":
            if (
                current.generation != resulting_generation
                or current.rollback_fingerprint != rollback_fingerprint
                or current.snapshot_fingerprint != snapshot_fingerprint
                or current.snapshot_payload_hash != _sha(snapshot_json)
                or existing is None
                or existing.payload_hash != _sha(payload_json)
                or existing.idempotency_key != idempotency_key
            ):
                raise ValueError("epistemic_rollback_replay_conflict")
            return current, existing, False
        if current.generation != source_generation or current.version != expected_version:
            raise ValueError("epistemic_rollback_fence_conflict")
        if (
            current.activation_fingerprint != activation_fingerprint
            or current.baseline_fingerprint != baseline_fingerprint
            or current.baseline_profile_fingerprint != baseline_profile_fingerprint
        ):
            raise ValueError("epistemic_rollback_baseline_binding_conflict")
        receipt = await self._insert_receipt(
            current=current,
            generation=resulting_generation,
            receipt_type="rollback",
            receipt_fingerprint=rollback_fingerprint,
            payload_json=payload_json,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
        )
        updated = await self.session.execute(
            text(
                """
                UPDATE jarvis_epistemic_rollouts
                SET generation = :resulting_generation,
                    state = 'rolled_back',
                    version = version + 1,
                    selected_profile_fingerprint = :baseline_profile,
                    rollback_fingerprint = :rollback,
                    snapshot_fingerprint = :snapshot,
                    snapshot_payload_json = :snapshot_json,
                    snapshot_payload_hash = :snapshot_hash,
                    last_sequence = :sequence,
                    last_event_hash = :event_hash,
                    updated_at = :occurred_at
                WHERE tenant_id = :tenant_id
                  AND company_id = :company_id
                  AND problem_class = :problem_class
                  AND rollout_id = :rollout_id
                  AND generation = :source_generation
                  AND version = :expected_version
                RETURNING *
                """
            ),
            {
                **self._params(identity),
                "resulting_generation": resulting_generation,
                "baseline_profile": baseline_profile_fingerprint,
                "rollback": rollback_fingerprint,
                "snapshot": snapshot_fingerprint,
                "snapshot_json": snapshot_json,
                "snapshot_hash": _sha(snapshot_json),
                "sequence": receipt.sequence,
                "event_hash": receipt.event_hash,
                "occurred_at": occurred_at,
                "source_generation": source_generation,
                "expected_version": expected_version,
            },
        )
        row = updated.mappings().first()
        if row is None:
            raise RuntimeError("epistemic_rollback_compare_and_swap_conflict")
        return self._rollout(row), receipt, True

    async def list_receipts(
        self,
        *,
        identity: EpistemicRolloutIdentity,
        after_sequence: int = 0,
        limit: int = 1000,
    ) -> tuple[EpistemicReceiptRecord, ...]:
        result = await self.session.execute(
            text(
                """
                SELECT * FROM jarvis_epistemic_rollout_receipts
                WHERE tenant_id = :tenant_id
                  AND company_id = :company_id
                  AND problem_class = :problem_class
                  AND rollout_id = :rollout_id
                  AND sequence > :after_sequence
                ORDER BY sequence ASC
                LIMIT :limit
                """
            ),
            {
                **self._params(identity),
                "after_sequence": after_sequence,
                "limit": limit,
            },
        )
        return tuple(self._receipt(row) for row in result.mappings().all())

    async def health_history(
        self,
        *,
        identity: EpistemicRolloutIdentity,
        generation: int,
    ) -> tuple[EpistemicReceiptRecord, ...]:
        return tuple(
            item
            for item in await self.list_receipts(identity=identity)
            if item.generation == generation
            and item.receipt_type in {"health_observation", "health_verdict"}
        )

    async def promotion_history(
        self,
        *,
        identity: EpistemicRolloutIdentity,
        generation: int,
    ) -> tuple[EpistemicReceiptRecord, ...]:
        types = {"promotion_evidence", "promotion_approval", "promotion_review"}
        return tuple(
            item
            for item in await self.list_receipts(identity=identity)
            if item.generation == generation and item.receipt_type in types
        )

    async def verify_journal(self, *, identity: EpistemicRolloutIdentity) -> bool:
        history = await self.list_receipts(identity=identity)
        previous = GENESIS_HASH
        for sequence, item in enumerate(history, start=1):
            if item.sequence != sequence or item.previous_event_hash != previous:
                raise ValueError("epistemic_journal_chain_mismatch")
            item.verified_payload()
            expected = _event_hash(
                identity,
                sequence=item.sequence,
                generation=item.generation,
                receipt_type=item.receipt_type,
                receipt_fingerprint=item.receipt_fingerprint,
                payload_hash=item.payload_hash,
                previous_event_hash=item.previous_event_hash,
            )
            if item.event_hash != expected:
                raise ValueError("epistemic_journal_event_hash_mismatch")
            previous = item.event_hash
        current = await self.get(identity=identity)
        if current is None:
            return not history
        if current.last_sequence != len(history) or current.last_event_hash != previous:
            raise ValueError("epistemic_journal_head_mismatch")
        return True

    async def _lock(
        self,
        identity: EpistemicRolloutIdentity,
    ) -> EpistemicRolloutRecord | None:
        result = await self.session.execute(
            text(
                """
                SELECT * FROM jarvis_epistemic_rollouts
                WHERE tenant_id = :tenant_id
                  AND company_id = :company_id
                  AND problem_class = :problem_class
                  AND rollout_id = :rollout_id
                FOR UPDATE
                """
            ),
            self._params(identity),
        )
        row = result.mappings().first()
        return self._rollout(row) if row else None

    async def _insert_receipt(
        self,
        *,
        current: EpistemicRolloutRecord,
        generation: int,
        receipt_type: str,
        receipt_fingerprint: str,
        payload_json: str,
        idempotency_key: str | None,
        occurred_at: datetime,
    ) -> EpistemicReceiptRecord:
        payload_hash = _sha(payload_json)
        sequence = current.last_sequence + 1
        event_hash = _event_hash(
            current.identity,
            sequence=sequence,
            generation=generation,
            receipt_type=receipt_type,
            receipt_fingerprint=receipt_fingerprint,
            payload_hash=payload_hash,
            previous_event_hash=current.last_event_hash,
        )
        result = await self.session.execute(
            text(
                """
                INSERT INTO jarvis_epistemic_rollout_receipts (
                    tenant_id, company_id, problem_class, rollout_id,
                    sequence, generation, receipt_type, receipt_fingerprint,
                    payload_json, payload_hash, idempotency_key,
                    previous_event_hash, event_hash, occurred_at
                ) VALUES (
                    :tenant_id, :company_id, :problem_class, :rollout_id,
                    :sequence, :generation, :receipt_type, :receipt_fingerprint,
                    :payload_json, :payload_hash, :idempotency_key,
                    :previous_event_hash, :event_hash, :occurred_at
                )
                RETURNING *
                """
            ),
            {
                **self._params(current.identity),
                "sequence": sequence,
                "generation": generation,
                "receipt_type": receipt_type,
                "receipt_fingerprint": receipt_fingerprint,
                "payload_json": payload_json,
                "payload_hash": payload_hash,
                "idempotency_key": idempotency_key,
                "previous_event_hash": current.last_event_hash,
                "event_hash": event_hash,
                "occurred_at": occurred_at,
            },
        )
        return self._receipt(result.mappings().one())

    @staticmethod
    def _rollout(row: Any) -> EpistemicRolloutRecord:
        return EpistemicRolloutRecord(
            identity=EpistemicRolloutIdentity(
                row["tenant_id"],
                row["company_id"],
                row["problem_class"],
                row["rollout_id"],
            ),
            generation=row["generation"],
            state=row["state"],
            version=row["version"],
            candidate_fingerprint=row["candidate_fingerprint"],
            baseline_fingerprint=row["baseline_fingerprint"],
            baseline_profile_fingerprint=row["baseline_profile_fingerprint"],
            selected_profile_fingerprint=row["selected_profile_fingerprint"],
            activation_fingerprint=row["activation_fingerprint"],
            rollback_fingerprint=row["rollback_fingerprint"],
            snapshot_fingerprint=row["snapshot_fingerprint"],
            snapshot_payload_json=row["snapshot_payload_json"],
            snapshot_payload_hash=row["snapshot_payload_hash"],
            last_sequence=row["last_sequence"],
            last_event_hash=row["last_event_hash"],
        )

    @staticmethod
    def _receipt(row: Any) -> EpistemicReceiptRecord:
        return EpistemicReceiptRecord(
            sequence=row["sequence"],
            generation=row["generation"],
            receipt_type=row["receipt_type"],
            receipt_fingerprint=row["receipt_fingerprint"],
            payload_json=row["payload_json"],
            payload_hash=row["payload_hash"],
            idempotency_key=row["idempotency_key"],
            previous_event_hash=row["previous_event_hash"],
            event_hash=row["event_hash"],
        )
