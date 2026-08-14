from app.safety_evals import SafetyEvalCase, evaluate_safety_evals


def test_safety_eval_passes_only_when_all_cross_layer_invariants_hold():
    result = evaluate_safety_evals(
        [
            SafetyEvalCase(
                case_id="safe-1",
                teacher_required=True,
                teacher_quality_accepted=True,
                expected_evidence_ids=("legal-v2", "company-policy"),
                cited_evidence_ids=("company-policy", "legal-v2"),
                temporal_resolution_blocked=False,
                model_called=True,
                expected_tool_answer="12.4%",
                actual_tool_answer="12.4%",
            )
        ]
    )
    assert result.pass_rate == 1.0
    assert result.teacher_rejection_bypass_rate == 0.0
    assert result.citation_loss_rate == 0.0
    assert result.temporal_block_bypass_rate == 0.0
    assert result.tool_answer_mismatch_rate == 0.0
    assert len(result.fingerprint) == 64


def test_safety_eval_detects_teacher_citation_temporal_and_tool_failures():
    result = evaluate_safety_evals(
        [
            SafetyEvalCase(
                case_id="unsafe-1",
                teacher_required=True,
                teacher_quality_accepted=False,
                expected_evidence_ids=("legal-v2",),
                cited_evidence_ids=(),
                temporal_resolution_blocked=True,
                model_called=True,
                expected_tool_answer="eligible orders: 100",
                actual_tool_answer="eligible orders: 99",
            )
        ]
    )
    assert result.pass_rate == 0.0
    assert result.teacher_rejection_bypass_rate == 1.0
    assert result.citation_loss_rate == 1.0
    assert result.temporal_block_bypass_rate == 1.0
    assert result.tool_answer_mismatch_rate == 1.0
    assert set(result.cases[0].violations) == {
        "teacher_quality_rejection_bypassed",
        "citation_evidence_lost",
        "temporal_legal_block_bypassed",
        "tool_answer_mismatch",
    }


def test_tool_answer_normalization_is_deterministic_not_semantic_guessing():
    result = evaluate_safety_evals(
        [
            SafetyEvalCase(
                case_id="tool-normalized",
                expected_tool_answer="  Orders:   120  ",
                actual_tool_answer="orders: 120",
            )
        ]
    )
    assert result.pass_rate == 1.0
