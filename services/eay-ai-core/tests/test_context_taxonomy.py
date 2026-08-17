from app.context_taxonomy import (
    CATEGORY_SPECS,
    ExecutiveContextCategory,
    require_context_category,
)


def test_every_executive_context_category_has_a_governed_mapping():
    assert set(CATEGORY_SPECS) == set(ExecutiveContextCategory)
    assert all(spec.expected_impacts for spec in CATEGORY_SPECS.values())


def test_critical_public_context_requires_official_sources():
    for category in (
        ExecutiveContextCategory.PUBLIC_HOLIDAY,
        ExecutiveContextCategory.PORT_AIRPORT_DISRUPTION,
        ExecutiveContextCategory.INFRASTRUCTURE_OUTAGE,
        ExecutiveContextCategory.ENERGY_UTILITY,
        ExecutiveContextCategory.PUBLIC_SAFETY_EMERGENCY,
        ExecutiveContextCategory.PUBLIC_HEALTH_SIGNAL,
    ):
        assert require_context_category(category).official_source_required is True


def test_market_and_social_signals_require_independent_corroboration():
    assert require_context_category(
        ExecutiveContextCategory.COMPETITOR_MARKET_MOVE
    ).min_independent_sources >= 2
    assert require_context_category(
        ExecutiveContextCategory.SOCIAL_SENTIMENT
    ).min_independent_sources >= 2


def test_taxonomy_preserves_base_context_engine_instead_of_creating_parallel_truth():
    spec = require_context_category(ExecutiveContextCategory.SPORTS_EVENT)
    assert spec.base_kind.value == "city_event"
