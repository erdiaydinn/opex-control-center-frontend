"""Adversarial runtime gate for the OPEX Identity Gateway trust boundary."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

COMPOSE_FILE = (
    ROOT
    / "docker-compose.platform.yml"
)

PRIVATE_PATH = (
    ROOT
    / "runtime"
    / "identity-gateway"
    / "signing-private-key.pem"
)

PUBLIC_PATH = (
    ROOT
    / "runtime"
    / "identity-gateway"
    / "public-jwks.json"
)

PROJECT = (
    "opex-identity-ci-gate"
)

CORE_NAME = (
    "opex-identity-ci-core-verifier"
)


if (
    not PRIVATE_PATH.is_file()
    or not PUBLIC_PATH.is_file()
):
    raise SystemExit(
        "IDENTITY_RUNTIME_GATE_KEY_MATERIAL_MISSING"
    )


jwks_payload = json.loads(
    PUBLIC_PATH.read_text(
        encoding="utf-8"
    )
)

jwks_keys = jwks_payload.get(
    "keys"
)

if (
    not isinstance(jwks_keys, list)
    or len(jwks_keys) != 1
):
    raise SystemExit(
        "IDENTITY_RUNTIME_GATE_JWKS_INVALID"
    )

KID = str(
    jwks_keys[0].get(
        "kid",
        "",
    )
)

if not KID:
    raise SystemExit(
        "IDENTITY_RUNTIME_GATE_KID_MISSING"
    )


ENV = os.environ.copy()

ENV.update(
    {
        "OPEX_ENVIRONMENT":
            "test",
        "OPEX_AUTH_MODE":
            "development",
        "OPEX_INTERNAL_ASSERTION_AUDIENCE":
            "opex-core-api",
        "OPEX_INTERNAL_SERVICE_ASSERTION_AUDIENCE":
            "opex-core-preauth",
        "OPEX_IDENTITY_GATEWAY_SIGNING_KID":
            KID,
        "OPEX_IDENTITY_GATEWAY_SIGNING_KEY_FILE":
            str(PRIVATE_PATH),
        "OPEX_INTERNAL_ASSERTION_JWKS_SOURCE_FILE":
            str(PUBLIC_PATH),
    }
)


COMPOSE = [
    "docker",
    "compose",
    "-p",
    PROJECT,
    "-f",
    str(COMPOSE_FILE),
]


def run(
    command: list[str],
    *,
    input_text: str | None = None,
    capture: bool = False,
    check: bool = True,
):
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=ENV,
        input=input_text,
        text=True,
        capture_output=capture,
        check=False,
    )

    if (
        check
        and result.returncode != 0
    ):
        if capture:
            if result.stdout:
                print(
                    result.stdout,
                    file=sys.stderr,
                )

            if result.stderr:
                print(
                    result.stderr,
                    file=sys.stderr,
                )

        raise SystemExit(
            "COMMAND_FAILED="
            + " ".join(
                command[:5]
            )
        )

    return result


def compose(
    *arguments: str,
    capture: bool = False,
    check: bool = True,
):
    return run(
        [
            *COMPOSE,
            *arguments,
        ],
        capture=capture,
        check=check,
    )


def inspect(
    container: str,
) -> dict:
    result = run(
        [
            "docker",
            "inspect",
            container,
        ],
        capture=True,
    )

    payload = json.loads(
        result.stdout
    )

    if len(payload) != 1:
        raise SystemExit(
            "DOCKER_INSPECT_RESULT_INVALID"
        )

    return payload[0]


def service_networks(
    service: dict,
) -> set[str]:
    raw = service.get(
        "networks"
    ) or {}

    if isinstance(
        raw,
        dict,
    ):
        return set(raw)

    return set(raw)


def service_secrets(
    service: dict,
) -> set[str]:
    raw = service.get(
        "secrets"
    ) or []

    if isinstance(
        raw,
        dict,
    ):
        return set(raw)

    result = set()

    for item in raw:
        if isinstance(
            item,
            str,
        ):
            result.add(
                item
            )
            continue

        if isinstance(
            item,
            dict,
        ):
            source = (
                item.get(
                    "source"
                )
                or item.get(
                    "target"
                )
            )

            if source:
                result.add(
                    str(source)
                )

    return result


def static_gate() -> None:
    rendered = compose(
        "config",
        "--format",
        "json",
        capture=True,
    )

    config = json.loads(
        rendered.stdout
    )

    services = config.get(
        "services"
    ) or {}

    networks = config.get(
        "networks"
    ) or {}

    required = {
        "identity-gateway",
        "core-api",
        "gateway",
    }

    if not required <= set(
        services
    ):
        raise SystemExit(
            "IDENTITY_STATIC_REQUIRED_SERVICES_MISSING"
        )

    identity = services[
        "identity-gateway"
    ]

    core = services[
        "core-api"
    ]

    gateway = services[
        "gateway"
    ]

    identity_env = (
        identity.get(
            "environment"
        )
        or {}
    )

    core_env = (
        core.get(
            "environment"
        )
        or {}
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
                "IDENTITY_RUNTIME_USER_AUDIENCE_INVALID:"
                + service_name
            )

        if (
            service_audience
            != expected_service_audience
        ):
            raise SystemExit(
                "IDENTITY_RUNTIME_SERVICE_AUDIENCE_INVALID:"
                + service_name
            )

        if (
            user_audience
            == service_audience
        ):
            raise SystemExit(
                "IDENTITY_RUNTIME_AUDIENCE_COLLISION:"
                + service_name
            )

    identity_networks = (
        service_networks(
            identity
        )
    )

    if identity_networks != {
        "identity_core_plane",
        "identity_egress",
    }:
        raise SystemExit(
            "IDENTITY_STATIC_NETWORKS_INVALID="
            + repr(
                sorted(
                    identity_networks
                )
            )
        )

    core_networks = (
        service_networks(
            core
        )
    )

    if (
        "identity_core_plane"
        not in core_networks
    ):
        raise SystemExit(
            "CORE_IDENTITY_NETWORK_MISSING"
        )

    if (
        "api_plane"
        not in core_networks
    ):
        raise SystemExit(
            "CORE_TRANSITIONAL_API_PLANE_MISSING"
        )

    if (
        "identity_core_plane"
        in service_networks(
            gateway
        )
    ):
        raise SystemExit(
            "EDGE_GATEWAY_IDENTITY_CORE_LEAK"
        )

    for (
        service_name,
        service,
    ) in services.items():

        if service_name in {
            "identity-gateway",
            "core-api",
        }:
            continue

        overlap = (
            identity_networks
            & service_networks(
                service
            )
        )

        if overlap:
            raise SystemExit(
                "IDENTITY_NETWORK_LATERAL_OVERLAP:"
                + service_name
                + ":"
                + repr(
                    sorted(overlap)
                )
            )

    private_holders = [
        name
        for name, service
        in services.items()
        if (
            "identity_gateway_signing_key"
            in service_secrets(
                service
            )
        )
    ]

    if private_holders != [
        "identity-gateway"
    ]:
        raise SystemExit(
            "IDENTITY_PRIVATE_KEY_HOLDERS_INVALID="
            + repr(
                private_holders
            )
        )

    public_holders = [
        name
        for name, service
        in services.items()
        if (
            "internal_assertion_jwks"
            in service_secrets(
                service
            )
        )
    ]

    if public_holders != [
        "core-api"
    ]:
        raise SystemExit(
            "IDENTITY_PUBLIC_JWKS_HOLDERS_INVALID="
            + repr(
                public_holders
            )
        )

    if identity.get(
        "ports"
    ):
        raise SystemExit(
            "IDENTITY_GATEWAY_PUBLIC_PORT_FORBIDDEN"
        )

    if identity.get(
        "volumes"
    ):
        raise SystemExit(
            "IDENTITY_GATEWAY_VOLUME_MOUNT_REQUIRES_REVIEW"
        )

    identity_core = networks.get(
        "identity_core_plane"
    ) or {}

    if (
        identity_core.get(
            "internal"
        )
        is not True
    ):
        raise SystemExit(
            "IDENTITY_CORE_PLANE_MUST_BE_INTERNAL"
        )

    identity_egress = networks.get(
        "identity_egress"
    ) or {}

    if (
        identity_egress.get(
            "internal"
        )
        is True
    ):
        raise SystemExit(
            "IDENTITY_EGRESS_CANNOT_REACH_IDP"
        )

    print(
        "IDENTITY_STATIC_COMPOSE_BOUNDARY=PASS"
    )


def wait_identity_health(
    container_id: str,
) -> None:
    """Wait for a bounded recovery window; fail closed with Docker evidence."""
    last_health = "missing"
    last_log: list[dict] = []

    for _ in range(60):
        state = inspect(
            container_id
        ).get(
            "State",
            {},
        )

        if not state.get(
            "Running"
        ):
            raise SystemExit(
                "IDENTITY_GATEWAY_EXITED"
            )

        health_state = (
            state.get(
                "Health",
                {}
            )
            or {}
        )
        last_health = str(
            health_state.get(
                "Status",
                "missing",
            )
        )
        raw_log = health_state.get(
            "Log",
            [],
        )
        if isinstance(raw_log, list):
            last_log = raw_log[-3:]

        if last_health == "healthy":
            print(
                "IDENTITY_GATEWAY_HEALTH=PASS"
            )
            return

        # Docker health can temporarily transition through `unhealthy`
        # during process/bootstrap races. Do not accept it; continue polling
        # only inside the bounded 60-second gate and fail if it never recovers.
        time.sleep(1)

    diagnostics = json.dumps(
        last_log,
        sort_keys=True,
        default=str,
    )
    raise SystemExit(
        "IDENTITY_GATEWAY_HEALTH_TIMEOUT="
        + last_health
        + ":"
        + diagnostics
    )


def exec_python(
    container: str,
    code: str,
    *,
    input_text: str = "",
    check: bool = True,
):
    return run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "python",
            "-c",
            code,
        ],
        input_text=input_text,
        capture=True,
        check=check,
    )


def runtime_key_gate(
    identity_id: str,
    core_id: str,
) -> None:

    identity_code = """
