from app.dataset_governance import filter_training_dataset, gate_training_example


def example(content="normal soru", **metadata):
    return {
        "messages": [
            {"role": "user", "content": content},
            {"role": "assistant", "content": "cevap"},
        ],
        "metadata": {"human_approved": True, **metadata},
    }


def test_approved_clean_example_passes():
    result = gate_training_example(example())
    assert result.approved
    assert len(result.content_sha256) == 64


def test_pii_is_rejected():
    result = gate_training_example(example("TC 12345678901"))
    assert not result.approved
    assert "possible_pii_detected" in result.reasons


def test_legal_claim_requires_verified_evidence():
    result = gate_training_example(example("mevzuat", contains_legal_claim=True))
    assert not result.approved
    assert "legal_claim_without_verified_evidence" in result.reasons


def test_filter_only_keeps_gated_examples():
    clean = example()
    dirty = example("erdi@example.com")
    approved, results = filter_training_dataset([clean, dirty])
    assert approved == [clean]
    assert len(results) == 2
