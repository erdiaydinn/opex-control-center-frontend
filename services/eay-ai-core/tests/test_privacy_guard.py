from app.privacy_guard import is_valid_tckn, scan_personal_data
from app.training_gate import validate_training_examples


TEACHER_FP = "f" * 64


def _training_example(user_text: str):
    return {
        "messages": [
            {"role": "user", "content": user_text},
            {
                "role": "assistant",
                "content": "Use the reviewed operational procedure, verify the supporting source, and record the decision before taking action.",
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


def test_tckn_checksum_reduces_false_positive_digit_runs():
    assert is_valid_tckn("10000000146") is True
    assert is_valid_tckn("10000000145") is False
    result = scan_personal_data(["order 10000000145"])
    assert result.safe is True


def test_scanner_detects_high_confidence_personal_data_without_returning_raw_values():
    raw = "TC 10000000146, mail user@example.com, phone +90 532 123 45 67, IBAN TR12 3456 7890 1234 5678 9012 34"
    result = scan_personal_data([raw])
    assert result.safe is False
    assert result.kinds == ("email", "tckn", "turkish_iban", "turkish_phone")
    serialized = repr(result)
    assert "10000000146" not in serialized
    assert "user@example.com" not in serialized
    assert "5321234567" not in serialized
    assert all(len(item.token_sha256) == 64 for item in result.findings)


def test_training_gate_fails_closed_when_metadata_claims_privacy_safe_but_pii_is_detected():
    result = validate_training_examples([
        _training_example("Please review employee record 10000000146 before training export.")
    ])
    assert result.accepted is False
    assert "example_0:personal_data_detected:tckn" in result.violations
    assert "example_0:personal_data_not_allowed" in result.violations


def test_training_gate_scans_metadata_that_is_exported_with_the_example():
    example = _training_example("How should this operational exception be handled?")
    example["metadata"]["review_reference"] = "approved by user@example.com"
    result = validate_training_examples([example])
    assert result.accepted is False
    assert "example_0:personal_data_detected:email" in result.violations
