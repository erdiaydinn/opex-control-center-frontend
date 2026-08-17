"""Multi-source agenda clustering for EAY Jarvis.

Raw headlines are not independent evidence. This module groups near-duplicate
articles into event clusters, counts independent source domains once, and keeps
agenda material context-only. It performs no web fetching; provider/search
adapters must supply normalized public items with provenance.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from enum import Enum
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

AGENDA_INTELLIGENCE_CONTRACT = "eay-agenda-intelligence-v1"


class AgendaStatus(str, Enum):
    UNCORROBORATED = "uncorroborated"
    CORROBORATED = "corroborated"
    HIGH_CONFIDENCE = "high_confidence"


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _norm_text(value: str) -> str:
    value = value.casefold().replace("ı", "i")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9çğıöşü\s-]", " ", value)
    return " ".join(value.split())


def _tokens(value: str) -> set[str]:
    return {token for token in _norm_text(value).split() if len(token) >= 3}


def _jaccard(left: str, right: str) -> float:
    a = _tokens(left)
    b = _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _domain(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("agenda_source_https_required")
    return parsed.hostname.casefold().rstrip(".")


def _norm_locations(values: tuple[str, ...]) -> set[str]:
    return {_norm_text(value) for value in values if value.strip()}


class AgendaItem(BaseModel):
    item_id: str = Field(min_length=1, max_length=180)
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(default="", max_length=3000)
    published_at: datetime
    fetched_at: datetime
    source_name: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=1, max_length=2048)
    source_confidence: float = Field(ge=0.0, le=1.0)
    locations: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    official: bool = False
    context_only: bool = True

    @model_validator(mode="after")
    def validate_item(self) -> "AgendaItem":
        if not _aware(self.published_at) or not _aware(self.fetched_at):
            raise ValueError("agenda_item_timezone_required")
        if self.fetched_at < self.published_at:
            raise ValueError("agenda_item_fetch_before_publish")
        if not self.context_only:
            raise ValueError("agenda_item_must_remain_context_only")
        _domain(self.source_url)
        return self

    @property
    def source_domain(self) -> str:
        return _domain(self.source_url)

    @property
    def canonical_text(self) -> str:
        return f"{self.title} {self.summary}".strip()


class AgendaCluster(BaseModel):
    contract: str = AGENDA_INTELLIGENCE_CONTRACT
    cluster_id: str
    representative_item_id: str
    item_ids: tuple[str, ...]
    source_domains: tuple[str, ...]
    independent_source_count: int = Field(ge=1)
    official_source_present: bool
    status: AgendaStatus
    confidence: float = Field(ge=0.0, le=1.0)
    locations: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    context_only: bool = True
    warnings: tuple[str, ...] = ()


class AgendaDigest(BaseModel):
    contract: str = AGENDA_INTELLIGENCE_CONTRACT
    clusters: tuple[AgendaCluster, ...]
    duplicate_item_ids: tuple[str, ...] = ()
    total_items: int = Field(ge=0)
    corroborated_clusters: int = Field(ge=0)


def _same_event(left: AgendaItem, right: AgendaItem) -> bool:
    if abs(left.published_at - right.published_at) > timedelta(hours=18):
        return False
    similarity = _jaccard(left.canonical_text, right.canonical_text)
    if similarity < 0.42:
        return False

    left_locations = _norm_locations(left.locations)
    right_locations = _norm_locations(right.locations)
    if left_locations and right_locations and not (left_locations & right_locations):
        return False

    left_topics = {_norm_text(value) for value in left.topics if value.strip()}
    right_topics = {_norm_text(value) for value in right.topics if value.strip()}
    if left_topics and right_topics and not (left_topics & right_topics):
        return False
    return True


def _cluster_confidence(items: list[AgendaItem], independent_domains: int) -> float:
    best_by_domain: dict[str, float] = {}
    for item in items:
        best_by_domain[item.source_domain] = max(
            best_by_domain.get(item.source_domain, 0.0), item.source_confidence
        )
    mean_quality = sum(best_by_domain.values()) / len(best_by_domain)
    diversity = min(independent_domains / 3.0, 1.0)
    official_bonus = 0.08 if any(item.official for item in items) else 0.0
    return round(min((0.70 * mean_quality) + (0.30 * diversity) + official_bonus, 0.98), 6)


def build_agenda_digest(
    items: list[AgendaItem] | tuple[AgendaItem, ...],
) -> AgendaDigest:
    clusters: list[list[AgendaItem]] = []
    duplicate_ids: list[str] = []

    for item in sorted(items, key=lambda value: (value.published_at, value.item_id)):
        placed = False
        for cluster in clusters:
            if any(_same_event(item, existing) for existing in cluster):
                if any(
                    existing.source_domain == item.source_domain
                    and _jaccard(existing.canonical_text, item.canonical_text) >= 0.80
                    for existing in cluster
                ):
                    duplicate_ids.append(item.item_id)
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])

    output: list[AgendaCluster] = []
    for index, cluster in enumerate(clusters, start=1):
        representative = max(
            cluster,
            key=lambda item: (item.official, item.source_confidence, item.published_at),
        )
        domains = tuple(sorted({item.source_domain for item in cluster}))
        independent_count = len(domains)
        official_present = any(item.official for item in cluster)
        confidence = _cluster_confidence(cluster, independent_count)
        if independent_count >= 3 and confidence >= 0.80:
            status = AgendaStatus.HIGH_CONFIDENCE
        elif independent_count >= 2:
            status = AgendaStatus.CORROBORATED
        else:
            status = AgendaStatus.UNCORROBORATED

        warnings: list[str] = []
        if status is AgendaStatus.UNCORROBORATED:
            warnings.append("agenda_independent_corroboration_missing")
        if len(cluster) > independent_count:
            warnings.append("syndicated_or_same_domain_duplicates_present")

        locations = tuple(
            sorted({value for item in cluster for value in item.locations if value.strip()})
        )
        topics = tuple(
            sorted({value for item in cluster for value in item.topics if value.strip()})
        )
        output.append(
            AgendaCluster(
                cluster_id=f"agenda-{index}",
                representative_item_id=representative.item_id,
                item_ids=tuple(item.item_id for item in cluster),
                source_domains=domains,
                independent_source_count=independent_count,
                official_source_present=official_present,
                status=status,
                confidence=confidence,
                locations=locations,
                topics=topics,
                warnings=tuple(warnings),
            )
        )

    output.sort(key=lambda item: (-item.confidence, item.cluster_id))
    return AgendaDigest(
        clusters=tuple(output),
        duplicate_item_ids=tuple(sorted(set(duplicate_ids))),
        total_items=len(items),
        corroborated_clusters=sum(
            cluster.status in {AgendaStatus.CORROBORATED, AgendaStatus.HIGH_CONFIDENCE}
            for cluster in output
        ),
    )
