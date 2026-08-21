from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Literal, Mapping

TrainingMethod = Literal["lora", "qlora"]
Precision = Literal["bf16", "fp16"]


@dataclass(frozen=True)
class TrainingJobSpec:
    job_version: str
    method: TrainingMethod
    base_model: str
    base_model_sha256: str
    base_model_license_id: str
    training_manifest_chain_sha256: str
    dataset_sha256: str
    eval_dataset_sha256: str
    seed: int
    epochs: int
    learning_rate: float
    batch_size: int
    gradient_accumulation_steps: int
    max_seq_length: int
    lora_rank: int
    lora_alpha: int
    lora_dropout: float
    precision: Precision
    local_only: bool = True
    allow_remote_code: bool = False
    allow_network_during_training: bool = False

    @property
    def fingerprint(self) -> str:
        payload = asdict(self)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sha256(value: str, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"training_job_invalid_sha256:{field}")
    return text


def validate_training_job_spec(spec: TrainingJobSpec) -> TrainingJobSpec:
    if not spec.job_version.strip() or not spec.base_model.strip() or not spec.base_model_license_id.strip():
        raise ValueError("training_job_identity_required")
    _sha256(spec.base_model_sha256, "base_model")
    _sha256(spec.training_manifest_chain_sha256, "manifest_chain")
    _sha256(spec.dataset_sha256, "dataset")
    _sha256(spec.eval_dataset_sha256, "eval_dataset")
    if spec.dataset_sha256 == spec.eval_dataset_sha256:
        raise ValueError("training_job_train_eval_same_dataset")
    if not spec.local_only or spec.allow_remote_code or spec.allow_network_during_training:
        raise ValueError("training_job_local_isolation_required")
    if not (0 <= spec.seed <= 2_147_483_647):
        raise ValueError("training_job_invalid_seed")
    if not (1 <= spec.epochs <= 20):
        raise ValueError("training_job_invalid_epochs")
    if not (0 < spec.learning_rate <= 0.01):
        raise ValueError("training_job_invalid_learning_rate")
    if not (1 <= spec.batch_size <= 256):
        raise ValueError("training_job_invalid_batch_size")
    if not (1 <= spec.gradient_accumulation_steps <= 256):
        raise ValueError("training_job_invalid_gradient_accumulation")
    if not (128 <= spec.max_seq_length <= 32768):
        raise ValueError("training_job_invalid_max_seq_length")
    if spec.lora_rank not in {4, 8, 16, 32, 64, 128}:
        raise ValueError("training_job_invalid_lora_rank")
    if not (spec.lora_rank <= spec.lora_alpha <= spec.lora_rank * 8):
        raise ValueError("training_job_invalid_lora_alpha")
    if not (0 <= spec.lora_dropout <= 0.5):
        raise ValueError("training_job_invalid_lora_dropout")
    if spec.method == "qlora" and spec.precision not in {"bf16", "fp16"}:
        raise ValueError("training_job_invalid_qlora_precision")
    return spec


def training_job_spec_from_mapping(payload: Mapping[str, object]) -> TrainingJobSpec:
    try:
        spec = TrainingJobSpec(
            job_version=str(payload["job_version"]),
            method=str(payload["method"]),  # type: ignore[arg-type]
            base_model=str(payload["base_model"]),
            base_model_sha256=str(payload["base_model_sha256"]),
            base_model_license_id=str(payload["base_model_license_id"]),
            training_manifest_chain_sha256=str(payload["training_manifest_chain_sha256"]),
            dataset_sha256=str(payload["dataset_sha256"]),
            eval_dataset_sha256=str(payload["eval_dataset_sha256"]),
            seed=int(payload["seed"]),
            epochs=int(payload["epochs"]),
            learning_rate=float(payload["learning_rate"]),
            batch_size=int(payload["batch_size"]),
            gradient_accumulation_steps=int(payload["gradient_accumulation_steps"]),
            max_seq_length=int(payload["max_seq_length"]),
            lora_rank=int(payload["lora_rank"]),
            lora_alpha=int(payload["lora_alpha"]),
            lora_dropout=float(payload["lora_dropout"]),
            precision=str(payload["precision"]),  # type: ignore[arg-type]
            local_only=bool(payload.get("local_only", True)),
            allow_remote_code=bool(payload.get("allow_remote_code", False)),
            allow_network_during_training=bool(payload.get("allow_network_during_training", False)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("training_job_spec_invalid_payload") from exc
    if spec.method not in {"lora", "qlora"}:
        raise ValueError("training_job_invalid_method")
    if spec.precision not in {"bf16", "fp16"}:
        raise ValueError("training_job_invalid_precision")
    return validate_training_job_spec(spec)
