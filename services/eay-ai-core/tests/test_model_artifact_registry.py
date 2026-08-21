import sqlite3

import pytest

from app.model_artifact_registry import ArtifactRegistration, ModelArtifactRegistry, artifact_provenance_fingerprint
from app.training_job_registry import TrainingJobRegistration


DATASET = "b" * 64
CHAIN = "c" * 64
EVAL_DATASET = "e" * 64


def seed_job(registry: ModelArtifactRegistry) -> str:
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
            VALUES ('manifest-art',?,?,?,?,1,?,1,'reviewer','REF-1','2026-08-11T00:00:00+00:00')""",
            (DATASET, "f" * 64, "9" * 64, EVAL_DATASET, CHAIN),
        )
    spec = {
        "job_version": "1", "method": "lora", "base_model": "local-base",
        "base_model_sha256": "1" * 64, "base_model_license_id": "apache-2.0",
        "training_manifest_chain_sha256": CHAIN, "dataset_sha256": DATASET,
        "eval_dataset_sha256": EVAL_DATASET, "seed": 42, "epochs": 2,
        "learning_rate": 0.0002, "batch_size": 2, "gradient_accumulation_steps": 8,
        "max_seq_length": 2048, "lora_rank": 16, "lora_alpha": 32,
        "lora_dropout": 0.05, "precision": "bf16", "local_only": True,
        "allow_remote_code": False, "allow_network_during_training": False,
    }
    return registry.training_jobs.register(
        TrainingJobRegistration(spec=spec, approved_by="reviewer", approval_reference="JOB-1")
    ).fingerprint


def test_artifact_registration_binds_sha_to_registered_training_job(tmp_path):
    registry = ModelArtifactRegistry(tmp_path / "eay.db")
    job = seed_job(registry)
    payload = ArtifactRegistration(
        training_job_fingerprint=job,
        artifact_sha256="a" * 64,
        artifact_format="safetensors",
        local_path_reference="artifacts/eay-ops-0.2",
        produced_by="local-trainer",
        approval_reference="ART-1",
    )
    record = registry.register(payload)
    assert record.provenance_fingerprint == artifact_provenance_fingerprint(payload)
    assert registry.verify(artifact_sha256="a" * 64, training_job_fingerprint=job).id == record.id


def test_artifact_registration_rejects_unregistered_job(tmp_path):
    registry = ModelArtifactRegistry(tmp_path / "eay.db")
    payload = ArtifactRegistration(
        training_job_fingerprint="d" * 64, artifact_sha256="a" * 64,
        artifact_format="safetensors", local_path_reference="artifacts/x",
        produced_by="local-trainer", approval_reference="ART-1",
    )
    with pytest.raises(KeyError, match="training_job_not_found"):
        registry.register(payload)


def test_artifact_verification_rejects_job_mismatch(tmp_path):
    registry = ModelArtifactRegistry(tmp_path / "eay.db")
    job = seed_job(registry)
    registry.register(ArtifactRegistration(
        training_job_fingerprint=job, artifact_sha256="a" * 64,
        artifact_format="safetensors", local_path_reference="artifacts/x",
        produced_by="local-trainer", approval_reference="ART-1",
    ))
    with pytest.raises(ValueError, match="model_artifact_training_job_mismatch"):
        registry.verify(artifact_sha256="a" * 64, training_job_fingerprint="9" * 64)
