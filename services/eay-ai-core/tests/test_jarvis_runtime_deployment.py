from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.jarvis_runtime import (
    JarvisRuntimeConfigurationError,
    build_platform_tool_authorizer,
    platform_authorizer_settings_from_environment,
)
from app.platform_tool_authorizer import PlatformToolAuthorizer


REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = REPO_ROOT / "services" / "eay-ai-core"


def write_private_key(path: Path) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def test_platform_authorizer_environment_fails_closed_without_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EAY_PLATFORM_CORE_BASE_URL", raising=False)

    with pytest.raises(JarvisRuntimeConfigurationError):
        platform_authorizer_settings_from_environment()


def test_platform_authorizer_environment_rejects_bad_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EAY_PLATFORM_CORE_BASE_URL", "http://core-api:8000")
    monkeypatch.setenv("EAY_PLATFORM_CORE_AUTH_TIMEOUT_SECONDS", "not-a-number")

    with pytest.raises(JarvisRuntimeConfigurationError):
        platform_authorizer_settings_from_environment()


def test_runtime_factory_builds_with_independent_service_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    private_key = tmp_path / "jarvis-private.pem"
    write_private_key(private_key)

    monkeypatch.setenv(
        "EAY_JARVIS_SERVICE_PRIVATE_KEY_FILE",
        str(private_key),
    )
    monkeypatch.setenv("EAY_JARVIS_SERVICE_SIGNING_KID", "runtime-test-v1")
    monkeypatch.setenv("EAY_JARVIS_SERVICE_ISSUER", "eay-ai-core")
    monkeypatch.setenv("EAY_JARVIS_SERVICE_AUDIENCE", "opex-core-jarvis")
    monkeypatch.setenv("EAY_JARVIS_SERVICE_LIFETIME_SECONDS", "30")
    monkeypatch.setenv("EAY_PLATFORM_CORE_BASE_URL", "http://core-api:8000")
    monkeypatch.setenv("EAY_PLATFORM_CORE_AUTH_TIMEOUT_SECONDS", "5")

    authorizer = build_platform_tool_authorizer()

    assert isinstance(authorizer, PlatformToolAuthorizer)


def test_container_image_is_non_root_and_secret_free() -> None:
    dockerfile = (SERVICE_ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (SERVICE_ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "USER 10001:10001" in dockerfile
    assert "COPY ." not in dockerfile
    assert "PRIVATE_KEY" not in dockerfile
    assert "*.pem" in dockerignore
    assert ".env" in dockerignore
    assert "data/" in dockerignore


def test_compose_runtime_is_internal_only_and_hardened() -> None:
    compose = (REPO_ROOT / "docker-compose.eay-ai-core.yml").read_text(
        encoding="utf-8"
    )

    assert "ports:" not in compose
    assert "- ai_plane" in compose
    assert "gateway:" not in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose
    assert "- ALL" in compose
    assert (
        "EAY_JARVIS_SERVICE_PRIVATE_KEY_FILE: "
        "/run/secrets/eay_jarvis_service_private_key"
    ) in compose
    assert "EAY_JARVIS_SERVICE_PRIVATE_KEY_SOURCE_FILE" in compose
    assert "EAY_PLATFORM_CORE_BASE_URL" in compose
    assert "/api/internal" not in compose


def test_runtime_example_never_contains_private_key_material() -> None:
    example = (SERVICE_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "EAY_JARVIS_SERVICE_PRIVATE_KEY_FILE=" in example
    assert "EAY_JARVIS_SERVICE_PRIVATE_KEY_SOURCE_FILE=" in example
    assert "BEGIN PRIVATE KEY" not in example
    assert "opex-core-preauth" not in example
