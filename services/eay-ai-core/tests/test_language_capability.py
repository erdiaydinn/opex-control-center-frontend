import pytest

from app.language_capability import (
    TIER1_LANGUAGES,
    evaluate_language_capability,
    language_direction,
    normalize_language_tag,
    validate_multilingual_release,
)


def _approved(language: str):
    return evaluate_language_capability(
        language=language,
        eval_pack_version="2026.08",
        eval_score=0.92,
        safety_score=0.995,
        domain_score=0.90,
        human_approved=True,
    )


def test_normalizes_language_tags_and_direction():
    assert normalize_language_tag("tr_tr") == "tr-TR"
    assert normalize_language_tag("ar") == "ar"
    assert language_direction("fa-IR") == "rtl"
    assert language_direction("de-DE") == "ltr"


def test_rejects_invalid_language_tag():
    with pytest.raises(ValueError):
        normalize_language_tag("english")


def test_capability_is_fail_closed_until_quality_and_human_gate_pass():
    result = evaluate_language_capability(
        language="ar",
        eval_pack_version="2026.08",
        eval_score=0.80,
        safety_score=0.97,
        domain_score=0.79,
        human_approved=False,
    )
    assert result.production_eligible is False
    assert "language_quality_below_threshold" in result.blockers
    assert "language_safety_below_threshold" in result.blockers
    assert "food_retail_domain_below_threshold" in result.blockers
    assert "human_approval_required" in result.blockers


def test_capability_fingerprint_is_deterministic():
    first = _approved("tr")
    second = _approved("tr")
    assert first.production_eligible is True
    assert first.capability_sha256 == second.capability_sha256
    assert len(first.capability_sha256) == 64


def test_release_gate_requires_every_requested_language():
    approved = [_approved("tr"), _approved("en"), _approved("de")]
    ok, blockers = validate_multilingual_release(
        approved,
        required_languages=("tr", "en", "de", "ar", "fa"),
    )
    assert ok is False
    assert blockers == ("missing_language_eval:ar", "missing_language_eval:fa")


def test_tier1_surface_has_thirty_continuously_evaluated_languages():
    assert len(TIER1_LANGUAGES) == 30
    assert {"tr", "en", "de", "ar", "fa"}.issubset(set(TIER1_LANGUAGES))