from pathlib import Path

private_key = Path(
    "/run/secrets/identity_gateway_signing_key"
)

public_jwks = Path(
    "/run/secrets/internal_assertion_jwks"
)

assert private_key.is_file()
assert b"PRIVATE KEY" in private_key.read_bytes()
assert not public_jwks.exists()

print(
    "IDENTITY_RUNTIME_PRIVATE_KEY_OWNER=PASS"
)
"""

    identity_result = (
        exec_python(
            identity_id,
            identity_code,
        )
    )

    print(
        identity_result.stdout.strip()
    )


    core_code = """
import json
from pathlib import Path

private_key = Path(
    "/run/secrets/identity_gateway_signing_key"
)

public_jwks = Path(
    "/run/secrets/internal_assertion_jwks"
)

assert not private_key.exists()
assert public_jwks.is_file()

payload = json.loads(
    public_jwks.read_text(
        encoding="utf-8"
    )
)

assert payload["keys"]

for key in payload["keys"]:
    assert not (
        {
            "d",
            "p",
            "q",
            "dp",
            "dq",
            "qi",
            "oth",
            "k",
        }
        & set(key)
    )

print(
    "CORE_RUNTIME_PUBLIC_JWKS_ONLY=PASS"
)
"""

    core_result = (
        exec_python(
            core_id,
            core_code,
        )
    )

    print(
        core_result.stdout.strip()
    )


def network_membership_gate(
    identity_id: str,
    core_id: str,
) -> None:

    identity_networks = set(
        inspect(
            identity_id
        )[
            "NetworkSettings"
        ][
            "Networks"
        ]
    )

    if len(
        identity_networks
    ) != 2:
        raise SystemExit(
            "IDENTITY_RUNTIME_NETWORK_COUNT_INVALID="
            + repr(
                sorted(
                    identity_networks
                )
            )
        )

    if not any(
        name.endswith(
            "_identity_core_plane"
        )
        for name in identity_networks
    ):
        raise SystemExit(
            "IDENTITY_RUNTIME_CORE_PLANE_MISSING"
        )

    if not any(
        name.endswith(
            "_identity_egress"
        )
        for name in identity_networks
    ):
        raise SystemExit(
            "IDENTITY_RUNTIME_EGRESS_MISSING"
        )

    print(
        "IDENTITY_RUNTIME_NETWORK_MEMBERSHIP=PASS"
    )


    connect_code = """
