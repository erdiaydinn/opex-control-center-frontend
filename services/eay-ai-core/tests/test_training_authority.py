import hashlib
import inspect
import json
import sqlite3

import pytest

from app.entrypoint import app
from app.model_registry import ModelRegistry, PromotionRequest
from app.training_execution import (
    TrainingExecutionReceiptCreate,
    TrainingExecutionRegistry,
    TrainingExecutionRequest,
    dataset_sha256_from_file,
    sha256_path,
)
from app.training_gate import canonical_dataset_sha256
from app.training_job_registry import TrainingJobRegistration


def _examples(label: str):
    return [{
        "messages": [
            {"role": "user", "content": f"{label} question"},
            {"role": "assistant", "content": f"{label} answer"},
        ],
        "metadata": {
            "human_approved": True,
            "contains_personal_data": False,
            "reason": "reviewed",
        },
    }]


def test_runtime_has_one_gated_learning_export_and_no_raw_export_handler():
    matches = [route for route in app.routes if getattr(route, "path", None) == "/v1/learning/export"]
    assert len(matches) == 1
    endpoint = matches[0].endpoint
    assert endpoint.__module__ == "app.main"
    assert endpoint.__name__ == "export_learning_dataset"
    endpoint_source = inspect.getsource(endpoint)
    assert "build_gated_export" in endpoint_source
    assert "store.export_approved" not in endpoint_source


def test_legacy_registry_production_mutation_is_fail_closed(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    with pytest.raises(ValueError, match="production_promotion_requires_governed_promotion_gate"):
        registry.promote(
            "model-id",
            PromotionRequest(
                canary_result_fingerprint="a" * 64,
                approved_by="operator",
                note="must not bypass governed promotion",
            ),
        )


def test_verified_receipt_rejects_database_fingerprint_tampering(tmp_path):
    db = tmp_path / "eay.db"
    executions = TrainingExecutionRegistry(db)
    base = tmp_path / "base.bin"
    base.write_bytes(b"base")
    train = tmp_path / "train.json"
    eval_path = tmp_path / "eval.json"
    train_examples = _examples("train")
    eval_examples = _examples("eval")
    train.write_text(json.dumps(train_examples), encoding="utf-8")
    eval_path.write_text(json.dumps(eval_examples), encoding="utf-8")
    train_sha = canonical_dataset_sha256(train_examples)
    eval_sha = canonical_dataset_sha256(eval_examples)
    chain = "c" * 64
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS training_dataset_manifests (
        id TEXT PRIMARY KEY, dataset_sha256 TEXT NOT NULL UNIQUE,
        dataset_integrity_sha256 TEXT, quality_lineage_sha256 TEXT,
        eval_dataset_sha256 TEXT, eval_example_count INTEGER NOT NULL DEFAULT 0,
        chain_sha256 TEXT NOT NULL UNIQUE, example_count INTEGER NOT NULL,
        approved_by TEXT NOT NULL, approval_reference TEXT NOT NULL,
        parent_manifest_id TEXT, parent_chain_sha256 TEXT, created_at TEXT NOT NULL)""")
        conn.execute("""INSERT INTO training_dataset_manifests(
        id,dataset_sha256,dataset_integrity_sha256,quality_lineage_sha256,
        eval_dataset_sha256,eval_example_count,chain_sha256,example_count,
        approved_by,approval_reference,created_at)
        VALUES ('m',?,?,?,?,1,?,1,'reviewer','REF','2026-08-14T00:00:00+00:00')""",
        (train_sha, "f" * 64, "9" * 64, eval_sha, chain))
    spec = {
        "job_version": "1", "method": "lora", "base_model": "local-base",
        "base_model_sha256": sha256_path(base), "base_model_license_id": "apache-2.0",
        "training_manifest_chain_sha256": chain, "dataset_sha256": train_sha,
        "eval_dataset_sha256": eval_sha, "seed": 42, "epochs": 1,
        "learning_rate": 0.0002, "batch_size": 1, "gradient_accumulation_steps": 1,
        "max_seq_length": 512, "lora_rank": 8, "lora_alpha": 16,
        "lora_dropout": 0.05, "precision": "bf16", "local_only": True,
        "allow_remote_code": False, "allow_network_during_training": False,
    }
    job = executions.training_jobs.register(TrainingJobRegistration(
        spec=spec, approved_by="reviewer", approval_reference="JOB-1"))
    assert dataset_sha256_from_file(train) == train_sha
    output = tmp_path / "adapter.safetensors"
    plan = executions.create_plan(TrainingExecutionRequest(
        training_job_fingerprint=job.fingerprint, base_model_path=str(base),
        training_dataset_path=str(train), eval_dataset_path=str(eval_path),
        output_path=str(output), requested_by="operator", execution_reference="RUN-1"))
    output.write_bytes(b"artifact")
    receipt = executions.register_receipt(TrainingExecutionReceiptCreate(
        plan_fingerprint=plan.fingerprint, executor="worker", execution_reference="RUN-1:0"))
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE training_execution_receipts SET executor='tampered' WHERE fingerprint=?",
            (receipt.fingerprint,),
        )
    with pytest.raises(ValueError, match="training_execution_receipt_fingerprint_drift"):
        executions.require_verified_artifact(
            training_job_fingerprint=job.fingerprint,
            artifact_sha256=hashlib.sha256(b"artifact").hexdigest(),
        )
