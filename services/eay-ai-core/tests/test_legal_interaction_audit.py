from app.legal_interaction_audit import LegalInteractionAuditStore


def test_legal_interaction_audit_is_immutable_and_idempotent(tmp_path):
    store = LegalInteractionAuditStore(tmp_path / "eay.db")
    fingerprint = "a" * 64

    first = store.record(
        interaction_id="interaction-1",
        as_of="2026-06-01",
        temporal_resolution_fingerprint=fingerprint,
        active_instrument_ids=["v2", "v1", "v2"],
        evidence_ids=["legal:v2:chunk:1", "company:policy:0"],
    )
    assert len(first.audit_fingerprint) == 64
    assert first.active_instrument_ids == ("v1", "v2")

    repeated = store.record(
        interaction_id="interaction-1",
        as_of="2026-06-01",
        temporal_resolution_fingerprint=fingerprint,
        active_instrument_ids=["v1", "v2"],
        evidence_ids=["legal:v2:chunk:1", "company:policy:0"],
    )
    assert repeated.audit_fingerprint == first.audit_fingerprint

    import pytest
    with pytest.raises(ValueError, match="immutable_legal_interaction_audit_conflict"):
        store.record(
            interaction_id="interaction-1",
            as_of="2026-06-02",
            temporal_resolution_fingerprint=fingerprint,
            active_instrument_ids=["v2"],
            evidence_ids=["legal:v2:chunk:1"],
        )


def test_legal_interaction_audit_requires_temporal_fingerprint(tmp_path):
    store = LegalInteractionAuditStore(tmp_path / "eay.db")
    import pytest
    with pytest.raises(ValueError, match="temporal_resolution_fingerprint_required"):
        store.record(
            interaction_id="interaction-2",
            as_of="2026-06-01",
            temporal_resolution_fingerprint="bad",
            active_instrument_ids=[],
            evidence_ids=[],
        )