import socket
import time

last_error = None

for _ in range(20):
    try:
        with socket.create_connection(
            (
                "core-api",
                8000,
            ),
            timeout=1,
        ):
            pass

        print(
            "IDENTITY_RUNTIME_TO_CORE_TCP=PASS"
        )

        raise SystemExit(0)

    except OSError as exc:
        last_error = exc
        time.sleep(0.5)

raise SystemExit(
    "IDENTITY_RUNTIME_TO_CORE_TCP_FAILED="
    + repr(last_error)
)
"""

    result = exec_python(
        identity_id,
        connect_code,
    )

    print(
        result.stdout.strip()
    )


    core_info = inspect(
        core_id
    )

    core_networks = set(
        core_info[
            "NetworkSettings"
        ][
            "Networks"
        ]
    )

    image = core_info[
        "Config"
    ][
        "Image"
    ]

    decoy_suffixes = (
        "_api_plane",
        "_ops_plane",
        "_data_plane",
        "_ai_plane",
        "_egress",
    )

    for number, suffix in enumerate(
        decoy_suffixes,
        start=1,
    ):
        matches = [
            name
            for name in core_networks
            if name.endswith(
                suffix
            )
            and not name.endswith(
                "_identity_egress"
            )
        ]

        if len(matches) != 1:
            raise SystemExit(
                "DECOY_NETWORK_RESOLUTION_INVALID:"
                + suffix
                + ":"
                + repr(matches)
            )

        network_name = matches[0]

        alias = (
            f"forbidden-decoy-{number}"
        )

        container_name = (
            f"opex-identity-ci-decoy-{number}"
        )

        run(
            [
                "docker",
                "rm",
                "-f",
                container_name,
            ],
            check=False,
            capture=True,
        )

        decoy = run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                container_name,
                "--network",
                network_name,
                "--network-alias",
                alias,
                image,
                "python",
                "-c",
                "import time; time.sleep(120)",
            ],
            capture=True,
        )

        try:
            if not decoy.stdout.strip():
                raise SystemExit(
                    "DECOY_CONTAINER_NOT_CREATED"
                )

            deny_code = """
