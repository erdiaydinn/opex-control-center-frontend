import pytest

from app.multilingual_learning import (
    CORE_LANGUAGES,
    EXPECTED_CORE_SLOTS,
    EXPECTED_LENSES_PER_LANGUAGE,
    LEARNING_LENSES,
    RTL_LANGUAGES,
    build_learning_depth_plan,
    evaluate_learning_depth_bundle,
)


def test_core_plan_expands_one_concept_to_150_distinct_slots():
    plan = build_learning_depth_plan(concept_id="nsfr")
    assert plan.languages == CORE_LANGUAGES
    assert plan.lens_count == EXPECTED_LENSES_PER_LANGUAGE == 30
    assert plan.slot_count == EXPECTED_CORE_SLOTS == 150
    assert len({slot.slot_fingerprint for slot in plan.slots}) == 150
    assert len({(slot.language, slot.lens) for slot in plan.slots}) == 150


def test_arabic_and_persian_slots_are_marked_rtl():
    plan = build_learning_depth_plan(concept_id="allergen-declaration")
    rtl_languages = {slot.language for slot in plan.slots if slot.rtl}
    assert rtl_languages == RTL_LANGUAGES


def test_full_core_bundle_passes_only_with_all_30_lenses_in_all_5_languages():
    plan = build_learning_depth_plan(concept_id="putaway-sla")
    result = evaluate_learning_depth_bundle(
        concept_id="putaway-sla",
        observed_pairs=((slot.language, slot.lens) for slot in plan.slots),
    )
    assert result.accepted is True
    assert result.expected_slots == 150
    assert result.observed_slots == 150
    assert result.missing_languages == ()
    assert result.missing_lenses_by_language == ()


def test_six_lens_style_bundle_is_rejected_by_5x_depth_gate():
    shallow_lenses = LEARNING_LENSES[:6]
    result = evaluate_learning_depth_bundle(
        concept_id="refund",
        observed_pairs=((language, lens) for language in CORE_LANGUAGES for lens in shallow_lenses),
    )
    assert result.accepted is False
    assert result.observed_slots == 30
    assert len(result.missing_lenses_by_language) == 5
    assert all(len(missing) == 24 for _, missing in result.missing_lenses_by_language)


def test_duplicate_language_lens_pair_fails_closed():
    plan = build_learning_depth_plan(concept_id="legal-effective-date")
    pairs = [(slot.language, slot.lens) for slot in plan.slots]
    pairs.append(pairs[0])
    result = evaluate_learning_depth_bundle(concept_id="legal-effective-date", observed_pairs=pairs)
    assert result.accepted is False
    assert result.duplicate_pairs


def test_language_normalization_deduplicates_locale_variants():
    plan = build_learning_depth_plan(concept_id="inventory", languages=("tr-TR", "TR_tr", "en-US"))
    assert plan.languages == ("tr", "en")
    assert plan.slot_count == 60


def test_empty_concept_fails_closed():
    with pytest.raises(ValueError, match="learning_concept_id_required"):
        build_learning_depth_plan(concept_id=" ")
