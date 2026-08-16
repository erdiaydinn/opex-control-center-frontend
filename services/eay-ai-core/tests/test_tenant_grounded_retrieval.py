import asyncio
import json
import time
from datetime import date
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from jwt.algorithms import ECAlgorithm
from pydantic import ValidationError

from app.main import KnowledgeUpsert
from app.tenant_context_assertion import TENANT_CONTEXT_PURPOSE, TENANT_CONTEXT_TYP
from app.tenant_context_replay import TenantContextReplayGuard
from app.tenant_grounded_retrieval import (
    TenantRetrievalRequest,
    _verify_header,
    retrieve_for_verified_tenant,
)
from app.tenant_retrieval import TenantScopedKnowledgeStore

ISSUER = "opex-identity-gateway"
AUDIENCE = "eay-ai-core-grounded-retrieval"
KID = "tenant-retrieval-test"
TENANT_A = UUID("00000000-0000-0000-0000-00000000a001")
TENANT_B = UUID("00000000-0000-0000-0000-00000000b001")
MEMBERSHIP_A = UUID("00000000-0000-0000-0000-00000000a101")


def _key_material(tmp_path):
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = json.loads(ECAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": KID, "use": "sig", "alg": "ES256"})
    jwks_file = tmp_path / "jwks.json"
    jwks_file.write_text(json.dumps({"keys": [public_jwk]}), encoding="utf-8")
    return private_key, str(jwks_file)


def _issue(private_key, tenant_id=TENANT_A):
    now = int(time.time())
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "operator@example.test",
            "tenant_id": str(tenant_id),
            "membership_id": str(MEMBERSHIP_A),
            "purpose": TENANT_CONTEXT_PURPOSE,
            "jti": str(uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + 30,
        },
        private_key,
        algorithm="ES256",
        headers={"kid": KID, "typ": TENANT_CONTEXT_TYP},
    )


def _company_doc(doc_id, title, content):
    return KnowledgeUpsert(
        id=doc_id,
        layer="company",
        title=title,
        content=content,
        source_name="EAY policy",
        authority_level="company",
        effective_from=date(2026, 1, 1),
    )


def _configure_runtime(tmp_path, monkeypatch, jwks_file, scoped_store):
    replay_guard = TenantContextReplayGuard(tmp_path / "replay.db")
    monkeypatch.setenv("EAY_AI_TENANT_CONTEXT_JWKS_FILE", jwks_file)
    monkeypatch.setenv("EAY_AI_TENANT_CONTEXT_ISSUER", ISSUER)
    monkeypatch.setenv("EAY_AI_TENANT_CONTEXT_AUDIENCE", AUDIENCE)
    monkeypatch.setattr("app.tenant_grounded_retrieval.tenant_store", scoped_store)
    monkeypatch.setattr(
        "app.tenant_grounded_retrieval.tenant_context_replay_guard",
        replay_guard,
    )


def test_internal_retrieval_uses_asserted_tenant_only(tmp_path, monkeypatch):
    private_key, jwks_file = _key_material(tmp_path)
    db_path = tmp_path / "tenant-retrieval.db"
    scoped_store = TenantScopedKnowledgeStore(db_path)
    scoped_store.upsert(
        _company_doc("tenant-a-policy", "Cold chain A", "coldchain alpha tenant A"),
        tenant_id=TENANT_A,
    )
    scoped_store.upsert(
        _company_doc("tenant-b-policy", "Cold chain B", "coldchain alpha tenant B"),
        tenant_id=TENANT_B,
    )
    _configure_runtime(tmp_path, monkeypatch, jwks_file, scoped_store)

    result = asyncio.run(
        retrieve_for_verified_tenant(
            TenantRetrievalRequest(
                message="coldchain alpha",
                as_of=date(2026, 8, 16),
                layers=["company"],
                limit=8,
            ),
            _issue(private_key, TENANT_A),
        )
    )

    ids = {item.id for item in result.evidence}
    assert "tenant-a-policy" in ids
    assert "tenant-b-policy" not in ids


def test_internal_retrieval_rejects_duplicate_layers_before_authorization():
    with pytest.raises(ValidationError, match="retrieval layers must be unique"):
        TenantRetrievalRequest(
            message="coldchain alpha",
            as_of=date(2026, 8, 16),
            layers=["company", "company"],
            limit=8,
        )


def test_internal_retrieval_rejects_assertion_replay(tmp_path, monkeypatch):
    private_key, jwks_file = _key_material(tmp_path)
    scoped_store = TenantScopedKnowledgeStore(tmp_path / "tenant-retrieval.db")
    scoped_store.upsert(
        _company_doc("tenant-a-policy", "Cold chain A", "coldchain alpha tenant A"),
        tenant_id=TENANT_A,
    )
    _configure_runtime(tmp_path, monkeypatch, jwks_file, scoped_store)
    token = _issue(private_key, TENANT_A)
    request = TenantRetrievalRequest(
        message="coldchain alpha",
        as_of=date(2026, 8, 16),
        layers=["company"],
        limit=8,
    )

    first = asyncio.run(retrieve_for_verified_tenant(request, token))
    assert {item.id for item in first.evidence} == {"tenant-a-policy"}

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retrieve_for_verified_tenant(request, token))
    assert exc_info.value.status_code == 401


def test_internal_retrieval_rejects_core_audience_token(tmp_path, monkeypatch):
    private_key, jwks_file = _key_material(tmp_path)
    monkeypatch.setenv("EAY_AI_TENANT_CONTEXT_JWKS_FILE", jwks_file)
    monkeypatch.setenv("EAY_AI_TENANT_CONTEXT_ISSUER", ISSUER)
    monkeypatch.setenv("EAY_AI_TENANT_CONTEXT_AUDIENCE", AUDIENCE)

    now = int(time.time())
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": "opex-core-api",
            "sub": "operator@example.test",
            "tenant_id": str(TENANT_A),
            "membership_id": str(MEMBERSHIP_A),
            "purpose": TENANT_CONTEXT_PURPOSE,
            "jti": str(uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + 30,
        },
        private_key,
        algorithm="ES256",
        headers={"kid": KID, "typ": TENANT_CONTEXT_TYP},
    )

    with pytest.raises(HTTPException) as exc_info:
        _verify_header(token)
    assert exc_info.value.status_code == 401


def test_internal_retrieval_fails_closed_without_trust_store(monkeypatch):
    monkeypatch.delenv("EAY_AI_TENANT_CONTEXT_JWKS_FILE", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        _verify_header("header.payload.signature")
    assert exc_info.value.status_code == 503
