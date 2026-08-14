from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .license_gate import assert_model_license_allowed
from .voice_adapter_candidates import candidate_by_id
from .voice_adapter_promotion import VoiceAdapterPromotion, adapter_fingerprint
from .voice_runtime import VoiceAdapterSpec


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_sha256(value: str | None) -> bool:
    return bool(value) and len(str(value)) == 64 and all(ch in "0123456789abcdef" for ch in str(value))


def hash_regular_file(path: Path, *, max_bytes: int = 1024 * 1024 * 1024) -> tuple[str, int]:
    """Hash one exact local runtime artifact without following symlinks."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("voice_runtime_artifact_symlink_forbidden")
    try:
        stat = path.stat()
    except FileNotFoundError as exc:
        raise ValueError("voice_runtime_artifact_missing") from exc
    if not path.is_file():
        raise ValueError("voice_runtime_artifact_regular_file_required")
    if stat.st_size <= 0 or stat.st_size > max_bytes:
        raise ValueError("voice_runtime_artifact_size_invalid")
    digest = hashlib.sha256()
    total = 0
    with path.open("rb", buffering=0) as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("voice_runtime_artifact_size_invalid")
            digest.update(chunk)
    return digest.hexdigest(), total


@dataclass(frozen=True)
class VoiceRuntimeDirectoryEntry:
    relative_path: str
    sha256: str
    size_bytes: int

    def validate(self) -> None:
        path = self.relative_path.strip()
        if not path or path.startswith("/") or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
            raise ValueError("voice_runtime_directory_relative_path_invalid")
        if not _valid_sha256(self.sha256):
            raise ValueError("voice_runtime_directory_file_hash_invalid")
        if self.size_bytes <= 0:
            raise ValueError("voice_runtime_directory_file_size_invalid")


@dataclass(frozen=True)
class VoiceRuntimeDirectoryManifest:
    logical_name: str
    file_count: int
    total_size_bytes: int
    entries: tuple[VoiceRuntimeDirectoryEntry, ...]
    fingerprint: str

    def validate(self) -> None:
        logical_name = self.logical_name.strip()
        if len(logical_name) < 2 or "/" in logical_name or "\\" in logical_name:
            raise ValueError("voice_runtime_directory_logical_name_invalid")
        if self.file_count < 1 or self.file_count != len(self.entries):
            raise ValueError("voice_runtime_directory_file_count_invalid")
        if self.total_size_bytes < 1 or self.total_size_bytes != sum(item.size_bytes for item in self.entries):
            raise ValueError("voice_runtime_directory_total_size_invalid")
        for item in self.entries:
            item.validate()
        paths = tuple(item.relative_path for item in self.entries)
        if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise ValueError("voice_runtime_directory_entries_not_canonical")
        payload = {
            "logical_name": logical_name,
            "file_count": self.file_count,
            "total_size_bytes": self.total_size_bytes,
            "entries": tuple(
                {"relative_path": item.relative_path, "sha256": item.sha256, "size_bytes": item.size_bytes}
                for item in self.entries
            ),
        }
        if not _valid_sha256(self.fingerprint) or _sha256(payload) != self.fingerprint:
            raise ValueError("voice_runtime_directory_fingerprint_drift")


def seal_runtime_directory_manifest(
    root: Path,
    *,
    logical_name: str,
    max_files: int = 20_000,
    max_total_bytes: int = 512 * 1024 * 1024,
    max_file_bytes: int = 64 * 1024 * 1024,
) -> VoiceRuntimeDirectoryManifest:
    """Deterministically attest a runtime resource directory without absolute paths.

    Symlinks are rejected at every level, entries are sorted by POSIX relative path,
    and neither mtimes nor machine-local root paths enter the fingerprint. This makes
    the manifest reproducible across hosts while preventing path redirection attacks.
    Any traversal error fails closed instead of silently producing a partial manifest.
    """
    root = Path(root)
    if root.is_symlink():
        raise ValueError("voice_runtime_directory_symlink_forbidden")
    if not root.exists():
        raise ValueError("voice_runtime_directory_missing")
    if not root.is_dir():
        raise ValueError("voice_runtime_directory_required")
    if not 1 <= int(max_files) <= 1_000_000:
        raise ValueError("voice_runtime_directory_file_limit_invalid")
    if not 1 <= int(max_total_bytes) <= 16 * 1024 * 1024 * 1024:
        raise ValueError("voice_runtime_directory_total_limit_invalid")
    if not 1 <= int(max_file_bytes) <= int(max_total_bytes):
        raise ValueError("voice_runtime_directory_per_file_limit_invalid")

    def _walk_error(exc: OSError) -> None:
        raise ValueError("voice_runtime_directory_walk_failed") from exc

    entries: list[VoiceRuntimeDirectoryEntry] = []
    total_size = 0
    for current_root, dir_names, file_names in os.walk(
        root,
        topdown=True,
        onerror=_walk_error,
        followlinks=False,
    ):
        current = Path(current_root)
        dir_names.sort()
        file_names.sort()
        for name in dir_names:
            if (current / name).is_symlink():
                raise ValueError("voice_runtime_directory_symlink_forbidden")
        for name in file_names:
            path = current / name
            if path.is_symlink():
                raise ValueError("voice_runtime_directory_symlink_forbidden")
            digest, size = hash_regular_file(path, max_bytes=max_file_bytes)
            total_size += size
            if total_size > max_total_bytes:
                raise ValueError("voice_runtime_directory_total_size_exceeded")
            relative = path.relative_to(root).as_posix()
            entry = VoiceRuntimeDirectoryEntry(relative_path=relative, sha256=digest, size_bytes=size)
            entry.validate()
            entries.append(entry)
            if len(entries) > max_files:
                raise ValueError("voice_runtime_directory_file_count_exceeded")

    entries.sort(key=lambda item: item.relative_path)
    if not entries:
        raise ValueError("voice_runtime_directory_empty")
    payload = {
        "logical_name": logical_name.strip(),
        "file_count": len(entries),
        "total_size_bytes": total_size,
        "entries": tuple(
            {"relative_path": item.relative_path, "sha256": item.sha256, "size_bytes": item.size_bytes}
            for item in entries
        ),
    }
    manifest = VoiceRuntimeDirectoryManifest(
        logical_name=logical_name.strip(),
        file_count=len(entries),
        total_size_bytes=total_size,
        entries=tuple(entries),
        fingerprint=_sha256(payload),
    )
    manifest.validate()
    return manifest


@dataclass(frozen=True)
class VoiceRuntimeArtifactSeal:
    candidate_id: str
    adapter_id: str
    kind: str
    implementation: str
    runtime_license_id: str
    artifact_license_id: str
    runtime_artifact_sha256: str
    runtime_artifact_size_bytes: int
    model_or_voice_artifact_sha256: str
    adapter_fingerprint: str
    promotion_fingerprint: str
    deployment_manifest_fingerprint: str
    fingerprint: str

    def validate(self) -> None:
        if len(self.candidate_id.strip()) < 3 or len(self.adapter_id.strip()) < 3:
            raise ValueError("voice_runtime_seal_identity_invalid")
        if self.kind not in {"wakeword", "vad", "stt", "tts"}:
            raise ValueError("voice_runtime_seal_kind_invalid")
        if len(self.implementation.strip()) < 3:
            raise ValueError("voice_runtime_seal_implementation_invalid")
        assert_model_license_allowed(self.runtime_license_id)
        assert_model_license_allowed(self.artifact_license_id)
        if self.runtime_artifact_size_bytes <= 0:
            raise ValueError("voice_runtime_seal_size_invalid")
        for value, code in (
            (self.runtime_artifact_sha256, "voice_runtime_seal_runtime_hash_invalid"),
            (self.model_or_voice_artifact_sha256, "voice_runtime_seal_model_hash_invalid"),
            (self.adapter_fingerprint, "voice_runtime_seal_adapter_fingerprint_invalid"),
            (self.promotion_fingerprint, "voice_runtime_seal_promotion_fingerprint_invalid"),
            (self.deployment_manifest_fingerprint, "voice_runtime_seal_manifest_invalid"),
            (self.fingerprint, "voice_runtime_seal_fingerprint_invalid"),
        ):
            if not _valid_sha256(value):
                raise ValueError(code)


def seal_local_voice_runtime(
    *,
    candidate_id: str,
    adapter: VoiceAdapterSpec,
    promotion: VoiceAdapterPromotion,
    deployment_manifest_fingerprint: str,
    runtime_artifact_path: Path,
    expected_runtime_artifact_sha256: str,
) -> VoiceRuntimeArtifactSeal:
    """Seal exact executable/runtime bytes to an already promoted adapter contract.

    Candidate metadata is discovery input only. Execution requires the current adapter
    and human promotion to match it, plus an independently supplied expected SHA-256
    for the local runtime file. This prevents a package/version name from standing in
    for the exact bytes that will execute.
    """
    candidate = candidate_by_id(candidate_id)
    candidate.validate()
    adapter.validate()
    if not adapter.local:
        raise ValueError("voice_runtime_local_adapter_required")
    if adapter.kind != candidate.kind or adapter.implementation != candidate.implementation:
        raise ValueError("voice_runtime_candidate_contract_mismatch")
    if adapter.resolved_runtime_license_id != candidate.runtime_license_id.strip().lower():
        raise ValueError("voice_runtime_candidate_license_mismatch")
    if promotion.adapter_id != adapter.adapter_id or promotion.kind != adapter.kind:
        raise ValueError("voice_runtime_promotion_adapter_mismatch")
    current_adapter_fp = adapter_fingerprint(adapter)
    if promotion.adapter_fingerprint != current_adapter_fp:
        raise ValueError("voice_runtime_promotion_contract_drift")
    if promotion.adapter_artifact_sha256 != adapter.artifact_sha256:
        raise ValueError("voice_runtime_model_artifact_drift")
    if not _valid_sha256(adapter.artifact_sha256):
        raise ValueError("voice_runtime_model_artifact_hash_required")
    if not _valid_sha256(promotion.fingerprint):
        raise ValueError("voice_runtime_promotion_fingerprint_invalid")
    if not _valid_sha256(deployment_manifest_fingerprint):
        raise ValueError("voice_runtime_deployment_manifest_invalid")
    if not _valid_sha256(expected_runtime_artifact_sha256):
        raise ValueError("voice_runtime_expected_artifact_hash_invalid")
    assert_model_license_allowed(adapter.resolved_runtime_license_id)
    assert_model_license_allowed(adapter.resolved_artifact_license_id)

    runtime_digest, runtime_size = hash_regular_file(runtime_artifact_path)
    if runtime_digest != expected_runtime_artifact_sha256:
        raise ValueError("voice_runtime_artifact_hash_mismatch")

    payload = {
        "candidate_id": candidate.candidate_id,
        "adapter_id": adapter.adapter_id,
        "kind": adapter.kind,
        "implementation": adapter.implementation,
        "runtime_license_id": adapter.resolved_runtime_license_id,
        "artifact_license_id": adapter.resolved_artifact_license_id,
        "runtime_artifact_sha256": runtime_digest,
        "runtime_artifact_size_bytes": runtime_size,
        "model_or_voice_artifact_sha256": adapter.artifact_sha256,
        "adapter_fingerprint": current_adapter_fp,
        "promotion_fingerprint": promotion.fingerprint,
        "deployment_manifest_fingerprint": deployment_manifest_fingerprint,
    }
    seal = VoiceRuntimeArtifactSeal(**payload, fingerprint=_sha256(payload))
    seal.validate()
    return seal
