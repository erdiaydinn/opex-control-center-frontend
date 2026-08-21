from datetime import datetime, timezone

import pytest

from app.vision_audit import AuditCreate, VisionAuditStore, VisualFinding, sha256_bytes


def sample_payload():
    return AuditCreate(
        image_sha256=sha256_bytes(b"image-bytes"),
        store_id="fulya",
        captured_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        model_name="local-vlm",
        model_version="0.1",
        findings=[
            VisualFinding(
                finding_type="blocked_walkway",
                description="Picker walkway appears obstructed",
                severity="high",
                confidence=0.91,
                region=[0.1, 0.2, 0.4, 0.7],
            )
        ],
    )


def test_visual_audit_starts_pending(tmp_path):
    store = VisionAuditStore(tmp_path / "eay.db")
    record = store.create(sample_payload())
    assert record.decision == "pending"
    assert record.findings[0].severity == "high"


def test_visual_audit_requires_single_human_decision(tmp_path):
    store = VisionAuditStore(tmp_path / "eay.db")
    record = store.create(sample_payload())
    accepted = store.decide(record.id, "accepted", "checked")
    assert accepted.decision == "accepted"
    with pytest.raises(ValueError):
        store.decide(record.id, "rejected", "second decision")


def test_duplicate_image_model_version_is_idempotency_guard(tmp_path):
    store = VisionAuditStore(tmp_path / "eay.db")
    store.create(sample_payload())
    with pytest.raises(ValueError):
        store.create(sample_payload())
