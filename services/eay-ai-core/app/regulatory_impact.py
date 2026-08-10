from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class RegulatoryImpactGrounding:
    instrument_id: str
    source_url: str
    citation_ids: tuple[str, ...]
    topics: tuple[str, ...]


_GENERIC_TOPICS = {
    "gıda",
    "gida",
    "ürün",
    "urun",
    "mevzuat",
    "yönetmelik",
    "yonetmelik",
    "tebliğ",
    "teblig",
    "türkiye",
    "turkiye",
}


def _clean_topic(value: str) -> str | None:
    topic = " ".join(value.strip().split())
    if len(topic) < 2 or len(topic) > 120:
        return None
    if topic.casefold() in _GENERIC_TOPICS:
        return None
    return topic


def resolve_verified_regulatory_impact(
    db_path: Path,
    *,
    instrument_id: str,
    as_of: date,
    max_topics: int = 12,
) -> RegulatoryImpactGrounding:
    """Resolve catalog-impact search terms only from verified, effective legal evidence.

    Watcher candidates, draft instruments, expired/future instruments and caller-authored
    free-text never become query terms. The returned topics are deterministic and traceable
    to the reviewed instrument or its normalized legal requirements.
    """

    if not db_path.exists():
        raise ValueError("legal_evidence_store_not_found")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        instrument = conn.execute(
            """
            SELECT id, source_url, topics_json
            FROM legal_instruments
            WHERE id = ?
              AND verification_status = 'verified'
              AND (effective_from IS NULL OR effective_from <= ?)
              AND (effective_to IS NULL OR effective_to >= ?)
            """,
            (instrument_id, as_of.isoformat(), as_of.isoformat()),
        ).fetchone()
        if instrument is None:
            raise ValueError("verified_effective_legal_instrument_required")

        requirements = conn.execute(
            """
            SELECT id, scope, dimension, text_value
            FROM normalized_requirements
            WHERE authority = 'legal'
              AND source_id = ?
              AND (effective_from IS NULL OR effective_from <= ?)
              AND (effective_to IS NULL OR effective_to >= ?)
            ORDER BY id
            """,
            (instrument_id, as_of.isoformat(), as_of.isoformat()),
        ).fetchall()
    finally:
        conn.close()

    candidates: list[str] = []
    try:
        reviewed_topics = json.loads(instrument["topics_json"] or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_reviewed_instrument_topics") from exc
    if not isinstance(reviewed_topics, list):
        raise ValueError("invalid_reviewed_instrument_topics")

    candidates.extend(str(value) for value in reviewed_topics if isinstance(value, str))
    citation_ids: list[str] = []
    for row in requirements:
        citation_ids.append(row["id"])
        candidates.extend(
            value
            for value in (row["scope"], row["dimension"], row["text_value"])
            if isinstance(value, str) and value.strip()
        )

    topics: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = _clean_topic(candidate)
        if cleaned is None:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        topics.append(cleaned)
        if len(topics) >= max_topics:
            break

    if not topics:
        raise ValueError("verified_legal_impact_topics_required")

    return RegulatoryImpactGrounding(
        instrument_id=instrument["id"],
        source_url=instrument["source_url"],
        citation_ids=tuple(citation_ids),
        topics=tuple(topics),
    )
