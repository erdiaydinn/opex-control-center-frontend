from datetime import datetime, timezone
import json

import pytest

import app.learning_export_guard as guard
from app.learning_export_guard import ExportReview, build_gated_export


class FakeCandidateStore:
    def __init__(self, *, target=None, legal=False):
        self.target = target or (
            "Use the reviewed warehouse procedure, verify the supporting source, and record the decision before taking operational action."
        )
        self.legal = legal

    def export_approved(self):
        return [
            {
                "messages": [
                    {"role": "user", "content": "What should the operator do?"},
                    {"role": "assistant", "content": self.target},
                ],
                "metadata": {
                    "candidate_id": "cand-1",
                    "reason": "reviewed correction",
                    "teacher_reviewed": True,
                },
            }
        ]

    def candidate_context(self, candidate_id):
        assert candidate_id == "cand-1"
        evidence = (
            '[{"id":"legal-1","layer":"legal","authority_level":"binding"}]'
            if self.legal
            else '[{"id":"ops-1","layer":"operational"}]'
        )
        review = {
            "critique": "The original answer was uncertain and did not identify the reviewed source or the required operational verification step.",
            "improved_answer": self.target,
            "principles": [
                "Use reviewed operational evidence before action",
                "Record the decision and supporting source",
            ],
        }
        return {
            "id": "cand-1",
            "status": "approved",
            "reason": "reviewed correction",
            "user_message": "What should the operator do?",
            "model_answer": "Original uncertain answer that requires a reviewed correction.",
            "corrected_answer": self.target,
            "teacher_review_json": json.dumps(review, ensure_ascii=False),
            "evidence_json": evidence,
        }


class FakeReviewStore:
    def __init__(self, review):
        self.review = review

    def get(self, candidate_id):
        assert candidate_id == "cand-1"
        return self.review


def review(*, privacy_safe=True, evidence_reviewed=False):
    return ExportReview(
        candidate_id="cand-1",
        reviewed_by="human-reviewer",
        privacy_safe=privacy_safe,
        evidence_reviewed=evidence_reviewed,
        review_reference="REV-1",
        reviewed_at=datetime.now(timezone.utc),
    )


def test_export_fails_closed_without_explicit_export_review(monkeypatch):
    monkeypatch.setattr(guard, "candidate_store", FakeCandidateStore())
    with pytest.raises(ValueError, match="export_review_required"):
        build_gated_export(review_store=FakeReviewStore(None))


def test_export_passes_quality_gate_after_privacy_review(monkeypatch):
    monkeypatch.setattr(guard, "candidate_store", FakeCandidateStore())
    result = build_gated_export(review_store=FakeReviewStore(review()))
    assert result.gate.accepted is True
    assert len(result.gate.integrity_sha256 or "") == 64
    assert result.examples[0]["metadata"]["human_approved"] is True
    assert result.examples[0]["metadata"]["export_reviewed_by"] == "human-reviewer"
    assert result.examples[0]["metadata"]["teacher_quality_accepted"] is True
    assert len(result.examples[0]["metadata"]["teacher_quality_sha256"]) == 64


def test_legal_export_requires_explicit_evidence_review(monkeypatch):
    target = (
        "Mevzuata göre bu gereklilik doğrulanmış bağlayıcı kanıt ve yürürlük tarihiyle birlikte uygulanmalıdır."
    )
    monkeypatch.setattr(
        guard,
        "candidate_store",
        FakeCandidateStore(target=target, legal=True),
    )
    with pytest.raises(ValueError, match="legal_evidence_review_required"):
        build_gated_export(review_store=FakeReviewStore(review(evidence_reviewed=False)))

    result = build_gated_export(
        review_store=FakeReviewStore(review(evidence_reviewed=True))
    )
    assert result.gate.accepted is True
    assert result.examples[0]["metadata"]["legal_provenance"] == {
        "evidence_0": "legal-1"
    }


def test_unchanged_model_answer_without_teacher_review_is_blocked(monkeypatch):
    class UnchangedStore(FakeCandidateStore):
        def candidate_context(self, candidate_id):
            row = super().candidate_context(candidate_id)
            row["teacher_review_json"] = None
            row["model_answer"] = self.target
            return row

    monkeypatch.setattr(guard, "candidate_store", UnchangedStore())
    with pytest.raises(ValueError, match="unchanged_model_answer_without_teacher_review"):
        build_gated_export(review_store=FakeReviewStore(review()))
