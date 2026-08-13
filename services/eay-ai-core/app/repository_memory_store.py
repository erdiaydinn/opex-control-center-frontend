from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .historical_repository_registry import (
    HistoricalRepositoryRegistryArchive,
    HistoricalRepositoryRegistryError,
)
from .repository_intelligence import RepositoryRegistry
from .repository_provenance import RepositorySnapshot, verify_repository_snapshot


class RepositoryMemoryStoreError(RuntimeError):
    pass


class AppendOnlyRepositoryMemoryStore:
    """Local-first append-only repository snapshot store.

    Persisted history is replayed against the exact registry revision fingerprint carried by each
    snapshot. The current registry is authoritative for new appends only; historical snapshots are
    never reinterpreted under a newer registry revision. The store detects accidental/casual
    tampering through deterministic snapshot fingerprints and hash-chain validation. It is not WORM
    storage because an operating-system or disk administrator can still alter local files.
    """

    def __init__(
        self,
        root: str | Path,
        registry: RepositoryRegistry,
        historical_registries: HistoricalRepositoryRegistryArchive | None = None,
    ) -> None:
        self.root = Path(root)
        self.registry = registry
        self.historical_registries = historical_registries
        self.snapshot_dir = self.root / "snapshots"
        self.index_path = self.root / "index.jsonl"

    def _snapshot_path(self, fingerprint: str) -> Path:
        return self.snapshot_dir / f"{fingerprint}.json"

    @staticmethod
    def _snapshot_json(snapshot: RepositorySnapshot) -> str:
        return json.dumps(
            snapshot.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ) + "\n"

    def _registry_for_snapshot(self, snapshot: RepositorySnapshot) -> RepositoryRegistry:
        current_fingerprint = self.registry.fingerprint()
        if snapshot.registry_fingerprint == current_fingerprint:
            return self.registry
        if self.historical_registries is None:
            raise RepositoryMemoryStoreError("repository_memory_historical_registry_unavailable")
        try:
            return self.historical_registries.resolve(snapshot.registry_fingerprint)
        except HistoricalRepositoryRegistryError as exc:
            raise RepositoryMemoryStoreError("repository_memory_historical_registry_unavailable") from exc

    def list_snapshots(self) -> tuple[RepositorySnapshot, ...]:
        if not self.index_path.exists():
            return ()

        snapshots: list[RepositorySnapshot] = []
        seen: set[str] = set()
        previous_fingerprint: str | None = None
        for raw_line in self.index_path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
                fingerprint = record["fingerprint"]
                indexed_registry_fingerprint = record["registry_fingerprint"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise RepositoryMemoryStoreError("repository_memory_index_corrupt") from exc
            if not isinstance(fingerprint, str) or len(fingerprint) != 64:
                raise RepositoryMemoryStoreError("repository_memory_index_fingerprint_invalid")
            if not isinstance(indexed_registry_fingerprint, str) or len(indexed_registry_fingerprint) != 64:
                raise RepositoryMemoryStoreError("repository_memory_index_registry_fingerprint_invalid")
            if fingerprint in seen:
                raise RepositoryMemoryStoreError("repository_memory_index_duplicate_fingerprint")
            seen.add(fingerprint)

            snapshot_path = self._snapshot_path(fingerprint)
            if not snapshot_path.exists():
                raise RepositoryMemoryStoreError("repository_memory_snapshot_missing")
            try:
                payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
                snapshot = RepositorySnapshot.model_validate(payload)
            except Exception as exc:
                raise RepositoryMemoryStoreError("repository_memory_snapshot_invalid") from exc
            if snapshot.fingerprint() != fingerprint:
                raise RepositoryMemoryStoreError("repository_memory_snapshot_fingerprint_mismatch")
            if snapshot.registry_fingerprint != indexed_registry_fingerprint:
                raise RepositoryMemoryStoreError("repository_memory_index_registry_fingerprint_mismatch")
            if snapshot.previous_snapshot_fingerprint != previous_fingerprint:
                raise RepositoryMemoryStoreError("repository_memory_chain_verification_failed")

            registry = self._registry_for_snapshot(snapshot)
            try:
                verify_repository_snapshot(registry=registry, snapshot=snapshot)
            except ValueError as exc:
                raise RepositoryMemoryStoreError("repository_memory_chain_verification_failed") from exc

            snapshots.append(snapshot)
            previous_fingerprint = fingerprint

        return tuple(snapshots)

    def append(self, snapshot: RepositorySnapshot) -> Path:
        # New truth may only be appended under the current canonical registry revision. Historical
        # registry resolution is a replay compatibility mechanism, never an authority to backdate
        # new writes.
        try:
            verify_repository_snapshot(registry=self.registry, snapshot=snapshot)
        except ValueError as exc:
            raise RepositoryMemoryStoreError("repository_memory_snapshot_rejected") from exc

        existing = self.list_snapshots()
        expected_previous = existing[-1].fingerprint() if existing else None
        if snapshot.previous_snapshot_fingerprint != expected_previous:
            raise RepositoryMemoryStoreError("repository_memory_append_would_fork_history")

        fingerprint = snapshot.fingerprint()
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = self._snapshot_path(fingerprint)
        if snapshot_path.exists():
            raise RepositoryMemoryStoreError("repository_memory_snapshot_already_exists")

        fd, temp_name = tempfile.mkstemp(prefix=".snapshot-", suffix=".json", dir=self.snapshot_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(self._snapshot_json(snapshot))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, snapshot_path)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise

        index_record = json.dumps(
            {
                "fingerprint": fingerprint,
                "registry_fingerprint": snapshot.registry_fingerprint,
                "created_at": snapshot.created_at.isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with self.index_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(index_record + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except Exception as exc:
            snapshot_path.unlink(missing_ok=True)
            raise RepositoryMemoryStoreError("repository_memory_index_commit_failed") from exc

        return snapshot_path
