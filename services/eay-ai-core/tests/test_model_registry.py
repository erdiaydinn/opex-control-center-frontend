import sqlite3

import pytest
from pydantic import ValidationError

from app.model_artifact_registry import ArtifactRegistration
from app.model_registry import ApprovalRequest, CanaryRequest, EvalSummary, ModelCandidateCreate, ModelRegistry
from app.training_job_registry import TrainingJobRegistration


DATASET = "b" * 64
CHAIN = "c" * 64
EVAL_DATASET = "e" * 64
ARTIFACT = "a" * 64


def evals():
    return EvalSummary(
        legal_grounding_rate=0.995,
        citation_validity_rate=1.0,
        unsafe_tool_call_rate=0.0,
        regression_pass_rate=0.99,
        kvkk_leak_rate=0.0,
        eval_set_version="2026-08-10",
    )


def seed_registered_job(registry: ModelRegistry, *, register_artifact: bool = True) -> str:
    with sqlite3.connect(registry.db_path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS training_dataset_manifests (
            id TEXT PRIMARY KEY, dataset_sha256 TEXT NOT NULL UNIQUE,
            dataset_integrity_sha256 TEXT, quality_lineage_sha256 TEXT,
            eval_dataset_sha256 TEXT, eval_example_count INTEGER NOT NULL DEFAULT 0,
            chain_sha256 TEXT NOT NULL UNIQUE, example_count INTEGER NOT NULL,
            approved_by TEXT NOT NULL, approval_reference TEXT NOT NULL,
            parent_manifest_id TEXT, parent_chain_sha256 TEXT, created_at TEXT NOT NULL)"""
        )
        conn.execute(
            """INSERT INTO training_dataset_manifests(
            id,dataset_sha256,dataset_integrity_sha256,quality_lineage_sha256,
            eval_dataset_sha256,eval_example_count,chain_sha256,example_count,
            approved_by,approval_reference,created_at)
            VALUES ('manifest-1',?,?,?,?,1,?,1,'reviewer','REF-1','2026-08-11T00:00:00+00:00')""",
            (DATASET, "f" * 64, "9" * 64, EVAL_DATASET, CHAIN),
        )
    spec = {
        "job_version": "1",
        "method": "lora",
        "base_model": "local-base",
        "base_model_sha256": "1" * 64,
        "base_model_license_id": "apache-2.0",
        "training_manifest_chain_sha256": CHAIN,
        "dataset_sha256": DATASET,
        "eval_dataset_sha256": EVAL_DATASET,
        "seed": 42,
        "epochs": 2,
        "learning_rate": 0.0002,
        "batch_size": 2,
        "gradient_accumulation_steps": 8,
        "max_seq_length": 2048,
        "lora_rank": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "precision": "bf16",
        "local_only": True,
        "allow_remote_code": False,
        "allow_network_during_training": False,
    }
    fingerprint = registry.training_jobs.register(
        TrainingJobRegistration(spec=spec, approved_by="reviewer", approval_reference="JOB-1")
    ).fingerprint
    if register_artifact:
        registry.artifacts.register(
            ArtifactRegistration(
                training_job_fingerprint=fingerprint,
                artifact_sha256=ARTIFACT,
                artifact_format="safetensors",
                local_path_reference="artifacts/eay-ops-0.2",
                produced_by="local-trainer",
                approval_reference="ART-1",
            )
        )
    return fingerprint


def good_candidate(fingerprint="d" * 64):
    return ModelCandidateCreate(
        model_name="eay-ops",
        model_version="0.2",
        base_model="local-base",
        artifact_sha256=ARTIFACT,
        license_id="apache-2.0",
        training_dataset_sha256=DATASET,
        training_manifest_chain_sha256=CHAIN,
        training_job_fingerprint=fingerprint,
        eval_dataset_sha256=EVAL_DATASET,
        evals=evals(),
    )


def test_good_candidate_requires_registered_job_and_artifact_before_canary(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    fingerprint = seed_registered_job(registry)
    record = registry.create(good_candidate(fingerprint))
    assert record.training_job_fingerprint == fingerprint
    assert record.artifact_provenance_fingerprint is not None
    with pytest.raises(ValueError):
        registry.set_canary(record.id, CanaryRequest(percent=5, approved_by="ops"))
    approved = registry.approve(record.id, ApprovalRequest(approved_by="ops", note="evals checked"))
    assert approved.status == "approved"
    canary = registry.set_canary(record.id, CanaryRequest(percent=10, approved_by="ops"))
    assert canary.status == "canary"


def test_model_candidate_rejects_unregistered_training_job(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    with pytest.raises(KeyError, match="training_job_not_found"):
        registry.create(good_candidate())


def test_model_candidate_rejects_missing_registered_artifact(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    fingerprint = seed_registered_job(registry, register_artifact=False)
    with pytest.raises(KeyError, match="model_artifact_not_found"):
        registry.create(good_candidate(fingerprint))


def test_model_candidate_rejects_registered_job_lineage_mismatch(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    fingerprint = seed_registered_job(registry)
    candidate = good_candidate(fingerprint).model_copy(update={"base_model": "different-base"})
    with pytest.raises(ValueError, match="model_training_job_lineage_mismatch:base_model"):
        registry.create(candidate)


def test_model_candidate_rejects_partial_training_lineage():
    with pytest.raises(ValidationError, match="model_training_lineage_incomplete"):
        ModelCandidateCreate(
            model_name="eay-ops", model_version="partial", base_model="local-base",
            artifact_sha256=ARTIFACT, license_id="apache-2.0",
            training_dataset_sha256=DATASET, evals=evals(),
        )


def test_model_candidate_rejects_train_eval_collision():
    payload = good_candidate().model_dump()
    payload["eval_dataset_sha256"] = DATASET
    with pytest.raises(ValidationError, match="model_train_eval_dataset_collision"):
        ModelCandidateCreate(**payload)


def test_release_gate_blocks_kvkk_leak(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    fingerprint = seed_registered_job(registry)
    candidate = good_candidate(fingerprint).model_copy(update={
        "model_version": "0.3", "evals": evals().model_copy(update={"kvkk_leak_rate": 0.01}),
    })
    record = registry.create(candidate)
    with pytest.raises(ValueError, match="kvkk_leak_detected"):
        registry.approve(record.id, ApprovalRequest(approved_by="ops", note="should fail"))


def test_release_gate_blocks_unsafe_tool_calls(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    fingerprint = seed_registered_job(registry)
    candidate = good_candidate(fingerprint).model_copy(update={
        "model_version": "0.4", "evals": evals().model_copy(update={"unsafe_tool_call_rate": 0.001}),
    })
    record = registry.create(candidate)
    with pytest.raises(ValueError, match="unsafe_tool_calls_detected"):
        registry.approve(record.id, ApprovalRequest(approved_by="ops", note="should fail"))
