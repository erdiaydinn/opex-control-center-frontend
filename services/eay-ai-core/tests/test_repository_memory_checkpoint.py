from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.repository_intelligence import load_repository_registry
from app.repository_memory_checkpoint import (
    RepositoryMemoryCheckpointError,
    create_signed_repository_memory_checkpoint,
    export_repository_memory_checkpoint,
    load_checkpoint_public_key,
    verify_repository_memory_checkpoint,
    verify_repository_memory_checkpoint_chain,
    write_repository_memory_checkpoint,
)
from app.repository_memory_store import AppendOnlyRepositoryMemoryStore
from app.repository_review_snapshot import RepositoryFileFact, create_repository_review_snapshot

REGISTRY_PATH = Path(__file__).parents[1] / "config" / "repository_intelligence_registry.json"
ENTRY_ID = "discovered-apache-superset"


def _registry():
    return load_repository_registry(REGISTRY_PATH)


def _write_keypair(tmp_path: Path, name: str):
    private_key = Ed25519PrivateKey.generate()
    private_path = tmp_path / f"{name}.private.pem"
    public_path = tmp_path / f"{name}.public.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_path, public_path


def _append_snapshot(store: AppendOnlyRepositoryMemoryStore, commit_sha: str, reviewed_at: str):
    existing = store.list_snapshots(ENTRY_ID)
    previous = existing[-1].fingerprint if existing else None
    snapshot = create_repository_review_snapshot(
        store.registry,
        registry_entry_id=ENTRY_ID,
        reviewed_ref="master",
        commit_sha=commit_sha,
        reviewed_at=reviewed_at,
        previous_snapshot_fingerprint=previous,
        files=(
            RepositoryFileFact(
                path="superset/security/checkpoint_reference.py",
                blob_sha="c" * 40,
                symbols=("checkpoint_reference",),
                contracts=("repository-memory-checkpoint",),
                content_sha256="d" * 64,
            ),
        ),
    )
    store.append(snapshot)
    return snapshot


def test_signed_checkpoint_verifies_and_is_deterministic(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path / "memory", registry)
    snapshot = _append_snapshot(store, "a" * 40, "2026-08-13T05:30:00+03:00")
    private_path, public_path = _write_keypair(tmp_path, "checkpoint-k1")

    first = create_signed_repository_memory_checkpoint(
        store,
        registry_entry_ids=(ENTRY_ID,),
        created_at="2026-08-13T05:31:00+03:00",
        private_key_path=private_path,
        signer_key_id="checkpoint-k1",
    )
    second = create_signed_repository_memory_checkpoint(
        store,
        registry_entry_ids=(ENTRY_ID,),
        created_at="2026-08-13T05:31:00+03:00",
        private_key_path=private_path,
        signer_key_id="checkpoint-k1",
    )

    assert first == second
    assert first.heads[0].head_snapshot_fingerprint == snapshot.fingerprint
    assert first.heads[0].snapshot_count == 1
    assert len(first.payload_fingerprint) == 64
    assert len(first.fingerprint) == 64
    verify_repository_memory_checkpoint(
        first,
        public_key=load_checkpoint_public_key(public_path),
        registry=registry,
        store=store,
        require_current_head=True,
    )


def test_checkpoint_remains_valid_after_later_append_but_can_require_current_head(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path / "memory", registry)
    _append_snapshot(store, "a" * 40, "2026-08-13T05:30:00+03:00")
    private_path, public_path = _write_keypair(tmp_path, "checkpoint-k1")
    checkpoint = create_signed_repository_memory_checkpoint(
        store,
        registry_entry_ids=(ENTRY_ID,),
        created_at="2026-08-13T05:31:00+03:00",
        private_key_path=private_path,
        signer_key_id="checkpoint-k1",
    )

    _append_snapshot(store, "b" * 40, "2026-08-13T05:32:00+03:00")
    public_key = load_checkpoint_public_key(public_path)
    verify_repository_memory_checkpoint(checkpoint, public_key=public_key, registry=registry, store=store)
    with pytest.raises(RepositoryMemoryCheckpointError, match="current repository memory head"):
        verify_repository_memory_checkpoint(
            checkpoint,
            public_key=public_key,
            registry=registry,
            store=store,
            require_current_head=True,
        )


