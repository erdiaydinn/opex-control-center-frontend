from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl

from .regulatory_atomic import AtomicRegulatoryPersistence
from .regulatory_lineage import RegulatoryLineageStore


SourceRole = Literal[
    "discovery",
    "official_registry",
    "binding_publication_index",
    "guidance",
]
ChangeStatus = Literal["pending", "acknowledged", "rejected"]

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
SOURCES_PATH = Path(
    os.getenv("EAY_REGULATORY_SOURCES_PATH", "./config/regulatory_sources.json")
)
MAX_FETCH_BYTES = int(os.getenv("EAY_REGULATORY_MAX_FETCH_BYTES", "3000000"))
USER_AGENT = os.getenv(
    "EAY_REGULATORY_USER_AGENT",
    "EAY-Regulatory-Watcher/0.1 (+local compliance monitoring)",
)

# Regulatory watcher never accepts arbitrary user URLs. Even the configured source
# registry is restricted to known official domains to reduce SSRF/supply-chain risk.
ALLOWED_HOST_SUFFIXES = (
    "tarimorman.gov.tr",
    "resmigazete.gov.tr",
    "kaysis.gov.tr",
)


class SourceDefinition(BaseModel):
    id: str = Field(min_length=3, max_length=120)
    name: str = Field(min_length=3, max_length=240)
    url: HttpUrl
    role: SourceRole
    jurisdiction: str = Field(default="TR", max_length=32)
    enabled: bool = True
    topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    notes: str | None = None


class SourceCheckResult(BaseModel):
    source_id: str
    source_name: str
    state: Literal[
        "baseline",
        "unchanged",
        "changed_relevant",
        "changed_irrelevant",
        "error",
    ]
    fetched_at: datetime
    content_hash: str | None = None
    previous_hash: str | None = None
    change_id: str | None = None
    snapshot_id: str | None = None
    snapshot_chain_hash: str | None = None
    change_chain_hash: str | None = None
    authority_level: str | None = None
    authority_fingerprint: str | None = None
    relevance_hits: list[str] = Field(default_factory=list)
    error: str | None = None


class RegulatoryChange(BaseModel):
    id: str
    source_id: str
    source_name: str
    source_url: str
    source_role: SourceRole
    old_hash: str
    new_hash: str
    diff_excerpt: str
    relevance_hits: list[str]
    status: ChangeStatus
    requires_binding_verification: bool
    authority_assessment: dict[str, object] | None = None
    authority_fingerprint: str | None = None
    lineage_chain_hash: str | None = None
    detected_at: datetime


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "\n".join(self.parts)


def _normalize_text(raw: str, content_type: str = "text/html") -> str:
    text = raw
    if "html" in content_type.lower() or "<html" in raw[:1000].lower():
        parser = _VisibleTextParser()
        parser.feed(raw)
        text = parser.text()

    text = text.replace("\xa0", " ")
    # Dynamic counters create noisy false positives on Ministry pages.
    text = re.sub(r"Gösterim\s+Sayısı\s*:?\s*\d+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+\s+(?:gösterim|views?)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_diff(old: str, new: str, max_chars: int = 18000) -> str:
    diff = "\n".join(
        difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile="previous",
            tofile="current",
            lineterm="",
            n=2,
        )
    )
    if len(diff) > max_chars:
        return diff[:max_chars] + "\n... [diff truncated]"
    return diff


def _host_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_HOST_SUFFIXES)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


class RegulatoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS regulatory_snapshots (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    content_text TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_regulatory_snapshots_source_time
                ON regulatory_snapshots(source_id, fetched_at DESC);

                CREATE TABLE IF NOT EXISTS regulatory_changes (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    source_role TEXT NOT NULL,
                    old_hash TEXT NOT NULL,
                    new_hash TEXT NOT NULL,
                    diff_excerpt TEXT NOT NULL,
                    relevance_hits_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    requires_binding_verification INTEGER NOT NULL DEFAULT 1,
                    authority_assessment_json TEXT,
                    authority_fingerprint TEXT,
                    lineage_chain_hash TEXT,
                    detected_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_regulatory_changes_status_time
                ON regulatory_changes(status, detected_at DESC);
                """
            )
            # Additive migration for databases created by earlier EAY AI Core builds.
            _ensure_column(conn, "regulatory_changes", "authority_assessment_json", "TEXT")
            _ensure_column(conn, "regulatory_changes", "authority_fingerprint", "TEXT")
            _ensure_column(conn, "regulatory_changes", "lineage_chain_hash", "TEXT")

    def latest_snapshot(self, source_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT * FROM regulatory_snapshots
                WHERE source_id = ?
                ORDER BY fetched_at DESC, rowid DESC
                LIMIT 1
                """,
                (source_id,),
            ).fetchone()

    # Legacy write helpers remain for migration/backfill callers. The live watcher
    # no longer uses them; process_text routes through AtomicRegulatoryPersistence.
    def save_snapshot(self, source_id: str, content_hash: str, content_text: str) -> tuple[str, str]:
        snapshot_id = str(uuid.uuid4())
        fetched_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO regulatory_snapshots (
                    id, source_id, content_hash, content_text, fetched_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (snapshot_id, source_id, content_hash, content_text, fetched_at),
            )
        return snapshot_id, fetched_at

    def save_change(
        self,
        *,
        source: SourceDefinition,
        old_hash: str,
        new_hash: str,
        diff_excerpt: str,
        relevance_hits: list[str],
        authority_assessment: dict[str, object],
    ) -> tuple[str, str]:
        change_id = str(uuid.uuid4())
        detected_at = datetime.now(timezone.utc).isoformat()
        authority_fingerprint = str(authority_assessment.get("assessment_fingerprint") or "")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO regulatory_changes (
                    id, source_id, source_name, source_url, source_role,
                    old_hash, new_hash, diff_excerpt, relevance_hits_json,
                    status, requires_binding_verification, authority_assessment_json,
                    authority_fingerprint, lineage_chain_hash, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 1, ?, ?, NULL, ?)
                """,
                (
                    change_id,
                    source.id,
                    source.name,
                    str(source.url),
                    source.role,
                    old_hash,
                    new_hash,
                    diff_excerpt,
                    json.dumps(relevance_hits, ensure_ascii=False),
                    json.dumps(authority_assessment, ensure_ascii=False, sort_keys=True),
                    authority_fingerprint,
                    detected_at,
                ),
            )
        return change_id, detected_at

    def set_change_lineage_hash(self, change_id: str, chain_hash: str) -> None:
        with self._connect() as conn:
            count = conn.execute(
                "UPDATE regulatory_changes SET lineage_chain_hash = ? WHERE id = ? AND lineage_chain_hash IS NULL",
                (chain_hash, change_id),
            ).rowcount
        if count == 0:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT lineage_chain_hash FROM regulatory_changes WHERE id = ?",
                    (change_id,),
                ).fetchone()
            if row is None:
                raise KeyError(change_id)
            if row["lineage_chain_hash"] != chain_hash:
                raise ValueError("immutable_regulatory_change_lineage_conflict")

    def list_changes(self, status: ChangeStatus | None, limit: int) -> list[RegulatoryChange]:
        where = "WHERE status = ?" if status else ""
        params: tuple[object, ...] = (status, limit) if status else (limit,)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM regulatory_changes
                {where}
                ORDER BY detected_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [
            RegulatoryChange(
                id=row["id"],
                source_id=row["source_id"],
                source_name=row["source_name"],
                source_url=row["source_url"],
                source_role=row["source_role"],
                old_hash=row["old_hash"],
                new_hash=row["new_hash"],
                diff_excerpt=row["diff_excerpt"],
                relevance_hits=json.loads(row["relevance_hits_json"]),
                status=row["status"],
                requires_binding_verification=bool(row["requires_binding_verification"]),
                authority_assessment=(
                    json.loads(row["authority_assessment_json"])
                    if row["authority_assessment_json"]
                    else None
                ),
                authority_fingerprint=row["authority_fingerprint"],
                lineage_chain_hash=row["lineage_chain_hash"],
                detected_at=datetime.fromisoformat(row["detected_at"]),
            )
            for row in rows
        ]

    def decide_change(self, change_id: str, status: Literal["acknowledged", "rejected"]) -> None:
        with self._connect() as conn:
            count = conn.execute(
                "UPDATE regulatory_changes SET status = ? WHERE id = ?",
                (status, change_id),
            ).rowcount
        if count == 0:
            raise KeyError(change_id)


class RegulatoryWatcher:
    def __init__(self, db_path: Path = DB_PATH, sources_path: Path = SOURCES_PATH) -> None:
        self.store = RegulatoryStore(db_path)
        self.lineage = RegulatoryLineageStore(db_path)
        self.atomic = AtomicRegulatoryPersistence(db_path)
        self.sources_path = sources_path

    def sources(self) -> list[SourceDefinition]:
        if not self.sources_path.exists():
            raise FileNotFoundError(f"Regulatory source registry not found: {self.sources_path}")
        payload = json.loads(self.sources_path.read_text(encoding="utf-8"))
        sources = [SourceDefinition.model_validate(item) for item in payload.get("sources", [])]
        for source in sources:
            if not _host_allowed(str(source.url)):
                raise ValueError(f"Unapproved regulatory source host: {source.url}")
        return sources

    def source_by_id(self, source_id: str) -> SourceDefinition:
        for source in self.sources():
            if source.id == source_id:
                return source
        raise KeyError(source_id)

    @staticmethod
    def _relevance_hits(source: SourceDefinition, diff_text: str) -> list[str]:
        lowered = diff_text.casefold()
        hits = []
        for keyword in source.keywords:
            if keyword.casefold() in lowered:
                hits.append(keyword)
        return sorted(set(hits), key=str.casefold)

    def process_text(
        self,
        source: SourceDefinition,
        raw_text: str,
        *,
        content_type: str = "text/html",
    ) -> SourceCheckResult:
        fetched_at = datetime.now(timezone.utc)
        normalized = _normalize_text(raw_text, content_type)
        if len(normalized) < 80:
            return SourceCheckResult(
                source_id=source.id,
                source_name=source.name,
                state="error",
                fetched_at=fetched_at,
                error="Source returned too little visible text to establish a reliable snapshot.",
            )

        content_hash = _hash_text(normalized)
        previous = self.store.latest_snapshot(source.id)
        previous_hash = previous["content_hash"] if previous is not None else None

        if previous_hash == content_hash:
            return SourceCheckResult(
                source_id=source.id,
                source_name=source.name,
                state="unchanged",
                fetched_at=fetched_at,
                content_hash=content_hash,
                previous_hash=previous_hash,
            )

        if previous is None:
            persisted = self.atomic.persist_observation(
                source_id=source.id,
                source_name=source.name,
                source_url=str(source.url),
                source_role=source.role,
                jurisdiction=source.jurisdiction,
                content_hash=content_hash,
                content_text=normalized,
                expected_previous_hash=None,
            )
            return SourceCheckResult(
                source_id=source.id,
                source_name=source.name,
                state="baseline",
                fetched_at=fetched_at,
                content_hash=content_hash,
                snapshot_id=persisted.snapshot_id,
                snapshot_chain_hash=persisted.snapshot_chain_hash,
            )

        diff_text = _safe_diff(previous["content_text"], normalized)
        relevance_hits = self._relevance_hits(source, diff_text)

        if source.keywords and not relevance_hits:
            persisted = self.atomic.persist_observation(
                source_id=source.id,
                source_name=source.name,
                source_url=str(source.url),
                source_role=source.role,
                jurisdiction=source.jurisdiction,
                content_hash=content_hash,
                content_text=normalized,
                expected_previous_hash=previous_hash,
            )
            return SourceCheckResult(
                source_id=source.id,
                source_name=source.name,
                state="changed_irrelevant",
                fetched_at=fetched_at,
                content_hash=content_hash,
                previous_hash=previous_hash,
                snapshot_id=persisted.snapshot_id,
                snapshot_chain_hash=persisted.snapshot_chain_hash,
            )

        # Local import avoids a module cycle because regulatory_authority uses the
        # SourceDefinition contract declared above.
        from .regulatory_authority import assess_regulatory_authority, assessment_dict

        authority = assess_regulatory_authority(
            source,
            document_url=str(source.url),
            text=normalized,
        )
        authority_payload = assessment_dict(authority)
        persisted = self.atomic.persist_observation(
            source_id=source.id,
            source_name=source.name,
            source_url=str(source.url),
            source_role=source.role,
            jurisdiction=source.jurisdiction,
            content_hash=content_hash,
            content_text=normalized,
            expected_previous_hash=previous_hash,
            diff_excerpt=diff_text,
            relevance_hits=relevance_hits,
            authority_assessment=authority_payload,
        )
        return SourceCheckResult(
            source_id=source.id,
            source_name=source.name,
            state="changed_relevant",
            fetched_at=fetched_at,
            content_hash=content_hash,
            previous_hash=previous_hash,
            change_id=persisted.change_id,
            snapshot_id=persisted.snapshot_id,
            snapshot_chain_hash=persisted.snapshot_chain_hash,
            change_chain_hash=persisted.change_chain_hash,
            authority_level=authority.authority_level,
            authority_fingerprint=authority.assessment_fingerprint,
            relevance_hits=relevance_hits,
        )

    async def check_source(self, source: SourceDefinition) -> SourceCheckResult:
        fetched_at = datetime.now(timezone.utc)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(20.0, connect=8.0),
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = await client.get(str(source.url))
                response.raise_for_status()
                content = response.content
                if len(content) > MAX_FETCH_BYTES:
                    raise ValueError(
                        f"Response exceeds EAY_REGULATORY_MAX_FETCH_BYTES ({MAX_FETCH_BYTES})."
                    )
                final_url = str(response.url)
                if not _host_allowed(final_url):
                    raise ValueError(f"Redirected to an unapproved host: {final_url}")
                raw_text = response.text
                content_type = response.headers.get("content-type", "text/html")
        except Exception as exc:
            return SourceCheckResult(
                source_id=source.id,
                source_name=source.name,
                state="error",
                fetched_at=fetched_at,
                error=str(exc)[:800],
            )
        return self.process_text(source, raw_text, content_type=content_type)

    async def check(self, source_id: str | None = None) -> list[SourceCheckResult]:
        if source_id:
            sources = [self.source_by_id(source_id)]
        else:
            sources = [source for source in self.sources() if source.enabled]
        results: list[SourceCheckResult] = []
        # Deliberately sequential: these are government websites, not a target for
        # aggressive concurrent polling.
        for source in sources:
            results.append(await self.check_source(source))
        return results


watcher = RegulatoryWatcher()
router = APIRouter(prefix="/v1/regulatory", tags=["regulatory"])


@router.get("/sources", response_model=list[SourceDefinition])
def list_sources():
    try:
        return watcher.sources()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/check", response_model=list[SourceCheckResult])
async def check_sources(source_id: str | None = Query(default=None, max_length=120)):
    try:
        return await watcher.check(source_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Regulatory source not found") from exc
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/changes", response_model=list[RegulatoryChange])
def list_changes(
    status: ChangeStatus | None = Query(default="pending"),
    limit: int = Query(default=100, ge=1, le=500),
):
    return watcher.store.list_changes(status, limit)


@router.get("/lineage/{source_id}")
def verify_source_lineage(source_id: str):
    return watcher.lineage.verify_source_chain(source_id)


@router.post("/changes/{change_id}/{decision}")
def decide_change(change_id: str, decision: str):
    if decision not in {"acknowledge", "reject"}:
        raise HTTPException(status_code=400, detail="Use acknowledge or reject")
    try:
        watcher.store.decide_change(
            change_id,
            "acknowledged" if decision == "acknowledge" else "rejected",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Regulatory change not found") from exc
    return {
        "ok": True,
        "status": "acknowledged" if decision == "acknowledge" else "rejected",
        "note": (
            "Acknowledgement is not legal promotion. Binding knowledge still requires "
            "verification of the exact legal instrument, effective date and source text."
        ),
    }
