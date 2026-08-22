from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.tuik_theme_catalog_adapter import read_tuik_theme_catalog_observation

NOW = datetime(2026, 8, 22, 21, 0, tzinfo=UTC)
TENANT = "tenant-field-shape"


def _document(*, omit_root_url: bool = False) -> dict[str, Any]:
    root: dict[str, Any] = {
        "id": 1,
        "name": "Adalet ve Seçim",
        "url": "",
        "icon": "justice",
        "metadataUrl": None,
        "children": [
            {
                "id": "1.21",
                "name": "Adalet İstatistikleri",
                "url": "",
                "icon": None,
                "children": [
                    {
                        "id": "1.21.141",
                        "name": "Güvenlik Birimine Gelen veya Getirilen Çocuk İstatistikleri",
                        "url": "/tr/statistical-themes/children-security",
                        "icon": None,
                        "children": [],
                    }
                ],
            }
        ],
    }
    if omit_root_url:
        root.pop("url")
    return {"data": [root], "isError": False, "message": None}


def _transport(document: dict[str, Any]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/tr/statistical-themes":
            return httpx.Response(
                200,
                headers={
                    "content-type": "text/html; charset=utf-8",
                    "set-cookie": "tuik-session=verified; Path=/; Secure; HttpOnly",
                },
                content=b"<html>" + (b"x" * 1_200) + b"</html>",
            )
        assert request.url.path == "/api/tr/data/statistical-themes"
        return httpx.Response(
            200,
            headers={"content-type": "application/json; charset=utf-8"},
            content=json.dumps(document, ensure_ascii=False).encode(),
        )

    return httpx.MockTransport(handler)


def test_field_verified_structural_nodes_may_have_blank_urls() -> None:
    result = read_tuik_theme_catalog_observation(
        tenant_id=TENANT,
        transport=_transport(_document()),
        now=NOW,
    )

    root = result.catalog_receipt.themes[0]
    group = root.children[0]
    leaf = group.children[0]
    assert root.url is None
    assert group.url is None
    assert leaf.url == "/tr/statistical-themes/children-security"
    assert result.catalog_receipt.root_theme_count == 1
    assert result.catalog_receipt.total_node_count == 3
    assert result.catalog_receipt.context_only is True
    assert result.observation.company_truth_granted is False
    assert result.observation.causal_claim_proven is False
    assert result.observation.execution_authority_granted is False


def test_structural_url_key_absence_is_normalized_without_authority_gain() -> None:
    result = read_tuik_theme_catalog_observation(
        tenant_id=TENANT,
        transport=_transport(_document(omit_root_url=True)),
        now=NOW,
    )

    root = result.catalog_receipt.themes[0]
    assert root.url is None
    assert root.theme_id == "1"
    assert root.children
    assert result.catalog_receipt.context_only is True
    assert result.observation.company_truth_granted is False
    assert result.observation.execution_authority_granted is False


def test_field_verified_missing_name_is_preserved_as_none_without_invention() -> None:
    document = _document()
    target = document["data"][0]["children"][0]["children"][0]
    target.pop("name")

    result = read_tuik_theme_catalog_observation(
        tenant_id=TENANT,
        transport=_transport(document),
        now=NOW,
    )

    leaf = result.catalog_receipt.themes[0].children[0].children[0]
    assert leaf.theme_id == "1.21.141"
    assert leaf.name is None
    assert result.catalog_receipt.context_only is True
    assert result.observation.company_truth_granted is False
    assert result.observation.causal_claim_proven is False
    assert result.observation.execution_authority_granted is False


def test_explicit_null_or_blank_name_remains_fail_closed() -> None:
    for invalid_name in (None, ""):
        document = _document()
        document["data"][0]["children"][0]["children"][0]["name"] = invalid_name
        with pytest.raises(ValueError, match="tuik_theme_catalog_theme_name_required"):
            read_tuik_theme_catalog_observation(
                tenant_id=TENANT,
                transport=_transport(document),
                now=NOW,
            )
