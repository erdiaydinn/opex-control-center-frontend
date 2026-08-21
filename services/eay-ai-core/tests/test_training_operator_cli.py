import json
from pathlib import Path

import pytest

from app.training_execution import TrainingExecutionRegistry
from app.training_executor import TrainingBackendResult, execute_registered_training
from app.training_operator_cli import main
from app.training_execution import sha256_path


TEACHER_FP = "f" * 64


def _example(*, user: str, answer: str, teacher_fp: str = TEACHER_FP):
    return {
        "messages": [
            {"role": "user", "content": user},
            {"role": "assistant", "content": answer},
        ],
        "metadata": {
            "human_approved": True,
            "contains_personal_data": False,
            "teacher_reviewed": True,
            "teacher_quality_accepted": True,
            "teacher_quality_sha256": teacher_fp,
            "reason": "reviewed production training correction",
        },
    }


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _setup_chain(tmp_path: Path, capsys):
    db = tmp_path / "eay.db"
    train = tmp_path / "train.json"
    eval_path = tmp_path / "eval.json"
    _write_json(
        train,
        [
            _example(
                user="How should receiving evidence be reviewed before operational action?",
                answer=(
                    "Use the reviewed receiving procedure, verify the supporting source, "
                    "confirm the effective operational rule, and document the evidence before action."
                ),
            )
        ],
    )
    _write_json(
        eval_path,
        [
            _example(
                user="How should putaway SLA compliance be evaluated?",
                answer=(
                    "Use the effective SLA version, compare elapsed minutes with the reviewed "
                    "threshold, and preserve the source evidence before classifying compliance."
                ),
                teacher_fp="e" * 64,
            )
        ],
    )

    assert main(
        [
            "--db-path",
            str(db),
            "create-manifest",
            "--train-json",
            str(train),
            "--eval-json",
            str(eval_path),
            "--approved-by",
            "dataset-reviewer",
            "--approval-reference",
            "DATASET-REVIEW-1",
        ]
    ) == 0
    manifest = json.loads(capsys.readouterr().out)

    base = tmp_path / "base-model"
    base.mkdir()
    (base / "config.json").write_text('{"model_type":"eay-test"}', encoding="utf-8")
    (base / "model.safetensors").write_bytes(b"reviewed-local-base-model")

    spec_path = tmp_path / "job-spec.json"
    _write_json(
        spec_path,
        {
            "job_version": "1",
            "method": "lora",
            "base_model": "reviewed-local-base",
            "base_model_sha256": sha256_path(base),
            "base_model_license_id": "apache-2.0",
            "training_manifest_chain_sha256": manifest["chain_sha256"],
            "dataset_sha256": manifest["dataset_sha256"],
            "eval_dataset_sha256": manifest["eval_dataset_sha256"],
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
        },
    )
    assert main(
        [
            "--db-path",
            str(db),
            "register-job",
            "--spec-json",
            str(spec_path),
            "--approved-by",
            "training-reviewer",
            "--approval-reference",
            "TRAINING-JOB-1",
        ]
    ) == 0
    job = json.loads(capsys.readouterr().out)

    output = tmp_path / "trained-adapter"
    assert main(
        [
            "--db-path",
            str(db),
            "create-plan",
            "--training-job-fingerprint",
            job["fingerprint"],
            "--base-model-path",
            str(base),
            "--training-dataset-path",
            str(train),
            "--eval-dataset-path",
            str(eval_path),
            "--output-path",
            str(output),
            "--requested-by",
            "training-operator",
            "--execution-reference",
            "LOCAL-TRAIN-1",
        ]
    ) == 0
    plan = json.loads(capsys.readouterr().out)
    return db, train, eval_path, base, output, manifest, job, plan


def test_operator_cli_manifest_job_plan_and_preview_chain(tmp_path, capsys):
    db, _, _, _, _, manifest, job, plan = _setup_chain(tmp_path, capsys)

    assert manifest["eval_example_count"] == 1
    assert len(manifest["chain_sha256"]) == 64
    assert len(job["fingerprint"]) == 64
    assert len(plan["fingerprint"]) == 64

    assert main(
        [
            "--db-path",
            str(db),
            "preview",
            "--plan-fingerprint",
            plan["fingerprint"],
        ]
    ) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["local_only"] is True
    assert preview["allow_remote_code"] is False
    assert preview["allow_network_during_training"] is False
    assert preview["offline_environment"]["HF_HUB_OFFLINE"] == "1"


def test_operator_cli_verify_receipt_rehashes_real_artifact(tmp_path, capsys):
    db, _, _, _, output, _, job, plan = _setup_chain(tmp_path, capsys)

    def fake_backend(received_plan):
        assert received_plan.fingerprint == plan["fingerprint"]
        output.mkdir()
        (output / "adapter_model.safetensors").write_bytes(b"real-observed-test-adapter")
        return TrainingBackendResult(
            runtime_evidence={
                "backend": "operator-cli-contract",
                "device_type": "cpu",
                "network_policy": "offline",
            }
        )

    receipt = execute_registered_training(
        db_path=db,
        plan_fingerprint=plan["fingerprint"],
        executor="contract-worker",
        execution_reference="LOCAL-TRAIN-1:exit-0",
        backend=fake_backend,
    )
    assert main(
        [
            "--db-path",
            str(db),
            "verify-receipt",
            "--training-job-fingerprint",
            job["fingerprint"],
            "--artifact-sha256",
            receipt.artifact_sha256,
        ]
    ) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["fingerprint"] == receipt.fingerprint
    assert verified["artifact_sha256"] == sha256_path(output)


def test_operator_cli_rejects_unreviewed_manifest(tmp_path):
    db = tmp_path / "eay.db"
    train = tmp_path / "train.json"
    item = _example(
        user="Can this unreviewed item enter training?",
        answer="This example must fail because human approval has explicitly not been granted.",
    )
    item["metadata"]["human_approved"] = False
    _write_json(train, [item])

    with pytest.raises(ValueError, match="training_gate_failed"):
        main(
            [
                "--db-path",
                str(db),
                "create-manifest",
                "--train-json",
                str(train),
                "--approved-by",
                "reviewer",
                "--approval-reference",
                "SHOULD-NOT-PASS",
            ]
        )


def test_operator_cli_rejects_non_object_job_spec(tmp_path):
    db = tmp_path / "eay.db"
    spec = tmp_path / "bad-spec.json"
    _write_json(spec, ["not", "a", "job", "object"])
    with pytest.raises(ValueError, match="training_cli_job_spec_object_required"):
        main(
            [
                "--db-path",
                str(db),
                "register-job",
                "--spec-json",
                str(spec),
                "--approved-by",
                "reviewer",
                "--approval-reference",
                "BAD-SPEC",
            ]
        )
