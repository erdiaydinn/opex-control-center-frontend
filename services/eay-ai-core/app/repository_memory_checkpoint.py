from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.repository_intelligence import RepositoryRegistry
from app.repository_memory_store import AppendOnlyRepositoryMemoryStore, RepositoryMemoryStoreError


class RepositoryMemoryCheckpointError(RuntimeError):
    pass


CHECKPOINT_TYPE = "eay.repository-memory-head"
SIGNING_ALGORITHM = "Ed25519"
MAX_SIGNING_KEY_BYTES = 16 * 1024
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class RepositoryMemoryHeadAnchor:
    registry_entry_id: str
    repository: str
    snapshot_count: int
    head_snapshot_fingerprint: str
    head_commit_sha: str
    head_reviewed_at: str


@dataclass(frozen=True)
class RepositoryMemoryCheckpoint:
    schema_version: int
    checkpoint_type: str
    created_at: str
    registry_fingerprint: str
    previous_checkpoint_fingerprint: str | None
    heads: tuple[RepositoryMemoryHeadAnchor, ...]
    signer_key_id: str
    signer_public_key_sha256: str
    signing_algorithm: str
    payload_fingerprint: str
    signature_b64url: str
    fingerprint: str


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_hex(value: str, length: int) -> bool:
    return len(value) == length and all(char in "0123456789abcdef" for char in value.lower())


def _b64url_encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise RepositoryMemoryCheckpointError("checkpoint signature is not ASCII base64url") from exc
    padding = b"=" * ((4 - len(encoded) % 4) % 4)
    try:
        return base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise RepositoryMemoryCheckpointError("checkpoint signature is not valid base64url") from exc


def _public_key_raw(public_key: Ed25519PublicKey) -> bytes:
    return public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def public_key_fingerprint(public_key: Ed25519PublicKey) -> str:
    return _sha256_bytes(_public_key_raw(public_key))


def _read_key_file(path: str | Path) -> bytes:
    key_path = Path(path)
    try:
        size = key_path.stat().st_size
    except OSError as exc:
        raise RepositoryMemoryCheckpointError("checkpoint signing key file is not readable") from exc
    if size <= 0 or size > MAX_SIGNING_KEY_BYTES:
        raise RepositoryMemoryCheckpointError("checkpoint signing key file size is invalid")
    try:
        return key_path.read_bytes()
    except OSError as exc:
        raise RepositoryMemoryCheckpointError("checkpoint signing key file is not readable") from exc


def load_checkpoint_private_key(path: str | Path) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(_read_key_file(path), password=None)
    except (TypeError, ValueError) as exc:
        raise RepositoryMemoryCheckpointError("checkpoint private key is not a valid unencrypted PEM key") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise RepositoryMemoryCheckpointError("checkpoint signing requires a dedicated Ed25519 private key")
    return key


def load_checkpoint_public_key(path: str | Path) -> Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(_read_key_file(path))
    except (TypeError, ValueError) as exc:
        raise RepositoryMemoryCheckpointError("checkpoint public key is not a valid PEM key") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise RepositoryMemoryCheckpointError("checkpoint verification requires an Ed25519 public key")
    return key


def _unsigned_payload(
    *,
    created_at: str,
    registry_fingerprint: str,
    previous_checkpoint_fingerprint: str | None,
    heads: tuple[RepositoryMemoryHeadAnchor, ...],
    signer_key_id: str,
    signer_public_key_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "checkpoint_type": CHECKPOINT_TYPE,
        "created_at": created_at,
        "registry_fingerprint": registry_fingerprint,
        "previous_checkpoint_fingerprint": previous_checkpoint_fingerprint,
        "heads": [asdict(head) for head in heads],
        "signer_key_id": signer_key_id,
        "signer_public_key_sha256": signer_public_key_sha256,
        "signing_algorithm": SIGNING_ALGORITHM,
    }


def _checkpoint_fingerprint(unsigned_payload: dict[str, Any], payload_fingerprint: str, signature_b64url: str) -> str:
    return _sha256_bytes(
        _canonical_json(
            {
                **unsigned_payload,
                "payload_fingerprint": payload_fingerprint,
                "signature_b64url": signature_b64url,
            }
        )
    )


def _validate_anchor(anchor: RepositoryMemoryHeadAnchor, registry: RepositoryRegistry) -> None:
    if anchor.snapshot_count <= 0:
        raise RepositoryMemoryCheckpointError("checkpoint anchor snapshot_count must be positive")
    if not _is_hex(anchor.head_snapshot_fingerprint, 64):
        raise RepositoryMemoryCheckpointError("checkpoint anchor snapshot fingerprint is invalid")
    if not _is_hex(anchor.head_commit_sha, 40):
        raise RepositoryMemoryCheckpointError("checkpoint anchor commit SHA is invalid")
    if not anchor.head_reviewed_at.strip():
        raise RepositoryMemoryCheckpointError("checkpoint anchor reviewed_at is required")

    try:
        entry = registry.by_id(anchor.registry_entry_id)
    except KeyError as exc:
        raise RepositoryMemoryCheckpointError("checkpoint anchor registry entry is unknown") from exc
    if entry.get("identity_status") != "VERIFIED" or not entry.get("repository"):
        raise RepositoryMemoryCheckpointError("checkpoint anchor requires a verified repository identity")
    if anchor.repository != entry["repository"]:
        raise RepositoryMemoryCheckpointError("checkpoint anchor repository does not match registry")


