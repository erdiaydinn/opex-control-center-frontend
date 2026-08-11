import pytest

from app.training_manifest import TrainingManifestCreate, TrainingManifestStore


def _example(text="Use the reviewed warehouse procedure and verify the supporting source before taking operational action."):
    return {
        "messages": [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": text},
        ],
        "metadata": {
            "human_approved": True,
            "contains_personal_data": False,
            "teacher_reviewed": True,
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


def test_duplicate_dataset_manifest_rejected(tmp_path):
    store = TrainingManifestStore(tmp_path / "eay.db")
    payload = TrainingManifestCreate(
        examples=[_example()], approved_by="reviewer", approval_reference="APR-1"
    )
    store.create(payload)
    with pytest.raises(ValueError, match="already_exists"):
        store.create(payload)
