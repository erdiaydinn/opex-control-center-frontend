import pytest

from app.training_job_spec import TrainingJobSpec, validate_training_job_spec


def good_spec(**overrides):
    data = dict(
        job_version="1",
        method="qlora",
        base_model="qwen-local",
        base_model_sha256="a" * 64,
        base_model_license_id="apache-2.0",
        training_manifest_chain_sha256="b" * 64,
        dataset_sha256="c" * 64,
        eval_dataset_sha256="d" * 64,
        seed=42,
        epochs=3,
        learning_rate=0.0002,
        batch_size=4,
        gradient_accumulation_steps=8,
        max_seq_length=4096,
        lora_rank=16,
        lora_alpha=32,
        lora_dropout=0.05,
        precision="bf16",
    )
    data.update(overrides)
    return TrainingJobSpec(**data)


def test_training_job_fingerprint_is_deterministic_and_config_sensitive():
    a = validate_training_job_spec(good_spec())
    b = validate_training_job_spec(good_spec())
    changed = validate_training_job_spec(good_spec(seed=43))
    assert len(a.fingerprint) == 64
    assert a.fingerprint == b.fingerprint
    assert a.fingerprint != changed.fingerprint


def test_training_job_requires_local_isolation():
    with pytest.raises(ValueError, match="training_job_local_isolation_required"):
        validate_training_job_spec(good_spec(allow_network_during_training=True))
    with pytest.raises(ValueError, match="training_job_local_isolation_required"):
        validate_training_job_spec(good_spec(allow_remote_code=True))


def test_training_job_rejects_train_eval_collision():
    with pytest.raises(ValueError, match="training_job_train_eval_same_dataset"):
        validate_training_job_spec(good_spec(eval_dataset_sha256="c" * 64))


def test_training_job_rejects_unbounded_hyperparameters():
    with pytest.raises(ValueError, match="training_job_invalid_epochs"):
        validate_training_job_spec(good_spec(epochs=100))
    with pytest.raises(ValueError, match="training_job_invalid_lora_rank"):
        validate_training_job_spec(good_spec(lora_rank=7))
