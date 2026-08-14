from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .training_execution import (
    TrainingExecutionPlan,
    TrainingExecutionReceipt,
    TrainingExecutionReceiptCreate,
    TrainingExecutionRegistry,
    apply_offline_training_environment,
    dataset_sha256_from_file,
    sha256_path,
)


class TrainingExecutorPreview(BaseModel):
    plan_fingerprint: str
    training_job_fingerprint: str
    method: str
    base_model_sha256: str
    training_dataset_sha256: str
    eval_dataset_sha256: str
    output_path: str
    local_only: bool
    allow_remote_code: bool
    allow_network_during_training: bool
    offline_environment: dict[str, str]


class TrainingBackendResult(BaseModel):
    runtime_evidence: dict[str, str]


TrainingBackend = Callable[[TrainingExecutionPlan], TrainingBackendResult]


def verify_plan_inputs(plan: TrainingExecutionPlan) -> None:
    """Re-verify immutable inputs immediately before training starts."""

    base_model = Path(plan.base_model_path)
    training_dataset = Path(plan.training_dataset_path)
    eval_dataset = Path(plan.eval_dataset_path)
    output = Path(plan.output_path)

    if sha256_path(base_model) != plan.base_model_sha256:
        raise ValueError("training_executor_base_model_drift")
    if dataset_sha256_from_file(training_dataset) != plan.training_dataset_sha256:
        raise ValueError("training_executor_training_dataset_drift")
    if dataset_sha256_from_file(eval_dataset) != plan.eval_dataset_sha256:
        raise ValueError("training_executor_eval_dataset_drift")
    if plan.training_dataset_sha256 == plan.eval_dataset_sha256:
        raise ValueError("training_executor_train_eval_collision")
    if not plan.local_only or plan.allow_remote_code or plan.allow_network_during_training:
        raise ValueError("training_executor_local_offline_policy_required")
    if plan.method not in {"lora", "qlora"}:
        raise ValueError("training_executor_method_not_supported")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("training_executor_output_must_be_absent_or_empty_directory")


def preview_registered_training(
    *,
    db_path: Path,
    plan_fingerprint: str,
) -> TrainingExecutorPreview:
    registry = TrainingExecutionRegistry(db_path)
    plan = registry.get_plan(plan_fingerprint)
    verify_plan_inputs(plan)
    apply_offline_training_environment()
    return TrainingExecutorPreview(
        plan_fingerprint=plan.fingerprint,
        training_job_fingerprint=plan.training_job_fingerprint,
        method=plan.method,
        base_model_sha256=plan.base_model_sha256,
        training_dataset_sha256=plan.training_dataset_sha256,
        eval_dataset_sha256=plan.eval_dataset_sha256,
        output_path=plan.output_path,
        local_only=plan.local_only,
        allow_remote_code=plan.allow_remote_code,
        allow_network_during_training=plan.allow_network_during_training,
        offline_environment=plan.offline_environment,
    )


def execute_registered_training(
    *,
    db_path: Path,
    plan_fingerprint: str,
    executor: str,
    execution_reference: str,
    backend: TrainingBackend | None = None,
) -> TrainingExecutionReceipt:
    """Execute one immutable local training plan and bind the observed artifact.

    The default backend performs actual Hugging Face TRL/PEFT training. Tests may
    inject a backend, but the same preflight and on-disk receipt hashing remain.
    Runtime evidence is written inside the output directory before hashing, so
    the receipt cryptographically binds the environment evidence as part of the
    trained artifact tree.
    """

    registry = TrainingExecutionRegistry(db_path)
    plan = registry.get_plan(plan_fingerprint)
    verify_plan_inputs(plan)
    apply_offline_training_environment()

    selected_backend = backend or _run_huggingface_training
    result = selected_backend(plan)
    output = Path(plan.output_path)
    if not output.exists():
        raise ValueError("training_executor_backend_did_not_create_artifact")
    if not output.is_dir():
        raise ValueError("training_executor_backend_output_must_be_directory")
    if not any(output.iterdir()):
        raise ValueError("training_executor_backend_created_empty_artifact")

    evidence = {
        "plan_fingerprint": plan.fingerprint,
        "training_job_fingerprint": plan.training_job_fingerprint,
        "base_model_sha256": plan.base_model_sha256,
        "training_dataset_sha256": plan.training_dataset_sha256,
        "eval_dataset_sha256": plan.eval_dataset_sha256,
        "executor": executor.strip(),
        "execution_reference": execution_reference.strip(),
        "method": plan.method,
        **result.runtime_evidence,
    }
    evidence_path = output / "eay_training_runtime_evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )

    return registry.register_receipt(
        TrainingExecutionReceiptCreate(
            plan_fingerprint=plan.fingerprint,
            executor=executor,
            execution_reference=execution_reference,
        )
    )


