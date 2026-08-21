from uuid import uuid4

import httpx
import pytest

from app.modules.field_intelligence.evidence_object_read import read_private_evidence_object
from app.modules.field_intelligence.evidence_object_upload import FieldEvidenceStoreUnavailable

TENANT_ID = str(uuid4())
RECEIPT_ID = str(uuid4())
BASE_URL = "https://field-evidence-store"
TRUSTED = frozenset({"field-evidence-store"})


@pytest.mark.asyncio
async def test_private_reader_returns_exact_jpeg_bytes_without_redirects() -> None:
    body = b"sanitized-jpeg"

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == f"/v1/private/field-evidence/{RECEIPT_ID}"
        assert request.headers["x-eay-field-tenant"] == TENANT_ID
        assert request.headers["x-eay-field-expected-bytes"] == str(len(body))
        assert request.headers["accept"] == "image/jpeg"
        return httpx.Response(
            200,
            headers={"content-type": "image/jpeg", "content-length": str(len(body))},
            content=body,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await read_private_evidence_object(
            tenant_id=TENANT_ID,
            receipt_id=RECEIPT_ID,
            expected_byte_size=len(body),
            client=client,
            base_url=BASE_URL,
            trusted_hosts=TRUSTED,
            token="opaque-test-token",
        )
    assert result == body


@pytest.mark.asyncio
async def test_gateway_without_get_support_fails_closed() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(405)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(FieldEvidenceStoreUnavailable, match="read is unavailable"):
            await read_private_evidence_object(
                tenant_id=TENANT_ID,
                receipt_id=RECEIPT_ID,
                expected_byte_size=4,
                client=client,
                base_url=BASE_URL,
                trusted_hosts=TRUSTED,
            )


@pytest.mark.asyncio
async def test_reader_rejects_declared_byte_size_mismatch() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "image/jpeg", "content-length": "9"},
            content=b"four",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(FieldEvidenceStoreUnavailable, match="declared a byte-size mismatch"):
            await read_private_evidence_object(
                tenant_id=TENANT_ID,
                receipt_id=RECEIPT_ID,
                expected_byte_size=4,
                client=client,
                base_url=BASE_URL,
                trusted_hosts=TRUSTED,
            )


@pytest.mark.asyncio
async def test_reader_rejects_non_jpeg_object() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain", "content-length": "4"},
            content=b"four",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(FieldEvidenceStoreUnavailable, match="unsupported media type"):
            await read_private_evidence_object(
                tenant_id=TENANT_ID,
                receipt_id=RECEIPT_ID,
                expected_byte_size=4,
                client=client,
                base_url=BASE_URL,
                trusted_hosts=TRUSTED,
            )


@pytest.mark.asyncio
async def test_reader_rejects_caller_attempt_to_expand_media_authority() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway must not be contacted for unauthorized media")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(FieldEvidenceStoreUnavailable, match="image/jpeg only"):
            await read_private_evidence_object(
                tenant_id=TENANT_ID,
                receipt_id=RECEIPT_ID,
                expected_byte_size=4,
                expected_media_type="video/mp4",
                client=client,
                base_url=BASE_URL,
                trusted_hosts=TRUSTED,
            )


@pytest.mark.asyncio
async def test_reader_rejects_untrusted_gateway_host() -> None:
    with pytest.raises(FieldEvidenceStoreUnavailable, match="configuration is invalid"):
        await read_private_evidence_object(
            tenant_id=TENANT_ID,
            receipt_id=RECEIPT_ID,
            expected_byte_size=4,
            base_url="https://evil.example",
            trusted_hosts=TRUSTED,
        )
