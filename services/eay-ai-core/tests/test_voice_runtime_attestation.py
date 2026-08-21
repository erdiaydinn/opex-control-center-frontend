import hashlib
from dataclasses import replace

import pytest

import app.voice_runtime_attestation as attestation
from app.voice_adapter_candidates import candidate_by_id
from app.voice_adapter_promotion import VoiceAdapterPromotion, adapter_fingerprint
from app.voice_runtime_attestation import (
    hash_regular_file,
    seal_local_voice_runtime,
    seal_runtime_directory_manifest,
)


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


def test_runtime_directory_manifest_is_host_path_independent_and_deterministic(tmp_path):
    first = tmp_path / "first" / "espeak-ng-data"
    second = tmp_path / "second" / "espeak-ng-data"
    for root in (first, second):
        (root / "lang" / "gmw").mkdir(parents=True)
        (root / "phontab").write_bytes(b"phoneme-table")
        (root / "lang" / "gmw" / "en").write_bytes(b"english-data")

    a = seal_runtime_directory_manifest(first, logical_name="espeak-ng-data")
    b = seal_runtime_directory_manifest(second, logical_name="espeak-ng-data")

    assert a.fingerprint == b.fingerprint
    assert a.file_count == 2
    assert tuple(item.relative_path for item in a.entries) == ("lang/gmw/en", "phontab")


def test_runtime_directory_manifest_detects_resource_drift(tmp_path):
    root = tmp_path / "espeak-ng-data"
    root.mkdir()
    resource = root / "phontab"
    resource.write_bytes(b"v1")
    before = seal_runtime_directory_manifest(root, logical_name="espeak-ng-data")
    resource.write_bytes(b"v2")
    after = seal_runtime_directory_manifest(root, logical_name="espeak-ng-data")
    assert after.fingerprint != before.fingerprint


def test_runtime_directory_manifest_rejects_nested_symlink(tmp_path):
    root = tmp_path / "espeak-ng-data"
    root.mkdir()
    target = tmp_path / "outside"
    target.mkdir()
    (target / "data").write_bytes(b"external")
    link = root / "redirect"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    with pytest.raises(ValueError, match="voice_runtime_directory_symlink_forbidden"):
        seal_runtime_directory_manifest(root, logical_name="espeak-ng-data")


def test_runtime_directory_manifest_fails_closed_on_walk_error(tmp_path, monkeypatch):
    root = tmp_path / "espeak-ng-data"
    root.mkdir()
    (root / "phontab").write_bytes(b"seed")

    def broken_walk(path, *, topdown, onerror, followlinks):
        onerror(PermissionError("denied"))
        return iter(())

    monkeypatch.setattr(attestation.os, "walk", broken_walk)
    with pytest.raises(ValueError, match="voice_runtime_directory_walk_failed"):
        seal_runtime_directory_manifest(root, logical_name="espeak-ng-data")