def _load_dataset(path: str):
    from datasets import Dataset

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError("training_executor_dataset_invalid")
    return Dataset.from_list(payload)


def _run_huggingface_training(plan: TrainingExecutionPlan) -> TrainingBackendResult:
    """Run actual local LoRA/QLoRA SFT with no model or dataset network fetch."""

    apply_offline_training_environment()
    started_at = datetime.now(timezone.utc)
    try:
        import torch
        from peft import LoraConfig, prepare_model_for_kbit_training
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from trl import SFTConfig, SFTTrainer
    except ImportError as exc:
        raise RuntimeError(
            "training_executor_dependencies_unavailable: install the training extra"
        ) from exc

    use_bf16 = plan.hyperparameters["precision"] == "bf16"
    use_fp16 = plan.hyperparameters["precision"] == "fp16"
    model_kwargs: dict[str, Any] = {
        "local_files_only": True,
        "trust_remote_code": False,
    }
    if plan.method == "qlora":
        if not torch.cuda.is_available():
            raise RuntimeError("training_executor_qlora_requires_cuda")
        compute_dtype = torch.bfloat16 if use_bf16 else torch.float16
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=compute_dtype,
        )
        model_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(plan.base_model_path, **model_kwargs)
    if plan.method == "qlora":
        model = prepare_model_for_kbit_training(model)
    tokenizer = AutoTokenizer.from_pretrained(
        plan.base_model_path,
        local_files_only=True,
        trust_remote_code=False,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    train_dataset = _load_dataset(plan.training_dataset_path)
    eval_dataset = _load_dataset(plan.eval_dataset_path)
    peft_config = LoraConfig(
        r=int(plan.hyperparameters["lora_rank"]),
        lora_alpha=int(plan.hyperparameters["lora_alpha"]),
        lora_dropout=float(plan.hyperparameters["lora_dropout"]),
        bias="none",
        task_type="CAUSAL_LM",
        target_modules="all-linear",
    )
    args = SFTConfig(
        output_dir=plan.output_path,
        num_train_epochs=float(plan.hyperparameters["epochs"]),
        learning_rate=float(plan.hyperparameters["learning_rate"]),
        per_device_train_batch_size=int(plan.hyperparameters["batch_size"]),
        per_device_eval_batch_size=int(plan.hyperparameters["batch_size"]),
        gradient_accumulation_steps=int(plan.hyperparameters["gradient_accumulation_steps"]),
        max_length=int(plan.hyperparameters["max_seq_length"]),
        seed=int(plan.hyperparameters["seed"]),
        data_seed=int(plan.hyperparameters["seed"]),
        bf16=use_bf16,
        fp16=use_fp16,
        eval_strategy="epoch",
        save_strategy="no",
        report_to="none",
        push_to_hub=False,
        trust_remote_code=False,
    )
    trainer = SFTTrainer(
        model=model,
        args=args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
        peft_config=peft_config,
    )
    trainer.train()
    trainer.save_model(plan.output_path)
    tokenizer.save_pretrained(plan.output_path)

    finished_at = datetime.now(timezone.utc)
    device_name = "cpu"
    if torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(0)
    return TrainingBackendResult(
        runtime_evidence={
            "backend": "huggingface-trl-peft",
            "python_version": platform.python_version(),
            "torch_version": str(torch.__version__),
            "cuda_version": str(torch.version.cuda or "none"),
            "device_type": "cuda" if torch.cuda.is_available() else "cpu",
            "device_name": device_name,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "local_files_only": "true",
            "trust_remote_code": "false",
            "network_policy": "offline",
        }
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EAY governed local LoRA/QLoRA executor")
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--plan-fingerprint", required=True)
    parser.add_argument("--executor", default="local-training-operator")
    parser.add_argument("--execution-reference", default="manual-local-training")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.dry_run:
        preview = preview_registered_training(
            db_path=args.db_path,
            plan_fingerprint=args.plan_fingerprint,
        )
        print(preview.model_dump_json(indent=2))
        return 0
    receipt = execute_registered_training(
        db_path=args.db_path,
        plan_fingerprint=args.plan_fingerprint,
        executor=args.executor,
        execution_reference=args.execution_reference,
    )
    print(receipt.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
