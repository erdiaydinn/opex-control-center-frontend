import sqlite3
from datetime import datetime, timezone

import pytest

from app.vision_audit import AuditCreate, VisionAuditStore, VisualFinding
from app.vision_provenance import VisionProvenanceStore
from app.vision_review_lineage import VisionReviewDecisionStore


def _seed(db):
    audits = VisionAuditStore(db)
    audit = audits.create(AuditCreate(
        image_sha256="a" * 64,
        store_id="store-1",
        captured_at=datetime.now(timezone.utc),
        model_name="local-vision",
        model_version="0.1",
        source_uri="file:///secure/audit.jpg",
        findings=[VisualFinding(
            finding_type="shelf_gap", description="gap detected",
            severity="medium", confidence=0.9,
        )],
    ))
    provenance = VisionProvenanceStore(db)
    provenance.register(audit.id)
    return audits, provenance, audit


def test_review_cannot_seal_before_final_human_decision(tmp_path):
    db = tmp_path / "eay.db"
    _, _, audit = _seed(db)
    with pytest.raises(ValueError, match="vision_review_decision_not_final"):
        VisionReviewDecisionStore(db).seal(
            audit.id, reviewer="reviewer", approval_reference="REV-1"
        )


def test_sealed_review_binds_evidence_retention_reviewer_and_note(tmp_path):
    db = tmp_path / "eay.db"
    audits, provenance, audit = _seed(db)
    audits.decide(audit.id, "accepted", "verified against source image")
    sealed = provenance.reviews.seal(
        audit.id, reviewer="reviewer", approval_reference="REV-1"
    )
    verified = provenance.reviews.verify(audit.id)
    assert verified.fingerprint == sealed.fingerprint
    assert verified.decision == "accepted"
    assert verified.evidence_chain_sha256
    assert verified.retention_fingerprint
    assert verified.reviewer_note_sha256
    assert provenance.learning_eligibility(audit.id) is True


def test_review_note_drift_revokes_learning_eligibility(tmp_path):
    db = tmp_path / "eay.db"
    audits, provenance, audit = _seed(db)
    audits.decide(audit.id, "accepted", "verified against source image")
    provenance.reviews.seal(audit.id, reviewer="reviewer", approval_reference="REV-1")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE vision_audits SET reviewer_note='changed after seal' WHERE id=?",
            (audit.id,),
        )
    with pytest.raises(ValueError, match="vision_review_note_drift"):
        provenance.reviews.verify(audit.id)
    assert provenance.learning_eligibility(audit.id) is False


def test_retention_tombstone_revokes_accepted_sealed_review(tmp_path):
    db = tmp_path / "eay.db"
    audits, provenance, audit = _seed(db)
    audits.decide(audit.id, "accepted", "verified")
    provenance.reviews.seal(audit.id, reviewer="reviewer", approval_reference="REV-1")
    assert provenance.learning_eligibility(audit.id) is True
    provenance.retention.tombstone(audit.id, reason="retention expired")
    assert provenance.learning_eligibility(audit.id) is False


def test_duplicate_review_seal_is_rejected(tmp_path):
    db = tmp_path / "eay.db"
    audits, provenance, audit = _seed(db)
    audits.decide(audit.id, "accepted", "verified")
    provenance.reviews.seal(audit.id, reviewer="reviewer", approval_reference="REV-1")
    with pytest.raises(ValueError, match="vision_review_decision_already_sealed"):
        provenance.reviews.seal(audit.id, reviewer="other", approval_reference="REV-2")
