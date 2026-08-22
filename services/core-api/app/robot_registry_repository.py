"""Restart-safe PostgreSQL registry for approved Jarvis robot versions.

The registry is deliberately not an approval or execution authority. It stores
already-approved immutable robot artifacts, maintains a generation-fenced active
version pointer, and records append-only hash-chained registration/activation/
rollback receipts. Mission execution remains the only side-effect authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

GENESIS_HASH = "0" * 64
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
ROBOT_KINDS = frozenset({"api", "playwright", "hybrid"})
RECEIPT_TYPES = frozenset({"register_version", "activate_version", "rollback_version"})


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value: dict[str, Any] | str) -> str:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("robot_registry_payload_must_be_object")
    return json.dumps(
        parsed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )


def _require_hash(value: str, code: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ValueError(code)


@dataclass(frozen=True)
class RobotRegistryIdentity:
    tenant_id: UUID
    company_id: str
    objective_id: str
    robot_id: str


@dataclass(frozen=True)
class RobotRegistryRecord:
    identity: RobotRegistryIdentity
    state: str
    active_version: int | None
    active_version_fingerprint: str | None
    generation: int
    revision: int
    last_sequence: int
    last_event_hash: str


@dataclass(frozen=True)
class RobotVersionRecord:
    identity: RobotRegistryIdentity
    robot_version: int
    parent_version: int | None
    parent_version_fingerprint: str | None
    kind: str
    semantic_intent: str
    capability_ref: str
    manifest_json: str
    manifest_hash: str
    expected_outcome_fingerprint: str
    source_robot_fingerprint: str
    candidate_fingerprint: str
    registry_candidate_fingerprint: str
    approval_evidence_ref: str
    version_fingerprint: str
    registered_at: datetime

    def verified_manifest(self) -> dict[str, Any]:
        if _sha(self.manifest_json) != self.manifest_hash:
            raise ValueError("robot_registry_manifest_hash_mismatch")
        parsed = json.loads(self.manifest_json)
        if not isinstance(parsed, dict):
            raise ValueError("robot_registry_manifest_must_be_object")
        if robot_version_fingerprint(
            identity=self.identity,
            robot_version=self.robot_version,
            parent_version=self.parent_version,
            parent_version_fingerprint=self.parent_version_fingerprint,
            kind=self.kind,
            semantic_intent=self.semantic_intent,
            capability_ref=self.capability_ref,
            manifest=parsed,
            expected_outcome_fingerprint=self.expected_outcome_fingerprint,
            source_robot_fingerprint=self.source_robot_fingerprint,
            candidate_fingerprint=self.candidate_fingerprint,
            registry_candidate_fingerprint=self.registry_candidate_fingerprint,
            approval_evidence_ref=self.approval_evidence_ref,
        ) != self.version_fingerprint:
            raise ValueError("robot_registry_version_fingerprint_mismatch")
        return parsed


@dataclass(frozen=True)
class RobotRegistryReceiptRecord:
    sequence: int
    generation: int
    receipt_type: str
    robot_version: int
    receipt_fingerprint: str
    payload_json: str
    payload_hash: str
    idempotency_key: str | None
    previous_event_hash: str
    event_hash: str
    occurred_at: datetime

    def verified_payload(self) -> dict[str, Any]:
        if _sha(self.payload_json) != self.payload_hash:
            raise ValueError("robot_registry_receipt_payload_hash_mismatch")
        parsed = json.loads(self.payload_json)
        if not isinstance(parsed, dict):
            raise ValueError("robot_registry_receipt_payload_must_be_object")
        return parsed


def _identity_payload(identity: RobotRegistryIdentity) -> dict[str, str]:
    return {
        "tenant_id": str(identity.tenant_id),
        "company_id": identity.company_id,
        "objective_id": identity.objective_id,
        "robot_id": identity.robot_id,
    }


def robot_version_fingerprint(
    *,
    identity: RobotRegistryIdentity,
    robot_version: int,
    parent_version: int | None,
    parent_version_fingerprint: str | None,
    kind: str,
    semantic_intent: str,
    capability_ref: str,
    manifest: dict[str, Any],
    expected_outcome_fingerprint: str,
    source_robot_fingerprint: str,
    candidate_fingerprint: str,
    registry_candidate_fingerprint: str,
    approval_evidence_ref: str,
) -> str:
    return _sha(
        _canonical(
            {
                **_identity_payload(identity),
                "robot_version": robot_version,
                "parent_version": parent_version,
                "parent_version_fingerprint": parent_version_fingerprint,
                "kind": kind,
                "semantic_intent": semantic_intent,
                "capability_ref": capability_ref,
                "manifest": manifest,
                "expected_outcome_fingerprint": expected_outcome_fingerprint,
                "source_robot_fingerprint": source_robot_fingerprint,
                "candidate_fingerprint": candidate_fingerprint,
                "registry_candidate_fingerprint": registry_candidate_fingerprint,
                "approval_evidence_ref": approval_evidence_ref,
            }
        )
    )


def _event_hash(
    identity: RobotRegistryIdentity,
    *,
    sequence: int,
    generation: int,
    receipt_type: str,
    robot_version: int,
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
                "robot_version": robot_version,
                "receipt_fingerprint": receipt_fingerprint,
                "payload_hash": payload_hash,
                "previous_event_hash": previous_event_hash,
            }
        )
    )


class PostgresRobotRegistryRepository:
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

    async def register_version(
        self,
        *,
        identity: RobotRegistryIdentity,
        robot_version: int,
        parent_version: int | None,
        parent_version_fingerprint: str | None,
        kind: str,
        semantic_intent: str,
        capability_ref: str,
        manifest: dict[str, Any] | str,
        expected_outcome_fingerprint: str,
        source_robot_fingerprint: str,
        candidate_fingerprint: str,
        registry_candidate_fingerprint: str,
        approval_evidence_ref: str,
        occurred_at: datetime,
        idempotency_key: str | None = None,
    ) -> tuple[RobotVersionRecord, RobotRegistryReceiptRecord, bool]:
        self._validate_version_inputs(
            robot_version=robot_version,
            parent_version=parent_version,
            parent_version_fingerprint=parent_version_fingerprint,
            kind=kind,
            semantic_intent=semantic_intent,
            capability_ref=capability_ref,
            expected_outcome_fingerprint=expected_outcome_fingerprint,
            source_robot_fingerprint=source_robot_fingerprint,
            candidate_fingerprint=candidate_fingerprint,
            registry_candidate_fingerprint=registry_candidate_fingerprint,
            approval_evidence_ref=approval_evidence_ref,
        )
        manifest_json = _canonical(manifest)
        manifest_obj = json.loads(manifest_json)
        version_fingerprint = robot_version_fingerprint(
            identity=identity,
            robot_version=robot_version,
            parent_version=parent_version,
            parent_version_fingerprint=parent_version_fingerprint,
            kind=kind,
            semantic_intent=semantic_intent,
            capability_ref=capability_ref,
            manifest=manifest_obj,
            expected_outcome_fingerprint=expected_outcome_fingerprint,
            source_robot_fingerprint=source_robot_fingerprint,
            candidate_fingerprint=candidate_fingerprint,
            registry_candidate_fingerprint=registry_candidate_fingerprint,
            approval_evidence_ref=approval_evidence_ref,
        )

        await self.session.execute(
            text(
                """
                INSERT INTO jarvis_robot_registries (
                    tenant_id, company_id, objective_id, robot_id,
                    state, generation, revision, last_sequence,
                    created_at, updated_at
                ) VALUES (
                    :tenant_id, :company_id, :objective_id, :robot_id,
                    'registered', 0, 0, 0, :occurred_at, :occurred_at
                )
                ON CONFLICT (tenant_id, company_id, objective_id, robot_id) DO NOTHING
                """
            ),
            {**self._params(identity), "occurred_at": occurred_at},
        )
        registry = await self._lock(identity)
        if registry is None:
            raise RuntimeError("robot_registry_row_missing_after_create")

        existing = await self.get_version(identity=identity, robot_version=robot_version)
        if existing is not None:
            existing.verified_manifest()
            if existing.version_fingerprint != version_fingerprint:
                raise ValueError("robot_registry_conflicting_version_replay")
            receipt = await self._registration_receipt_for_version(
                identity=identity,
                robot_version=robot_version,
            )
            if receipt is None:
                raise RuntimeError("robot_registry_registration_receipt_missing")
            return existing, receipt, False

        latest = await self._latest_version(identity)
        if latest is None:
            if parent_version is not None or parent_version_fingerprint is not None:
                raise ValueError("robot_registry_bootstrap_version_cannot_claim_parent")
        else:
            if robot_version != latest.robot_version + 1:
                raise ValueError("robot_registry_version_must_increment_exactly_once")
            if parent_version != latest.robot_version:
                raise ValueError("robot_registry_parent_version_mismatch")
            if parent_version_fingerprint != latest.version_fingerprint:
                raise ValueError("robot_registry_parent_fingerprint_mismatch")

        await self.session.execute(
            text(
                """
                INSERT INTO jarvis_robot_versions (
                    tenant_id, company_id, objective_id, robot_id,
                    robot_version, parent_version, parent_version_fingerprint,
                    kind, semantic_intent, capability_ref,
                    manifest_json, manifest_hash,
                    expected_outcome_fingerprint, source_robot_fingerprint,
                    candidate_fingerprint, registry_candidate_fingerprint,
                    approval_evidence_ref, version_fingerprint, registered_at
                ) VALUES (
                    :tenant_id, :company_id, :objective_id, :robot_id,
                    :robot_version, :parent_version, :parent_version_fingerprint,
                    :kind, :semantic_intent, :capability_ref,
                    :manifest_json, :manifest_hash,
                    :expected_outcome_fingerprint, :source_robot_fingerprint,
                    :candidate_fingerprint, :registry_candidate_fingerprint,
                    :approval_evidence_ref, :version_fingerprint, :registered_at
                )
                """
            ),
            {
                **self._params(identity),
                "robot_version": robot_version,
                "parent_version": parent_version,
                "parent_version_fingerprint": parent_version_fingerprint,
                "kind": kind,
                "semantic_intent": semantic_intent,
                "capability_ref": capability_ref,
                "manifest_json": manifest_json,
                "manifest_hash": _sha(manifest_json),
                "expected_outcome_fingerprint": expected_outcome_fingerprint,
                "source_robot_fingerprint": source_robot_fingerprint,
                "candidate_fingerprint": candidate_fingerprint,
                "registry_candidate_fingerprint": registry_candidate_fingerprint,
                "approval_evidence_ref": approval_evidence_ref,
                "version_fingerprint": version_fingerprint,
                "registered_at": occurred_at,
            },
        )
        payload = {
            "identity": _identity_payload(identity),
            "robot_version": robot_version,
            "version_fingerprint": version_fingerprint,
            "approval_evidence_ref": approval_evidence_ref,
        }
        receipt_fingerprint = _sha(
            _canonical(
                {
                    "receipt_type": "register_version",
                    "robot_version": robot_version,
                    "version_fingerprint": version_fingerprint,
                }
            )
        )
        receipt = await self._append_receipt_locked(
            registry=registry,
            receipt_type="register_version",
            robot_version=robot_version,
            generation=registry.generation,
            receipt_fingerprint=receipt_fingerprint,
            payload=payload,
            occurred_at=occurred_at,
            idempotency_key=idempotency_key,
        )
        version = await self.get_version(identity=identity, robot_version=robot_version)
        if version is None:
            raise RuntimeError("robot_registry_version_missing_after_insert")
        return version, receipt, True

    async def activate_version(
        self,
        *,
        identity: RobotRegistryIdentity,
        robot_version: int,
        expected_generation: int,
        activation_evidence_ref: str,
        occurred_at: datetime,
        idempotency_key: str | None = None,
    ) -> tuple[RobotRegistryRecord, RobotRegistryReceiptRecord, bool]:
        if not activation_evidence_ref.strip():
            raise ValueError("robot_registry_activation_requires_evidence")
        registry = await self._lock(identity)
        if registry is None:
            raise ValueError("robot_registry_not_found")
        target = await self.get_version(identity=identity, robot_version=robot_version)
        if target is None:
            raise ValueError("robot_registry_activation_version_not_found")
        target.verified_manifest()
        if registry.generation != expected_generation:
            raise ValueError("robot_registry_stale_generation")
        if (
            registry.state == "active"
            and registry.active_version == robot_version
            and registry.active_version_fingerprint == target.version_fingerprint
        ):
            receipt = await self._latest_selection_receipt(
                identity=identity,
                robot_version=robot_version,
            )
            if receipt is None:
                raise RuntimeError("robot_registry_activation_receipt_missing")
            return registry, receipt, False

        resulting_generation = registry.generation + 1
        payload = {
            "identity": _identity_payload(identity),
            "robot_version": robot_version,
            "version_fingerprint": target.version_fingerprint,
            "resulting_generation": resulting_generation,
            "activation_evidence_ref": activation_evidence_ref,
        }
        receipt_fingerprint = _sha(
            _canonical(
                {
                    "receipt_type": "activate_version",
                    **payload,
                }
            )
        )
        updated = await self.session.execute(
            text(
                """
                UPDATE jarvis_robot_registries
                SET state = 'active', active_version = :robot_version,
                    active_version_fingerprint = :version_fingerprint,
                    generation = :resulting_generation,
                    updated_at = :occurred_at
                WHERE tenant_id = :tenant_id AND company_id = :company_id
                  AND objective_id = :objective_id AND robot_id = :robot_id
                  AND generation = :expected_generation
                RETURNING *
                """
            ),
            {
                **self._params(identity),
                "robot_version": robot_version,
                "version_fingerprint": target.version_fingerprint,
                "resulting_generation": resulting_generation,
                "expected_generation": expected_generation,
                "occurred_at": occurred_at,
            },
        )
        row = updated.mappings().first()
        if row is None:
            raise ValueError("robot_registry_stale_generation")
        updated_registry = self._registry_from_row(row)
        receipt = await self._append_receipt_locked(
            registry=updated_registry,
            receipt_type="activate_version",
            robot_version=robot_version,
            generation=resulting_generation,
            receipt_fingerprint=receipt_fingerprint,
            payload=payload,
            occurred_at=occurred_at,
            idempotency_key=idempotency_key,
        )
        result = await self.get(identity=identity)
        if result is None:
            raise RuntimeError("robot_registry_missing_after_activation")
        return result, receipt, True

    async def rollback_version(
        self,
        *,
        identity: RobotRegistryIdentity,
        target_version: int,
        expected_generation: int,
        rollback_evidence_ref: str,
        occurred_at: datetime,
        idempotency_key: str | None = None,
    ) -> tuple[RobotRegistryRecord, RobotRegistryReceiptRecord]:
        if not rollback_evidence_ref.strip():
            raise ValueError("robot_registry_rollback_requires_evidence")
        registry = await self._lock(identity)
        if registry is None or registry.state != "active" or registry.active_version is None:
            raise ValueError("robot_registry_rollback_requires_active_version")
        if registry.generation != expected_generation:
            raise ValueError("robot_registry_stale_generation")
        if target_version >= registry.active_version:
            raise ValueError("robot_registry_rollback_must_target_older_version")
        target = await self.get_version(identity=identity, robot_version=target_version)
        if target is None:
            raise ValueError("robot_registry_rollback_version_not_found")
        target.verified_manifest()
        resulting_generation = registry.generation + 1
        payload = {
            "identity": _identity_payload(identity),
            "from_version": registry.active_version,
            "robot_version": target_version,
            "version_fingerprint": target.version_fingerprint,
            "resulting_generation": resulting_generation,
            "rollback_evidence_ref": rollback_evidence_ref,
        }
        receipt_fingerprint = _sha(
            _canonical(
                {
                    "receipt_type": "rollback_version",
                    **payload,
                }
            )
        )
        updated = await self.session.execute(
            text(
                """
                UPDATE jarvis_robot_registries
                SET active_version = :target_version,
                    active_version_fingerprint = :version_fingerprint,
                    generation = :resulting_generation,
                    updated_at = :occurred_at
                WHERE tenant_id = :tenant_id AND company_id = :company_id
                  AND objective_id = :objective_id AND robot_id = :robot_id
                  AND generation = :expected_generation AND state = 'active'
                  AND active_version = :from_version
                RETURNING *
                """
            ),
            {
                **self._params(identity),
                "target_version": target_version,
                "version_fingerprint": target.version_fingerprint,
                "resulting_generation": resulting_generation,
                "expected_generation": expected_generation,
                "from_version": registry.active_version,
                "occurred_at": occurred_at,
            },
        )
        row = updated.mappings().first()
        if row is None:
            raise ValueError("robot_registry_stale_generation")
        updated_registry = self._registry_from_row(row)
        receipt = await self._append_receipt_locked(
            registry=updated_registry,
            receipt_type="rollback_version",
            robot_version=target_version,
            generation=resulting_generation,
            receipt_fingerprint=receipt_fingerprint,
            payload=payload,
            occurred_at=occurred_at,
            idempotency_key=idempotency_key,
        )
        result = await self.get(identity=identity)
        if result is None:
            raise RuntimeError("robot_registry_missing_after_rollback")
        return result, receipt

    async def get_active(
        self,
        *,
        identity: RobotRegistryIdentity,
    ) -> tuple[RobotRegistryRecord, RobotVersionRecord] | None:
        registry = await self.get(identity=identity)
        if registry is None or registry.state != "active" or registry.active_version is None:
            return None
        version = await self.get_version(
            identity=identity,
            robot_version=registry.active_version,
        )
        if version is None:
            raise RuntimeError("robot_registry_active_version_missing")
        version.verified_manifest()
        if registry.active_version_fingerprint != version.version_fingerprint:
            raise ValueError("robot_registry_active_fingerprint_mismatch")
        return registry, version

    async def get(self, *, identity: RobotRegistryIdentity) -> RobotRegistryRecord | None:
        result = await self.session.execute(
            text(
                """
                SELECT * FROM jarvis_robot_registries
                WHERE tenant_id = :tenant_id AND company_id = :company_id
                  AND objective_id = :objective_id AND robot_id = :robot_id
                """
            ),
            self._params(identity),
        )
        row = result.mappings().first()
        return None if row is None else self._registry_from_row(row)

    async def get_version(
        self,
        *,
        identity: RobotRegistryIdentity,
        robot_version: int,
    ) -> RobotVersionRecord | None:
        result = await self.session.execute(
            text(
                """
                SELECT * FROM jarvis_robot_versions
                WHERE tenant_id = :tenant_id AND company_id = :company_id
                  AND objective_id = :objective_id AND robot_id = :robot_id
                  AND robot_version = :robot_version
                """
            ),
            {**self._params(identity), "robot_version": robot_version},
        )
        row = result.mappings().first()
        return None if row is None else self._version_from_row(row)

    async def list_versions(
        self,
        *,
        identity: RobotRegistryIdentity,
    ) -> tuple[RobotVersionRecord, ...]:
        result = await self.session.execute(
            text(
                """
                SELECT * FROM jarvis_robot_versions
                WHERE tenant_id = :tenant_id AND company_id = :company_id
                  AND objective_id = :objective_id AND robot_id = :robot_id
                ORDER BY robot_version
                """
            ),
            self._params(identity),
        )
        return tuple(self._version_from_row(row) for row in result.mappings().all())

    async def list_receipts(
        self,
        *,
        identity: RobotRegistryIdentity,
    ) -> tuple[RobotRegistryReceiptRecord, ...]:
        result = await self.session.execute(
            text(
                """
                SELECT * FROM jarvis_robot_registry_receipts
                WHERE tenant_id = :tenant_id AND company_id = :company_id
                  AND objective_id = :objective_id AND robot_id = :robot_id
                ORDER BY sequence
                """
            ),
            self._params(identity),
        )
        return tuple(self._receipt_from_row(row) for row in result.mappings().all())

    async def verify_journal(self, *, identity: RobotRegistryIdentity) -> bool:
        previous = GENESIS_HASH
        expected_sequence = 1
        for receipt in await self.list_receipts(identity=identity):
            receipt.verified_payload()
            if receipt.sequence != expected_sequence or receipt.previous_event_hash != previous:
                return False
            expected = _event_hash(
                identity,
                sequence=receipt.sequence,
                generation=receipt.generation,
                receipt_type=receipt.receipt_type,
                robot_version=receipt.robot_version,
                receipt_fingerprint=receipt.receipt_fingerprint,
                payload_hash=receipt.payload_hash,
                previous_event_hash=previous,
            )
            if receipt.event_hash != expected:
                return False
            previous = receipt.event_hash
            expected_sequence += 1
        registry = await self.get(identity=identity)
        return registry is not None and (
            registry.last_sequence == expected_sequence - 1
            and registry.last_event_hash == previous
        )

    async def _latest_version(
        self,
        identity: RobotRegistryIdentity,
    ) -> RobotVersionRecord | None:
        result = await self.session.execute(
            text(
                """
                SELECT * FROM jarvis_robot_versions
                WHERE tenant_id = :tenant_id AND company_id = :company_id
                  AND objective_id = :objective_id AND robot_id = :robot_id
                ORDER BY robot_version DESC LIMIT 1
                """
            ),
            self._params(identity),
        )
        row = result.mappings().first()
        return None if row is None else self._version_from_row(row)

    async def _lock(self, identity: RobotRegistryIdentity) -> RobotRegistryRecord | None:
        result = await self.session.execute(
            text(
                """
                SELECT * FROM jarvis_robot_registries
                WHERE tenant_id = :tenant_id AND company_id = :company_id
                  AND objective_id = :objective_id AND robot_id = :robot_id
                FOR UPDATE
                """
            ),
            self._params(identity),
        )
        row = result.mappings().first()
        return None if row is None else self._registry_from_row(row)

    async def _registration_receipt_for_version(
        self,
        *,
        identity: RobotRegistryIdentity,
        robot_version: int,
    ) -> RobotRegistryReceiptRecord | None:
        result = await self.session.execute(
            text(
                """
                SELECT * FROM jarvis_robot_registry_receipts
                WHERE tenant_id = :tenant_id AND company_id = :company_id
                  AND objective_id = :objective_id AND robot_id = :robot_id
                  AND receipt_type = 'register_version'
                  AND robot_version = :robot_version
                ORDER BY sequence LIMIT 1
                """
            ),
            {**self._params(identity), "robot_version": robot_version},
        )
        row = result.mappings().first()
        return None if row is None else self._receipt_from_row(row)

    async def _latest_selection_receipt(
        self,
        *,
        identity: RobotRegistryIdentity,
        robot_version: int,
    ) -> RobotRegistryReceiptRecord | None:
        result = await self.session.execute(
            text(
                """
                SELECT * FROM jarvis_robot_registry_receipts
                WHERE tenant_id = :tenant_id AND company_id = :company_id
                  AND objective_id = :objective_id AND robot_id = :robot_id
                  AND receipt_type IN ('activate_version', 'rollback_version')
                  AND robot_version = :robot_version
                ORDER BY sequence DESC LIMIT 1
                """
            ),
            {**self._params(identity), "robot_version": robot_version},
        )
        row = result.mappings().first()
        return None if row is None else self._receipt_from_row(row)

    async def _append_receipt_locked(
        self,
        *,
        registry: RobotRegistryRecord,
        receipt_type: str,
        robot_version: int,
        generation: int,
        receipt_fingerprint: str,
        payload: dict[str, Any] | str,
        occurred_at: datetime,
        idempotency_key: str | None,
    ) -> RobotRegistryReceiptRecord:
        if receipt_type not in RECEIPT_TYPES:
            raise ValueError("robot_registry_receipt_type_not_allowed")
        _require_hash(receipt_fingerprint, "robot_registry_receipt_fingerprint_invalid")
        payload_json = _canonical(payload)
        payload_hash = _sha(payload_json)
        sequence = registry.last_sequence + 1
        event_hash = _event_hash(
            registry.identity,
            sequence=sequence,
            generation=generation,
            receipt_type=receipt_type,
            robot_version=robot_version,
            receipt_fingerprint=receipt_fingerprint,
            payload_hash=payload_hash,
            previous_event_hash=registry.last_event_hash,
        )
        inserted = await self.session.execute(
            text(
                """
                INSERT INTO jarvis_robot_registry_receipts (
                    tenant_id, company_id, objective_id, robot_id,
                    sequence, generation, receipt_type, robot_version,
                    receipt_fingerprint, payload_json, payload_hash,
                    idempotency_key, previous_event_hash, event_hash, occurred_at
                ) VALUES (
                    :tenant_id, :company_id, :objective_id, :robot_id,
                    :sequence, :generation, :receipt_type, :robot_version,
                    :receipt_fingerprint, :payload_json, :payload_hash,
                    :idempotency_key, :previous_event_hash, :event_hash, :occurred_at
                )
                RETURNING *
                """
            ),
            {
                **self._params(registry.identity),
                "sequence": sequence,
                "generation": generation,
                "receipt_type": receipt_type,
                "robot_version": robot_version,
                "receipt_fingerprint": receipt_fingerprint,
                "payload_json": payload_json,
                "payload_hash": payload_hash,
                "idempotency_key": idempotency_key,
                "previous_event_hash": registry.last_event_hash,
                "event_hash": event_hash,
                "occurred_at": occurred_at,
            },
        )
        row = inserted.mappings().first()
        if row is None:
            raise RuntimeError("robot_registry_receipt_insert_failed")
        updated = await self.session.execute(
            text(
                """
                UPDATE jarvis_robot_registries
                SET revision = revision + 1,
                    last_sequence = :sequence,
                    last_event_hash = :event_hash,
                    updated_at = :occurred_at
                WHERE tenant_id = :tenant_id AND company_id = :company_id
                  AND objective_id = :objective_id AND robot_id = :robot_id
                  AND revision = :expected_revision
                  AND last_sequence = :expected_sequence
                  AND last_event_hash = :expected_event_hash
                RETURNING revision
                """
            ),
            {
                **self._params(registry.identity),
                "sequence": sequence,
                "event_hash": event_hash,
                "occurred_at": occurred_at,
                "expected_revision": registry.revision,
                "expected_sequence": registry.last_sequence,
                "expected_event_hash": registry.last_event_hash,
            },
        )
        if updated.first() is None:
            raise ValueError("robot_registry_stale_revision")
        return self._receipt_from_row(row)

    @staticmethod
    def _validate_version_inputs(
        *,
        robot_version: int,
        parent_version: int | None,
        parent_version_fingerprint: str | None,
        kind: str,
        semantic_intent: str,
        capability_ref: str,
        expected_outcome_fingerprint: str,
        source_robot_fingerprint: str,
        candidate_fingerprint: str,
        registry_candidate_fingerprint: str,
        approval_evidence_ref: str,
    ) -> None:
        if robot_version < 1:
            raise ValueError("robot_registry_version_must_be_positive")
        if kind not in ROBOT_KINDS:
            raise ValueError("robot_registry_kind_not_allowed")
        if not semantic_intent.strip() or not capability_ref.strip():
            raise ValueError("robot_registry_semantic_identity_required")
        if not approval_evidence_ref.strip():
            raise ValueError("robot_registry_approval_evidence_required")
        for value, code in (
            (expected_outcome_fingerprint, "robot_registry_outcome_fingerprint_invalid"),
            (source_robot_fingerprint, "robot_registry_source_fingerprint_invalid"),
            (candidate_fingerprint, "robot_registry_candidate_fingerprint_invalid"),
            (
                registry_candidate_fingerprint,
                "robot_registry_registry_candidate_fingerprint_invalid",
            ),
        ):
            _require_hash(value, code)
        if (parent_version is None) != (parent_version_fingerprint is None):
            raise ValueError("robot_registry_parent_fields_must_be_paired")
        if parent_version is not None:
            if parent_version < 1 or parent_version >= robot_version:
                raise ValueError("robot_registry_parent_version_invalid")
            _require_hash(
                parent_version_fingerprint or "",
                "robot_registry_parent_fingerprint_invalid",
            )

    @staticmethod
    def _registry_from_row(row: Any) -> RobotRegistryRecord:
        return RobotRegistryRecord(
            identity=RobotRegistryIdentity(
                tenant_id=row["tenant_id"],
                company_id=row["company_id"],
                objective_id=row["objective_id"],
                robot_id=row["robot_id"],
            ),
            state=row["state"],
            active_version=row["active_version"],
            active_version_fingerprint=row["active_version_fingerprint"],
            generation=row["generation"],
            revision=row["revision"],
            last_sequence=row["last_sequence"],
            last_event_hash=row["last_event_hash"],
        )

    @staticmethod
    def _version_from_row(row: Any) -> RobotVersionRecord:
        return RobotVersionRecord(
            identity=RobotRegistryIdentity(
                tenant_id=row["tenant_id"],
                company_id=row["company_id"],
                objective_id=row["objective_id"],
                robot_id=row["robot_id"],
            ),
            robot_version=row["robot_version"],
            parent_version=row["parent_version"],
            parent_version_fingerprint=row["parent_version_fingerprint"],
            kind=row["kind"],
            semantic_intent=row["semantic_intent"],
            capability_ref=row["capability_ref"],
            manifest_json=row["manifest_json"],
            manifest_hash=row["manifest_hash"],
            expected_outcome_fingerprint=row["expected_outcome_fingerprint"],
            source_robot_fingerprint=row["source_robot_fingerprint"],
            candidate_fingerprint=row["candidate_fingerprint"],
            registry_candidate_fingerprint=row["registry_candidate_fingerprint"],
            approval_evidence_ref=row["approval_evidence_ref"],
            version_fingerprint=row["version_fingerprint"],
            registered_at=row["registered_at"],
        )

    @staticmethod
    def _receipt_from_row(row: Any) -> RobotRegistryReceiptRecord:
        return RobotRegistryReceiptRecord(
            sequence=row["sequence"],
            generation=row["generation"],
            receipt_type=row["receipt_type"],
            robot_version=row["robot_version"],
            receipt_fingerprint=row["receipt_fingerprint"],
            payload_json=row["payload_json"],
            payload_hash=row["payload_hash"],
            idempotency_key=row["idempotency_key"],
            previous_event_hash=row["previous_event_hash"],
            event_hash=row["event_hash"],
            occurred_at=row["occurred_at"],
        )
