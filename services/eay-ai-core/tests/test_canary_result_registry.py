import sqlite3

import pytest

from app.canary_evals import CanaryMetrics
from app.canary_result_registry import CanaryResultRegistration
from app.model_artifact_registry import ArtifactRegistration
from app.model_registry import (
    ApprovalRequest,
    CanaryRequest,
    EvalSummary,
    ModelCandidateCreate,
    ModelRegistry,
    PromotionRequest,
)
from app.training_job_registry import TrainingJobRegistration


DATASET = "b" * 64
CHAIN = "c" * 64
EVAL_DATASET = "e" * 64
ARTIFACT = "a" * 64


def good_metrics(**updates):
    values = dict(
        sample_size=250,
        error_rate=0.01,
        grounded_answer_rate=0.99,
        citation_validity_rate=1.0,
        unsafe_action_rate=0.0,
        kvkk_leak_rate=0.0,
        p95_latency_ms=2500.0,
    )
    values.update(updates)
    return CanaryMetrics(**values)


def seed_canary(registry: ModelRegistry):
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
    artifact = registry.artifacts.register(
        ArtifactRegistration(
            training_job_fingerprint=job.fingerprint,
            artifact_sha256=ARTIFACT,
            artifact_format="safetensors",
            local_path_reference="artifacts/eay-ops-0.2",
            produced_by="local-trainer",
            approval_reference="ART-1",
        )
    )
    record = registry.create(
        ModelCandidateCreate(
            model_name="eay-ops", model_version="0.2", base_model="local-base",
            artifact_sha256=ARTIFACT, license_id="apache-2.0",
            training_dataset_sha256=DATASET,
            training_manifest_chain_sha256=CHAIN,
            training_job_fingerprint=job.fingerprint,
            eval_dataset_sha256=EVAL_DATASET,
            evals=EvalSummary(
                legal_grounding_rate=0.995, citation_validity_rate=1.0,
                unsafe_tool_call_rate=0.0, regression_pass_rate=0.99,
                kvkk_leak_rate=0.0, eval_set_version="2026-08-11",
            ),
        )
    )
    registry.approve(record.id, ApprovalRequest(approved_by="ops", note="offline eval pass"))
    canary = registry.set_canary(record.id, CanaryRequest(percent=10, approved_by="ops"))
    return canary, artifact


def test_production_promotion_requires_registered_passing_canary_result(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    canary, artifact = seed_canary(registry)
    result = registry.canary_results.register(
        CanaryResultRegistration(
            model_record_id=canary.id,
            artifact_provenance_fingerprint=artifact.provenance_fingerprint,
            current_percent=10,
            metrics=good_metrics(),
            evaluated_by="canary-evaluator",
            evidence_reference="CANARY-2026-08-11-01",
        )
    )
    assert result.passed is True
    with pytest.raises(ValueError, match="production_promotion_requires_governed_promotion_gate"):
        registry.promote(
            canary.id,
            PromotionRequest(
                canary_result_fingerprint=result.result_fingerprint,
                approved_by="release-owner",
                note="legacy canary evidence is not sufficient for production",
            ),
        )


def test_failed_canary_cannot_promote(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    canary, artifact = seed_canary(registry)
    result = registry.canary_results.register(
        CanaryResultRegistration(
            model_record_id=canary.id,
            artifact_provenance_fingerprint=artifact.provenance_fingerprint,
            current_percent=10,
            metrics=good_metrics(kvkk_leak_rate=0.01),
            evaluated_by="canary-evaluator",
            evidence_reference="CANARY-FAIL",
        )
    )
    assert result.passed is False
    assert "kvkk_leak_detected" in result.violations
    with pytest.raises(ValueError, match="production_promotion_requires_governed_promotion_gate"):
        registry.promote(
            canary.id,
            PromotionRequest(
                canary_result_fingerprint=result.result_fingerprint,
                approved_by="release-owner",
                note="legacy promotion remains unavailable",
            ),
        )


def test_canary_result_rejects_artifact_provenance_mismatch(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    canary, _ = seed_canary(registry)
    with pytest.raises(ValueError, match="canary_result_artifact_provenance_mismatch"):
        registry.canary_results.register(
            CanaryResultRegistration(
                model_record_id=canary.id,
                artifact_provenance_fingerprint="d" * 64,
                current_percent=10,
                metrics=good_metrics(),
                evaluated_by="canary-evaluator",
                evidence_reference="CANARY-TAMPER",
            )
        )


def test_offline_eval_tampering_blocks_promotion(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    canary, artifact = seed_canary(registry)
    result = registry.canary_results.register(
        CanaryResultRegistration(
            model_record_id=canary.id,
            artifact_provenance_fingerprint=artifact.provenance_fingerprint,
            current_percent=10,
            metrics=good_metrics(),
            evaluated_by="canary-evaluator",
            evidence_reference="CANARY-OK",
        )
    )
    with sqlite3.connect(registry.db_path) as conn:
        conn.execute(
            "UPDATE model_registry SET offline_eval_fingerprint=? WHERE id=?",
            ("0" * 64, canary.id),
        )
    with pytest.raises(ValueError, match="production_promotion_requires_governed_promotion_gate"):
        registry.promote(
            canary.id,
            PromotionRequest(
                canary_result_fingerprint=result.result_fingerprint,
                approved_by="release-owner",
                note="legacy path cannot be used to mutate production",
            ),
        )
