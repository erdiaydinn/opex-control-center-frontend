import hashlib
import json
import sqlite3
from datetime import date

import pytest

from app.historical_legal_rag_evals import HistoricalLegalRagCase, evaluate_historical_legal_rag
from app.model_artifact_provenance import (
    ArtifactRegistration as PromotionArtifactRegistration,
    CanaryEvidenceRegistration,
    ModelArtifactProvenanceRegistry,
)
from app.model_artifact_registry import ArtifactRegistration as RegistryArtifactRegistration
from app.model_promotion_gate import ModelPromotionGate, PromotionRequest
from app.model_registry import ApprovalRequest, CanaryRequest, EvalSummary, ModelCandidateCreate, ModelRegistry
from app.release_evidence_registry import ReleaseEvaluationEvidenceRegistry
from app.safety_evals import SafetyEvalCase, evaluate_safety_evals
from app.training_execution import (
    TrainingExecutionReceiptCreate,
    TrainingExecutionRegistry,
    TrainingExecutionRequest,
    dataset_sha256_from_file,
    sha256_path,
)
from app.training_gate import canonical_dataset_sha256
from app.training_job_registry import TrainingJobRegistration

TRAIN_EXAMPLES = [{"messages": [{"role": "user", "content": "train question"}, {"role": "assistant", "content": "train answer"}], "metadata": {"human_approved": True, "contains_personal_data": False, "reason": "reviewed"}}]
EVAL_EXAMPLES = [{"messages": [{"role": "user", "content": "eval question"}, {"role": "assistant", "content": "eval answer"}], "metadata": {"human_approved": True, "contains_personal_data": False, "reason": "reviewed"}}]
DATASET = canonical_dataset_sha256(TRAIN_EXAMPLES)
CHAIN = "c" * 64
EVAL_DATASET = canonical_dataset_sha256(EVAL_EXAMPLES)
BASE_BYTES = b"eay-local-base-model"
BASE_SHA = hashlib.sha256(BASE_BYTES).hexdigest()
ARTIFACT_BYTES = b"eay-trained-adapter-artifact"
ARTIFACT = hashlib.sha256(ARTIFACT_BYTES).hexdigest()


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
        "base_model_sha256": BASE_SHA, "base_model_license_id": "apache-2.0",
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
    fixture_root = registry.db_path.parent
    base_path = fixture_root / "local-base-model.bin"
    train_path = fixture_root / "train.json"
    eval_path = fixture_root / "eval.json"
    artifact_path = fixture_root / "trained-adapter.safetensors"
    base_path.write_bytes(BASE_BYTES)
    train_path.write_text(json.dumps(TRAIN_EXAMPLES), encoding="utf-8")
    eval_path.write_text(json.dumps(EVAL_EXAMPLES), encoding="utf-8")
    assert sha256_path(base_path) == BASE_SHA
    assert dataset_sha256_from_file(train_path) == DATASET
    assert dataset_sha256_from_file(eval_path) == EVAL_DATASET
    executions = TrainingExecutionRegistry(registry.db_path)
    plan = executions.create_plan(TrainingExecutionRequest(
        training_job_fingerprint=job.fingerprint,
        base_model_path=str(base_path),
        training_dataset_path=str(train_path),
        eval_dataset_path=str(eval_path),
        output_path=str(artifact_path),
        requested_by="training-operator",
        execution_reference="TRAIN-TEST-1",
    ))
    artifact_path.write_bytes(ARTIFACT_BYTES)
    executions.register_receipt(TrainingExecutionReceiptCreate(
        plan_fingerprint=plan.fingerprint,
        executor="local-test-worker",
        execution_reference="TRAIN-TEST-1:exit-0",
    ))
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


def _release_evidence(db_path, *, eval_dataset=EVAL_DATASET, chain=CHAIN):
    historical = evaluate_historical_legal_rag([
        HistoricalLegalRagCase(
            case_id=f"historical-{idx}", as_of=date(2026, 6, 1),
            expected_source_ids=(f"legal-{idx}",), retrieved_source_ids=(f"legal-{idx}",),
            temporal_resolution_fingerprint=f"{idx % 10}" * 64,
        )
        for idx in range(20)
    ])
    safety = evaluate_safety_evals([
        SafetyEvalCase(
            case_id=f"safety-{idx}", expected_evidence_ids=(f"e-{idx}",),
            cited_evidence_ids=(f"e-{idx}",), expected_tool_answer="42", actual_tool_answer="42",
        )
        for idx in range(20)
    ])
    return ReleaseEvaluationEvidenceRegistry(db_path).record(
        historical=historical,
        safety=safety,
        eval_dataset_sha256=eval_dataset,
        training_manifest_chain_sha256=chain,
    )


