from app.main import ChatAnswer, LayerFinding, validate_citations


def test_legal_claim_is_downgraded_without_binding_evidence():
    answer = ChatAnswer(
        answer="test",
        legal=LayerFinding(status="supported", summary="law", citations=["fake"]),
        company=LayerFinding(status="ok", summary="company", citations=["c1", "fake"]),
        standards=LayerFinding(status="none", summary="", citations=[]),
        operational=LayerFinding(status="none", summary="", citations=[]),
        recommendation="review",
        risk="unknown",
        confidence=0.7,
        requires_human_review=False,
        evidence=[],
        model="test",
        interaction_id="i1",
    )

    checked = validate_citations(answer, {"c1"}, has_legal=False)

    assert checked.legal.status == "insufficient"
    assert checked.legal.citations == []
    assert checked.company.citations == ["c1"]
    assert checked.requires_human_review is True
