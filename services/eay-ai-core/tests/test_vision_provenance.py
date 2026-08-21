from datetime import datetime, timezone

from app.vision_audit import AuditCreate, VisionAuditStore, VisualFinding
from app.vision_provenance import VisionProvenanceStore


def _audit(store):
    return store.create(
        AuditCreate(
            image_sha256="a" * 64,
            store_id="store-1",
            captured_at=datetime.now(timezone.utc),
            model_name="local-vision",
            model_version="0.1",
            source_uri="file:///secure/audit.jpg",
            findings=[
                VisualFinding(
                    finding_type="shelf_gap",
                    description="gap detected",
                    severity="medium",
                    confidence=0.9,
                )
            ],
        )
    )


def test_pending_visual_audit_not_eligible_for_learning(tmp_path):
    db = tmp_path / "eay.db"
    audit_store = VisionAuditStore(db)
    audit = _audit(audit_store)
    provenance = VisionProvenanceStore(db)
    evidence = provenance.register(audit.id, {"camera": "fixed"})
    assert evidence.human_review_required is True
    assert evidence.eligible_for_learning is False
    assert provenance.learning_eligibility(audit.id) is False


def test_accepted_visual_audit_requires_sealed_review_lineage(tmp_path):
    db = tmp_path / "eay.db"
    audit_store = VisionAuditStore(db)
    audit = _audit(audit_store)
    provenance = VisionProvenanceStore(db)
    provenance.register(audit.id)
    audit_store.decide(audit.id, "accepted", "verified against source image")
    assert provenance.learning_eligibility(audit.id) is False
    sealed = provenance.reviews.seal(
        audit.id,
        reviewer="vision-reviewer",
        approval_reference="VISION-REV-1",
    )
    assert len(sealed.fingerprint) == 64
    assert provenance.learning_eligibility(audit.id) is True


def test_pending_review_queue_contains_audit(tmp_path):
    db = tmp_path / "eay.db"
    audit_store = VisionAuditStore(db)
    audit = _audit(audit_store)
    provenance = VisionProvenanceStore(db)
    items = provenance.pending_reviews()
    assert [item["id"] for item in items] == [audit.id]
