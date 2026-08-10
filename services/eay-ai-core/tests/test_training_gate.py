from app.training_gate import validate_training_examples


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
                {"role": "assistant", "content": "Yasal olarak bu işlem zorunludur."},
            ],
            "metadata": {"human_approved": True},
        }
    ])
    assert not result.accepted
    assert "example_0:legal_claim_without_provenance" in result.violations


def test_accepts_human_approved_grounded_example():
    result = validate_training_examples([
        {
            "messages": [
                {"role": "user", "content": "Is this mandatory?"},
                {"role": "assistant", "content": "Mevzuata göre bu şart uygulanır."},
            ],
            "metadata": {
                "human_approved": True,
                "contains_personal_data": False,
                "legal_provenance": {"instrument_id": "tgk-x", "verification_id": "v1"},
            },
        }
    ])
    assert result.accepted
    assert len(result.dataset_sha256) == 64
