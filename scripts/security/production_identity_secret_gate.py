"""Fail-closed production Identity Gateway secret-boundary gate."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

FILES = [
    ROOT / "docker-compose.platform.yml",
    ROOT / "docker-compose.production.yml",
]


for path in FILES:
    if not path.is_file():
        raise SystemExit(
            "COMPOSE_FILE_MISSING="
            + str(path)
        )


source = "\n".join(
    path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )
    for path in FILES
)


required_vars = sorted(
    set(
        re.findall(
            r"\$\{([A-Za-z_][A-Za-z0-9_]*):\?",
            source,
        )
    )
)


BASE_ENV = os.environ.copy()


for name in required_vars:
    if (
        name.endswith("_URL")
        or "ISSUER" in name
    ):
        value = (
            "https://example.invalid/value"
        )

    elif name == "OPEX_CORS_ORIGINS":
        value = (
            "https://app.example.invalid"
        )

    elif name == "OPEX_ALLOWED_HOSTS":
        value = (
            "app.example.invalid"
        )

    elif "FILE" in name:
        value = str(
            ROOT
            / "runtime"
            / "compose-static-test"
            / (
                name.lower()
                + ".secret"
            )
        )

    else:
        value = (
            "production-static-test-value"
        )

    BASE_ENV[name] = value


BASE_ENV[
    "OPEX_IDENTITY_GATEWAY_SIGNING_KID"
] = "production-static-es256-v1"

BASE_ENV[
    "OPEX_IDENTITY_GATEWAY_SIGNING_KEY_SECRET_FILE"
] = str(
    ROOT
    / "runtime"
    / "compose-static-test"
    / "production-identity-private.pem"
)

BASE_ENV[
    "OPEX_INTERNAL_ASSERTION_JWKS_SECRET_FILE"
] = str(
    ROOT
    / "runtime"
    / "compose-static-test"
    / "production-identity-public-jwks.json"
)


COMMAND = [
    "docker",
    "compose",
    "-f",
    str(FILES[0]),
    "-f",
    str(FILES[1]),
    "config",
    "--format",
    "json",
]


def render(
    environment,
):
    return subprocess.run(
        COMMAND,
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def secret_sources(
    service,
):
    raw = service.get(
        "secrets",
        [],
    )

    result = set()

    if isinstance(
        raw,
        dict,
    ):
        return set(raw)

    for item in raw:
        if isinstance(
            item,
            str,
        ):
            result.add(
                item
            )

        elif isinstance(
            item,
            dict,
        ):
            source = (
                item.get("source")
                or item.get("target")
            )

            if source:
                result.add(
                    str(source)
                )

    return result


def main() -> None:
    result = render(
        BASE_ENV
    )

    if result.returncode != 0:
        if result.stderr:
            print(
                result.stderr,
                file=sys.stderr,
            )

        raise SystemExit(
            "PRODUCTION_COMPOSE_RENDER_FAILED"
        )


    config = json.loads(
        result.stdout
    )

    services = config.get(
        "services",
        {},
    )


    for required in (
        "identity-gateway",
        "core-api",
    ):
        if required not in services:
            raise SystemExit(
                "PRODUCTION_SERVICE_MISSING="
                + required
            )


    identity = services[
        "identity-gateway"
    ]

    core = services[
        "core-api"
    ]


    identity_secrets = (
        secret_sources(
            identity
        )
    )

    core_secrets = (
        secret_sources(
            core
        )
    )


    if identity_secrets != {
        "identity_gateway_signing_key"
    }:
        raise SystemExit(
            "PRODUCTION_IDENTITY_SECRET_OWNERSHIP_INVALID="
            + repr(
                sorted(
                    identity_secrets
                )
            )
        )


    if (
        "identity_gateway_signing_key"
        in core_secrets
    ):
        raise SystemExit(
            "PRODUCTION_PRIVATE_KEY_LEAKED_TO_CORE"
        )


    if (
        "internal_assertion_jwks"
        not in core_secrets
    ):
        raise SystemExit(
            "PRODUCTION_CORE_PUBLIC_JWKS_MISSING"
        )


    identity_env = identity.get(
        "environment",
        {},
    )

    core_env = core.get(
        "environment",
        {},
    )


    expected_user_audience = (
        "opex-core-api"
    )

    expected_service_audience = (
        "opex-core-preauth"
    )

    for service_name, environment in (
        (
            "identity-gateway",
            identity_env,
        ),
        (
            "core-api",
            core_env,
        ),
    ):
        user_audience = environment.get(
            "OPEX_INTERNAL_ASSERTION_AUDIENCE"
        )

        service_audience = environment.get(
            "OPEX_INTERNAL_SERVICE_ASSERTION_AUDIENCE"
        )

        if (
            user_audience
            != expected_user_audience
        ):
            raise SystemExit(
                "PRODUCTION_USER_AUDIENCE_INVALID:"
                + service_name
            )

        if (
            service_audience
            != expected_service_audience
        ):
            raise SystemExit(
                "PRODUCTION_SERVICE_AUDIENCE_INVALID:"
                + service_name
            )

        if (
            user_audience
            == service_audience
        ):
            raise SystemExit(
                "PRODUCTION_INTERNAL_AUDIENCE_COLLISION:"
                + service_name
            )


    if (
        identity_env.get(
            "OPEX_ENVIRONMENT"
        )
        != "production"
    ):
        raise SystemExit(
            "PRODUCTION_IDENTITY_ENV_INVALID"
        )


    if (
        identity_env.get(
            "OPEX_IDENTITY_GATEWAY_SIGNING_KEY_FILE"
        )
        != (
            "/run/secrets/"
            "identity_gateway_signing_key"
        )
    ):
        raise SystemExit(
            "PRODUCTION_PRIVATE_KEY_PATH_INVALID"
        )


    if (
        identity_env.get(
            "OPEX_IDENTITY_GATEWAY_SIGNING_KID"
        )
        != "production-static-es256-v1"
    ):
        raise SystemExit(
            "PRODUCTION_SIGNING_KID_INVALID"
        )


    if (
        core_env.get(
            "OPEX_AUTH_MODE"
        )
        != "oidc"
    ):
        raise SystemExit(
            "PRODUCTION_AUTH_MODE_CHANGED"
        )


    if (
        core_env.get(
            "OPEX_INTERNAL_ASSERTION_JWKS_FILE"
        )
        != (
            "/run/secrets/"
            "internal_assertion_jwks"
        )
    ):
        raise SystemExit(
            "PRODUCTION_PUBLIC_JWKS_PATH_INVALID"
        )


    rendered = (
        result.stdout
        .lower()
        .replace(
            "\\",
            "/",
        )
    )


    for forbidden in (
        "opex-dev-es256-v1",
        (
            "runtime/identity-gateway/"
            "signing-private-key.pem"
        ),
        (
            "runtime/identity-gateway/"
            "public-jwks.json"
        ),
    ):
        if forbidden in rendered:
            raise SystemExit(
                "PRODUCTION_DEV_IDENTITY_FALLBACK_VISIBLE="
                + forbidden
            )


    print(
        "PRODUCTION_IDENTITY_COMPOSE_RENDER=PASS"
    )

    print(
        "PRODUCTION_IDENTITY_PRIVATE_KEY_OWNER=PASS"
    )

    print(
        "PRODUCTION_IDENTITY_PUBLIC_JWKS_BOUNDARY=PASS"
    )

    print(
        "PRODUCTION_IDENTITY_DEV_FALLBACK=ABSENT"
    )

    print(
        "PRODUCTION_IDENTITY_AUTH_MODE=OIDC_UNCHANGED"
    )


    for variable in (
        "OPEX_IDENTITY_GATEWAY_SIGNING_KID",
        (
            "OPEX_IDENTITY_GATEWAY_"
            "SIGNING_KEY_SECRET_FILE"
        ),
        (
            "OPEX_INTERNAL_ASSERTION_"
            "JWKS_SECRET_FILE"
        ),
    ):
        attack_env = (
            BASE_ENV.copy()
        )

        attack_env.pop(
            variable,
            None,
        )

        rejected = render(
            attack_env
        )

        if rejected.returncode == 0:
            raise SystemExit(
                "PRODUCTION_REQUIRED_IDENTITY_INPUT_ACCEPTED="
                + variable
            )

        print(
            "PRODUCTION_MISSING_"
            + variable
            + "=REJECTED"
        )


    print(
        "PRODUCTION_IDENTITY_SECRET_CI_GATE=PASS"
    )


if __name__ == "__main__":
    main()
