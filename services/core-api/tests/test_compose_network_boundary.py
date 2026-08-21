from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


PROTECTED_SERVICES = {
    "core-api",
    "postgres",
    "redis",
    "frontend",
    "platform-agent",
    "docker-socket-proxy",
}


def _read(name: str) -> str:
    path = REPO_ROOT / name

    if not path.exists():
        return ""

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def _service_block(text: str, service: str) -> str:
    lines = text.splitlines()

    marker = f"  {service}:"

    try:
        start = lines.index(marker) + 1
    except ValueError:
        return ""

    collected = []

    for line in lines[start:]:
        if (
            line.startswith("  ")
            and not line.startswith("    ")
            and line.rstrip().endswith(":")
        ):
            break

        collected.append(line)

    return "\n".join(collected)


def test_internal_services_are_never_host_published() -> None:
    compose_files = (
        "docker-compose.platform.yml",
        "docker-compose.production.yml",
        "docker-compose.production-email.yml",
    )

    for compose_name in compose_files:
        text = _read(compose_name)

        if not text:
            continue

        for service in PROTECTED_SERVICES:
            block = _service_block(
                text,
                service,
            )

            if not block:
                continue

            assert not any(
                line.strip() == "ports:"
                for line in block.splitlines()
            ), (
                f"{service} must not publish host ports "
                f"in {compose_name}; use Docker internal "
                f"network + gateway only"
            )


def test_core_api_is_internal_only() -> None:
    text = _read(
        "docker-compose.platform.yml"
    )

    block = _service_block(
        text,
        "core-api",
    )

    assert block
    assert '      - "8000"' in block
    assert "ports:" not in block


def test_gateway_is_the_platform_ingress() -> None:
    text = _read(
        "docker-compose.platform.yml"
    )

    gateway = _service_block(
        text,
        "gateway",
    )

    assert gateway
    assert "ports:" in gateway

    assert (
        '${OPEX_GATEWAY_PORT:-8080}:80'
        in gateway
    )


def test_nginx_api_proxy_targets_internal_core_api() -> None:
    nginx = _read(
        "infra/nginx/platform.conf"
    )

    assert (
        "proxy_pass http://core-api:8000/;"
        in nginx
    )

    forbidden = (
        "proxy_pass http://127.0.0.1:8000",
        "proxy_pass http://localhost:8000",
    )

    for value in forbidden:
        assert value not in nginx


def test_frontend_source_cannot_target_core_api_port() -> None:
    src_root = REPO_ROOT / "src"

    for path in src_root.rglob("*"):
        if (
            not path.is_file()
            or path.suffix
            not in {".js", ".jsx", ".ts", ".tsx"}
        ):
            continue

        text = path.read_text(
            encoding="utf-8-sig",
            errors="ignore",
        )

        assert ":8000" not in text, (
            "Frontend must never bypass gateway: "
            f"{path.relative_to(REPO_ROOT)}"
        )


def test_database_and_redis_are_not_host_published() -> None:
    text = _read(
        "docker-compose.platform.yml"
    )

    for service in (
        "postgres",
        "redis",
    ):
        block = _service_block(
            text,
            service,
        )

        assert block
        assert "ports:" not in block
