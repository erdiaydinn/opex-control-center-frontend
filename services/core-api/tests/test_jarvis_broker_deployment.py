from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BASE_COMPOSE = ROOT / "docker-compose.platform.yml"
BROKER_COMPOSE = ROOT / "docker-compose.jarvis-broker.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_base_platform_does_not_enable_execution_broker_implicitly() -> None:
    base = read(BASE_COMPOSE)

    assert "OPEX_JARVIS_BROKER_ENABLED" not in base
    assert "OPEX_JARVIS_BROKER_AI_CORE_BASE_URL" not in base


def test_broker_overlay_uses_internal_ai_core_dns_only() -> None:
    overlay = read(BROKER_COMPOSE)

    assert 'OPEX_JARVIS_BROKER_ENABLED: "true"' in overlay
    assert "http://eay-ai-core:8030" in overlay
    assert "gateway:" not in overlay
    assert "/api/" not in overlay
    assert "localhost" not in overlay
    assert "127.0.0.1" not in overlay


def test_broker_overlay_has_no_network_or_secret_expansion() -> None:
    overlay = read(BROKER_COMPOSE)

    assert "ports:" not in overlay
    assert "networks:" not in overlay
    assert "secrets:" not in overlay
    assert "PRIVATE_KEY" not in overlay
    assert "JWKS" not in overlay


def test_browser_never_receives_grant_route_from_broker_overlay() -> None:
    overlay = read(BROKER_COMPOSE)

    assert "tool-grants" not in overlay
    assert "grant_token" not in overlay
