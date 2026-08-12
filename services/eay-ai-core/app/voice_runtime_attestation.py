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
    return VoiceRuntimeArtifactSeal(**payload, fingerprint=_sha256(payload))
