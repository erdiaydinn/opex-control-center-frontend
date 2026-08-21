from app.teacher_quality import evaluate_teacher_review


GOOD_REVIEW = {
    "critique": "The original answer is too vague because it does not separate verified evidence from an operational recommendation.",
    "improved_answer": "Verify the reviewed operational source, apply the current procedure, and record the evidence used before closing the decision.",
    "principles": [
        "Separate verified evidence from recommendations.",
        "Record the source used for operational decisions.",
    ],
}


def test_teacher_quality_accepts_structured_grounded_review():
    result = evaluate_teacher_review(
        model_answer="I think the operator should proceed.",
        review=GOOD_REVIEW,
        evidence_ids=["ops-1"],
    )
    assert result.accepted is True
    assert result.score == 100
    assert len(result.review_sha256) == 64


def test_teacher_quality_blocks_unchanged_student_answer():
    answer = GOOD_REVIEW["improved_answer"]
    result = evaluate_teacher_review(
        model_answer=answer,
        review=GOOD_REVIEW,
        evidence_ids=["ops-1"],
    )
    assert result.accepted is False
    assert "teacher_answer_unchanged" in result.violations


def test_teacher_quality_blocks_thin_placeholder_review():
    result = evaluate_teacher_review(
        model_answer="Old answer",
        review={
            "critique": "TODO",
            "improved_answer": "placeholder",
            "principles": ["be clear"],
        },
    )
    assert result.accepted is False
    assert "teacher_placeholder_not_allowed" in result.violations
    assert "teacher_principles_insufficient" in result.violations


def test_teacher_quality_blocks_legal_claim_without_evidence():
    result = evaluate_teacher_review(
        model_answer="Uncertain answer.",
        review={
            "critique": "The original answer states a conclusion without grounding it in the supplied legal evidence.",
            "improved_answer": "Mevzuata göre bu işlem zorunludur ve uygulama ilgili yönetmelik hükmüne uygun yürütülmelidir.",
            "principles": [
                "Bind legal conclusions to verified evidence.",
                "Do not invent legal obligations without sources.",
            ],
        },
        evidence_ids=[],
    )
    assert result.accepted is False
    assert "teacher_legal_claim_without_evidence" in result.violations


def test_teacher_quality_fingerprint_changes_with_evidence_lineage():
    first = evaluate_teacher_review(
        model_answer="Old answer",
        review=GOOD_REVIEW,
        evidence_ids=["ops-1"],
    )
    second = evaluate_teacher_review(
        model_answer="Old answer",
        review=GOOD_REVIEW,
        evidence_ids=["ops-2"],
    )
    assert first.review_sha256 != second.review_sha256
