from pathlib import Path

from starlette.requests import Request

import app.core.client_ip as client_ip

REPO_ROOT = Path(__file__).resolve().parents[3]


def _request(
    peer: str,
    *,
    real_ip: str = "",
    forwarded_for: str = "",
) -> Request:
    headers = []

    if real_ip:
        headers.append(
            (b"x-real-ip", real_ip.encode())
        )

    if forwarded_for:
        headers.append(
            (
                b"x-forwarded-for",
                forwarded_for.encode(),
            )
        )

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": (peer, 12345),
            "server": ("core-api", 8000),
            "scheme": "http",
        }
    )


def test_direct_peer_cannot_spoof_real_ip(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        client_ip,
        "_trusted_proxy_addresses",
        lambda: {"172.30.0.10"},
    )

    request = _request(
        "172.30.0.55",
        real_ip="203.0.113.10",
        forwarded_for="198.51.100.20",
    )

    assert (
        client_ip.resolve_client_ip(request)
        == "172.30.0.55"
    )


def test_gateway_may_supply_single_valid_real_ip(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        client_ip,
        "_trusted_proxy_addresses",
        lambda: {"172.30.0.10"},
    )

    request = _request(
        "172.30.0.10",
        real_ip="203.0.113.10",
    )

    assert (
        client_ip.resolve_client_ip(request)
        == "203.0.113.10"
    )


def test_gateway_cannot_supply_ip_chain(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        client_ip,
        "_trusted_proxy_addresses",
        lambda: {"172.30.0.10"},
    )

    request = _request(
        "172.30.0.10",
        real_ip=(
            "203.0.113.10, "
            "198.51.100.20"
        ),
    )

    assert (
        client_ip.resolve_client_ip(request)
        == "172.30.0.10"
    )


def test_gateway_cannot_supply_invalid_real_ip(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        client_ip,
        "_trusted_proxy_addresses",
        lambda: {"172.30.0.10"},
    )

    request = _request(
        "172.30.0.10",
        real_ip="attacker-controlled",
    )

    assert (
        client_ip.resolve_client_ip(request)
        == "172.30.0.10"
    )


def test_uvicorn_does_not_trust_forwarded_headers_globally() -> None:
    text = (
        REPO_ROOT
        / "services/core-api/Dockerfile"
    ).read_text(
        encoding="utf-8-sig",
        errors="strict",
    )

    assert "--no-proxy-headers" in text
    assert "--forwarded-allow-ips" not in text
    assert '"*"' not in text


def test_nginx_discards_incoming_xff_chain() -> None:
    text = (
        REPO_ROOT
        / "infra/nginx/platform.conf"
    ).read_text(
        encoding="utf-8-sig",
        errors="strict",
    )

    assert (
        "$proxy_add_x_forwarded_for"
        not in text
    )

    assert (
        text.count(
            "proxy_set_header "
            "X-Forwarded-For $remote_addr;"
        )
        == 2
    )


def test_audit_uses_resolved_client_ip() -> None:
    text = (
        REPO_ROOT
        / "services/core-api/app/main.py"
    ).read_text(
        encoding="utf-8-sig",
        errors="strict",
    )

    assert (
        "resolve_client_ip(request)"
        in text
    )

    assert (
        '"client_host": getattr('
        in text
    )
