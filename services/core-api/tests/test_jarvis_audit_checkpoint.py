from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import os
from uuid import uuid4

import asyncpg
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
import pytest

from app.core.audit_checkpoint import (
    AUDIT_CHECKPOINT_PURPOSE,
    AuditCheckpointConfigurationError,
    AuditCheckpointSettings,
    AuditCheckpointSigner,
    AuditCheckpointValidationError,
    issue_tenant_audit_checkpoint,
    verify_audit_chain_rows,
    verify_signed_audit_checkpoint,
    verify_tenant_audit_chain,
)

GENESIS_HASH = "0" * 64


def _integration_enabled() -> bool:
    return os.getenv("EAY_JARVIS_SECURITY_POSTGRES_INTEGRATION") == "1"


def _write_private_key(path, curve: ec.EllipticCurve) -> None:
    private_key = ec.generate_private_key(curve)
    path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)


def _event_hash(sequence: int, previous_hash: str, payload: str) -> str:
    value = f"eay-audit-chain-v1|{sequence}|{previous_hash}|{payload}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_verify_audit_chain_rows_rejects_payload_tampering() -> None:
    tenant_id = uuid4()
    first_payload = '{"event":"one"}'
    first_hash = _event_hash(1, GENESIS_HASH, first_payload)
    second_payload = '{"event":"two"}'
    second_hash = _event_hash(2, first_hash, second_payload)
    rows = [
        {
            "tenant_id": tenant_id,
            "chain_sequence": 1,
            "previous_event_hash": GENESIS_HASH,
            "event_hash": first_hash,
            "event_payload": first_payload,
        },
        {
            "tenant_id": tenant_id,
            "chain_sequence": 2,
            "previous_event_hash": first_hash,
            "event_hash": second_hash,
            "event_payload": second_payload,
        },
    ]

    tip = verify_audit_chain_rows(rows, tenant_id=tenant_id)
    assert tip.chain_sequence == 2
    assert tip.event_count == 2
    assert tip.event_hash == second_hash

    rows[1]["event_payload"] = '{"event":"tampered"}'
    with pytest.raises(
        AuditCheckpointValidationError,
        match="canonical payload",
    ):
        verify_audit_chain_rows(rows, tenant_id=tenant_id)


def test_production_settings_reject_private_key_environment_material(monkeypatch) -> None:
    monkeypatch.setenv("OPEX_ENVIRONMENT", "production")
    monkeypatch.setenv("OPEX_AUDIT_CHECKPOINT_ISSUER", "eay-audit-anchor")
    monkeypatch.setenv("OPEX_AUDIT_CHECKPOINT_SIGNING_KEY_FILE", "/run/secrets/audit.pem")
    monkeypatch.setenv("OPEX_AUDIT_CHECKPOINT_SIGNING_KID", "audit-2026-01")
    monkeypatch.setenv("OPEX_AUDIT_CHECKPOINT_SIGNING_KEY", "forbidden-inline-material")

    with pytest.raises(
        AuditCheckpointConfigurationError,
        match="must not be supplied through environment variables",
    ):
        AuditCheckpointSettings.from_environment()


