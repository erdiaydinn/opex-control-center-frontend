import json
import time
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from app.tenant_context_assertion import (
    TENANT_CONTEXT_PURPOSE,
    TENANT_CONTEXT_TYP,
    TenantContextAssertionInvalid,
    TenantContextAssertionUnavailable,
    verify_tenant_context_assertion,
)

ISSUER = "opex-identity-gateway"
AUDIENCE = "eay-ai-core-grounded-retrieval"
KID = "eay-test-key"
TENANT_ID = UUID("00000000-0000-0000-0000-00000000a001")
MEMBERSHIP_ID = UUID("00000000-0000-0000-0000-00000000a101")


@pytest.fixture()
def key_material(tmp_path):
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = json.loads(ECAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": KID, "use": "sig", "alg": "ES256"})
    path = tmp_path / "jwks.json"
    path.write_text(json.dumps({"keys": [public_jwk]}), encoding="utf-8")
    return private_key, str(path)


def issue(private_key, **overrides):
    now = int(time.time())
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "operator@example.test",
        "tenant_id": str(TENANT_ID),
        "membership_id": str(MEMBERSHIP_ID),
        "purpose": TENANT_CONTEXT_PURPOSE,
        "jti": str(uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + 30,
    }
    payload.update(overrides)
    return jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers={"kid": KID, "typ": TENANT_CONTEXT_TYP},
    )


def verify(token, jwks_file, **kwargs):
    return verify_tenant_context_assertion(
        token,
        jwks_file=jwks_file,
        issuer=kwargs.pop("issuer", ISSUER),
        audience=kwargs.pop("audience", AUDIENCE),
        **kwargs,
    )


def test_verifies_exact_tenant_context(key_material):
    private_key, jwks_file = key_material
    result = verify(issue(private_key), jwks_file)
    assert result.tenant_id == TENANT_ID
    assert result.membership_id == MEMBERSHIP_ID
    assert result.actor_subject == "operator@example.test"


def test_rejects_existing_core_api_audience_reuse(key_material):
    private_key, jwks_file = key_material
    token = issue(private_key, aud="opex-core-api")
    with pytest.raises(TenantContextAssertionInvalid):
        verify(token, jwks_file, audience="opex-core-api")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("aud", "another-service"),
        ("tenant_id", "not-a-uuid"),
        ("membership_id", "not-a-uuid"),
        ("purpose", "analytics"),
    ],
)
def test_rejects_claim_substitution(key_material, field, value):
    private_key, jwks_file = key_material
    with pytest.raises(TenantContextAssertionInvalid):
        verify(issue(private_key, **{field: value}), jwks_file)


def test_rejects_unexpected_authorization_claim_smuggling(key_material):
    private_key, jwks_file = key_material
    with pytest.raises(TenantContextAssertionInvalid):
        verify(issue(private_key, roles=["super_admin"]), jwks_file)


def test_rejects_wrong_type(key_material):
    private_key, jwks_file = key_material
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "operator@example.test",
            "tenant_id": str(TENANT_ID),
            "membership_id": str(MEMBERSHIP_ID),
            "purpose": TENANT_CONTEXT_PURPOSE,
            "jti": str(uuid4()),
            "iat": now,
            "nbf": now,
            "exp": now + 30,
        },
        private_key,
        algorithm="ES256",
        headers={"kid": KID, "typ": "opex-internal+jwt"},
    )
    with pytest.raises(TenantContextAssertionInvalid):
        verify(token, jwks_file)


def test_rejects_excessive_lifetime(key_material):
    private_key, jwks_file = key_material
    now = int(time.time())
    with pytest.raises(TenantContextAssertionInvalid):
        verify(issue(private_key, iat=now, nbf=now, exp=now + 61), jwks_file)


def test_rejects_private_key_material_in_trust_store(key_material, tmp_path):
    private_key, _ = key_material
    private_jwk = json.loads(ECAlgorithm.to_jwk(private_key))
    private_jwk.update({"kid": KID, "use": "sig", "alg": "ES256"})
    path = tmp_path / "private-jwks.json"
    path.write_text(json.dumps({"keys": [private_jwk]}), encoding="utf-8")
    with pytest.raises(TenantContextAssertionUnavailable):
        verify(issue(private_key), str(path))
