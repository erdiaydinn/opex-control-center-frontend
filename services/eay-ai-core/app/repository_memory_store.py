from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from app.repository_intelligence import RepositoryRegistry
from app.repository_review_snapshot import (
    RepositoryFileFact,
    RepositoryReviewSnapshot,
    RepositorySnapshotError,
    verify_repository_review_snapshot,
    verify_repository_snapshot_chain,
)


class RepositoryMemoryStoreError(RuntimeError):
    pass


def _snapshot_from_payload(payload: dict) -> RepositoryReviewSnapshot:
    try:
        files = tuple(
            RepositoryFileFact(
                path=fact["path"],
                blob_sha=fact["blob_sha"],
                symbols=tuple(fact.get("symbols", ())),
                contracts=tuple(fact.get("contracts", ())),
                content_sha256=fact.get("content_sha256"),
            )
            for fact in payload["files"]
        )
        return RepositoryReviewSnapshot(
            schema_version=payload["schema_version"],
            registry_fingerprint=payload["registry_fingerprint"],
            registry_entry_id=payload["registry_entry_id"],
            repository=payload["repository"],
            canonical_upstream=payload["canonical_upstream"],
            relation=payload["relation"],
            reviewed_ref=payload["reviewed_ref"],
            commit_sha=payload["commit_sha"],
            reviewed_at=payload["reviewed_at"],
            previous_snapshot_fingerprint=payload["previous_snapshot_fingerprint"],
            files=files,
            fingerprint=payload["fingerprint"],
        )
    except (KeyError, TypeError) as exc:
        raise RepositoryMemoryStoreError("invalid repository snapshot payload") from exc


class AppendOnlyRepositoryMemoryStore:
    """Filesystem-backed append-only store for provenance-bound repository reviews."""

    def __init__(self, root: str | Path, registry: RepositoryRegistry) -> None:
        self.root = Path(root)
        self.registry = registry

    def _repo_dir(self, registry_entry_id: str) -> Path:
        safe = registry_entry_id.replace("/", "_").replace("\\", "_")
        return self.root / safe

    def _snapshot_path(self, registry_entry_id: str, fingerprint: str) -> Path:
        return self._repo_dir(registry_entry_id) / f"{fingerprint}.json"

    def _index_path(self, registry_entry_id: str) -> Path:
        return self._repo_dir(registry_entry_id) / "index.jsonl"

    def list_snapshots(self, registry_entry_id: str) -> tuple[RepositoryReviewSnapshot, ...]:
        index_path = self._index_path(registry_entry_id)
        if not index_path.exists():
            return ()

        snapshots: list[RepositoryReviewSnapshot] = []
        seen: set[str] = set()
        for raw_line in index_path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            try:
                index_record = json.loads(raw_line)
                fingerprint = index_record["fingerprint"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise RepositoryMemoryStoreError("repository memory index is corrupt") from exc
            if fingerprint in seen:
                raise RepositoryMemoryStoreError("repository memory index contains duplicate fingerprint")
            seen.add(fingerprint)

            snapshot_path = self._snapshot_path(registry_entry_id, fingerprint)
            if not snapshot_path.exists():
                raise RepositoryMemoryStoreError("repository memory index references missing snapshot")
            try:
                payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise RepositoryMemoryStoreError("repository memory snapshot JSON is corrupt") from exc
            snapshot = _snapshot_from_payload(payload)
            if snapshot.fingerprint != fingerprint:
                raise RepositoryMemoryStoreError("repository memory filename/index fingerprint mismatch")
            snapshots.append(snapshot)

        try:
            verify_repository_snapshot_chain(snapshots, self.registry)
        except RepositorySnapshotError as exc:
            raise RepositoryMemoryStoreError("repository memory chain verification failed") from exc
        return tuple(snapshots)

    def append(self, snapshot: RepositoryReviewSnapshot) -> Path:
        try:
            verify_repository_review_snapshot(snapshot, self.registry)
        except RepositorySnapshotError as exc:
            raise RepositoryMemoryStoreError("invalid repository snapshot") from exc

        repo_dir = self._repo_dir(snapshot.registry_entry_id)
        repo_dir.mkdir(parents=True, exist_ok=True)
        existing = self.list_snapshots(snapshot.registry_entry_id)
        expected_previous = existing[-1].fingerprint if existing else None
        if snapshot.previous_snapshot_fingerprint != expected_previous:
            raise RepositoryMemoryStoreError("append would fork or rewrite repository memory history")

        snapshot_path = self._snapshot_path(snapshot.registry_entry_id, snapshot.fingerprint)
        if snapshot_path.exists():
            raise RepositoryMemoryStoreError("repository snapshot already exists; store is append-only")

        payload = json.dumps(asdict(snapshot), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        fd, temp_name = tempfile.mkstemp(prefix=".snapshot-", suffix=".json", dir=repo_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, snapshot_path)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise

        index_path = self._index_path(snapshot.registry_entry_id)
        index_record = json.dumps(
            {
                "fingerprint": snapshot.fingerprint,
                "commit_sha": snapshot.commit_sha,
                "reviewed_at": snapshot.reviewed_at,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            with index_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(index_record + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except Exception as exc:
            # Never leave an unindexed snapshot as apparent committed history.
            snapshot_path.unlink(missing_ok=True)
            raise RepositoryMemoryStoreError("failed to commit repository memory index") from exc

        return snapshot_path
