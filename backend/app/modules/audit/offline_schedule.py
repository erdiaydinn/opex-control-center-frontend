"""Roadmap 25/60: full offline scheduled Audit authority.

A published template is pinned into an immutable schedule occurrence. The mobile
package is device/assignee/version bound, queue bytes are AES-GCM encrypted at
rest, and online reconciliation is idempotent against the same occurrence.
Tenant authority is supplied separately by the trusted server principal; client
mutations do not carry tenant identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from typing import Any, Iterable, Mapping
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .template_authority import AuditTemplateRevision, AuditTemplateStatus


class OfflineAuditError(ValueError):
    """Raised when schedule/offline/sync authority is violated."""


@dataclass(frozen=True, slots=True)
class AuditSchedule:
    schedule_id: UUID
    tenant_id: str
    schedule_key: str
    template_key: str
    template_revision: int
    template_hash: str
    location_id: str
    assignee_subject: str
    window_start: datetime
    window_end: datetime
    created_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuditOccurrence:
    occurrence_id: UUID
    tenant_id: str
    schedule_id: UUID
    scheduled_for: datetime
    template_key: str
    template_revision: int
    template_hash: str
    location_id: str
    assignee_subject: str
    occurrence_hash: str


@dataclass(frozen=True, slots=True)
class OfflineAuditPackage:
    package_id: UUID
    tenant_id: str
    occurrence_id: UUID
    schedule_id: UUID
    template_key: str
    template_revision: int
    template_hash: str
    location_id: str
    assignee_subject: str
    device_id: str
    package_version: str
    client_schema_version: str
    policy_version: str
    issued_at: datetime
    expires_at: datetime
    package_hash: str


@dataclass(frozen=True, slots=True)
class OfflineAuditMutation:
    mutation_id: UUID
    occurrence_id: UUID
    package_hash: str
    device_id: str
    sequence: int
    nonce: str
    idempotency_key: str
    mutation_type: str
    payload: tuple[tuple[str, Any], ...]
    captured_at: datetime

    @property
    def payload_hash(self) -> str:
        return _sha({"mutation_type": self.mutation_type, "payload": list(self.payload)})


@dataclass(frozen=True, slots=True)
class EncryptedOfflineQueue:
    algorithm: str
    nonce_hex: str
    ciphertext_hex: str
    aad_hash: str
    mutation_count: int


@dataclass(frozen=True, slots=True)
class OfflineSyncLedger:
    occurrence_id: UUID
    audit_run_id: UUID
    accepted: tuple[tuple[str, str, str, int], ...] = ()
    # (idempotency_key, payload_hash, nonce, sequence)

    @property
    def highest_sequence(self) -> int:
        return max((row[3] for row in self.accepted), default=0)


@dataclass(frozen=True, slots=True)
class OfflineSyncReceipt:
    occurrence_id: UUID
    audit_run_id: UUID
    accepted_mutation_ids: tuple[UUID, ...]
    replayed_mutation_ids: tuple[UUID, ...]
    highest_sequence: int
    receipt_hash: str


def create_schedule(
    template: AuditTemplateRevision,
    *,
    schedule_key: str,
    location_id: str,
    assignee_subject: str,
    window_start: datetime,
    window_end: datetime,
    actor: str,
    created_at: datetime | None = None,
    schedule_id: UUID | None = None,
) -> AuditSchedule:
    if template.status is not AuditTemplateStatus.PUBLISHED:
        raise OfflineAuditError("scheduled audit requires an exact published template revision")
    values = [schedule_key.strip(), location_id.strip(), assignee_subject.strip(), actor.strip()]
    if not all(values):
        raise OfflineAuditError("schedule_key, location_id, assignee and actor are required")
    start, end = _utc(window_start), _utc(window_end)
    if end <= start:
        raise OfflineAuditError("schedule window_end must be after window_start")
    return AuditSchedule(
        schedule_id=schedule_id or uuid4(),
        tenant_id=template.tenant_id,
        schedule_key=values[0],
        template_key=template.template_key,
        template_revision=template.revision,
        template_hash=_hex64(template.content_hash, "template hash"),
        location_id=values[1],
        assignee_subject=values[2],
        window_start=start,
        window_end=end,
        created_by=values[3],
        created_at=_utc(created_at or datetime.now(UTC)),
    )


def materialize_occurrence(
    schedule: AuditSchedule,
    *,
    scheduled_for: datetime,
) -> AuditOccurrence:
    when = _utc(scheduled_for)
    if when < schedule.window_start or when > schedule.window_end:
        raise OfflineAuditError("occurrence must be inside its schedule window")
    occurrence_id = uuid5(
        NAMESPACE_URL,
        f"eay:audit-occurrence:{schedule.tenant_id}:{schedule.schedule_id}:{when.isoformat()}",
    )
    payload = {
        "tenant_id": schedule.tenant_id,
        "schedule_id": str(schedule.schedule_id),
        "occurrence_id": str(occurrence_id),
        "scheduled_for": when.isoformat(),
        "template_key": schedule.template_key,
        "template_revision": schedule.template_revision,
        "template_hash": schedule.template_hash,
        "location_id": schedule.location_id,
        "assignee_subject": schedule.assignee_subject,
    }
    return AuditOccurrence(
        occurrence_id=occurrence_id,
        tenant_id=schedule.tenant_id,
        schedule_id=schedule.schedule_id,
        scheduled_for=when,
        template_key=schedule.template_key,
        template_revision=schedule.template_revision,
        template_hash=schedule.template_hash,
        location_id=schedule.location_id,
        assignee_subject=schedule.assignee_subject,
        occurrence_hash=_sha(payload),
    )


def issue_offline_package(
    occurrence: AuditOccurrence,
    *,
    device_id: str,
    assignee_subject: str,
    package_version: str,
    client_schema_version: str,
    policy_version: str,
    issued_at: datetime,
    expires_at: datetime,
    package_id: UUID | None = None,
) -> OfflineAuditPackage:
    device_id = device_id.strip()
    assignee_subject = assignee_subject.strip()
    versions = [package_version.strip(), client_schema_version.strip(), policy_version.strip()]
    if not device_id or not assignee_subject or not all(versions):
        raise OfflineAuditError("device, assignee and offline package versions are required")
    if assignee_subject != occurrence.assignee_subject:
        raise OfflineAuditError("offline package assignee must match frozen schedule occurrence")
    issued, expires = _utc(issued_at), _utc(expires_at)
    if expires <= issued:
        raise OfflineAuditError("offline package expiry must be after issue time")
    pid = package_id or uuid4()
    payload = {
        "package_id": str(pid),
        "tenant_id": occurrence.tenant_id,
        "occurrence_id": str(occurrence.occurrence_id),
        "occurrence_hash": occurrence.occurrence_hash,
        "schedule_id": str(occurrence.schedule_id),
        "template_key": occurrence.template_key,
        "template_revision": occurrence.template_revision,
        "template_hash": occurrence.template_hash,
        "location_id": occurrence.location_id,
        "assignee_subject": assignee_subject,
        "device_id": device_id,
        "package_version": versions[0],
        "client_schema_version": versions[1],
        "policy_version": versions[2],
        "issued_at": issued.isoformat(),
        "expires_at": expires.isoformat(),
    }
    return OfflineAuditPackage(
        package_id=pid,
        tenant_id=occurrence.tenant_id,
        occurrence_id=occurrence.occurrence_id,
        schedule_id=occurrence.schedule_id,
        template_key=occurrence.template_key,
        template_revision=occurrence.template_revision,
        template_hash=occurrence.template_hash,
        location_id=occurrence.location_id,
        assignee_subject=assignee_subject,
        device_id=device_id,
        package_version=versions[0],
        client_schema_version=versions[1],
        policy_version=versions[2],
        issued_at=issued,
        expires_at=expires,
        package_hash=_sha(payload),
    )


def mutation(
    package: OfflineAuditPackage,
    *,
    sequence: int,
    nonce: str,
    idempotency_key: str,
    mutation_type: str,
    payload: Mapping[str, Any],
    captured_at: datetime,
    mutation_id: UUID | None = None,
) -> OfflineAuditMutation:
    if sequence < 1:
        raise OfflineAuditError("offline mutation sequence must start at 1")
    nonce = nonce.strip()
    idempotency_key = idempotency_key.strip()
    mutation_type = mutation_type.strip()
    if not nonce or not idempotency_key or not mutation_type:
        raise OfflineAuditError("nonce, idempotency_key and mutation_type are required")
    if not payload:
        raise OfflineAuditError("offline mutation payload cannot be empty")
    return OfflineAuditMutation(
        mutation_id=mutation_id or uuid4(),
        occurrence_id=package.occurrence_id,
        package_hash=package.package_hash,
        device_id=package.device_id,
        sequence=sequence,
        nonce=nonce,
        idempotency_key=idempotency_key,
        mutation_type=mutation_type,
        payload=tuple(sorted((str(k), v) for k, v in payload.items())),
        captured_at=_utc(captured_at),
    )


def seal_queue(
    mutations: Iterable[OfflineAuditMutation],
    *,
    key: bytes,
    package_hash: str,
    nonce: bytes | None = None,
) -> EncryptedOfflineQueue:
    rows = tuple(mutations)
    if len(key) not in (16, 24, 32):
        raise OfflineAuditError("AES-GCM key must be 128, 192 or 256 bits")
    package_hash = _hex64(package_hash, "package hash")
    iv = nonce or os.urandom(12)
    if len(iv) != 12:
        raise OfflineAuditError("AES-GCM queue nonce must be 12 bytes")
    plaintext = json.dumps(
        [_mutation_record(row) for row in rows],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    aad = f"eay-audit-offline:{package_hash}".encode("utf-8")
    ciphertext = AESGCM(key).encrypt(iv, plaintext, aad)
    return EncryptedOfflineQueue(
        algorithm="AES-256-GCM" if len(key) == 32 else f"AES-{len(key)*8}-GCM",
        nonce_hex=iv.hex(),
        ciphertext_hex=ciphertext.hex(),
        aad_hash=sha256(aad).hexdigest(),
        mutation_count=len(rows),
    )


def open_queue(
    sealed: EncryptedOfflineQueue,
    *,
    key: bytes,
    package_hash: str,
) -> tuple[OfflineAuditMutation, ...]:
    package_hash = _hex64(package_hash, "package hash")
    aad = f"eay-audit-offline:{package_hash}".encode("utf-8")
    if sha256(aad).hexdigest() != sealed.aad_hash:
        raise OfflineAuditError("offline queue package binding mismatch")
    try:
        plaintext = AESGCM(key).decrypt(
            bytes.fromhex(sealed.nonce_hex),
            bytes.fromhex(sealed.ciphertext_hex),
            aad,
        )
    except Exception as error:
        raise OfflineAuditError("offline queue decryption/authentication failed") from error
    rows = json.loads(plaintext.decode("utf-8"))
    mutations = tuple(_mutation_from_record(row) for row in rows)
    if len(mutations) != sealed.mutation_count:
        raise OfflineAuditError("offline queue mutation count mismatch")
    return mutations


def reconcile_offline_mutations(
    package: OfflineAuditPackage,
    mutations: Iterable[OfflineAuditMutation],
    *,
    principal_tenant_id: str,
    actor_subject: str,
    now: datetime,
    ledger: OfflineSyncLedger | None = None,
) -> tuple[OfflineSyncLedger, OfflineSyncReceipt]:
    # Tenant is server/principal authority. Mutations intentionally have no tenant field.
    principal_tenant_id = principal_tenant_id.strip()
    actor_subject = actor_subject.strip()
    if principal_tenant_id != package.tenant_id:
        raise OfflineAuditError("server principal tenant does not own offline package")
    if actor_subject != package.assignee_subject:
        raise OfflineAuditError("sync actor does not match frozen schedule assignment")
    if _utc(now) < package.issued_at:
        raise OfflineAuditError("sync clock precedes package issue time")

    run_id = uuid5(NAMESPACE_URL, f"eay:audit-run:{package.tenant_id}:{package.occurrence_id}")
    current = ledger or OfflineSyncLedger(
        occurrence_id=package.occurrence_id,
        audit_run_id=run_id,
    )
    if current.occurrence_id != package.occurrence_id or current.audit_run_id != run_id:
        raise OfflineAuditError("sync ledger is not bound to this schedule occurrence")

    accepted_rows = list(current.accepted)
    by_key = {row[0]: row for row in accepted_rows}
    nonce_to_key = {row[2]: row[0] for row in accepted_rows}
    next_sequence = current.highest_sequence + 1
    accepted_ids: list[UUID] = []
    replayed_ids: list[UUID] = []

    for item in mutations:
        _validate_mutation_package(item, package)
        previous = by_key.get(item.idempotency_key)
        if previous is not None:
            if previous[1] != item.payload_hash or previous[2] != item.nonce or previous[3] != item.sequence:
                raise OfflineAuditError("idempotency key replay changed governed mutation content")
            replayed_ids.append(item.mutation_id)
            continue
        if item.nonce in nonce_to_key:
            raise OfflineAuditError("offline mutation nonce reuse detected")
        if item.sequence != next_sequence:
            raise OfflineAuditError(
                f"offline mutation sequence conflict: expected {next_sequence}, got {item.sequence}"
            )
        row = (item.idempotency_key, item.payload_hash, item.nonce, item.sequence)
        accepted_rows.append(row)
        by_key[item.idempotency_key] = row
        nonce_to_key[item.nonce] = item.idempotency_key
        next_sequence += 1
        accepted_ids.append(item.mutation_id)

    new_ledger = OfflineSyncLedger(
        occurrence_id=package.occurrence_id,
        audit_run_id=run_id,
        accepted=tuple(accepted_rows),
    )
    receipt_payload = {
        "occurrence_id": str(package.occurrence_id),
        "audit_run_id": str(run_id),
        "accepted": [str(value) for value in accepted_ids],
        "replayed": [str(value) for value in replayed_ids],
        "highest_sequence": new_ledger.highest_sequence,
    }
    return new_ledger, OfflineSyncReceipt(
        occurrence_id=package.occurrence_id,
        audit_run_id=run_id,
        accepted_mutation_ids=tuple(accepted_ids),
        replayed_mutation_ids=tuple(replayed_ids),
        highest_sequence=new_ledger.highest_sequence,
        receipt_hash=_sha(receipt_payload),
    )


def _validate_mutation_package(item: OfflineAuditMutation, package: OfflineAuditPackage) -> None:
    if item.occurrence_id != package.occurrence_id:
        raise OfflineAuditError("offline mutation occurrence mismatch")
    if item.package_hash != package.package_hash:
        raise OfflineAuditError("offline mutation package hash mismatch")
    if item.device_id != package.device_id:
        raise OfflineAuditError("offline mutation device mismatch")
    if item.captured_at < package.issued_at or item.captured_at > package.expires_at:
        raise OfflineAuditError("offline mutation capture time is outside package validity")


def _mutation_record(item: OfflineAuditMutation) -> dict[str, Any]:
    return {
        "mutation_id": str(item.mutation_id),
        "occurrence_id": str(item.occurrence_id),
        "package_hash": item.package_hash,
        "device_id": item.device_id,
        "sequence": item.sequence,
        "nonce": item.nonce,
        "idempotency_key": item.idempotency_key,
        "mutation_type": item.mutation_type,
        "payload": list(item.payload),
        "captured_at": item.captured_at.isoformat(),
    }


def _mutation_from_record(row: Mapping[str, Any]) -> OfflineAuditMutation:
    return OfflineAuditMutation(
        mutation_id=UUID(str(row["mutation_id"])),
        occurrence_id=UUID(str(row["occurrence_id"])),
        package_hash=str(row["package_hash"]),
        device_id=str(row["device_id"]),
        sequence=int(row["sequence"]),
        nonce=str(row["nonce"]),
        idempotency_key=str(row["idempotency_key"]),
        mutation_type=str(row["mutation_type"]),
        payload=tuple((str(k), v) for k, v in row["payload"]),
        captured_at=_utc(datetime.fromisoformat(str(row["captured_at"]))),
    )


def _hex64(value: str, label: str) -> str:
    value = value.strip().lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise OfflineAuditError(f"{label} must be a 64-character lowercase hex digest")
    return value


def _sha(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise OfflineAuditError("timestamps must be timezone-aware")
    return value.astimezone(UTC)