import socket

try:
    socket.getaddrinfo(
        %r,
        None,
    )
except socket.gaierror:
    print(
        "IDENTITY_RUNTIME_LATERAL_DNS_DENIED=PASS"
    )
else:
    raise SystemExit(
        "IDENTITY_RUNTIME_LATERAL_DNS_LEAK"
    )
""" % alias

            denied = exec_python(
                identity_id,
                deny_code,
            )

            print(
                denied.stdout.strip()
            )

        finally:
            run(
                [
                    "docker",
                    "rm",
                    "-f",
                    container_name,
                ],
                check=False,
                capture=True,
            )

    print(
        "IDENTITY_RUNTIME_LATERAL_ISOLATION=PASS"
    )


def crypto_gate(
    identity_id: str,
    core_id: str,
) -> None:

    signer_code = """
from uuid import UUID

from app.main import signer

print(
    signer.issue_internal_assertion(
        tenant_id=UUID(
            "00000000-0000-0000-0000-00000000ee01"
        ),
        membership_id=UUID(
            "00000000-0000-0000-0000-00000000ee11"
        ),
    )
)
"""

    signed = exec_python(
        identity_id,
        signer_code,
    )

    token = (
        signed.stdout.strip()
    )

    if (
        not token
        or token.count(".") != 2
    ):
        raise SystemExit(
            "IDENTITY_RUNTIME_ASSERTION_INVALID"
        )


    verifier_code = """
