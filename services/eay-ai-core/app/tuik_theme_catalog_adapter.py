"""Verified one-shot TÜİK theme catalog adapter for Jarvis Company World.

The official portal catalog is external context only. This adapter validates the
live session-aware payload, seals its provenance, and emits a canonical external
observation. It never promotes a theme catalog into company truth, causality, or
execution authority and it does not authorize continuous ingestion.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .company_world_live_bridge import (
    ExternalContextDomain,
    ExternalContextObservation,
    GeographicScope,
    GeographicScopeLevel,
    build_external_context_observation,
)
from .context_provider_gateway import RequestPurpose, plan_provider_request
from .context_provider_runtime import ProviderEvidenceReceipt, execute_provider_request
from .real_world_timeline import (
    TimelineAuthorityClass,
    TimelineEventKind,
    TimelineObjectKind,
    TimelineObjectQualifier,
    TimelineObjectRelation,
    build_timeline_event,
)

TUIK_THEME_CATALOG_CONTRACT = "eay-tuik-theme-catalog-v1"
TUIK_THEME_PROVIDER_ID = "tr-tuik-theme-catalog"
TUIK_THEME_API_URL = "https://veriportali.tuik.gov.tr/api/tr/data/statistical-themes"
TUIK_THEME_HOST = "veriportali.tuik.gov.tr"
MAX_THEME_DEPTH = 12
MAX_THEME_NODES = 5_000


class TUIKThemeNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    theme_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=500)
    # Field evidence shows structural/group nodes legitimately carry null/blank URLs.
    # The source key remains mandatory in _parse_node; any non-empty URL is still
    # constrained to a safe relative path or HTTPS under the official TÜİK domain.
    url: str | None = Field(max_length=2_000)
    icon: str | None = Field(default=None, max_length=2_000)
    metadata_url: str | None = Field(default=None, max_length=2_000)
    children: tuple[TUIKThemeNode, ...] = ()


class TUIKThemeCatalogReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = TUIK_THEME_CATALOG_CONTRACT
    provider_id: str = TUIK_THEME_PROVIDER_ID
    source_url: str
    fetched_at: datetime
    provider_evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bootstrap_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    root_theme_count: int = Field(gt=0, le=1_000)
    total_node_count: int = Field(gt=0, le=MAX_THEME_NODES)
    themes: tuple[TUIKThemeNode, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    context_only: bool = True
    company_truth_granted: bool = False
    causal_claim_proven: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_catalog_receipt(self) -> TUIKThemeCatalogReceipt:
        if self.provider_id != TUIK_THEME_PROVIDER_ID:
            raise ValueError("tuik_theme_catalog_provider_mismatch")
        if self.source_url != TUIK_THEME_API_URL:
            raise ValueError("tuik_theme_catalog_source_url_mismatch")
        if self.fetched_at.tzinfo is None:
            raise ValueError("tuik_theme_catalog_fetched_at_timezone_required")
        if self.root_theme_count != len(self.themes):
            raise ValueError("tuik_theme_catalog_root_count_mismatch")
        if self.total_node_count != _count_nodes(self.themes):
            raise ValueError("tuik_theme_catalog_total_count_mismatch")
        if (
            not self.context_only
            or self.company_truth_granted
            or self.causal_claim_proven
            or self.execution_authority_granted
        ):
            raise ValueError("tuik_theme_catalog_never_grants_company_authority")
        _verify_sealed(self)
        return self


class TUIKThemeCatalogRead(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    provider_receipt: ProviderEvidenceReceipt
    catalog_receipt: TUIKThemeCatalogReceipt
    observation: ExternalContextObservation


def _safe_catalog_url(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"tuik_theme_catalog_{field_name}_required")
    normalized = value.strip()
    if normalized.startswith("/") and not normalized.startswith("//"):
        return normalized
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme == "https"
        and (host == "tuik.gov.tr" or host.endswith(".tuik.gov.tr"))
        and not parsed.username
        and not parsed.password
        and parsed.port in (None, 443)
        and not parsed.fragment
    ):
        return normalized
    raise ValueError(f"tuik_theme_catalog_{field_name}_unsafe")


def _normalize_theme_id(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("tuik_theme_catalog_theme_id_invalid")
    normalized = str(value).strip()
    if not normalized or len(normalized) > 200:
        raise ValueError("tuik_theme_catalog_theme_id_invalid")
    return normalized


def _optional_text(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"tuik_theme_catalog_{field_name}_invalid")
    normalized = value.strip()
    return normalized or None


def _optional_catalog_url(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"tuik_theme_catalog_{field_name}_invalid")
    normalized = value.strip()
    if not normalized:
        return None
    return _safe_catalog_url(normalized, field_name=field_name)


def _parse_node(
    raw: Any,
    *,
    depth: int,
    seen_ids: set[str],
    node_counter: list[int],
) -> TUIKThemeNode:
    if depth > MAX_THEME_DEPTH:
        raise ValueError("tuik_theme_catalog_depth_exceeded")
    if not isinstance(raw, dict):
        raise ValueError("tuik_theme_catalog_node_must_be_object")
    required = {"id", "name", "url", "children"}
    if not required.issubset(raw):
        raise ValueError("tuik_theme_catalog_node_required_field_missing")

    theme_id = _normalize_theme_id(raw["id"])
    if theme_id in seen_ids:
        raise ValueError("tuik_theme_catalog_duplicate_theme_id")
    seen_ids.add(theme_id)

    name = raw["name"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError("tuik_theme_catalog_theme_name_required")
    normalized_name = name.strip()
    if len(normalized_name) > 500:
        raise ValueError("tuik_theme_catalog_theme_name_too_long")

    children_raw = raw["children"]
    if not isinstance(children_raw, list):
        raise ValueError("tuik_theme_catalog_children_must_be_list")

    node_counter[0] += 1
    if node_counter[0] > MAX_THEME_NODES:
        raise ValueError("tuik_theme_catalog_node_limit_exceeded")

    children = tuple(
        _parse_node(
            child,
            depth=depth + 1,
            seen_ids=seen_ids,
            node_counter=node_counter,
        )
        for child in children_raw
    )
    icon = _optional_text(raw.get("icon"), field_name="icon")
    metadata_url_raw = _optional_text(raw.get("metadataUrl"), field_name="metadata_url")
    metadata_url = (
        _safe_catalog_url(metadata_url_raw, field_name="metadata_url")
        if metadata_url_raw is not None
        else None
    )
    return TUIKThemeNode(
        theme_id=theme_id,
        name=normalized_name,
        url=_optional_catalog_url(raw["url"], field_name="url"),
        icon=icon,
        metadata_url=metadata_url,
        children=children,
    )


def _count_nodes(nodes: tuple[TUIKThemeNode, ...]) -> int:
    return sum(1 + _count_nodes(node.children) for node in nodes)


def _canonical_fingerprint_payload(payload: dict[str, Any]) -> dict[str, Any]:
    fetched_at = payload["fetched_at"]
    if isinstance(fetched_at, str):
        fetched_at = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    if not isinstance(fetched_at, datetime) or fetched_at.tzinfo is None:
        raise ValueError("tuik_theme_catalog_fetched_at_timezone_required")
    themes = [
        (theme if isinstance(theme, TUIKThemeNode) else TUIKThemeNode.model_validate(theme)).model_dump(
            mode="json"
        )
        for theme in payload["themes"]
    ]
    return {
        "contract": payload["contract"],
        "provider_id": payload["provider_id"],
        "source_url": payload["source_url"],
        "fetched_at": fetched_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "provider_evidence_fingerprint": payload["provider_evidence_fingerprint"],
        "provider_body_sha256": payload["provider_body_sha256"],
        "bootstrap_body_sha256": payload["bootstrap_body_sha256"],
        "root_theme_count": payload["root_theme_count"],
        "total_node_count": payload["total_node_count"],
        "themes": themes,
        "evidence_refs": list(payload["evidence_refs"]),
        "context_only": payload["context_only"],
        "company_truth_granted": payload["company_truth_granted"],
        "causal_claim_proven": payload["causal_claim_proven"],
        "execution_authority_granted": payload["execution_authority_granted"],
    }


def _catalog_fingerprint(payload: dict[str, Any]) -> str:
    canonical = _canonical_fingerprint_payload(payload)
    material = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(material).hexdigest()


def _seal_catalog(payload: dict[str, Any]) -> TUIKThemeCatalogReceipt:
    canonical = _canonical_fingerprint_payload(payload)
    return TUIKThemeCatalogReceipt.model_validate(
        {**canonical, "fingerprint": _catalog_fingerprint(canonical)}
    )


def _verify_sealed(receipt: TUIKThemeCatalogReceipt) -> None:
    payload = receipt.model_dump(mode="python", exclude={"fingerprint"})
    expected = _catalog_fingerprint(payload)
    if receipt.fingerprint != expected:
        raise ValueError("tuik_theme_catalog_fingerprint_mismatch")


def parse_tuik_theme_catalog(
    provider_receipt: ProviderEvidenceReceipt,
) -> TUIKThemeCatalogReceipt:
    validated = ProviderEvidenceReceipt.model_validate(
        provider_receipt.model_dump(mode="python")
    )
    if validated.provider_id != TUIK_THEME_PROVIDER_ID:
        raise ValueError("tuik_theme_catalog_provider_receipt_mismatch")
    if validated.purpose is not RequestPurpose.ONE_SHOT_OBSERVATION:
        raise ValueError("tuik_theme_catalog_requires_one_shot_receipt")
    if validated.source_url != TUIK_THEME_API_URL:
        raise ValueError("tuik_theme_catalog_source_receipt_mismatch")
    if validated.media_type != "application/json":
        raise ValueError("tuik_theme_catalog_json_receipt_required")
    if validated.bootstrap_body_sha256 is None:
        raise ValueError("tuik_theme_catalog_session_bootstrap_required")

    try:
        document = json.loads(validated.raw_body)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("tuik_theme_catalog_invalid_json") from exc
    if not isinstance(document, dict):
        raise ValueError("tuik_theme_catalog_document_must_be_object")
    if not {"data", "isError", "message"}.issubset(document):
        raise ValueError("tuik_theme_catalog_envelope_contract_mismatch")
    if document["isError"] is not False:
        raise ValueError("tuik_theme_catalog_upstream_error")
    data = document["data"]
    if not isinstance(data, list) or not data:
        raise ValueError("tuik_theme_catalog_data_must_be_nonempty_list")

    seen_ids: set[str] = set()
    node_counter = [0]
    themes = tuple(
        _parse_node(
            item,
            depth=0,
            seen_ids=seen_ids,
            node_counter=node_counter,
        )
        for item in data
    )
    evidence_refs = tuple(
        dict.fromkeys(
            (
                *validated.provider_evidence_refs,
                *validated.adapter_evidence_refs,
                f"provider-receipt://{validated.evidence_fingerprint}",
            )
        )
    )
    return _seal_catalog(
        {
            "contract": TUIK_THEME_CATALOG_CONTRACT,
            "provider_id": TUIK_THEME_PROVIDER_ID,
            "source_url": validated.source_url,
            "fetched_at": validated.fetched_at,
            "provider_evidence_fingerprint": validated.evidence_fingerprint,
            "provider_body_sha256": validated.body_sha256,
            "bootstrap_body_sha256": validated.bootstrap_body_sha256,
            "root_theme_count": len(themes),
            "total_node_count": node_counter[0],
            "themes": themes,
            "evidence_refs": evidence_refs,
            "context_only": True,
            "company_truth_granted": False,
            "causal_claim_proven": False,
            "execution_authority_granted": False,
        }
    )


def build_tuik_theme_catalog_observation(
    catalog: TUIKThemeCatalogReceipt,
    *,
    tenant_id: str,
) -> ExternalContextObservation:
    validated = TUIKThemeCatalogReceipt.model_validate(catalog.model_dump(mode="python"))
    event = build_timeline_event(
        event_id=f"tuik:theme-catalog:{validated.fingerprint[:24]}",
        event_type="eay.external.tuik.theme_catalog.observed",
        event_kind=TimelineEventKind.EXTERNAL_CONTEXT,
        source_ref=validated.source_url,
        tenant_id=tenant_id,
        occurred_at=validated.fetched_at,
        observed_at=validated.fetched_at,
        data_ref=f"external-data://tuik/theme-catalog/{validated.fingerprint}",
        authority_class=TimelineAuthorityClass.VERIFIED_EXTERNAL,
        confidence=1.0,
        object_relations=(
            TimelineObjectRelation(
                object_ref="context:tuik-theme-catalog",
                object_kind=TimelineObjectKind.CONTEXT_SIGNAL,
                qualifier=TimelineObjectQualifier.CONTEXT,
            ),
        ),
        evidence_refs=tuple(
            dict.fromkeys(
                (*validated.evidence_refs, f"catalog-receipt://{validated.fingerprint}")
            )
        ),
    )
    summary = {
        "catalog_fingerprint": validated.fingerprint,
        "root_theme_count": validated.root_theme_count,
        "total_node_count": validated.total_node_count,
        "root_theme_ids": [theme.theme_id for theme in validated.themes],
        "root_theme_names": [theme.name for theme in validated.themes],
    }
    return build_external_context_observation(
        event=event,
        observation_id=f"observation:tuik-theme-catalog:{validated.fingerprint[:24]}",
        domain=ExternalContextDomain.MACROECONOMIC,
        claim_key="tuik_statistical_theme_catalog",
        claim_value=summary,
        geographic_scope=GeographicScope(
            level=GeographicScopeLevel.COUNTRY,
            country_code="TR",
        ),
    )


def read_tuik_theme_catalog_observation(
    *,
    tenant_id: str,
    transport: httpx.BaseTransport | None = None,
    now: datetime | None = None,
) -> TUIKThemeCatalogRead:
    plan = plan_provider_request(
        provider_id=TUIK_THEME_PROVIDER_ID,
        url=TUIK_THEME_API_URL,
        purpose=RequestPurpose.ONE_SHOT_OBSERVATION,
    )
    provider_receipt = execute_provider_request(
        plan,
        transport=transport,
        now=now,
    )
    catalog_receipt = parse_tuik_theme_catalog(provider_receipt)
    observation = build_tuik_theme_catalog_observation(
        catalog_receipt,
        tenant_id=tenant_id,
    )
    return TUIKThemeCatalogRead(
        provider_receipt=provider_receipt,
        catalog_receipt=catalog_receipt,
        observation=observation,
    )
