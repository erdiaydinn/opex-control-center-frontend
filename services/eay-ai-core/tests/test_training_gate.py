from app.training_gate import validate_training_examples


TEACHER_FP = "f" * 64


def _approved_example(user="Is this mandatory?", assistant=None):
    return {
        "messages": [
            {"role": "user", "content": user},
            {
                "role": "assistant",
                "content": assistant
                or "Use the reviewed operational procedure, verify the supporting source, and record the decision before taking action.",
            },
        ],
        "metadata": {
            "human_approved": True,
            "contains_personal_data": False,
            "teacher_reviewed": True,
            "teacher_quality_accepted": True,
            "teacher_quality_sha256": TEACHER_FP,
            "reason": "reviewed training correction",
        },
    }


def test_rejects_unapproved_training_example():
    result = validate_training_examples([
        {
            "messages": [
                {"role": "user", "content": "What is the SOP?"},
                {"role": "assistant", "content": "Use the approved process."},
            ],
            "metadata": {"human_approved": False},
        }
    ])
    assert not result.accepted
    assert "example_0:not_human_approved" in result.violations


def test_rejects_legal_claim_without_provenance():
    result = validate_training_examples([
        {
            "messages": [
                {"role": "user", "content": "Is this mandatory?"},
                {"role": "assistant", "content": "Yasal olarak bu işlem zorunludur ve ilgili operasyon bu kurala uymalıdır."},
            ],
            "metadata": {
                "human_approved": True,
                "reason": "legal correction",
                "teacher_reviewed": True,
                "teacher_quality_accepted": True,
                "teacher_quality_sha256": TEACHER_FP,
            },
        }
    ])
    assert not result.accepted
    assert "example_0:legal_claim_without_provenance" in result.violations


def test_accepts_human_approved_grounded_example():
    result = validate_training_examples([
        {
            "messages": [
                {"role": "user", "content": "Is this mandatory?"},
                {
                    "role": "assistant",
                    "content": "Mevzuata göre bu şart belirtilen tarih için uygulanır; operasyon kararı doğrulanmış kaynak ve yürürlük bilgisine dayanmalıdır.",
                },
            ],
            "metadata": {
                "human_approved": True,
                "contains_personal_data": False,
                "teacher_reviewed": True,
                "teacher_quality_accepted": True,
                "teacher_quality_sha256": TEACHER_FP,
                "reason": "verified legal correction",
                "legal_provenance": {"instrument_id": "tgk-x", "verification_id": "v1"},
            },
        }
    ])
    assert result.accepted
    assert len(result.dataset_sha256) == 64
    assert len(result.integrity_sha256 or "") == 64
    assert len(result.quality_fingerprints) == 1
    assert len(result.quality_fingerprints[0]) == 64
    assert result.teacher_quality_fingerprints == [TEACHER_FP]


def test_rejects_thin_or_unreasoned_target_even_when_human_flag_is_true():
    result = validate_training_examples([
        {
            "messages": [
                {"role": "user", "content": "Explain this"},
                {"role": "assistant", "content": "Use it."},
            ],
            "metadata": {"human_approved": True},
        }
    ])
    assert not result.accepted
    assert "example_0:target_answer_too_short" in result.violations
    assert "example_0:learning_reason_required" in result.violations


def test_training_gate_rejects_duplicate_examples_before_manifest():
    item = _approved_example()
    result = validate_training_examples([item, item])
    assert result.accepted is False
    assert "example_1:exact_duplicate_of_0" in result.violations
