import sqlite3

import pytest

from app.model_artifact_provenance import (
    ArtifactRegistration as PromotionArtifactRegistration,
    CanaryEvidenceRegistration,
    ModelArtifactProvenanceRegistry,
)
from app.model_artifact_registry import ArtifactRegistration as RegistryArtifactRegistration
from app.model_promotion_gate import ModelPromotionGate, PromotionRequest
from app.model_registry import ApprovalRequest, CanaryRequest, EvalSummary, ModelCandidateCreate, ModelRegistry
from app.training_job_registry import TrainingJobRegistration

DATASET = "b" * 64
CHAIN = "c" * 64
EVAL_DATASET = "e" * 64
ARTIFACT = "a" * 64


def _seed(registry: ModelRegistry):
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
            VALUES ('manifest-1',?,?,?,?,10,?,10,'reviewer','REF-1','2026-08-11T00:00:00+00:00')""",
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
    job = registry.training_jobs.register(
        TrainingJobRegistration(spec=spec, approved_by="reviewer", approval_reference="JOB-1")
    )
    registry.artifacts.register(
        RegistryArtifactRegistration(
            training_job_fingerprint=job.fingerprint,
            artifact_sha256=ARTIFACT,
            artifact_format="safetensors",
            local_path_reference="artifacts/eay-ops/0.3/model.safetensors",
            produced_by="local-trainer",
            approval_reference="ARTIFACT-1",
        )
    )
    evals = EvalSummary(
        legal_grounding_rate=0.995, citation_validity_rate=1.0,
        unsafe_tool_call_rate=0.0, regression_pass_rate=0.99,
        kvkk_leak_rate=0.0, eval_set_version="2026-08-11",
    )
    model = registry.create(ModelCandidateCreate(
        model_name="eay-ops", model_version="0.3", base_model="local-base",
        artifact_sha256=ARTIFACT, license_id="apache-2.0",
        training_dataset_sha256=DATASET, training_manifest_chain_sha256=CHAIN,
        training_job_fingerprint=job.fingerprint, eval_dataset_sha256=EVAL_DATASET,
        evals=evals,
    ))
    registry.approve(model.id, ApprovalRequest(approved_by="human", note="offline eval passed"))
    registry.set_canary(model.id, CanaryRequest(percent=10, approved_by="human"))
    return model.id, job.fingerprint


def _good_canary(model_id):
    return CanaryEvidenceRegistration(
        model_record_id=model_id, artifact_sha256=ARTIFACT,
        eval_dataset_sha256=EVAL_DATASET, canary_percent=10, request_count=250,
        legal_grounding_rate=0.99, citation_validity_rate=1.0,
        unsafe_tool_call_rate=0.0, regression_pass_rate=0.99, kvkk_leak_rate=0.0,
        reviewer="canary-reviewer", evidence_reference="CANARY-1",
    )


def test_artifact_requires_registered_training_job(tmp_path):
    provenance = ModelArtifactProvenanceRegistry(tmp_path / "eay.db")
    with pytest.raises(KeyError, match="training_job_not_found"):
        provenance.register_artifact(PromotionArtifactRegistration(
            training_job_fingerprint="d" * 64, artifact_sha256=ARTIFACT,
            format="safetensors", created_by="trainer", build_reference="BUILD-1",
        ))


def test_failed_canary_cannot_promote(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    model_id, job_fp = _seed(registry)
    provenance = ModelArtifactProvenanceRegistry(registry.db_path)
    provenance.register_artifact(PromotionArtifactRegistration(
        training_job_fingerprint=job_fp, artifact_sha256=ARTIFACT,
        format="safetensors", created_by="trainer", build_reference="BUILD-1",
    ))
    weak = _good_canary(model_id).model_copy(update={"request_count": 20})
    evidence = provenance.register_canary_evidence(weak)
    assert evidence.passed is False
    with pytest.raises(ValueError, match="canary_evidence_release_gate_failed"):
        ModelPromotionGate(registry.db_path).promote(PromotionRequest(
            model_record_id=model_id, canary_evidence_fingerprint=evidence.fingerprint,
            approved_by="release-manager", approval_reference="REL-1",
        ))


def test_production_promotion_blocks_tampered_primary_artifact_provenance(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    model_id, job_fp = _seed(registry)
    provenance = ModelArtifactProvenanceRegistry(registry.db_path)
    provenance.register_artifact(PromotionArtifactRegistration(
        training_job_fingerprint=job_fp, artifact_sha256=ARTIFACT,
        format="safetensors", created_by="trainer", build_reference="BUILD-1",
    ))
    evidence = provenance.register_canary_evidence(_good_canary(model_id))
    with sqlite3.connect(registry.db_path) as conn:
        conn.execute(
            "UPDATE model_registry SET artifact_provenance_fingerprint=? WHERE id=?",
            ("0" * 64, model_id),
        )
    with pytest.raises(ValueError, match="production_promotion_artifact_provenance_mismatch"):
        ModelPromotionGate(registry.db_path).promote(PromotionRequest(
            model_record_id=model_id, canary_evidence_fingerprint=evidence.fingerprint,
            approved_by="release-manager", approval_reference="REL-TAMPER",
        ))


def test_production_promotion_binds_registered_artifact_canary_and_human_approval(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    model_id, job_fp = _seed(registry)
    provenance = ModelArtifactProvenanceRegistry(registry.db_path)
    artifact = provenance.register_artifact(PromotionArtifactRegistration(
        training_job_fingerprint=job_fp, artifact_sha256=ARTIFACT,
        format="safetensors", created_by="trainer", build_reference="BUILD-1",
    ))
    evidence = provenance.register_canary_evidence(_good_canary(model_id))
    assert evidence.passed is True

    proof = ModelPromotionGate(registry.db_path).promote(PromotionRequest(
        model_record_id=model_id, canary_evidence_fingerprint=evidence.fingerprint,
        approved_by="release-manager", approval_reference="REL-1",
    ))
    assert len(proof.fingerprint) == 64
    assert proof.artifact_sha256 == artifact.artifact_sha256
    assert proof.training_job_fingerprint == job_fp

    with sqlite3.connect(registry.db_path) as conn:
        status = conn.execute("SELECT status FROM model_registry WHERE id=?", (model_id,)).fetchone()[0]
        promotion_count = conn.execute("SELECT COUNT(*) FROM model_production_promotions").fetchone()[0]
    assert status == "production"
    assert promotion_count == 1

    with pytest.raises(ValueError, match="production_promotion_requires_canary_status"):
        ModelPromotionGate(registry.db_path).promote(PromotionRequest(
            model_record_id=model_id, canary_evidence_fingerprint=evidence.fingerprint,
            approved_by="release-manager", approval_reference="REL-2",
        ))
