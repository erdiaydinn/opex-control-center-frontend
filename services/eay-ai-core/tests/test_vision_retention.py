from datetime import datetime, timedelta, timezone

import pytest

from app.vision_audit import AuditCreate, VisionAuditStore, VisualFinding
from app.vision_provenance import VisionProvenanceStore
from app.vision_retention import VisionRetentionStore


def _audit(store, *, image="a" * 64):
    return store.create(
        AuditCreate(
            image_sha256=image,
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


def test_provenance_registration_creates_retention_lineage(tmp_path):
    db = tmp_path / "eay.db"
    audits = VisionAuditStore(db)
    audit = _audit(audits)
    provenance = VisionProvenanceStore(db)

    evidence = provenance.register(audit.id)
    retention = VisionRetentionStore(db).get(audit.id)

    assert evidence.retention_fingerprint == retention.fingerprint
    assert retention.evidence_chain_sha256 == evidence.evidence_chain_sha256
    assert retention.state == "active"


def test_tombstoned_evidence_is_never_learning_eligible(tmp_path):
    db = tmp_path / "eay.db"
    audits = VisionAuditStore(db)
    audit = _audit(audits)
    provenance = VisionProvenanceStore(db)
    provenance.register(audit.id)
    audits.decide(audit.id, "accepted", "human verified")
    provenance.reviews.seal(
        audit.id,
        reviewer="reviewer-1",
        approval_reference="vision-review-approval-1",
    )
    assert provenance.learning_eligibility(audit.id) is True

    tombstone = provenance.retention.tombstone(audit.id, reason="retention window closed")
    assert tombstone.state == "tombstoned"
    assert len(tombstone.tombstone_fingerprint or "") == 64
    assert provenance.learning_eligibility(audit.id) is False


def test_expired_retention_blocks_learning_without_erasing_provenance(tmp_path):
    db = tmp_path / "eay.db"
    audits = VisionAuditStore(db)
    audit = _audit(audits)
    provenance = VisionProvenanceStore(db)
    evidence = provenance.register(audit.id)
    audits.decide(audit.id, "accepted", "human verified")
    provenance.reviews.seal(
        audit.id,
        reviewer="reviewer-1",
        approval_reference="vision-review-approval-2",
    )

    retention = provenance.retention.get(audit.id)
    after_expiry = datetime.fromisoformat(retention.retain_until) + timedelta(seconds=1)
    assert provenance.retention.is_active(audit.id, as_of=after_expiry) is False
    assert provenance.retention.get(audit.id).evidence_chain_sha256 == evidence.evidence_chain_sha256


def test_retention_chain_drift_is_rejected(tmp_path):
    db = tmp_path / "eay.db"
    retention = VisionRetentionStore(db)
    retention.ensure_policy(audit_id="audit-1", evidence_chain_sha256="a" * 64)
    with pytest.raises(ValueError, match="vision_retention_evidence_chain_drift"):
        retention.ensure_policy(audit_id="audit-1", evidence_chain_sha256="b" * 64)
