from datetime import datetime, timezone

import pytest

from app.teaching_distillation import (
    DistillationApproval,
    KnowledgeSensitivity,
    SourceTrainingPolicy,
    TeachingMaterial,
    TrainingScope,
    build_training_candidate,
)

NOW = datetime(2026, 8, 18, 10, 10, tzinfo=timezone.utc)


def _policy(*, derivative=True, commercial=True, redistribute=True):
    return SourceTrainingPolicy(
        source_ref="source://public-course",
        license_ref="license://apache-2.0",
        commercial_use_allowed=commercial,
        derivative_training_allowed=derivative,
        redistribution_allowed=redistribute,
        verified_at=NOW,
        policy_evidence_refs=("license-evidence://1",),
    )


def _approval(scope, tenant_ref=None):
    return DistillationApproval(
        approval_ref=f"approval://{scope.value}",
        approved_by_principal_ref="user:platform-admin",
        approved_at=NOW,
        scope=scope,
        tenant_ref=tenant_ref,
    )


def _public_material(**updates):
    payload = dict(
        material_id="material:1",
        source_ref="source://public-course",
        objective_id="objective:1",
        instruction="Explain a verified concept.",
        ideal_response="A concise, source-grounded explanation.",
        sensitivity=KnowledgeSensitivity.PUBLIC,
        factual_evidence_refs=("fact-evidence://1",),
    )
    payload.update(updates)
    return TeachingMaterial(**payload)


def test_public_license_cleared_material_can_be_shared_base_candidate():
    result = build_training_candidate(
        material=_public_material(),
        source_policy=_policy(),
        approval=_approval(TrainingScope.SHARED_BASE),
    )
    assert result.blockers == ()
    assert result.export_allowed is True
    assert result.production_weight_update_allowed is False
    assert result.automatic_training_allowed is False
    assert result.candidate_ref.startswith("teaching-candidate:")


def test_shared_base_rejects_tenant_private_material():
    material = _public_material(
        sensitivity=KnowledgeSensitivity.CONFIDENTIAL,
        tenant_ref="tenant:a",
    )
    result = build_training_candidate(
        material=material,
        source_policy=_policy(),
        approval=_approval(TrainingScope.SHARED_BASE),
    )
    assert "teaching_distillation_shared_base_requires_public_non_tenant_material" in result.blockers
    assert result.export_allowed is False


def test_personal_data_cannot_enter_shared_model_weights():
    result = build_training_candidate(
        material=_public_material(contains_personal_data=True),
        source_policy=_policy(),
        approval=_approval(TrainingScope.SHARED_BASE),
    )
    assert "teaching_distillation_shared_base_personal_data_forbidden" in result.blockers


def test_secret_or_hidden_reasoning_material_fails_at_model_boundary():
    with pytest.raises(ValueError, match="teaching_distillation_secret_material_forbidden"):
        _public_material(contains_secret=True)
    with pytest.raises(ValueError, match="teaching_distillation_hidden_reasoning_forbidden"):
        _public_material(contains_hidden_reasoning=True)


def test_tenant_adapter_requires_exact_tenant_and_never_exports():
    material = _public_material(
        sensitivity=KnowledgeSensitivity.INTERNAL,
        tenant_ref="tenant:a",
    )
    with pytest.raises(ValueError, match="teaching_distillation_tenant_approval_mismatch"):
        build_training_candidate(
            material=material,
            source_policy=_policy(),
            approval=_approval(TrainingScope.TENANT_ISOLATED_ADAPTER, tenant_ref="tenant:b"),
        )
    result = build_training_candidate(
        material=material,
        source_policy=_policy(),
        approval=_approval(TrainingScope.TENANT_ISOLATED_ADAPTER, tenant_ref="tenant:a"),
    )
    assert result.tenant_ref == "tenant:a"
    assert result.export_allowed is False
    assert result.blockers == ()


def test_restricted_or_unlicensed_training_fails_closed():
    restricted = _public_material(
        sensitivity=KnowledgeSensitivity.RESTRICTED,
        tenant_ref="tenant:a",
    )
    result = build_training_candidate(
        material=restricted,
        source_policy=_policy(),
        approval=_approval(TrainingScope.TENANT_ISOLATED_ADAPTER, tenant_ref="tenant:a"),
    )
    assert "teaching_distillation_restricted_material_weight_training_forbidden" in result.blockers

    public = build_training_candidate(
        material=_public_material(),
        source_policy=_policy(derivative=False),
        approval=_approval(TrainingScope.SHARED_BASE),
    )
    assert "teaching_distillation_derivative_training_not_cleared" in public.blockers


def test_memory_only_can_store_learning_reference_but_not_train():
    result = build_training_candidate(
        material=_public_material(),
        source_policy=_policy(),
        approval=_approval(TrainingScope.MEMORY_ONLY),
    )
    assert result.blockers == ("teaching_distillation_memory_only_not_trainable",)
    assert result.export_allowed is False
