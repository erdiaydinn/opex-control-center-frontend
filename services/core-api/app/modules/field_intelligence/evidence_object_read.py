from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import httpx

from .evidence_object_upload import (
    DEFAULT_TRUSTED_STORAGE_HOSTS,
    MAX_EVIDENCE_BYTES,
    FieldEvidenceStoreUnavailable,
    _normalize_base_url,
    storage_runtime_config,
)


async def _bounded_content(
    response: httpx.Response,
    *,
    expected_byte_size: int,
) -> bytes:
    content = bytearray()
    iterator: AsyncIterator[bytes] = response.aiter_bytes()
    async for chunk in iterator:
        if len(content) + len(chunk) > expected_byte_size:
            raise FieldEvidenceStoreUnavailable(
                "private Field evidence store returned more bytes than the immutable receipt"
            )
        content.extend(chunk)
    if len(content) != expected_byte_size:
        raise FieldEvidenceStoreUnavailable(
            "private Field evidence store returned a byte-size mismatch"
        )
    return bytes(content)


async def read_private_evidence_object(
    *,
    tenant_id: str,
    receipt_id: str,
    expected_byte_size: int,
    client: httpx.AsyncClient | None = None,
    base_url: str | None = None,
    trusted_hosts: frozenset[str] | None = None,
    token: str | None = None,
) -> bytes:
    """Read one private evidence object without granting semantic authority.

    The adapter deliberately knows only tenant, server receipt identity and an immutable byte-size
    bound. Hash/privacy/model decisions remain separate authorities. Redirects are forbidden and
    raw bytes never leave the caller's in-process lifetime.
    """

    try:
        UUID(tenant_id)
        UUID(receipt_id)
    except ValueError as exc:
        raise FieldEvidenceStoreUnavailable("invalid private Field evidence identity") from exc
    if expected_byte_size <= 0 or expected_byte_size > MAX_EVIDENCE_BYTES:
        raise FieldEvidenceStoreUnavailable("invalid private Field evidence byte-size bound")

    if base_url is None:
        configured_url, configured_hosts, configured_token = storage_runtime_config()
        base_url = configured_url
        trusted_hosts = configured_hosts
        token = configured_token
    else:
        trusted_hosts = trusted_hosts or DEFAULT_TRUSTED_STORAGE_HOSTS
        base_url = _normalize_base_url(base_url, trusted_hosts)

    headers = {
        "Accept": "image/jpeg",
        "X-EAY-Field-Tenant": tenant_id,
        "X-EAY-Field-Expected-Bytes": str(expected_byte_size),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=httpx.Timeout(20.0))
    try:
        try:
            async with active_client.stream(
                "GET",
                f"{base_url}/v1/private/field-evidence/{receipt_id}",
                headers=headers,
                follow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise FieldEvidenceStoreUnavailable(
                        "private Field evidence store read is unavailable"
                    )
                media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if media_type != "image/jpeg":
                    raise FieldEvidenceStoreUnavailable(
                        "private Field evidence store returned an unsupported media type"
                    )
                declared_length = response.headers.get("content-length")
                if declared_length is not None:
                    try:
                        parsed_length = int(declared_length)
                    except ValueError as exc:
                        raise FieldEvidenceStoreUnavailable(
                            "private Field evidence store returned an invalid content length"
                        ) from exc
                    if parsed_length != expected_byte_size:
                        raise FieldEvidenceStoreUnavailable(
                            "private Field evidence store declared a byte-size mismatch"
                        )
                return await _bounded_content(
                    response,
                    expected_byte_size=expected_byte_size,
                )
        except httpx.HTTPError as exc:
            raise FieldEvidenceStoreUnavailable(
                "private Field evidence store read is unavailable"
            ) from exc
    finally:
        if owns_client:
            await active_client.aclose()