import sys

from app.core.config import Settings
from app.core.internal_identity import (
    verify_internal_identity_assertion,
)

token = sys.stdin.read().strip()

settings = Settings(
    environment="test",
    auth_mode="internal_assertion",
    internal_assertion_issuer=(
        "opex-identity-gateway"
    ),
    internal_assertion_audience=(
        "opex-core-api"
    ),
    internal_assertion_jwks_file=(
        "/run/secrets/internal_assertion_jwks"
    ),
    internal_assertion_algorithms=(
        "ES256"
    ),
    internal_assertion_max_lifetime_seconds=60,
)

verified = (
    verify_internal_identity_assertion(
        token,
        settings,
    )
)

assert str(
    verified.tenant_id
) == (
    "00000000-0000-0000-0000-00000000ee01"
)

assert str(
    verified.membership_id
) == (
    "00000000-0000-0000-0000-00000000ee11"
)

print(
    "IDENTITY_RUNTIME_SIGNER_VERIFIER=PASS"
)
"""

    verified = exec_python(
        core_id,
        verifier_code,
        input_text=token,
    )

    print(
        verified.stdout.strip()
    )


    header, payload, signature = (
        token.split(".")
    )

    first = signature[0]

    replacement = (
        "A"
        if first != "A"
        else "B"
    )

    tampered = (
        header
        + "."
        + payload
        + "."
        + replacement
        + signature[1:]
    )

    rejected = exec_python(
        core_id,
        verifier_code,
        input_text=tampered,
        check=False,
    )

    if rejected.returncode == 0:
        raise SystemExit(
            "IDENTITY_RUNTIME_TAMPER_ACCEPTED"
        )

    print(
        "IDENTITY_RUNTIME_TAMPER_REJECTION=PASS"
    )


def main() -> None:
    core_id = ""
    identity_id = ""

    try:
        static_gate()

        compose(
            "build",
            "identity-gateway",
            "core-api",
        )

        compose(
            "up",
            "-d",
            "--no-deps",
            "identity-gateway",
        )

        identity_id = (
            compose(
                "ps",
                "-q",
                "identity-gateway",
                capture=True,
            )
            .stdout
            .strip()
        )

        if not identity_id:
            raise SystemExit(
                "IDENTITY_RUNTIME_CONTAINER_MISSING"
            )

        wait_identity_health(
            identity_id
        )


        run(
            [
                "docker",
                "rm",
                "-f",
                CORE_NAME,
            ],
            check=False,
            capture=True,
        )

        core_result = compose(
            "run",
            "-d",
            "--no-deps",
            "--use-aliases",
            "--name",
            CORE_NAME,
            "core-api",
            "python",
            "-m",
            "http.server",
            "8000",
            "--bind",
            "0.0.0.0",
            capture=True,
        )

        core_id = (
            core_result
            .stdout
            .strip()
        )

        if not core_id:
            raise SystemExit(
                "CORE_RUNTIME_VERIFIER_CONTAINER_MISSING"
            )


        runtime_key_gate(
            identity_id,
            core_id,
        )

        network_membership_gate(
            identity_id,
            core_id,
        )

        crypto_gate(
            identity_id,
            core_id,
        )


        print(
            "IDENTITY_GATEWAY_CI_ADVERSARIAL_BOUNDARY=PASS"
        )

    finally:
        run(
            [
                "docker",
                "rm",
                "-f",
                CORE_NAME,
            ],
            check=False,
            capture=True,
        )

        compose(
            "down",
            "--remove-orphans",
            check=False,
        )


if __name__ == "__main__":
    main()
