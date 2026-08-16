from uuid import UUID

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.security import GatewaySettings, IdentitySigner
from app.session_assertions import issue_authorized_session_assertions


TENANT_ID = UUID("00000000-0000-0000-0000-00000000ee01")
MEMBERSHIP_ID = UUID("00000000-0000-0000-0000-00000000ee11")


def _signer(tmp_path) -> IdentitySigner:
    key = ec.generate_private_key(ec.SECP256R1())
    path = tmp_path / "private.pem"
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return IdentitySigner(
        GatewaySettings(
            environment="test",
            issuer="opex-identity-gateway",
            audience="opex-core-api",
            service_audience="opex-core-preauth",
            ai_tenant_context_audience="eay-ai-core-grounded-retrieval",
            signing_key_file=str(path),
            signing_kid="test-es256-v1",
            assertion_lifetime_seconds=30,
        )
    )


def _public_key(signer: IdentitySigner):
    return jwt.PyJWK.from_dict(signer.public_jwks()["keys"][0]).key


def test_authorized_session_assertions_share_tenant_and_membership(tmp_path):
    signer = _signer(tmp_path)
    assertions = issue_authorized_session_assertions(
        signer,
        tenant_id=TENANT_ID,
        membership_id=MEMBERSHIP_ID,
        actor_subject="operator@example.test",
    )
    public_key = _public_key(signer)

    core = jwt.decode(
        assertions.core_assertion,
        public_key,
        algorithms=["ES256"],
        audience="opex-core-api",
        issuer="opex-identity-gateway",
    )
    ai = jwt.decode(
        assertions.ai_tenant_context_assertion,
        public_key,
        algorithms=["ES256"],
        audience="eay-ai-core-grounded-retrieval",
        issuer="opex-identity-gateway",
    )

    assert core["tenant_id"] == ai["tenant_id"] == str(TENANT_ID)
    assert core["sub"] == ai["membership_id"] == str(MEMBERSHIP_ID)
    assert ai["sub"] == "operator@example.test"
    assert ai["purpose"] == "grounded-retrieval"
    assert core["aud"] != ai["aud"]
    assert core["jti"] != ai["jti"]


def test_ai_assertion_cannot_be_used_as_core_identity(tmp_path):
    signer = _signer(tmp_path)
    assertions = issue_authorized_session_assertions(
        signer,
        tenant_id=TENANT_ID,
        membership_id=MEMBERSHIP_ID,
        actor_subject="operator@example.test",
    )

    try:
        jwt.decode(
            assertions.ai_tenant_context_assertion,
            _public_key(signer),
            algorithms=["ES256"],
            audience="opex-core-api",
            issuer="opex-identity-gateway",
        )
    except jwt.InvalidAudienceError:
        return
    raise AssertionError("AI tenant-context assertion was accepted as Core identity")
