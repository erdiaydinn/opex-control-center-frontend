import json
import os
import sqlite3
from pathlib import Path

import pytest

from app.training_execution import (
    TrainingExecutionRegistry,
    TrainingExecutionRequest,
    dataset_sha256_from_file,
    sha256_path,
)
from app.training_executor import (
    TrainingBackendResult,
    execute_registered_training,
    main,
    preview_registered_training,
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


def _seed(tmp_path: Path, *, method: str = "lora"):
    db_path = tmp_path / "eay.db"
    registry = TrainingExecutionRegistry(db_path)

    base_model = tmp_path / "base-model"
    base_model.mkdir()
    (base_model / "config.json").write_text('{"model_type":"test"}', encoding="utf-8")
    (base_model / "weights.safetensors").write_bytes(b"local-base-weights")

    train_path = tmp_path / "train.json"
    eval_path = tmp_path / "eval.json"
    train_path.write_text(json.dumps(_examples("train")), encoding="utf-8")
    eval_path.write_text(json.dumps(_examples("eval")), encoding="utf-8")
    train_sha = dataset_sha256_from_file(train_path)
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
            VALUES ('manifest-executor',?,?,?,?,1,?,1,'dataset-reviewer','DATASET-EXEC',
            '2026-08-14T00:00:00+00:00')""",
            (train_sha, "f" * 64, "9" * 64, eval_sha, chain),
        )

    spec = {
        "job_version": "1",
        "method": method,
        "base_model": "local-base",
        "base_model_sha256": sha256_path(base_model),
        "base_model_license_id": "apache-2.0",
        "training_manifest_chain_sha256": chain,
        "dataset_sha256": train_sha,
        "eval_dataset_sha256": eval_sha,
        "seed": 42,
        "epochs": 1,
        "learning_rate": 0.0002,
        "batch_size": 1,
        "gradient_accumulation_steps": 2,
        "max_seq_length": 512,
        "lora_rank": 8,
        "lora_alpha": 16,
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
            approval_reference="JOB-EXEC",
        )
    )
    output = tmp_path / "output"
    plan = registry.create_plan(
        TrainingExecutionRequest(
            training_job_fingerprint=job.fingerprint,
            base_model_path=str(base_model),
            training_dataset_path=str(train_path),
            eval_dataset_path=str(eval_path),
            output_path=str(output),
            requested_by="training-operator",
            execution_reference="TRAIN-EXEC-1",
        )
    )
    return registry, plan, base_model, train_path, eval_path, output


def test_dry_run_reverifies_plan_and_enforces_offline_environment(tmp_path):
    _, plan, _, _, _, _ = _seed(tmp_path, method="qlora")
    preview = preview_registered_training(
        db_path=tmp_path / "eay.db",
        plan_fingerprint=plan.fingerprint,
    )

    assert preview.method == "qlora"
    assert preview.local_only is True
    assert preview.allow_remote_code is False
    assert preview.allow_network_during_training is False
    assert preview.offline_environment["HF_HUB_OFFLINE"] == "1"
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert os.environ["HF_DATASETS_OFFLINE"] == "1"


def test_dry_run_fails_closed_when_base_model_changes_after_plan(tmp_path):
    _, plan, base_model, _, _, _ = _seed(tmp_path)
    (base_model / "weights.safetensors").write_bytes(b"tampered-after-plan")

    with pytest.raises(ValueError, match="training_executor_base_model_drift"):
        preview_registered_training(
            db_path=tmp_path / "eay.db",
            plan_fingerprint=plan.fingerprint,
        )


def test_dry_run_fails_closed_when_dataset_changes_after_plan(tmp_path):
    _, plan, _, train_path, _, _ = _seed(tmp_path)
    train_path.write_text(json.dumps(_examples("tampered")), encoding="utf-8")

    with pytest.raises(ValueError, match="training_executor_training_dataset_drift"):
        preview_registered_training(
            db_path=tmp_path / "eay.db",
            plan_fingerprint=plan.fingerprint,
        )


def test_fake_backend_creates_receipted_artifact_with_bound_runtime_evidence(tmp_path):
    registry, plan, _, _, _, output = _seed(tmp_path)

    def backend(received_plan):
        assert received_plan.fingerprint == plan.fingerprint
        output.mkdir()
        (output / "adapter_model.safetensors").write_bytes(b"trained-adapter")
        return TrainingBackendResult(
            runtime_evidence={
                "backend": "contract-test-backend",
                "device_type": "cpu",
                "network_policy": "offline",
            }
        )

    receipt = execute_registered_training(
        db_path=tmp_path / "eay.db",
        plan_fingerprint=plan.fingerprint,
        executor="contract-test-worker",
        execution_reference="TRAIN-EXEC-1:exit-0",
        backend=backend,
    )

    evidence_path = output / "eay_training_runtime_evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["plan_fingerprint"] == plan.fingerprint
    assert evidence["training_job_fingerprint"] == plan.training_job_fingerprint
    assert evidence["backend"] == "contract-test-backend"
    assert evidence["network_policy"] == "offline"
    assert receipt.artifact_sha256 == sha256_path(output)
    assert registry.require_verified_artifact(
        training_job_fingerprint=plan.training_job_fingerprint,
        artifact_sha256=receipt.artifact_sha256,
    ).fingerprint == receipt.fingerprint


def test_backend_must_create_nonempty_directory_artifact(tmp_path):
    _, plan, _, _, _, _ = _seed(tmp_path)

    def missing_backend(_plan):
        return TrainingBackendResult(runtime_evidence={"backend": "missing"})

    with pytest.raises(ValueError, match="training_executor_backend_did_not_create_artifact"):
        execute_registered_training(
            db_path=tmp_path / "eay.db",
            plan_fingerprint=plan.fingerprint,
            executor="worker",
            execution_reference="RUN-MISSING",
            backend=missing_backend,
        )


def test_backend_exception_cannot_leave_a_receipt(tmp_path):
    _, plan, _, _, _, _ = _seed(tmp_path)

    def failing_backend(_plan):
        raise RuntimeError("gpu-worker-failed")

    with pytest.raises(RuntimeError, match="gpu-worker-failed"):
        execute_registered_training(
            db_path=tmp_path / "eay.db",
            plan_fingerprint=plan.fingerprint,
            executor="worker",
            execution_reference="RUN-FAIL",
            backend=failing_backend,
        )
    with sqlite3.connect(tmp_path / "eay.db") as conn:
        count = conn.execute("SELECT COUNT(*) FROM training_execution_receipts").fetchone()[0]
    assert count == 0


def test_cli_dry_run_uses_registered_plan_without_loading_ml_stack(tmp_path, capsys):
    _, plan, _, _, _, _ = _seed(tmp_path)
    result = main(
        [
            "--db-path",
            str(tmp_path / "eay.db"),
            "--plan-fingerprint",
            plan.fingerprint,
            "--dry-run",
        ]
    )
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan_fingerprint"] == plan.fingerprint
    assert payload["method"] == "lora"
