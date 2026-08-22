from __future__ import annotations

from datetime import date

from app.ys_tr_cycle_count_intelligence import (
    RULE,
    YS_TR_CYCLE_COUNT_KNOWLEDGE_CONTRACT,
    cycle_count_company_knowledge_text,
    explain_cycle_count_rule,
    is_cycle_count_question,
)


def test_ys_tr_cycle_count_rule_is_fingerprint_sealed_and_week_bound():
    assert RULE.contract_id == YS_TR_CYCLE_COUNT_KNOWLEDGE_CONTRACT
    assert RULE.tenant_id == "YS_TR"
    assert RULE.assignment_date_field == "cycle_count_created_at_date"
    assert RULE.completion_date_field == "cycle_count_completed_at_date"
    assert RULE.week_start == "MONDAY"
    assert RULE.week_end == "SUNDAY"
    assert RULE.completion_deadline == "SUNDAY"
    assert RULE.main_metric == "total_completion_rate"
    assert RULE.main_metric_scale == "0_to_1"
    assert RULE.hybrid_go_live_date == date(2026, 4, 13)
    assert RULE.hybrid_weekly_sku_target == 210
    assert len(RULE.fingerprint) == 64


def test_late_completion_semantics_cannot_credit_the_next_week():
    text = cycle_count_company_knowledge_text()
    assert "Monday through Sunday" in text
    assert "no later than Sunday" in text
    assert "following Monday or later" in text
    assert "does not complete the original week" in text
    assert "must not give credit to the later week" in text


def test_cycle_count_questions_are_recognized_in_turkish_and_english():
    assert is_cycle_count_question("Karlıktepe sayım completion neden 0.75?")
    assert is_cycle_count_question("What is the cycle count weekly compliance rule?")
    assert is_cycle_count_question("cycle_count_completed_at_date nasıl kullanılıyor?")
    assert not is_cycle_count_question("Bugünkü hava nasıl?")


def test_deterministic_rule_explanation_is_available_for_jarvis():
    answer = explain_cycle_count_rule("Yemeksepeti cycle count sayım kuralı nedir?")
    assert answer is not None
    assert "total_completion_rate" in answer
    assert "0.25" in answer
    assert "210 SKU/week" in answer
    assert explain_cycle_count_rule("hello") is None