def create_signed_repository_memory_checkpoint(
    store: AppendOnlyRepositoryMemoryStore,
    *,
    registry_entry_ids: Iterable[str],
    created_at: str,
    private_key_path: str | Path,
    signer_key_id: str,
    previous_checkpoint_fingerprint: str | None = None,
) -> RepositoryMemoryCheckpoint:
    if not created_at.strip():
        raise RepositoryMemoryCheckpointError("checkpoint created_at is required")
    if not _KEY_ID_RE.fullmatch(signer_key_id):
        raise RepositoryMemoryCheckpointError("checkpoint signer_key_id is invalid")
    if previous_checkpoint_fingerprint is not None and not _is_hex(previous_checkpoint_fingerprint, 64):
        raise RepositoryMemoryCheckpointError("previous checkpoint fingerprint is invalid")

    entry_ids = tuple(registry_entry_ids)
    if not entry_ids:
        raise RepositoryMemoryCheckpointError("at least one repository memory head must be checkpointed")
    if len(set(entry_ids)) != len(entry_ids):
        raise RepositoryMemoryCheckpointError("duplicate registry entry in checkpoint request")

    anchors: list[RepositoryMemoryHeadAnchor] = []
    for entry_id in entry_ids:
        try:
            snapshots = store.list_snapshots(entry_id)
        except RepositoryMemoryStoreError as exc:
            raise RepositoryMemoryCheckpointError("repository memory failed verification before checkpoint") from exc
        if not snapshots:
            raise RepositoryMemoryCheckpointError(f"repository memory has no snapshots to checkpoint: {entry_id}")
        head = snapshots[-1]
        anchor = RepositoryMemoryHeadAnchor(
            registry_entry_id=entry_id,
            repository=head.repository,
            snapshot_count=len(snapshots),
            head_snapshot_fingerprint=head.fingerprint,
            head_commit_sha=head.commit_sha,
            head_reviewed_at=head.reviewed_at,
        )
        _validate_anchor(anchor, store.registry)
        anchors.append(anchor)

    normalized_heads = tuple(sorted(anchors, key=lambda item: item.registry_entry_id))
    private_key = load_checkpoint_private_key(private_key_path)
    public_key = private_key.public_key()
    public_fingerprint = public_key_fingerprint(public_key)
    unsigned = _unsigned_payload(
        created_at=created_at,
        registry_fingerprint=store.registry.fingerprint,
        previous_checkpoint_fingerprint=previous_checkpoint_fingerprint,
        heads=normalized_heads,
        signer_key_id=signer_key_id,
        signer_public_key_sha256=public_fingerprint,
    )
    payload_bytes = _canonical_json(unsigned)
    payload_fingerprint = _sha256_bytes(payload_bytes)
    signature_b64url = _b64url_encode(private_key.sign(payload_bytes))
    fingerprint = _checkpoint_fingerprint(unsigned, payload_fingerprint, signature_b64url)

    return RepositoryMemoryCheckpoint(
        schema_version=1,
        checkpoint_type=CHECKPOINT_TYPE,
        created_at=created_at,
        registry_fingerprint=store.registry.fingerprint,
        previous_checkpoint_fingerprint=previous_checkpoint_fingerprint,
        heads=normalized_heads,
        signer_key_id=signer_key_id,
        signer_public_key_sha256=public_fingerprint,
        signing_algorithm=SIGNING_ALGORITHM,
        payload_fingerprint=payload_fingerprint,
        signature_b64url=signature_b64url,
        fingerprint=fingerprint,
    )


