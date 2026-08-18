import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.mobile_policy import (
    MobileOperationPolicy,
    MobilePolicySnapshot,
    MobileRisk,
    MobileRuntimeProfile,
)
from app.core.mobile_policy_signing import (
    MOBILE_POLICY_ALGORITHM,
    MOBILE_POLICY_TOKEN_TYPE,
    MobilePolicyBinding,
    MobilePolicyTokenError,
    sign_mobile_policy,
    verify_mobile_policy,
)

TENANT = UUID("11111111-1111-1111-1111-111111111111")
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


class EphemeralSigner:
    algorithm = MOBILE_POLICY_ALGORITHM

    def __init__(self, private_key, kid: str = "mobile-policy-test-1") -> None:
        self.private_key = private_key
        self.kid = kid

    def sign(self, claims, headers):
        return jwt.encode(
            claims,
            self.private_key,
            algorithm=self.algorithm,
            headers=headers,
        )


def keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_key


def snapshot(
    *,
    issued_at: datetime = NOW,
    expires_at: datetime | None = None,
):
    policy = MobileOperationPolicy(
        operation="inventory.count.capture",
        risk=MobileRisk.MEDIUM,
        offline_allowed=True,
        requires_active_shift=True,
        permission_key="module.inventory",
        scope_fingerprint="b" * 64,
    )
    return MobilePolicySnapshot(
        tenant_id=TENANT,
        actor_id="actor-a",
        device_id="device-1",
        installation_id="install-1",
        location_id="store-1",
        auth_binding_id="auth-1",
        runtime_profile=MobileRuntimeProfile.EAY_TERMINAL,
        operation_policies={policy.operation: policy},
        issued_at=issued_at,
        expires_at=expires_at or issued_at + timedelta(seconds=120),
        policy_fingerprint="a" * 64,
    )


def binding(**changes):
    values = {
        "tenant_id": TENANT,
        "actor_id": "actor-a",
        "device_id": "device-1",
        "installation_id": "install-1",
        "location_id": "store-1",
        "auth_binding_id": "auth-1",
        "runtime_profile": MobileRuntimeProfile.EAY_TERMINAL,
    }
    values.update(changes)
    return MobilePolicyBinding(**values)


def test_valid_es256_policy_verifies_with_public_key_only() -> None:
    private_key, public_key = keypair()
    signer = EphemeralSigner(private_key)
    token = sign_mobile_policy(snapshot(), signer)
    claims = verify_mobile_policy(
        token,
        {signer.kid: public_key},
        binding(),
        now=NOW + timedelta(seconds=1),
    )
    assert claims.policy_fingerprint == "a" * 64
    assert claims.operation_policies["inventory.count.capture"].offline_allowed is True


def test_algorithm_confusion_is_rejected_before_key_use() -> None:
    token = jwt.encode(
        {
            "iss": "eay-platform-core",
            "aud": "eay-mobile-edge",
            "sub": "actor-a",
            "exp": int((NOW + timedelta(seconds=60)).timestamp()),
        },
        "attacker-secret",
        algorithm="HS256",
        headers={
            "kid": "mobile-policy-test-1",
            "typ": MOBILE_POLICY_TOKEN_TYPE,
        },
    )
    _, public_key = keypair()
    with pytest.raises(
        MobilePolicyTokenError,
        match="DENY_POLICY_TOKEN_ALGORITHM",
    ):
        verify_mobile_policy(
            token,
            {"mobile-policy-test-1": public_key},
            binding(),
            now=NOW,
        )


def test_unknown_kid_and_wrong_key_fail_closed() -> None:
    private_key, _ = keypair()
    _, wrong_public_key = keypair()
    signer = EphemeralSigner(private_key, kid="kid-a")
    token = sign_mobile_policy(snapshot(), signer)

    with pytest.raises(MobilePolicyTokenError, match="DENY_POLICY_TOKEN_KID"):
        verify_mobile_policy(token, {}, binding(), now=NOW)
    with pytest.raises(
        MobilePolicyTokenError,
        match="DENY_POLICY_TOKEN_SIGNATURE_OR_CLAIMS",
    ):
        verify_mobile_policy(
            token,
            {"kid-a": wrong_public_key},
            binding(),
            now=NOW,
        )


def test_signed_payload_tamper_is_rejected() -> None:
    private_key, public_key = keypair()
    signer = EphemeralSigner(private_key)
    token = sign_mobile_policy(snapshot(), signer)
    header, payload, signature = token.split(".")
    padded = payload + "=" * (-len(payload) % 4)
    raw = json.loads(base64.urlsafe_b64decode(padded))
    raw["location_id"] = "store-attacker"
    changed = base64.urlsafe_b64encode(
        json.dumps(raw, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    tampered = ".".join((header, changed, signature))

    with pytest.raises(
        MobilePolicyTokenError,
        match="DENY_POLICY_TOKEN_SIGNATURE_OR_CLAIMS",
    ):
        verify_mobile_policy(
            tampered,
            {signer.kid: public_key},
            binding(),
            now=NOW,
        )


def test_policy_is_bound_to_exact_mobile_context() -> None:
    private_key, public_key = keypair()
    signer = EphemeralSigner(private_key)
    token = sign_mobile_policy(snapshot(), signer)
    with pytest.raises(
        MobilePolicyTokenError,
        match="DENY_POLICY_TOKEN_BINDING",
    ):
        verify_mobile_policy(
            token,
            {signer.kid: public_key},
            binding(device_id="device-2"),
            now=NOW,
        )


def test_expired_or_overlong_policy_fails_closed() -> None:
    private_key, public_key = keypair()
    signer = EphemeralSigner(private_key)
    token = sign_mobile_policy(snapshot(), signer)
    with pytest.raises(
        MobilePolicyTokenError,
        match="DENY_POLICY_TOKEN_EXPIRED",
    ):
        verify_mobile_policy(
            token,
            {signer.kid: public_key},
            binding(),
            now=NOW + timedelta(seconds=121),
        )

    with pytest.raises(MobilePolicyTokenError, match="DENY_POLICY_LIFETIME"):
        sign_mobile_policy(
            snapshot(expires_at=NOW + timedelta(seconds=301)),
            signer,
        )
