import hashlib
from dataclasses import replace

import pytest

from app.voice_adapter_candidates import candidate_by_id
from app.voice_adapter_promotion import VoiceAdapterPromotion, adapter_fingerprint
from app.voice_runtime_attestation import hash_regular_file, seal_local_voice_runtime


def _hash(ch: str) -> str:
    return ch * 64


def _adapter():
    return candidate_by_id("whisper-cpp-openai-whisper").build_spec(
        adapter_id="stt-prod-v1",
        artifact_sha256=_hash("a"),
    )


def _promotion(adapter):
    return VoiceAdapterPromotion(
        adapter_id=adapter.adapter_id,
        kind=adapter.kind,
        adapter_artifact_sha256=adapter.artifact_sha256,
        adapter_fingerprint=adapter_fingerprint(adapter),
        profile_fingerprint=_hash("b"),
        language_capability_fingerprints=(_hash("c"),),
        reviewer="voice-reviewer",
        approval_reference="VOICE-001",
        promoted_at="2026-08-12T09:00:00+00:00",
        fingerprint=_hash("d"),
    )


def test_runtime_attestation_binds_exact_runtime_bytes_model_and_promotion(tmp_path):
    runtime = tmp_path / "whisper-runtime.bin"
    runtime.write_bytes(b"exact-local-runtime-bytes")
    runtime_sha = hashlib.sha256(runtime.read_bytes()).hexdigest()
    adapter = _adapter()

    seal = seal_local_voice_runtime(
        candidate_id="whisper-cpp-openai-whisper",
        adapter=adapter,
        promotion=_promotion(adapter),
        deployment_manifest_fingerprint=_hash("e"),
        runtime_artifact_path=runtime,
        expected_runtime_artifact_sha256=runtime_sha,
    )

    assert seal.runtime_artifact_sha256 == runtime_sha
    assert seal.model_or_voice_artifact_sha256 == _hash("a")
    assert seal.promotion_fingerprint == _hash("d")
    assert len(seal.fingerprint) == 64


def test_runtime_attestation_rejects_tampered_runtime_bytes(tmp_path):
    runtime = tmp_path / "runtime.bin"
    runtime.write_bytes(b"runtime-v1")
    expected = hashlib.sha256(runtime.read_bytes()).hexdigest()
    runtime.write_bytes(b"runtime-v2")
    adapter = _adapter()

    with pytest.raises(ValueError, match="voice_runtime_artifact_hash_mismatch"):
        seal_local_voice_runtime(
            candidate_id="whisper-cpp-openai-whisper",
            adapter=adapter,
            promotion=_promotion(adapter),
            deployment_manifest_fingerprint=_hash("e"),
            runtime_artifact_path=runtime,
            expected_runtime_artifact_sha256=expected,
        )


def test_runtime_attestation_rejects_candidate_contract_drift(tmp_path):
    runtime = tmp_path / "runtime.bin"
    runtime.write_bytes(b"runtime")
    runtime_sha = hashlib.sha256(runtime.read_bytes()).hexdigest()
    adapter = replace(_adapter(), implementation="different-runtime")

    with pytest.raises(ValueError, match="voice_runtime_candidate_contract_mismatch"):
        seal_local_voice_runtime(
            candidate_id="whisper-cpp-openai-whisper",
            adapter=adapter,
            promotion=_promotion(adapter),
            deployment_manifest_fingerprint=_hash("e"),
            runtime_artifact_path=runtime,
            expected_runtime_artifact_sha256=runtime_sha,
        )


def test_runtime_artifact_hashing_rejects_symlinks(tmp_path):
    target = tmp_path / "target.bin"
    target.write_bytes(b"runtime")
    link = tmp_path / "runtime-link.bin"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    with pytest.raises(ValueError, match="voice_runtime_artifact_symlink_forbidden"):
        hash_regular_file(link)
