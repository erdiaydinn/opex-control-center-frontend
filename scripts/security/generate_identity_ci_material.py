"""Generate or verify gitignored ES256 material for identity security gates."""

import base64
import json
import os
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


ROOT = Path(__file__).resolve().parents[2]

RUNTIME = (
    ROOT
    / "runtime"
    / "identity-gateway"
)

PRIVATE_PATH = (
    RUNTIME
    / "signing-private-key.pem"
)

PUBLIC_PATH = (
    RUNTIME
    / "public-jwks.json"
)

KID = os.environ.get(
    "OPEX_IDENTITY_GATEWAY_SIGNING_KID",
    "opex-dev-es256-v1",
)


def b64url_uint(
    value: int,
) -> str:
    return (
        base64.urlsafe_b64encode(
            value.to_bytes(
                32,
                "big",
            )
        )
        .rstrip(b"=")
        .decode("ascii")
    )


def public_jwk_from_private(
    private_key,
) -> dict[str, str]:
    numbers = (
        private_key
        .public_key()
        .public_numbers()
    )

    return {
        "kty": "EC",
        "crv": "P-256",
        "x": b64url_uint(
            numbers.x
        ),
        "y": b64url_uint(
            numbers.y
        ),
        "use": "sig",
        "alg": "ES256",
        "kid": KID,
    }


def verify_git_isolation() -> None:
    for path in (
        PRIVATE_PATH,
        PUBLIC_PATH,
    ):
        result = subprocess.run(
            [
                "git",
                "check-ignore",
                "-q",
                str(
                    path.relative_to(
                        ROOT
                    )
                ),
            ],
            cwd=ROOT,
            check=False,
        )

        if result.returncode != 0:
            raise SystemExit(
                "IDENTITY_CI_MATERIAL_NOT_GITIGNORED="
                + str(path)
            )


def verify_existing_pair() -> None:
    private_key = (
        serialization
        .load_pem_private_key(
            PRIVATE_PATH.read_bytes(),
            password=None,
        )
    )

    if not isinstance(
        private_key,
        ec.EllipticCurvePrivateKey,
    ):
        raise SystemExit(
            "IDENTITY_CI_PRIVATE_KEY_TYPE_INVALID"
        )

    if not isinstance(
        private_key.curve,
        ec.SECP256R1,
    ):
        raise SystemExit(
            "IDENTITY_CI_PRIVATE_KEY_CURVE_INVALID"
        )

    payload = json.loads(
        PUBLIC_PATH.read_text(
            encoding="utf-8"
        )
    )

    keys = payload.get(
        "keys"
    )

    if (
        not isinstance(keys, list)
        or len(keys) != 1
    ):
        raise SystemExit(
            "IDENTITY_CI_JWKS_KEY_COUNT_INVALID"
        )

    expected = (
        public_jwk_from_private(
            private_key
        )
    )

    if keys[0] != expected:
        raise SystemExit(
            "IDENTITY_CI_PRIVATE_PUBLIC_KEY_MISMATCH"
        )

    print(
        "IDENTITY_CI_KEYPAIR=EXISTING_VERIFIED"
    )


def generate_pair() -> None:
    private_key = (
        ec.generate_private_key(
            ec.SECP256R1()
        )
    )

    PRIVATE_PATH.write_bytes(
        private_key.private_bytes(
            encoding=(
                serialization
                .Encoding.PEM
            ),
            format=(
                serialization
                .PrivateFormat.PKCS8
            ),
            encryption_algorithm=(
                serialization
                .NoEncryption()
            ),
        )
    )

    try:
        os.chmod(
            PRIVATE_PATH,
            0o600,
        )
    except OSError:
        pass

    payload = {
        "keys": [
            public_jwk_from_private(
                private_key
            )
        ]
    }

    PUBLIC_PATH.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "IDENTITY_CI_KEYPAIR=GENERATED"
    )


def main() -> None:
    RUNTIME.mkdir(
        parents=True,
        exist_ok=True,
    )

    private_exists = (
        PRIVATE_PATH.exists()
    )

    public_exists = (
        PUBLIC_PATH.exists()
    )

    if (
        private_exists
        != public_exists
    ):
        raise SystemExit(
            "IDENTITY_CI_PARTIAL_KEYPAIR_STATE"
        )

    if private_exists:
        verify_existing_pair()
    else:
        generate_pair()

    verify_git_isolation()

    print(
        "IDENTITY_CI_KEYPAIR_GIT_ISOLATION=PASS"
    )


if __name__ == "__main__":
    main()
