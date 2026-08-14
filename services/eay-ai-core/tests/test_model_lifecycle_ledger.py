import sqlite3

import pytest

from app.model_lifecycle_ledger import (
    ModelLifecycleLedger,
    RetirementRequest,
    RollbackAuthorizationRequest,
)


SOURCE_PROOF = "a" * 64
TARGET_PROOF = "b" * 64


def _seed(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE model_registry (
            id TEXT PRIMARY KEY, status TEXT NOT NULL)"""
        )
        conn.execute(
            """CREATE TABLE model_production_promotions (
            id TEXT PRIMARY KEY, model_record_id TEXT NOT NULL UNIQUE,
            release_proof_fingerprint TEXT NOT NULL UNIQUE)"""
        )
        conn.execute("INSERT INTO model_registry VALUES ('source','production')")
        conn.execute("INSERT INTO model_registry VALUES ('target','retired')")
        conn.execute(
            "INSERT INTO model_production_promotions VALUES ('p1','source',?)",
            (SOURCE_PROOF,),
        )
        conn.execute(
            "INSERT INTO model_production_promotions VALUES ('p2','target',?)",
            (TARGET_PROOF,),
        )


def test_retirement_is_atomic_and_binds_release_proof(tmp_path):
    db_path = tmp_path / "eay.db"
    _seed(db_path)
    ledger = ModelLifecycleLedger(db_path)

    record = ledger.retire(
        RetirementRequest(
            model_record_id="source",
            release_proof_fingerprint=SOURCE_PROOF,
            approved_by="release-manager",
            approval_reference="RET-1",
            reason="Observed production regression",
        )
    )

    assert record.action == "retire"
    assert record.sequence_no == 1
    assert record.previous_fingerprint is None
    assert len(record.fingerprint) == 64
    with sqlite3.connect(db_path) as conn:
        status = conn.execute("SELECT status FROM model_registry WHERE id='source'").fetchone()[0]
        stored = conn.execute(
            "SELECT source_release_proof_fingerprint FROM model_lifecycle_ledger WHERE id=?",
            (record.id,),
        ).fetchone()[0]
    assert status == "retired"
    assert stored == SOURCE_PROOF


def test_retirement_rejects_unmatched_release_proof_without_state_change(tmp_path):
    db_path = tmp_path / "eay.db"
    _seed(db_path)
    ledger = ModelLifecycleLedger(db_path)

    with pytest.raises(KeyError, match="production_release_proof_not_found"):
        ledger.retire(
            RetirementRequest(
                model_record_id="source",
                release_proof_fingerprint="f" * 64,
                approved_by="release-manager",
                approval_reference="RET-BAD",
                reason="Should fail closed",
            )
        )

    with sqlite3.connect(db_path) as conn:
        status = conn.execute("SELECT status FROM model_registry WHERE id='source'").fetchone()[0]
        count = conn.execute("SELECT COUNT(*) FROM model_lifecycle_ledger").fetchone()[0]
    assert status == "production"
    assert count == 0


def test_rollback_authorization_retires_source_but_never_reactivates_target(tmp_path):
    db_path = tmp_path / "eay.db"
    _seed(db_path)
    ledger = ModelLifecycleLedger(db_path)

    record = ledger.authorize_rollback(
        RollbackAuthorizationRequest(
            model_record_id="source",
            release_proof_fingerprint=SOURCE_PROOF,
            target_model_record_id="target",
            target_release_proof_fingerprint=TARGET_PROOF,
            approved_by="incident-commander",
            approval_reference="RB-1",
            reason="Rollback authorized after canary regression",
        )
    )

    assert record.action == "rollback_authorized"
    assert record.target_model_record_id == "target"
    assert record.target_release_proof_fingerprint == TARGET_PROOF
    with sqlite3.connect(db_path) as conn:
        source_status = conn.execute("SELECT status FROM model_registry WHERE id='source'").fetchone()[0]
        target_status = conn.execute("SELECT status FROM model_registry WHERE id='target'").fetchone()[0]
    assert source_status == "retired"
    assert target_status == "retired"


def test_rollback_rejects_unknown_target_release_proof(tmp_path):
    db_path = tmp_path / "eay.db"
    _seed(db_path)
    ledger = ModelLifecycleLedger(db_path)

    with pytest.raises(KeyError, match="production_release_proof_not_found"):
        ledger.authorize_rollback(
            RollbackAuthorizationRequest(
                model_record_id="source",
                release_proof_fingerprint=SOURCE_PROOF,
                target_model_record_id="target",
                target_release_proof_fingerprint="0" * 64,
                approved_by="incident-commander",
                approval_reference="RB-BAD",
                reason="Invalid target proof must fail closed",
            )
        )

    with sqlite3.connect(db_path) as conn:
        source_status = conn.execute("SELECT status FROM model_registry WHERE id='source'").fetchone()[0]
    assert source_status == "production"


def test_verify_chain_replays_retirement_and_release_proof(tmp_path):
    db_path = tmp_path / "eay.db"
    _seed(db_path)
    ledger = ModelLifecycleLedger(db_path)
    record = ledger.retire(
        RetirementRequest(
            model_record_id="source",
            release_proof_fingerprint=SOURCE_PROOF,
            approved_by="release-manager",
            approval_reference="RET-VERIFY",
            reason="Verify immutable lifecycle chain",
        )
    )

    verified = ledger.verify_chain()
    assert verified.passed is True
    assert verified.record_count == 1
    assert verified.head_fingerprint == record.fingerprint
    assert verified.verified_release_proofs == 1


def test_verify_chain_detects_payload_tampering(tmp_path):
    db_path = tmp_path / "eay.db"
    _seed(db_path)
    ledger = ModelLifecycleLedger(db_path)
    ledger.retire(
        RetirementRequest(
            model_record_id="source",
            release_proof_fingerprint=SOURCE_PROOF,
            approved_by="release-manager",
            approval_reference="RET-TAMPER",
            reason="Original reason",
        )
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE model_lifecycle_ledger SET reason='tampered reason' WHERE sequence_no=1")

    with pytest.raises(ValueError, match="model_lifecycle_fingerprint_mismatch"):
        ledger.verify_chain()


def test_verify_chain_detects_broken_release_lineage(tmp_path):
    db_path = tmp_path / "eay.db"
    _seed(db_path)
    ledger = ModelLifecycleLedger(db_path)
    ledger.authorize_rollback(
        RollbackAuthorizationRequest(
            model_record_id="source",
            release_proof_fingerprint=SOURCE_PROOF,
            target_model_record_id="target",
            target_release_proof_fingerprint=TARGET_PROOF,
            approved_by="incident-commander",
            approval_reference="RB-VERIFY",
            reason="Rollback lineage verification",
        )
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM model_production_promotions WHERE model_record_id='target'")

    with pytest.raises(KeyError, match="production_release_proof_not_found"):
        ledger.verify_chain()
