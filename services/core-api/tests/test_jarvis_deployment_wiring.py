from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BASE_COMPOSE = ROOT / "docker-compose.platform.yml"
JARVIS_TRUST_COMPOSE = ROOT / "docker-compose.jarvis-trust.yml"
ENV_EXAMPLE = ROOT / ".env.example"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_base_platform_does_not_enable_jarvis_implicitly() -> None:
    base = read(BASE_COMPOSE)

    assert "OPEX_JARVIS_SERVICE_ENABLED" not in base
    assert "jarvis_service_jwks" not in base


def test_jarvis_trust_override_mounts_public_jwks_only() -> None:
    override = read(JARVIS_TRUST_COMPOSE)

    assert 'OPEX_JARVIS_SERVICE_ENABLED: "true"' in override
    assert (
        'OPEX_JARVIS_SERVICE_ASSERTION_JWKS_FILE: '
        '"/run/secrets/jarvis_service_jwks"'
    ) in override
    assert "OPEX_JARVIS_SERVICE_JWKS_SOURCE_FILE" in override
    assert "EAY_JARVIS_SERVICE_PRIVATE_KEY_FILE" not in override
    assert "jarvis_service_private_key" not in override


def test_jarvis_trust_override_cannot_publish_network_surface() -> None:
    override = read(JARVIS_TRUST_COMPOSE)

    assert "ports:" not in override
    assert "gateway:" not in override
    assert "identity-gateway:" not in override
    assert "/api/internal" not in override


def test_env_example_labels_jarvis_material_public_only() -> None:
    example = read(ENV_EXAMPLE)

    assert "OPEX_JARVIS_SERVICE_JWKS_SOURCE_FILE=" in example
    assert "PUBLIC JWKS" in example
    assert "EAY_JARVIS_SERVICE_PRIVATE_KEY_FILE=" not in example
