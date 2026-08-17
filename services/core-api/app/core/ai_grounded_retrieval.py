"""Internal Core -> EAY AI Core tenant-grounded retrieval transport.

Tenant identity is deliberately absent from the request API. The only tenant,
membership and actor authority crossing this boundary is the short-lived signed
Identity Gateway assertion supplied by trusted server-side orchestration.
"""

from __future__ import annotations

from datetime import date
from ipaddress import ip_address
from urllib.parse import urlsplit

import httpx

AI_TENANT_CONTEXT_HEADER = "X-EAY-AI-Tenant-Context"
ALLOWED_LAYERS = frozenset({"legal", "standard", "company", "operational"})
ALLOWED_AUTHORITY_LEVELS = frozenset({"binding", "company", "voluntary", "operational"})
DEFAULT_TRUSTED_AI_HOSTS = frozenset({"eay-ai-core", "localhost"})
EVIDENCE_FIELDS = frozenset(
    {
        "id",
        "layer",
        "title",
        "excerpt",
        "source_name",
        "source_url",
        "effective_from",
        "effective_to",
        "authority_level",
        "score",
    }
)


class AIGroundedRetrievalUnavailable(RuntimeError):
    pass


def _is_loopback_host(hostname: str) -> bool:
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def _normalized_base_url(
    base_url: str,
    *,
    trusted_hosts: frozenset[str] = DEFAULT_TRUSTED_AI_HOSTS,
) -> str:
    value = base_url.strip().rstrip("/")
    parsed = urlsplit(value)
    hostname = (parsed.hostname or "").lower()
    normalized_trusted_hosts = {
        host.strip().lower() for host in trusted_hosts if host.strip()
    }

    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (hostname not in normalized_trusted_hosts and not _is_loopback_host(hostname))
    ):
        raise ValueError("AI Core base URL is invalid")
    return value


def _validated_assertion(assertion: str) -> str:
    if (
        not assertion
        or len(assertion) > 8192
        or assertion != assertion.strip()
        or "," in assertion
        or any(character.isspace() for character in assertion)
    ):
        raise ValueError("AI tenant-context assertion is invalid")
    return assertion


def _validated_evidence_response(
    body: object,
    *,
    requested_limit: int,
    requested_layers: frozenset[str],
) -> list[dict[str, object]]:
    evidence = body.get("evidence") if isinstance(body, dict) else None
    if not isinstance(evidence, list) or len(evidence) > requested_limit:
        raise AIGroundedRetrievalUnavailable("AI grounded retrieval unavailable")

    validated: list[dict[str, object]] = []
    for item in evidence:
        if not isinstance(item, dict) or set(item) != EVIDENCE_FIELDS:
            raise AIGroundedRetrievalUnavailable("AI grounded retrieval unavailable")
        if item["layer"] not in requested_layers:
            raise AIGroundedRetrievalUnavailable("AI grounded retrieval unavailable")
        if item["authority_level"] not in ALLOWED_AUTHORITY_LEVELS:
            raise AIGroundedRetrievalUnavailable("AI grounded retrieval unavailable")
        if not isinstance(item["score"], (int, float)) or isinstance(item["score"], bool):
            raise AIGroundedRetrievalUnavailable("AI grounded retrieval unavailable")
        for field, maximum in (
            ("id", 180),
            ("title", 500),
            ("excerpt", 1401),
            ("source_name", 300),
        ):
            value = item[field]
            if not isinstance(value, str) or not value or len(value) > maximum:
                raise AIGroundedRetrievalUnavailable("AI grounded retrieval unavailable")
        source_url = item["source_url"]
        if source_url is not None and (
            not isinstance(source_url, str) or len(source_url) > 2048
        ):
            raise AIGroundedRetrievalUnavailable("AI grounded retrieval unavailable")
        for field in ("effective_from", "effective_to"):
            value = item[field]
            if value is not None and (
                not isinstance(value, str) or len(value) != 10
            ):
                raise AIGroundedRetrievalUnavailable("AI grounded retrieval unavailable")
        validated.append(item)
    return validated


async def retrieve_tenant_grounded_evidence(
    *,
    base_url: str,
    tenant_context_assertion: str,
    message: str,
    as_of: date,
    layers: tuple[str, ...],
    limit: int = 8,
    client: httpx.AsyncClient | None = None,
    trusted_hosts: frozenset[str] = DEFAULT_TRUSTED_AI_HOSTS,
) -> list[dict[str, object]]:
    """Retrieve tenant-scoped evidence without accepting a tenant identifier."""

    normalized_message = message.strip()
    if not 2 <= len(normalized_message) <= 4000:
        raise ValueError("Grounded retrieval message is invalid")
    if (
        not layers
        or len(layers) > 4
        or len(set(layers)) != len(layers)
        or any(layer not in ALLOWED_LAYERS for layer in layers)
    ):
        raise ValueError("Grounded retrieval layers are invalid")
    if not 1 <= limit <= 32:
        raise ValueError("Grounded retrieval limit is invalid")

    url = (
        _normalized_base_url(base_url, trusted_hosts=trusted_hosts)
        + "/v1/internal/grounded/retrieve"
    )
    headers = {AI_TENANT_CONTEXT_HEADER: _validated_assertion(tenant_context_assertion)}
    payload = {
        "message": normalized_message,
        "as_of": as_of.isoformat(),
        "layers": list(layers),
        "limit": limit,
    }

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
    try:
        # The tenant-context assertion is a bearer-equivalent server credential.
        # Never inherit a caller-provided client's redirect policy: a 30x response
        # must not be able to forward this assertion to another origin.
        response = await active_client.post(
            url,
            headers=headers,
            json=payload,
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        raise AIGroundedRetrievalUnavailable("AI grounded retrieval unavailable") from exc
    finally:
        if owns_client:
            await active_client.aclose()

    if response.status_code != 200:
        raise AIGroundedRetrievalUnavailable("AI grounded retrieval unavailable")

    try:
        body = response.json()
    except ValueError as exc:
        raise AIGroundedRetrievalUnavailable("AI grounded retrieval unavailable") from exc

    return _validated_evidence_response(
        body,
        requested_limit=limit,
        requested_layers=frozenset(layers),
    )
