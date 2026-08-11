import pytest

from app.training_manifest import TrainingManifestCreate, TrainingManifestStore


TEACHER_FP = "f" * 64


def _example(text="Use the reviewed warehouse procedure and verify the supporting source before taking operational action.", user="question"):
    return {
        "messages": [
            {"role": "user", "content": user},
            {"role": "assistant", "content": text},
        ],
        "metadata": {
            "human_approved": True,
            "contains_personal_data": False,
            "teacher_reviewed": True,
            "teacher_quality_accepted": True,
            "teacher_quality_sha256": TEACHER_FP,
            "reason": "approved training correction",
        },
    }


def test_manifest_requires_training_gate(tmp_path):
    store = TrainingManifestStore(tmp_path / "eay.db")
    bad = _example()
    bad["metadata"]["human_approved"] = False
    with pytest.raises(ValueError, match="training_gate_failed"):
        store.create(
            TrainingManifestCreate(
                examples=[bad],
                approved_by="reviewer",
                approval_reference="APR-1",
            )
        )


def test_manifest_builds_parent_hash_chain(tmp_path):
    store = TrainingManifestStore(tmp_path / "eay.db")
    root = store.create(
        TrainingManifestCreate(
            examples=[_example("Apply the reviewed warehouse process for version one and verify the approved operational source before action.")],
            approved_by="reviewer",
            approval_reference="APR-1",
        )
    )
    child = store.create(
        TrainingManifestCreate(
            examples=[_example("Apply the reviewed warehouse process for version two and verify the approved operational source before action.")],
            approved_by="reviewer",
            approval_reference="APR-2",
            parent_manifest_id=root.id,
        )
    )
    assert child.parent_manifest_id == root.id
    assert child.parent_chain_sha256 == root.chain_sha256
    assert child.chain_sha256 != root.chain_sha256
    assert len(root.dataset_integrity_sha256) == 64
    assert len(root.quality_lineage_sha256) == 64
    assert child.dataset_integrity_sha256 != root.dataset_integrity_sha256


def test_manifest_chain_binds_quality_lineage(tmp_path):
    store = TrainingManifestStore(tmp_path / "eay.db")
    first = store.create(
        TrainingManifestCreate(
            examples=[_example("Use the reviewed receiving procedure and verify all evidence before closing the operational case.")],
            approved_by="reviewer",
            approval_reference="APR-QUALITY-1",
        )
    )
    changed = _example("Use the reviewed receiving procedure, verify all source evidence, and document the operational decision before closure.")
    changed["metadata"]["teacher_quality_sha256"] = "e" * 64
    second = store.create(
        TrainingManifestCreate(
            examples=[changed],
            approved_by="reviewer",
            approval_reference="APR-QUALITY-2",
            parent_manifest_id=first.id,
        )
    )
    assert first.quality_lineage_sha256 != second.quality_lineage_sha256
    assert second.parent_chain_sha256 == first.chain_sha256


def test_manifest_rejects_train_eval_leakage(tmp_path):
    store = TrainingManifestStore(tmp_path / "eay.db")
    shared = _example(
        "Picking averages must be weighted by eligible orders to avoid average-of-averages drift.",
        user="How should picker-day picking time be aggregated?",
    )
    with pytest.raises(ValueError, match="training_eval_leakage:eval_0:exact_leakage_from_train_0"):
        store.create(
            TrainingManifestCreate(
                examples=[shared],
                eval_examples=[shared],
                approved_by="reviewer",
                approval_reference="APR-LEAK-1",
            )
        )


def test_manifest_persists_distinct_eval_split_hash(tmp_path):
    store = TrainingManifestStore(tmp_path / "eay.db")
    eval_item = _example(
        "Use the effective SLA version and compare elapsed minutes with the reviewed threshold before classifying compliance.",
        user="How should putaway SLA compliance be evaluated?",
    )
    eval_item["metadata"]["teacher_quality_sha256"] = "e" * 64
    manifest = store.create(
        TrainingManifestCreate(
            examples=[_example(
                "Use the reviewed receiving procedure and verify the source before accepting the operational conclusion.",
                user="How should receiving be reviewed?",
            )],
            eval_examples=[eval_item],
            approved_by="reviewer",
            approval_reference="APR-EVAL-1",
        )
    )
    assert manifest.eval_example_count == 1
    assert len(manifest.eval_dataset_sha256 or "") == 64
    assert manifest.eval_dataset_sha256 != manifest.dataset_sha256


def test_duplicate_dataset_manifest_rejected(tmp_path):
    store = TrainingManifestStore(tmp_path / "eay.db")
    payload = TrainingManifestCreate(
        examples=[_example()], approved_by="reviewer", approval_reference="APR-1"
    )
    store.create(payload)
    with pytest.raises(ValueError, match="already_exists"):
        store.create(payload)