def verify_repository_memory_checkpoint(
    checkpoint: RepositoryMemoryCheckpoint,
    *,
    public_key: Ed25519PublicKey,
    registry: RepositoryRegistry,
    store: AppendOnlyRepositoryMemoryStore | None = None,
    require_current_head: bool = False,
) -> None:
    if checkpoint.schema_version != 1 or checkpoint.checkpoint_type != CHECKPOINT_TYPE:
        raise RepositoryMemoryCheckpointError("unsupported repository memory checkpoint schema/type")
    if checkpoint.signing_algorithm != SIGNING_ALGORITHM:
        raise RepositoryMemoryCheckpointError("unsupported checkpoint signing algorithm")
    if not checkpoint.created_at.strip():
        raise RepositoryMemoryCheckpointError("checkpoint created_at is required")
    if not _KEY_ID_RE.fullmatch(checkpoint.signer_key_id):
        raise RepositoryMemoryCheckpointError("checkpoint signer_key_id is invalid")
    if checkpoint.registry_fingerprint != registry.fingerprint:
        raise RepositoryMemoryCheckpointError("checkpoint is bound to a different registry revision")
    if checkpoint.previous_checkpoint_fingerprint is not None and not _is_hex(
        checkpoint.previous_checkpoint_fingerprint, 64
    ):
        raise RepositoryMemoryCheckpointError("previous checkpoint fingerprint is invalid")
    if not checkpoint.heads:
        raise RepositoryMemoryCheckpointError("checkpoint contains no repository heads")

    ids = [head.registry_entry_id for head in checkpoint.heads]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise RepositoryMemoryCheckpointError("checkpoint repository heads are not canonical and unique")
    for head in checkpoint.heads:
        _validate_anchor(head, registry)

    expected_public_fingerprint = public_key_fingerprint(public_key)
    if checkpoint.signer_public_key_sha256 != expected_public_fingerprint:
        raise RepositoryMemoryCheckpointError("checkpoint public key fingerprint mismatch")

    unsigned = _unsigned_payload(
        created_at=checkpoint.created_at,
        registry_fingerprint=checkpoint.registry_fingerprint,
        previous_checkpoint_fingerprint=checkpoint.previous_checkpoint_fingerprint,
        heads=checkpoint.heads,
        signer_key_id=checkpoint.signer_key_id,
        signer_public_key_sha256=checkpoint.signer_public_key_sha256,
    )
    payload_bytes = _canonical_json(unsigned)
    if _sha256_bytes(payload_bytes) != checkpoint.payload_fingerprint:
        raise RepositoryMemoryCheckpointError("checkpoint payload fingerprint mismatch")
    if _checkpoint_fingerprint(unsigned, checkpoint.payload_fingerprint, checkpoint.signature_b64url) != checkpoint.fingerprint:
        raise RepositoryMemoryCheckpointError("checkpoint fingerprint mismatch")

    signature = _b64url_decode(checkpoint.signature_b64url)
    if len(signature) != 64:
        raise RepositoryMemoryCheckpointError("checkpoint Ed25519 signature length is invalid")
    try:
        public_key.verify(signature, payload_bytes)
    except InvalidSignature as exc:
        raise RepositoryMemoryCheckpointError("checkpoint signature verification failed") from exc

    if store is not None:
        if store.registry.fingerprint != registry.fingerprint:
            raise RepositoryMemoryCheckpointError("checkpoint store is bound to a different registry revision")
        for anchor in checkpoint.heads:
            try:
                snapshots = store.list_snapshots(anchor.registry_entry_id)
            except RepositoryMemoryStoreError as exc:
                raise RepositoryMemoryCheckpointError("checkpointed repository memory no longer verifies") from exc
            if len(snapshots) < anchor.snapshot_count:
                raise RepositoryMemoryCheckpointError("checkpointed repository memory history was truncated")
            anchored = snapshots[anchor.snapshot_count - 1]
            if (
                anchored.fingerprint != anchor.head_snapshot_fingerprint
                or anchored.commit_sha != anchor.head_commit_sha
                or anchored.reviewed_at != anchor.head_reviewed_at
            ):
                raise RepositoryMemoryCheckpointError("checkpointed repository memory anchor no longer matches history")
            if require_current_head and len(snapshots) != anchor.snapshot_count:
                raise RepositoryMemoryCheckpointError("checkpoint no longer represents the current repository memory head")


def verify_repository_memory_checkpoint_chain(
    checkpoints: Iterable[RepositoryMemoryCheckpoint],
    *,
    public_keys: Mapping[str, Ed25519PublicKey],
    registries: Mapping[str, RepositoryRegistry],
) -> None:
    previous: RepositoryMemoryCheckpoint | None = None
    seen: set[str] = set()
    for checkpoint in checkpoints:
        if checkpoint.fingerprint in seen:
            raise RepositoryMemoryCheckpointError("duplicate repository memory checkpoint fingerprint")
        seen.add(checkpoint.fingerprint)
        expected_previous = previous.fingerprint if previous is not None else None
        if checkpoint.previous_checkpoint_fingerprint != expected_previous:
            raise RepositoryMemoryCheckpointError("repository memory checkpoint chain is broken")
        try:
            public_key = public_keys[checkpoint.signer_key_id]
        except KeyError as exc:
            raise RepositoryMemoryCheckpointError("checkpoint signer public key is unavailable") from exc
        try:
            registry = registries[checkpoint.registry_fingerprint]
        except KeyError as exc:
            raise RepositoryMemoryCheckpointError("checkpoint historical registry revision is unavailable") from exc
        verify_repository_memory_checkpoint(checkpoint, public_key=public_key, registry=registry)
        previous = checkpoint


def export_repository_memory_checkpoint(checkpoint: RepositoryMemoryCheckpoint) -> str:
    return json.dumps(asdict(checkpoint), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def write_repository_memory_checkpoint(checkpoint: RepositoryMemoryCheckpoint, output_path: str | Path) -> Path:
    """Atomically publish one signed checkpoint without ever overwriting an existing artifact."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = export_repository_memory_checkpoint(checkpoint).encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix=".checkpoint-", suffix=".json", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_name, target)
        except FileExistsError as exc:
            raise RepositoryMemoryCheckpointError("checkpoint export target already exists; overwrite is forbidden") from exc
        try:
            directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return target
