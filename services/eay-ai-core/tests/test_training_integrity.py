import pytest

from app.training_integrity import (
    example_fingerprint,
    validate_dataset_integrity,
    validate_split_leakage,
)


def example(user: str, assistant: str):
    return {
        "messages": [
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "metadata": {
            "human_approved": True,
            "teacher_reviewed": True,
            "reason": "reviewed correction",
            "contains_personal_data": False,
        },
    }


def test_example_fingerprint_normalizes_case_and_spacing():
    left = example("NSFR nasıl hesaplanır?", "Başarılı siparişler denominator olarak kullanılır.")
    right = example("  nsfr   NASIL hesaplanır ", "başarılı siparişler denominator olarak kullanılır")
    assert example_fingerprint(left) == example_fingerprint(right)


def test_exact_duplicate_is_rejected():
    item = example(
        "Putaway gecikmesi nasıl değerlendirilir?",
        "İlgili SLA versiyonu tarihe göre çözülür ve geçen süre eşikle karşılaştırılır.",
    )
    result = validate_dataset_integrity([item, item])
    assert result.accepted is False
    assert result.violations == ("example_1:exact_duplicate_of_0",)
    assert len(result.integrity_sha256) == 64


def test_near_duplicate_is_rejected():
    left = example(
        "NSFR oranı nasıl doğrulanır başarılı sipariş denominator ile",
        "PFR refund compensation sayıları başarılı sipariş denominator üzerinden yeniden hesaplanır ve precedence uygulanır.",
    )
    right = example(
        "NSFR oranı nasıl doğrulanır başarılı sipariş denominator ile bugün",
        "PFR refund compensation sayıları başarılı sipariş denominator üzerinden yeniden hesaplanır ve precedence uygulanır dikkatle.",
    )
    result = validate_dataset_integrity([left, right], near_duplicate_threshold=0.70)
    assert result.accepted is False
    assert "example_1:near_duplicate_of_0" in result.violations


def test_distinct_examples_pass():
    result = validate_dataset_integrity(
        [
            example("NSFR nedir?", "NSFR müşteri kalite etkilerini sipariş bazında birleştiren operasyonel metriktir."),
            example("Putaway SLA nedir?", "Putaway SLA mal kabul sonrası raf yerleştirme süresinin sözleşmeli eşiğe göre değerlendirilmesidir."),
        ]
    )
    assert result.accepted is True
    assert result.violations == ()


def test_exact_train_eval_leakage_is_rejected():
    item = example(
        "OTP nasıl hesaplanır?",
        "OTP late prep oranı açıkça pinlenmiş scale üzerinden yüzdeye çevrildikten sonra hesaplanır.",
    )
    assert validate_split_leakage([item], [item]) == (
        "eval_0:exact_leakage_from_train_0",
    )


def test_near_duplicate_train_eval_leakage_is_rejected():
    train = example(
        "Picking süresi nasıl ağırlıklandırılır picker day seviyesinde",
        "Picker day ortalamaları eligible orders ile ağırlıklandırılır aksi halde average of averages oluşur.",
    )
    evaluation = example(
        "Picking süresi nasıl ağırlıklandırılır picker day seviyesinde bugün",
        "Picker day ortalamaları eligible orders ile ağırlıklandırılır aksi halde average of averages oluşur hatası.",
    )
    violations = validate_split_leakage(
        [train], [evaluation], near_duplicate_threshold=0.70
    )
    assert violations == ("eval_0:near_duplicate_leakage_from_train_0",)


def test_invalid_similarity_threshold_fails_closed():
    with pytest.raises(ValueError, match="training_integrity_invalid_threshold"):
        validate_dataset_integrity([], near_duplicate_threshold=0)
