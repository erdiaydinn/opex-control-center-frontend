from __future__ import annotations

import ipaddress
import socket

from starlette.requests import Request

TRUSTED_PROXY_HOST = "gateway"


def _trusted_proxy_addresses(
    hostname: str = TRUSTED_PROXY_HOST,
) -> set[str]:
    try:
        records = socket.getaddrinfo(
            hostname,
            None,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        return set()

    return {
        record[4][0]
        for record in records
        if record
        and len(record) >= 5
        and record[4]
    }


def _valid_single_ip(value: str) -> str | None:
    candidate = str(value or "").strip()

    # Never accept an XFF-style list here.
    if not candidate or "," in candidate:
        return None

    try:
        return str(
            ipaddress.ip_address(candidate)
        )
    except ValueError:
        return None


def resolve_client_ip(request: Request) -> str | None:
    """
    Trust X-Real-IP only when the immediate TCP peer is
    the Docker gateway service.

    Uvicorn proxy-header processing is disabled, so
    request.client always represents the real peer socket.
    """
    if request.client is None:
        return None

    peer = str(request.client.host or "").strip()

    if not peer:
        return None

    trusted = _trusted_proxy_addresses()

    if peer not in trusted:
        return peer

    forwarded = _valid_single_ip(
        request.headers.get("X-Real-IP", "")
    )

    return forwarded or peer