def test_checkpoint_tamper_and_wrong_key_fail_closed(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path / "memory", registry)
    _append_snapshot(store, "a" * 40, "2026-08-13T05:30:00+03:00")
    private_path, public_path = _write_keypair(tmp_path, "checkpoint-k1")
    _, wrong_public_path = _write_keypair(tmp_path, "checkpoint-k2")
    checkpoint = create_signed_repository_memory_checkpoint(
        store,
        registry_entry_ids=(ENTRY_ID,),
        created_at="2026-08-13T05:31:00+03:00",
        private_key_path=private_path,
        signer_key_id="checkpoint-k1",
    )

    tampered_head = replace(checkpoint.heads[0], head_commit_sha="f" * 40)
    tampered = replace(checkpoint, heads=(tampered_head,))
    with pytest.raises(RepositoryMemoryCheckpointError, match="payload fingerprint mismatch"):
        verify_repository_memory_checkpoint(
            tampered,
            public_key=load_checkpoint_public_key(public_path),
            registry=registry,
        )

    with pytest.raises(RepositoryMemoryCheckpointError, match="public key fingerprint mismatch"):
        verify_repository_memory_checkpoint(
            checkpoint,
            public_key=load_checkpoint_public_key(wrong_public_path),
            registry=registry,
        )


def test_checkpoint_chain_supports_key_rotation_and_detects_reorder(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path / "memory", registry)
    _append_snapshot(store, "a" * 40, "2026-08-13T05:30:00+03:00")
    private_k1, public_k1 = _write_keypair(tmp_path, "checkpoint-k1")
    first = create_signed_repository_memory_checkpoint(
        store,
        registry_entry_ids=(ENTRY_ID,),
        created_at="2026-08-13T05:31:00+03:00",
        private_key_path=private_k1,
        signer_key_id="checkpoint-k1",
    )

    _append_snapshot(store, "b" * 40, "2026-08-13T05:32:00+03:00")
    private_k2, public_k2 = _write_keypair(tmp_path, "checkpoint-k2")
    second = create_signed_repository_memory_checkpoint(
        store,
        registry_entry_ids=(ENTRY_ID,),
        created_at="2026-08-13T05:33:00+03:00",
        private_key_path=private_k2,
        signer_key_id="checkpoint-k2",
        previous_checkpoint_fingerprint=first.fingerprint,
    )

    public_keys = {
        "checkpoint-k1": load_checkpoint_public_key(public_k1),
        "checkpoint-k2": load_checkpoint_public_key(public_k2),
    }
    registries = {registry.fingerprint: registry}
    verify_repository_memory_checkpoint_chain(
        (first, second),
        public_keys=public_keys,
        registries=registries,
    )
    with pytest.raises(RepositoryMemoryCheckpointError, match="chain is broken"):
        verify_repository_memory_checkpoint_chain(
            (second, first),
            public_keys=public_keys,
            registries=registries,
        )


def test_checkpoint_export_is_append_only_and_contains_no_private_key(tmp_path: Path) -> None:
    registry = _registry()
    store = AppendOnlyRepositoryMemoryStore(tmp_path / "memory", registry)
    _append_snapshot(store, "a" * 40, "2026-08-13T05:30:00+03:00")
    private_path, _ = _write_keypair(tmp_path, "checkpoint-k1")
    checkpoint = create_signed_repository_memory_checkpoint(
        store,
        registry_entry_ids=(ENTRY_ID,),
        created_at="2026-08-13T05:31:00+03:00",
        private_key_path=private_path,
        signer_key_id="checkpoint-k1",
    )

    exported = export_repository_memory_checkpoint(checkpoint)
    assert "PRIVATE KEY" not in exported
    assert str(private_path) not in exported
    assert checkpoint.signature_b64url in exported

    target = tmp_path / "external-checkpoints" / f"{checkpoint.fingerprint}.json"
    assert write_repository_memory_checkpoint(checkpoint, target) == target
    assert target.read_text(encoding="utf-8") == exported
    with pytest.raises(RepositoryMemoryCheckpointError, match="overwrite is forbidden"):
        write_repository_memory_checkpoint(checkpoint, target)