def test_artifact_requires_registered_training_job(tmp_path):
    provenance = ModelArtifactProvenanceRegistry(tmp_path / "eay.db")
    with pytest.raises(KeyError, match="training_job_not_found"):
        provenance.register_artifact(PromotionArtifactRegistration(
            training_job_fingerprint="d" * 64, artifact_sha256=ARTIFACT,
            format="safetensors", created_by="trainer", build_reference="BUILD-1",
        ))


def test_production_promotion_requires_registered_release_eval_evidence(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    model_id, job_fp = _seed(registry)
    provenance = ModelArtifactProvenanceRegistry(registry.db_path)
    provenance.register_artifact(PromotionArtifactRegistration(
        training_job_fingerprint=job_fp, artifact_sha256=ARTIFACT,
        format="safetensors", created_by="trainer", build_reference="BUILD-1",
    ))
    evidence = provenance.register_canary_evidence(_good_canary(model_id))
    with pytest.raises(KeyError, match="release_evaluation_evidence_not_found"):
        ModelPromotionGate(registry.db_path).promote(PromotionRequest(
            model_record_id=model_id, canary_evidence_fingerprint=evidence.fingerprint,
            release_evaluation_evidence_fingerprint="7" * 64,
            approved_by="release-manager", approval_reference="REL-MISSING-EVAL",
        ))


def test_release_eval_evidence_from_another_eval_dataset_cannot_promote(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    model_id, job_fp = _seed(registry)
    provenance = ModelArtifactProvenanceRegistry(registry.db_path)
    provenance.register_artifact(PromotionArtifactRegistration(
        training_job_fingerprint=job_fp, artifact_sha256=ARTIFACT,
        format="safetensors", created_by="trainer", build_reference="BUILD-1",
    ))
    canary = provenance.register_canary_evidence(_good_canary(model_id))
    foreign = _release_evidence(registry.db_path, eval_dataset="8" * 64)
    with pytest.raises(ValueError, match="release_evaluation_evidence_eval_dataset_mismatch"):
        ModelPromotionGate(registry.db_path).promote(PromotionRequest(
            model_record_id=model_id, canary_evidence_fingerprint=canary.fingerprint,
            release_evaluation_evidence_fingerprint=foreign.fingerprint,
            approved_by="release-manager", approval_reference="REL-CROSS-EVAL",
        ))


def test_release_eval_evidence_from_another_training_manifest_cannot_promote(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    model_id, job_fp = _seed(registry)
    provenance = ModelArtifactProvenanceRegistry(registry.db_path)
    provenance.register_artifact(PromotionArtifactRegistration(
        training_job_fingerprint=job_fp, artifact_sha256=ARTIFACT,
        format="safetensors", created_by="trainer", build_reference="BUILD-1",
    ))
    canary = provenance.register_canary_evidence(_good_canary(model_id))
    foreign = _release_evidence(registry.db_path, chain="7" * 64)
    with pytest.raises(ValueError, match="release_evaluation_evidence_training_manifest_mismatch"):
        ModelPromotionGate(registry.db_path).promote(PromotionRequest(
            model_record_id=model_id, canary_evidence_fingerprint=canary.fingerprint,
            release_evaluation_evidence_fingerprint=foreign.fingerprint,
            approved_by="release-manager", approval_reference="REL-CROSS-MANIFEST",
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
    release_evidence = _release_evidence(registry.db_path)
    assert evidence.passed is False
    with pytest.raises(ValueError, match="canary_evidence_release_gate_failed"):
        ModelPromotionGate(registry.db_path).promote(PromotionRequest(
            model_record_id=model_id, canary_evidence_fingerprint=evidence.fingerprint,
            release_evaluation_evidence_fingerprint=release_evidence.fingerprint,
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
    release_evidence = _release_evidence(registry.db_path)
    with sqlite3.connect(registry.db_path) as conn:
        conn.execute(
            "UPDATE model_registry SET artifact_provenance_fingerprint=? WHERE id=?",
            ("0" * 64, model_id),
        )
    with pytest.raises(ValueError, match="production_promotion_artifact_provenance_mismatch"):
        ModelPromotionGate(registry.db_path).promote(PromotionRequest(
            model_record_id=model_id, canary_evidence_fingerprint=evidence.fingerprint,
            release_evaluation_evidence_fingerprint=release_evidence.fingerprint,
            approved_by="release-manager", approval_reference="REL-TAMPER",
        ))


def test_production_promotion_binds_registered_artifact_evals_canary_and_human_approval(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    model_id, job_fp = _seed(registry)
    provenance = ModelArtifactProvenanceRegistry(registry.db_path)
    artifact = provenance.register_artifact(PromotionArtifactRegistration(
        training_job_fingerprint=job_fp, artifact_sha256=ARTIFACT,
        format="safetensors", created_by="trainer", build_reference="BUILD-1",
    ))
    evidence = provenance.register_canary_evidence(_good_canary(model_id))
    release_evidence = _release_evidence(registry.db_path)
    assert evidence.passed is True

    proof = ModelPromotionGate(registry.db_path).promote(PromotionRequest(
        model_record_id=model_id, canary_evidence_fingerprint=evidence.fingerprint,
        release_evaluation_evidence_fingerprint=release_evidence.fingerprint,
        approved_by="release-manager", approval_reference="REL-1",
    ))
    assert len(proof.fingerprint) == 64
    assert len(proof.release_proof_fingerprint) == 64
    assert len(proof.offline_eval_fingerprint) == 64
    assert proof.release_evaluation_evidence_fingerprint == release_evidence.fingerprint
    assert proof.historical_legal_eval_fingerprint == release_evidence.historical_legal_fingerprint
    assert proof.safety_eval_fingerprint == release_evidence.safety_eval_fingerprint
    assert proof.eval_dataset_sha256 == EVAL_DATASET
    assert proof.training_manifest_chain_sha256 == CHAIN
    assert proof.artifact_sha256 == artifact.artifact_sha256
    assert proof.training_job_fingerprint == job_fp
    assert len(proof.training_execution_receipt_fingerprint) == 64

    with sqlite3.connect(registry.db_path) as conn:
        status = conn.execute("SELECT status FROM model_registry WHERE id=?", (model_id,)).fetchone()[0]
        row = conn.execute(
            """SELECT release_proof_fingerprint,offline_eval_fingerprint,
            release_evaluation_evidence_fingerprint,historical_legal_eval_fingerprint,
            safety_eval_fingerprint,eval_dataset_sha256,training_manifest_chain_sha256,
            artifact_provenance_fingerprint,training_execution_receipt_fingerprint FROM model_production_promotions"""
        ).fetchone()
    assert status == "production"
    assert row == (
        proof.release_proof_fingerprint,
        proof.offline_eval_fingerprint,
        proof.release_evaluation_evidence_fingerprint,
        proof.historical_legal_eval_fingerprint,
        proof.safety_eval_fingerprint,
        proof.eval_dataset_sha256,
        proof.training_manifest_chain_sha256,
        proof.artifact_provenance_fingerprint,
        proof.training_execution_receipt_fingerprint,
    )

    with pytest.raises(ValueError, match="production_promotion_requires_canary_status"):
        ModelPromotionGate(registry.db_path).promote(PromotionRequest(
            model_record_id=model_id, canary_evidence_fingerprint=evidence.fingerprint,
            release_evaluation_evidence_fingerprint=release_evidence.fingerprint,
            approved_by="release-manager", approval_reference="REL-2",
        ))


def test_governed_promotion_rejects_stored_offline_eval_fingerprint_tampering(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    model_id, job_fp = _seed(registry)
    provenance = ModelArtifactProvenanceRegistry(registry.db_path)
    provenance.register_artifact(PromotionArtifactRegistration(
        training_job_fingerprint=job_fp, artifact_sha256=ARTIFACT,
        format="safetensors", created_by="trainer", build_reference="BUILD-OFFLINE-TAMPER",
    ))
    canary = provenance.register_canary_evidence(_good_canary(model_id))
    release_evidence = _release_evidence(registry.db_path)
    with sqlite3.connect(registry.db_path) as conn:
        conn.execute(
            "UPDATE model_registry SET offline_eval_fingerprint=? WHERE id=?",
            ("0" * 64, model_id),
        )
    with pytest.raises(ValueError, match="model_offline_eval_provenance_mismatch"):
        ModelPromotionGate(registry.db_path).promote(PromotionRequest(
            model_record_id=model_id,
            canary_evidence_fingerprint=canary.fingerprint,
            release_evaluation_evidence_fingerprint=release_evidence.fingerprint,
            approved_by="release-manager",
            approval_reference="REL-OFFLINE-TAMPER",
        ))
