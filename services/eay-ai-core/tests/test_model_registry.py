import pytest

from app.model_registry import ApprovalRequest, CanaryRequest, EvalSummary, ModelCandidateCreate, ModelRegistry


def good_candidate():
    return ModelCandidateCreate(
        model_name="eay-ops",
        model_version="0.2",
        base_model="local-base",
        artifact_sha256="a" * 64,
        license_id="apache-2.0",
        training_dataset_sha256="b" * 64,
        evals=EvalSummary(
            legal_grounding_rate=0.995,
            citation_validity_rate=1.0,
            unsafe_tool_call_rate=0.0,
            regression_pass_rate=0.99,
            kvkk_leak_rate=0.0,
            eval_set_version="2026-08-10",
        ),
    )


def test_good_candidate_requires_human_approval_before_canary(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    record = registry.create(good_candidate())
    with pytest.raises(ValueError):
        registry.set_canary(record.id, CanaryRequest(percent=5, approved_by="ops"))
    approved = registry.approve(record.id, ApprovalRequest(approved_by="ops", note="evals checked"))
    assert approved.status == "approved"
    canary = registry.set_canary(record.id, CanaryRequest(percent=10, approved_by="ops"))
    assert canary.status == "canary"
    assert canary.canary_percent == 10


def test_release_gate_blocks_kvkk_leak(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    candidate = good_candidate().model_copy(update={
        "model_version": "0.3",
        "evals": good_candidate().evals.model_copy(update={"kvkk_leak_rate": 0.01}),
    })
    record = registry.create(candidate)
    with pytest.raises(ValueError, match="kvkk_leak_detected"):
        registry.approve(record.id, ApprovalRequest(approved_by="ops", note="should fail"))


def test_release_gate_blocks_unsafe_tool_calls(tmp_path):
    registry = ModelRegistry(tmp_path / "eay.db")
    candidate = good_candidate().model_copy(update={
        "model_version": "0.4",
        "evals": good_candidate().evals.model_copy(update={"unsafe_tool_call_rate": 0.001}),
    })
    record = registry.create(candidate)
    with pytest.raises(ValueError, match="unsafe_tool_calls_detected"):
        registry.approve(record.id, ApprovalRequest(approved_by="ops", note="should fail"))
