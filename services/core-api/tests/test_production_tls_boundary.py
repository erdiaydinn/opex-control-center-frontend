from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (
        REPO_ROOT / path
    ).read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def test_production_gateway_requires_tls_secrets() -> None:
    compose = _read(
        "docker-compose.production.yml"
    )

    assert "OPEX_TLS_CERTIFICATE_FILE:?" in compose
    assert "OPEX_TLS_PRIVATE_KEY_FILE:?" in compose
    assert "target: tls_certificate" in compose
    assert "target: tls_private_key" in compose


def test_production_gateway_replaces_dev_ports() -> None:
    compose = _read(
        "docker-compose.production.yml"
    )

    assert "ports: !override" in compose
    assert (
        '${OPEX_GATEWAY_HTTP_PORT:-80}:80'
        in compose
    )
    assert (
        '${OPEX_GATEWAY_HTTPS_PORT:-443}:443'
        in compose
    )


def test_production_gateway_replaces_dev_nginx_config() -> None:
    compose = _read(
        "docker-compose.production.yml"
    )

    assert "volumes: !override" in compose
    assert (
        "platform.production.conf.template"
        in compose
    )


def test_public_hostname_is_required() -> None:
    compose = _read(
        "docker-compose.production.yml"
    )

    assert "OPEX_PUBLIC_HOST:?" in compose


def test_http_redirect_is_fixed_host_https() -> None:
    nginx = _read(
        "infra/nginx/"
        "platform.production.conf.template"
    )

    assert (
        "return 308 "
        "https://${OPEX_PUBLIC_HOST}"
        "$request_uri;"
        in nginx
    )

    assert "return 308 https://$host" not in nginx


def test_production_tls_listener_is_required() -> None:
    nginx = _read(
        "infra/nginx/"
        "platform.production.conf.template"
    )

    assert "listen 443 ssl default_server;" in nginx

    assert (
        "ssl_certificate "
        "/run/secrets/tls_certificate;"
        in nginx
    )

    assert (
        "ssl_certificate_key "
        "/run/secrets/tls_private_key;"
        in nginx
    )


def test_only_modern_tls_protocols_are_enabled() -> None:
    nginx = _read(
        "infra/nginx/"
        "platform.production.conf.template"
    )

    assert "ssl_protocols TLSv1.2 TLSv1.3;" in nginx
    assert "TLSv1.0" not in nginx
    assert "TLSv1.1" not in nginx


def test_hsts_exists_only_after_tls_listener() -> None:
    nginx = _read(
        "infra/nginx/"
        "platform.production.conf.template"
    )

    assert nginx.count(
        "Strict-Transport-Security"
    ) == 1

    assert nginx.index(
        "Strict-Transport-Security"
    ) > nginx.index(
        "listen 443 ssl default_server;"
    )

    hsts = next(
        line
        for line in nginx.splitlines()
        if "Strict-Transport-Security" in line
    )

    assert "max-age=31536000" in hsts
    assert "preload" not in hsts
    assert "includeSubDomains" not in hsts


def test_tls_gateway_overwrites_forwarding_headers() -> None:
    nginx = _read(
        "infra/nginx/"
        "platform.production.conf.template"
    )

    assert "$proxy_add_x_forwarded_for" not in nginx

    assert nginx.count(
        "proxy_set_header "
        "X-Forwarded-For $remote_addr;"
    ) == 2

    assert nginx.count(
        "proxy_set_header "
        "X-Real-IP $remote_addr;"
    ) == 2

    assert nginx.count(
        "proxy_set_header "
        "X-Forwarded-Proto https;"
    ) == 2

    assert nginx.count(
        'proxy_set_header Forwarded "";'
    ) == 2


def test_host_header_is_fail_closed() -> None:
    nginx = _read(
        "infra/nginx/"
        "platform.production.conf.template"
    )

    assert nginx.count(
        'if ($host != "${OPEX_PUBLIC_HOST}")'
    ) == 2

    assert nginx.count(
        "return 421;"
    ) == 2
