import pytest
from pydantic import ValidationError

from app.modules.audit.field_truth import (
    AuditScoredItem,
    AuditSectionScoreInput,
    score_audit_items,
    score_weighted_sections,
)
from app.modules.audit.visit_planning import (
    AuditVisitCreate,
    AuditVisitNoteCreate,
    AuditVisitScopeEntry,
    build_visit_plan,
)


def _scope(state_second: str = "OUT_OF_SCOPE") -> tuple[AuditVisitScopeEntry, ...]:
    return (
        AuditVisitScopeEntry(
            section_key="oven",
            item_key="oven.clean",
            state="IN_SCOPE",
        ),
        AuditVisitScopeEntry(
            section_key="coffee",
            item_key="coffee.clean",
            state=state_second,
            reason=(
                "Auditor selected oven-only focus visit"
                if state_second == "OUT_OF_SCOPE"
                else None
            ),
        ),
    )


def test_focus_visit_is_not_official_compliance() -> None:
    payload = AuditVisitCreate(
        visit_type="FOCUS_AUDIT",
        title="Fırın odak ziyareti",
        location_id="ortakoy",
        program_key="market-quality",
        program_version=3,
        scope=_scope(),
    )

    plan = build_visit_plan(payload)

    assert plan.score_mode == "FOCUS_SCORE"
    assert plan.official_compliance_eligible is False
    assert plan.in_scope_count == 1
    assert plan.out_of_scope_count == 1


def test_full_audit_cannot_hide_approved_questions_as_out_of_scope() -> None:
    with pytest.raises(ValidationError, match="FULL_AUDIT cannot hide"):
        AuditVisitCreate(
            visit_type="FULL_AUDIT",
            title="Tam denetim",
            location_id="ortakoy",
            program_key="market-quality",
            program_version=3,
            scope=_scope(),
        )


def test_people_visit_is_explicitly_no_score_and_no_audit_program() -> None:
    payload = AuditVisitCreate(
        visit_type="PEOPLE_VISIT",
        title="İnsan ve operasyon ziyareti",
        location_id="ortakoy",
        people_topics=("çalışan geri bildirimi", "iş yükü"),
    )

    plan = build_visit_plan(payload)

    assert plan.score_mode == "NO_SCORE"
    assert plan.official_compliance_eligible is False
    assert plan.in_scope_count == 0


def test_people_visit_rejects_scored_audit_scope() -> None:
    with pytest.raises(ValidationError, match="PEOPLE_VISIT cannot claim"):
        AuditVisitCreate(
            visit_type="PEOPLE_VISIT",
            title="Yanlış karışık ziyaret",
            location_id="ortakoy",
            program_key="market-quality",
            program_version=3,
            scope=_scope("IN_SCOPE"),
            people_topics=("çalışan geri bildirimi",),
        )


def test_out_of_scope_requires_reason_and_is_not_not_applicable() -> None:
    with pytest.raises(ValidationError, match="OUT_OF_SCOPE requires"):
        AuditVisitScopeEntry(
            section_key="coffee",
            item_key="coffee.clean",
            state="OUT_OF_SCOPE",
        )

    score = score_audit_items(
        (
            AuditScoredItem(item_key="oven.clean", decision="PASS", max_points=1),
            AuditScoredItem(item_key="coffee.clean", decision="OUT_OF_SCOPE", max_points=9),
        )
    )

    assert score.out_of_scope_count == 1
    assert score.not_applicable_count == 0
    assert score.applicable_max_points == 1
    assert score.final_score_pct == 100.0


def test_not_applicable_section_weight_is_redistributed_proportionally() -> None:
    summary = score_weighted_sections(
        (
            AuditSectionScoreInput(
                section_key="coffee",
                base_weight=10,
                scope_state="NOT_APPLICABLE",
            ),
            AuditSectionScoreInput(
                section_key="oven",
                base_weight=20,
                items=(
                    AuditScoredItem(item_key="oven.clean", decision="PASS", max_points=1),
                ),
            ),
            AuditSectionScoreInput(
                section_key="shelf",
                base_weight=70,
                items=(
                    AuditScoredItem(item_key="shelf.a", decision="PASS", max_points=1),
                    AuditScoredItem(item_key="shelf.b", decision="FAIL", max_points=1),
                ),
            ),
        )
    )

    by_key = {section.section_key: section for section in summary.sections}
    assert summary.not_applicable_section_count == 1
    assert summary.out_of_scope_section_count == 0
    assert summary.excluded_base_weight == 10
    assert summary.applicable_base_weight == 90
    assert by_key["coffee"].effective_weight_pct == 0
    assert by_key["oven"].effective_weight_pct == pytest.approx(22.222222, abs=1e-6)
    assert by_key["shelf"].effective_weight_pct == pytest.approx(77.777778, abs=1e-6)
    assert summary.final_score_pct == 61.11


def test_incomplete_evidence_blocks_weighted_final_score() -> None:
    summary = score_weighted_sections(
        (
            AuditSectionScoreInput(
                section_key="oven",
                base_weight=50,
                items=(
                    AuditScoredItem(
                        item_key="oven.clean",
                        decision="INSUFFICIENT_EVIDENCE",
                        max_points=1,
                    ),
                ),
            ),
            AuditSectionScoreInput(
                section_key="coffee",
                base_weight=50,
                scope_state="NOT_APPLICABLE",
            ),
        )
    )

    assert summary.completion_state == "INCOMPLETE"
    assert summary.provisional_score_pct is None
    assert summary.final_score_pct is None


def test_scope_fingerprint_is_stable_and_scope_sensitive() -> None:
    base = AuditVisitCreate(
        visit_type="FOCUS_AUDIT",
        title="Fırın ziyareti",
        location_id="ortakoy",
        program_key="market-quality",
        program_version=3,
        scope=_scope(),
    )
    same = base.model_copy()
    changed = base.model_copy(
        update={
            "scope": (
                AuditVisitScopeEntry(
                    section_key="oven",
                    item_key="oven.clean",
                    state="OUT_OF_SCOPE",
                    reason="Coffee-only visit",
                ),
                AuditVisitScopeEntry(
                    section_key="coffee",
                    item_key="coffee.clean",
                    state="IN_SCOPE",
                ),
            )
        }
    )

    assert build_visit_plan(base).scope_fingerprint == build_visit_plan(same).scope_fingerprint
    assert build_visit_plan(base).scope_fingerprint != build_visit_plan(changed).scope_fingerprint


def test_visit_notes_are_append_only_shaped_and_source_refs_are_unique() -> None:
    note = AuditVisitNoteCreate(
        note_type="HUMAN_CONVERSATION",
        note="Ekip ile iş yükü ve eğitim ihtiyacı konuşuldu.",
        source_refs=("visit://conversation/1",),
    )
    assert note.note_type == "HUMAN_CONVERSATION"

    with pytest.raises(ValidationError, match="source refs must be unique"):
        AuditVisitNoteCreate(
            note_type="FOLLOW_UP",
            note="Takip gerekli.",
            source_refs=("ref://1", "ref://1"),
        )
