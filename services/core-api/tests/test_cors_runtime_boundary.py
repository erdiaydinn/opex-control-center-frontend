# PRODUCTION_CORS_RUNTIME_GATE_V1

import os
import subprocess
import sys
import textwrap
from pathlib import Path

RUNTIME_SCRIPT = r"""
import asyncio
import httpx

import app.main as app_main


ALLOWED_ORIGIN = "https://app.example.com"
EVIL_ORIGIN = "https://evil.example"
PREFIX_ATTACK_ORIGIN = "https://app.example.com.evil.example"


async def _discard_audit(*args, **kwargs):
    # CORS tests must exercise the real middleware stack
    # without requiring a database connection.
    return None


app_main.write_audit_event = _discard_audit


async def run():
    transport = httpx.ASGITransport(
        app=app_main.app,
        raise_app_exceptions=True,
    )

    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://app.example.com",
    ) as client:

        # --------------------------------------------------------
        # 1. Exact allowed origin
        # --------------------------------------------------------
        response = await client.get(
            "/health/live",
            headers={
                "Origin": ALLOWED_ORIGIN,
            },
        )

        assert response.status_code == 200
        assert (
            response.headers.get(
                "access-control-allow-origin"
            )
            == ALLOWED_ORIGIN
        )
        assert (
            "access-control-allow-credentials"
            not in response.headers
        )

        print("CORS_EXACT_ALLOWED_ORIGIN=PASS")


        # --------------------------------------------------------
        # 2. Evil origin receives no browser authorization
        # --------------------------------------------------------
        response = await client.get(
            "/health/live",
            headers={
                "Origin": EVIL_ORIGIN,
            },
        )

        assert response.status_code == 200
        assert (
            "access-control-allow-origin"
            not in response.headers
        )
        assert (
            "access-control-allow-credentials"
            not in response.headers
        )

        print("CORS_EVIL_ORIGIN_DENIED=PASS")


        # --------------------------------------------------------
        # 3. "null" origin denied
        # --------------------------------------------------------
        response = await client.get(
            "/health/live",
            headers={
                "Origin": "null",
            },
        )

        assert response.status_code == 200
        assert (
            "access-control-allow-origin"
            not in response.headers
        )

        print("CORS_NULL_ORIGIN_DENIED=PASS")


        # --------------------------------------------------------
        # 4. Prefix / suffix origin confusion denied
        # --------------------------------------------------------
        response = await client.get(
            "/health/live",
            headers={
                "Origin": PREFIX_ATTACK_ORIGIN,
            },
        )

        assert response.status_code == 200
        assert (
            "access-control-allow-origin"
            not in response.headers
        )

        print("CORS_PREFIX_ATTACK_DENIED=PASS")


        # --------------------------------------------------------
        # 5. Valid authenticated API preflight
        # --------------------------------------------------------
        response = await client.options(
            "/v1/context",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": (
                    "Authorization,"
                    "Content-Type,"
                    "Idempotency-Key,"
                    "X-Request-ID"
                ),
            },
        )

        assert response.status_code == 200

        assert (
            response.headers.get(
                "access-control-allow-origin"
            )
            == ALLOWED_ORIGIN
        )

        allowed_headers = {
            item.strip().lower()
            for item in response.headers.get(
                "access-control-allow-headers",
                "",
            ).split(",")
            if item.strip()
        }

        required_headers = {
            "authorization",
            "content-type",
            "idempotency-key",
            "x-request-id",
        }

        assert required_headers.issubset(
            allowed_headers
        )

        assert "x-evil-header" not in allowed_headers

        assert (
            "access-control-allow-credentials"
            not in response.headers
        )

        print("CORS_VALID_PREFLIGHT=PASS")
        print("CORS_CREDENTIALS_DISABLED=PASS")


        # --------------------------------------------------------
        # 6. Unapproved request header must fail preflight
        # --------------------------------------------------------
        response = await client.options(
            "/v1/context",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": (
                    "Authorization,X-Evil-Header"
                ),
            },
        )

        assert response.status_code == 400

        returned_headers = (
            response.headers.get(
                "access-control-allow-headers",
                "",
            ).lower()
        )

        assert "x-evil-header" not in returned_headers

        print("CORS_UNAPPROVED_HEADER_DENIED=PASS")


        # --------------------------------------------------------
        # 7. Evil origin preflight must fail
        # --------------------------------------------------------
        response = await client.options(
            "/v1/context",
            headers={
                "Origin": EVIL_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": (
                    "Authorization"
                ),
            },
        )

        assert response.status_code == 400

        assert (
            "access-control-allow-origin"
            not in response.headers
        )

        print("CORS_EVIL_PREFLIGHT_DENIED=PASS")


        # --------------------------------------------------------
        # 8. Credentialed browser request gets no ACAC
        # --------------------------------------------------------
        response = await client.get(
            "/health/live",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Cookie": "session=attacker-controlled",
            },
        )

        assert response.status_code == 200

        assert (
            response.headers.get(
                "access-control-allow-origin"
            )
            == ALLOWED_ORIGIN
        )

        assert (
            "access-control-allow-credentials"
            not in response.headers
        )

        print("CORS_COOKIE_CREDENTIAL_TRUST=DISABLED")
        print("PRODUCTION_CORS_RUNTIME_GATE=PASS")

        # CORS_INNER_HARD_EXIT_AFTER_ASSERTIONS
        # All CORS assertions completed successfully.
        # Exit the intentionally isolated child before
        # asyncio.run() waits on unrelated global resources.
        import os
        import sys

        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)


asyncio.run(run())
"""


def test_actual_production_app_cors_runtime_boundary(
    tmp_path,
) -> None:
    runtime_secret = (
        tmp_path /
        "runtime-database-url"
    )

    runtime_secret.write_text(
        (
            "postgresql+asyncpg://"
            "runtime:test@postgres:5432/opex"
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()

    # Production app configuration.
    env.update(
        {
            "OPEX_ENVIRONMENT": "production",
            "OPEX_AUTH_MODE": "oidc",
            "OPEX_OIDC_ISSUER":
                "https://identity.example.com",
            "OPEX_OIDC_AUDIENCE":
                "opex-core-api",
            "OPEX_OIDC_JWKS_URL":
                "https://identity.example.com/"
                ".well-known/jwks.json",
            "OPEX_ALLOWED_HOSTS":
                "app.example.com",
            "OPEX_CORS_ORIGINS":
                "https://app.example.com",
            "OPEX_DATABASE_URL":
                "",
            "OPEX_DATABASE_URL_FILE":
                str(runtime_secret),
            "OPEX_MIGRATION_DATABASE_URL":
                "",
            "OPEX_MIGRATION_DATABASE_URL_FILE":
                "",
        }
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                RUNTIME_SCRIPT
            ),
        ],
        cwd=str(
            Path(__file__)
            .resolve()
            .parents[1]
        ),
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )

    assert result.returncode == 0, (
        "\nPRODUCTION CORS RUNTIME FAILURE\n\n"
        "STDOUT:\n"
        f"{result.stdout}\n\n"
        "STDERR:\n"
        f"{result.stderr}"
    )

    assert (
        "PRODUCTION_CORS_RUNTIME_GATE=PASS"
        in result.stdout
    )
