import json
import sqlite3

import pytest

from app.training_execution import (
    TrainingExecutionReceiptCreate,
    TrainingExecutionRegistry,
    TrainingExecutionRequest,
    dataset_sha256_from_file,
    sha256_path,
)
from app.training_job_registry import TrainingJobRegistration


def _examples(label: str):
    return [
        {
            "messages": [
                {"role": "user", "content": f"question-{label}"},
                {"role": "assistant", "content": f"answer-{label}"},
            ],
            "metadata": {
                "human_approved": True,
                "contains_personal_data": False,
                "reason": "reviewed",
            },
        }
    ]


def _seed(tmp_path):
    db_path = tmp_path / "eay.db"
    registry = TrainingExecutionRegistry(db_path)

    base_model = tmp_path / "base-model"
    base_model.mkdir()
    (base_model / "config.json").write_text('{"model_type":"test"}', encoding="utf-8")
    (base_model / "weights.safetensors").write_bytes(b"local-model-weights")

    train_path = tmp_path / "train.json"
    eval_path = tmp_path / "eval.json"
    train_path.write_text(json.dumps(_examples("train")), encoding="utf-8")
    eval_path.write_text(json.dumps(_examples("eval")), encoding="utf-8")

    dataset_sha = dataset_sha256_from_file(train_path)
    eval_sha = dataset_sha256_from_file(eval_path)
    chain = "c" * 64
    with sqlite3.connect(db_path) as conn:
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
            VALUES ('manifest-exec',?,?,?,?,1,?,1,'dataset-reviewer','DATASET-1',
            '2026-08-14T00:00:00+00:00')""",
            (dataset_sha, "f" * 64, "9" * 64, eval_sha, chain),
        )

    spec = {
        "job_version": "1",
        "method": "qlora",
        "base_model": "local-base",
        "base_model_sha256": sha256_path(base_model),
        "base_model_license_id": "apache-2.0",
        "training_manifest_chain_sha256": chain,
        "dataset_sha256": dataset_sha,
        "eval_dataset_sha256": eval_sha,
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
    job = registry.training_jobs.register(
        TrainingJobRegistration(
            spec=spec,
            approved_by="training-reviewer",
            approval_reference="JOB-1",
        )
    )
    return registry, job.fingerprint, base_model, train_path, eval_path


def _request(job, base_model, train_path, eval_path, output_path):
    return TrainingExecutionRequest(
        training_job_fingerprint=job,
        base_model_path=str(base_model),
        training_dataset_path=str(train_path),
        eval_dataset_path=str(eval_path),
        output_path=str(output_path),
        requested_by="training-operator",
        execution_reference="TRAIN-RUN-1",
    )


def test_execution_plan_reverifies_all_local_inputs_and_is_offline(tmp_path):
    registry, job, base_model, train_path, eval_path = _seed(tmp_path)
    plan = registry.create_plan(
        _request(job, base_model, train_path, eval_path, tmp_path / "output")
    )

    assert plan.training_job_fingerprint == job
    assert plan.method == "qlora"
    assert plan.base_model_sha256 == sha256_path(base_model)
    assert plan.training_dataset_sha256 == dataset_sha256_from_file(train_path)
    assert plan.eval_dataset_sha256 == dataset_sha256_from_file(eval_path)
    assert plan.local_only is True
    assert plan.allow_remote_code is False
    assert plan.allow_network_during_training is False
    assert plan.offline_environment["HF_HUB_OFFLINE"] == "1"
    assert plan.offline_environment["TRANSFORMERS_OFFLINE"] == "1"
    assert len(plan.fingerprint) == 64


def test_execution_plan_rejects_base_model_drift(tmp_path):
    registry, job, base_model, train_path, eval_path = _seed(tmp_path)
    (base_model / "weights.safetensors").write_bytes(b"tampered")

    with pytest.raises(ValueError, match="training_execution_base_model_hash_mismatch"):
        registry.create_plan(
            _request(job, base_model, train_path, eval_path, tmp_path / "output")
        )


def test_execution_plan_rejects_dataset_drift(tmp_path):
    registry, job, base_model, train_path, eval_path = _seed(tmp_path)
    train_path.write_text(json.dumps(_examples("changed")), encoding="utf-8")

    with pytest.raises(ValueError, match="training_execution_training_dataset_hash_mismatch"):
        registry.create_plan(
            _request(job, base_model, train_path, eval_path, tmp_path / "output")
        )


def test_execution_receipt_hashes_real_artifact_and_detects_later_drift(tmp_path):
    registry, job, base_model, train_path, eval_path = _seed(tmp_path)
    output = tmp_path / "output"
    plan = registry.create_plan(_request(job, base_model, train_path, eval_path, output))

    output.mkdir()
    (output / "adapter_config.json").write_text('{"r":16}', encoding="utf-8")
    (output / "adapter_model.safetensors").write_bytes(b"trained-adapter")

    receipt = registry.register_receipt(
        TrainingExecutionReceiptCreate(
            plan_fingerprint=plan.fingerprint,
            executor="local-gpu-worker",
            execution_reference="TRAIN-RUN-1:exit-0",
        )
    )
    assert receipt.training_job_fingerprint == job
    assert receipt.artifact_sha256 == sha256_path(output)
    assert registry.require_verified_artifact(
        training_job_fingerprint=job,
        artifact_sha256=receipt.artifact_sha256,
    ).fingerprint == receipt.fingerprint

    (output / "adapter_model.safetensors").write_bytes(b"tampered-after-receipt")
    with pytest.raises(ValueError, match="training_execution_artifact_drift"):
        registry.require_verified_artifact(
            training_job_fingerprint=job,
            artifact_sha256=receipt.artifact_sha256,
        )


def test_execution_receipt_is_single_use_per_plan(tmp_path):
    registry, job, base_model, train_path, eval_path = _seed(tmp_path)
    output = tmp_path / "output"
    plan = registry.create_plan(_request(job, base_model, train_path, eval_path, output))
    output.mkdir()
    (output / "adapter_model.safetensors").write_bytes(b"trained-adapter")
    payload = TrainingExecutionReceiptCreate(
        plan_fingerprint=plan.fingerprint,
        executor="local-gpu-worker",
        execution_reference="TRAIN-RUN-1:exit-0",
    )
    registry.register_receipt(payload)
    with pytest.raises(ValueError, match="training_execution_receipt_already_registered"):
        registry.register_receipt(payload)
