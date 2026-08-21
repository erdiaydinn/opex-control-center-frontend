from datetime import date

from app.main import Evidence
from app.rag_evals import evaluate_evidence


def ev(**kwargs):
    base = dict(
        id="x", layer="legal", title="t", excerpt="e", source_name="s",
        source_url="https://www.resmigazete.gov.tr/x", effective_from=date(2026,1,1),
        effective_to=None, authority_level="binding", score=1.0,
    )
    base.update(kwargs)
    return Evidence(**base)


def test_valid_legal_evidence_passes():
    result = evaluate_evidence([ev()], as_of=date(2026,8,10), legal_required=True)
    assert result.passed
    assert result.legal_count == 1


def test_future_and_unverified_legal_fail():
    result = evaluate_evidence([
        ev(id="future", effective_from=date(2027,1,1), authority_level="voluntary", source_url=None)
    ], as_of=date(2026,8,10), legal_required=True)
    assert not result.passed
    assert any(x.startswith("future_evidence") for x in result.failures)
    assert any(x.startswith("legal_not_binding") for x in result.failures)
    assert any(x.startswith("legal_missing_source") for x in result.failures)