def test_signer_rejects_non_p256_key(tmp_path) -> None:
    key_path = tmp_path / "audit-p384.pem"
    _write_private_key(key_path, ec.SECP384R1())
    settings = AuditCheckpointSettings(
        environment="test",
        issuer="eay-audit-anchor",
        signing_key_file=str(key_path),
        signing_kid="audit-test",
    )

    with pytest.raises(
        AuditCheckpointConfigurationError,
        match="P-256",
    ):
        AuditCheckpointSigner(settings)


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _integration_enabled(),
    reason="PostgreSQL Jarvis audit-checkpoint acceptance is opt-in",
)
async def test_signed_checkpoint_binds_verified_postgres_chain_without_worm_claim(
    tmp_path,
) -> None:
    connection = await asyncpg.connect(os.environ["EAY_TEST_MIGRATOR_DSN"])
    tenant_id = uuid4()
    empty_tenant_id = uuid4()
    try:
        await connection.executemany(
            """
            INSERT INTO public.tenants(id, slug, display_name)
            VALUES ($1, $2, $3)
            """,
            (
                (tenant_id, f"checkpoint-{tenant_id.hex}", "Checkpoint tenant"),
                (
                    empty_tenant_id,
                    f"checkpoint-empty-{empty_tenant_id.hex}",
                    "Empty checkpoint tenant",
                ),
            ),
        )

        async def insert_event(sequence: int) -> None:
            event_id = uuid4()
            await connection.execute(
                """
                INSERT INTO public.audit_events(
                    id,
                    tenant_id,
                    actor_subject,
                    action,
                    resource_type,
                    resource_id,
                    decision,
                    request_id,
                    data,
                    created_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb,
                    clock_timestamp() + ($10::bigint * interval '1 microsecond')
                )
                """,
                event_id,
                tenant_id,
                "jarvis-checkpoint-test",
                "ai_tool_execution_authorized",
                "ai_tool",
                f"checkpoint-execution-{sequence}",
                "allowed",
                f"checkpoint-request-{sequence}-{event_id}",
                '{"checkpoint_test":true}',
                sequence,
            )

        await insert_event(1)
        await insert_event(2)

        tip = await verify_tenant_audit_chain(
            connection,
            tenant_id=tenant_id,
            page_size=1,
        )
        assert tip.chain_sequence == 2
        assert tip.event_count == 2

        key_path = tmp_path / "audit-checkpoint.pem"
        _write_private_key(key_path, ec.SECP256R1())
        signer = AuditCheckpointSigner(
            AuditCheckpointSettings(
                environment="test",
                issuer="eay-audit-anchor-test",
                signing_key_file=str(key_path),
                signing_kid="audit-test-2026",
            )
        )
        issued_at = datetime(2026, 8, 19, 21, 30, tzinfo=UTC)
        token = await issue_tenant_audit_checkpoint(
            connection,
            tenant_id=tenant_id,
            signer=signer,
            page_size=1,
            issued_at=issued_at,
        )
        claims = verify_signed_audit_checkpoint(
            token,
            public_key_pem=signer.public_key_pem(),
            expected_issuer="eay-audit-anchor-test",
            expected_tenant_id=tenant_id,
            expected_kid="audit-test-2026",
        )

        assert claims["purpose"] == AUDIT_CHECKPOINT_PURPOSE
        assert claims["chain_sequence"] == 2
        assert claims["event_count"] == 2
        assert claims["event_hash"] == tip.event_hash
        assert claims["anchor_state"] == "unanchored_signed_checkpoint"
        assert claims["immutable_storage_receipt"] is False
        assert claims["iat"] == int(issued_at.timestamp())

        header, payload, signature = token.split(".")
        replacement = "A" if payload[-1] != "A" else "B"
        tampered = ".".join((header, payload[:-1] + replacement, signature))
        with pytest.raises(AuditCheckpointValidationError):
            verify_signed_audit_checkpoint(
                tampered,
                public_key_pem=signer.public_key_pem(),
                expected_issuer="eay-audit-anchor-test",
                expected_tenant_id=tenant_id,
                expected_kid="audit-test-2026",
            )

        with pytest.raises(
            AuditCheckpointValidationError,
            match="tenant boundary",
        ):
            verify_signed_audit_checkpoint(
                token,
                public_key_pem=signer.public_key_pem(),
                expected_issuer="eay-audit-anchor-test",
                expected_tenant_id=uuid4(),
                expected_kid="audit-test-2026",
            )

        with pytest.raises(
            AuditCheckpointValidationError,
            match="empty tenant audit chain",
        ):
            await verify_tenant_audit_chain(
                connection,
                tenant_id=empty_tenant_id,
            )
    finally:
        await connection.close()
