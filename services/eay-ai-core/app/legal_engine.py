from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, HttpUrl, model_validator


InstrumentType = Literal[
    "law",
    "regulation",
    "communique",
    "guideline",
    "decision",
    "other",
]
VerificationStatus = Literal["draft", "verified", "superseded", "repealed"]
RequirementOperator = Literal["<=", ">=", "==", "required", "prohibited"]
RequirementAuthority = Literal["legal", "company"]
ConflictStatus = Literal[
    "company_stricter",
    "aligned",
    "company_weaker_conflict",
    "incomparable",
    "missing_legal_baseline",
]


BINDING_SOURCE_HOSTS = {
    "resmigazete.gov.tr",
    "www.resmigazete.gov.tr",
    "mevzuat.gov.tr",
    "www.mevzuat.gov.tr",
}


class LegalInstrumentUpsert(BaseModel):
    id: str = Field(min_length=3, max_length=180)
    title: str = Field(min_length=3, max_length=600)
    instrument_type: InstrumentType
    jurisdiction: str = Field(default="TR", max_length=32)
    publication_date: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    transition_deadline: date | None = None
    official_gazette_number: str | None = Field(default=None, max_length=80)
    source_url: HttpUrl
    verification_status: VerificationStatus = "draft"
    amends: list[str] = Field(default_factory=list)
    repeals: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_dates_and_source(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        if self.transition_deadline and self.publication_date and self.transition_deadline < self.publication_date:
            raise ValueError("transition_deadline cannot be before publication_date")
        if self.verification_status == "verified":
            host = (urlparse(str(self.source_url)).hostname or "").lower()
            if host not in BINDING_SOURCE_HOSTS:
                raise ValueError(
                    "verified legal instruments must point to Resmî Gazete or Mevzuat Bilgi Sistemi"
                )
            if not self.publication_date:
                raise ValueError("verified legal instruments require publication_date")
            if not self.effective_from:
                raise ValueError("verified legal instruments require effective_from")
        return self


class LegalRequirementUpsert(BaseModel):
    id: str = Field(min_length=3, max_length=180)
    authority: RequirementAuthority
    source_id: str = Field(min_length=3, max_length=180)
    scope: str = Field(min_length=2, max_length=240)
    dimension: str = Field(min_length=2, max_length=160)
    operator: RequirementOperator
    numeric_value: float | None = None
    text_value: str | None = Field(default=None, max_length=500)
    unit: str | None = Field(default=None, max_length=80)
    effective_from: date | None = None
    effective_to: date | None = None
    citation: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_value(self):
        if self.operator in {"<=", ">=", "=="} and self.numeric_value is None and not self.text_value:
            raise ValueError("comparison requirements need numeric_value or text_value")
        if self.operator in {"required", "prohibited"} and self.numeric_value is not None:
            raise ValueError("required/prohibited requirements should not use numeric_value")
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        return self


class ConflictFinding(BaseModel):
    legal_requirement_id: str | None = None
    company_requirement_id: str
    status: ConflictStatus
    scope: str
    dimension: str
    summary: str
    legal_value: str | None = None
    company_value: str | None = None
    requires_human_review: bool = False


class LegalEngine:
    def __init__(self, db_path: Path):
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
                CREATE TABLE IF NOT EXISTS legal_instruments (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    jurisdiction TEXT NOT NULL,
                    publication_date TEXT,
                    effective_from TEXT,
                    effective_to TEXT,
                    transition_deadline TEXT,
                    official_gazette_number TEXT,
                    source_url TEXT NOT NULL,
                    verification_status TEXT NOT NULL,
                    amends_json TEXT NOT NULL,
                    repeals_json TEXT NOT NULL,
                    topics_json TEXT NOT NULL,
                    notes TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_legal_instruments_effective
                ON legal_instruments(effective_from, effective_to, verification_status);

                CREATE TABLE IF NOT EXISTS normalized_requirements (
                    id TEXT PRIMARY KEY,
                    authority TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    dimension TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    numeric_value REAL,
                    text_value TEXT,
                    unit TEXT,
                    effective_from TEXT,
                    effective_to TEXT,
                    citation TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_requirements_match
                ON normalized_requirements(authority, scope, dimension, effective_from, effective_to);
                """
            )

    def upsert_instrument(self, item: LegalInstrumentUpsert) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO legal_instruments(
                    id, title, instrument_type, jurisdiction, publication_date,
                    effective_from, effective_to, transition_deadline,
                    official_gazette_number, source_url, verification_status,
                    amends_json, repeals_json, topics_json, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    instrument_type=excluded.instrument_type,
                    jurisdiction=excluded.jurisdiction,
                    publication_date=excluded.publication_date,
                    effective_from=excluded.effective_from,
                    effective_to=excluded.effective_to,
                    transition_deadline=excluded.transition_deadline,
                    official_gazette_number=excluded.official_gazette_number,
                    source_url=excluded.source_url,
                    verification_status=excluded.verification_status,
                    amends_json=excluded.amends_json,
                    repeals_json=excluded.repeals_json,
                    topics_json=excluded.topics_json,
                    notes=excluded.notes,
                    updated_at=excluded.updated_at
                """,
                (
                    item.id,
                    item.title,
                    item.instrument_type,
                    item.jurisdiction,
                    item.publication_date.isoformat() if item.publication_date else None,
                    item.effective_from.isoformat() if item.effective_from else None,
                    item.effective_to.isoformat() if item.effective_to else None,
                    item.transition_deadline.isoformat() if item.transition_deadline else None,
                    item.official_gazette_number,
                    str(item.source_url),
                    item.verification_status,
                    json.dumps(item.amends, ensure_ascii=False),
                    json.dumps(item.repeals, ensure_ascii=False),
                    json.dumps(item.topics, ensure_ascii=False),
                    item.notes,
                    now,
                ),
            )

    def upsert_requirement(self, item: LegalRequirementUpsert) -> None:
        if item.authority == "legal":
            with self._connect() as conn:
                instrument = conn.execute(
                    "SELECT verification_status FROM legal_instruments WHERE id = ?",
                    (item.source_id,),
                ).fetchone()
            if instrument is None or instrument["verification_status"] != "verified":
                raise ValueError("legal requirements require a verified legal instrument source")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO normalized_requirements(
                    id, authority, source_id, scope, dimension, operator,
                    numeric_value, text_value, unit, effective_from, effective_to,
                    citation, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    authority=excluded.authority,
                    source_id=excluded.source_id,
                    scope=excluded.scope,
                    dimension=excluded.dimension,
                    operator=excluded.operator,
                    numeric_value=excluded.numeric_value,
                    text_value=excluded.text_value,
                    unit=excluded.unit,
                    effective_from=excluded.effective_from,
                    effective_to=excluded.effective_to,
                    citation=excluded.citation,
                    updated_at=excluded.updated_at
                """,
                (
                    item.id,
                    item.authority,
                    item.source_id,
                    item.scope,
                    item.dimension,
                    item.operator,
                    item.numeric_value,
                    item.text_value,
                    item.unit,
                    item.effective_from.isoformat() if item.effective_from else None,
                    item.effective_to.isoformat() if item.effective_to else None,
                    item.citation,
                    now,
                ),
            )

    def instruments_as_of(self, as_of: date) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM legal_instruments
                WHERE verification_status = 'verified'
                  AND (effective_from IS NULL OR effective_from <= ?)
                  AND (effective_to IS NULL OR effective_to >= ?)
                ORDER BY title
                """,
                (as_of.isoformat(), as_of.isoformat()),
            ).fetchall()
        return [dict(row) for row in rows]

    def _requirements(self, authority: RequirementAuthority, as_of: date) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT * FROM normalized_requirements
                WHERE authority = ?
                  AND (effective_from IS NULL OR effective_from <= ?)
                  AND (effective_to IS NULL OR effective_to >= ?)
                ORDER BY scope, dimension, id
                """,
                (authority, as_of.isoformat(), as_of.isoformat()),
            ).fetchall()

    @staticmethod
    def _fmt(row: sqlite3.Row) -> str:
        if row["operator"] in {"required", "prohibited"}:
            return row["operator"]
        value = row["numeric_value"] if row["numeric_value"] is not None else row["text_value"]
        unit = f" {row['unit']}" if row["unit"] else ""
        return f"{row['operator']} {value}{unit}"

    @staticmethod
    def _compare(legal: sqlite3.Row, company: sqlite3.Row) -> ConflictStatus:
        if legal["unit"] and company["unit"] and legal["unit"] != company["unit"]:
            return "incomparable"
        lop = legal["operator"]
        cop = company["operator"]
        if lop in {"required", "prohibited"} or cop in {"required", "prohibited"}:
            if lop == cop:
                return "aligned"
            return "company_weaker_conflict"
        if lop != cop:
            return "incomparable"
        lv = legal["numeric_value"]
        cv = company["numeric_value"]
        if lv is None or cv is None:
            if legal["text_value"] == company["text_value"] and legal["text_value"] is not None:
                return "aligned"
            return "incomparable"
        if lop == "<=":
            if cv < lv:
                return "company_stricter"
            if cv == lv:
                return "aligned"
            return "company_weaker_conflict"
        if lop == ">=":
            if cv > lv:
                return "company_stricter"
            if cv == lv:
                return "aligned"
            return "company_weaker_conflict"
        if lop == "==":
            return "aligned" if cv == lv else "company_weaker_conflict"
        return "incomparable"

    def compare_company_to_law(self, as_of: date) -> list[ConflictFinding]:
        legal_rows = self._requirements("legal", as_of)
        company_rows = self._requirements("company", as_of)
        legal_index: dict[tuple[str, str], list[sqlite3.Row]] = {}
        for row in legal_rows:
            legal_index.setdefault((row["scope"], row["dimension"]), []).append(row)

        findings: list[ConflictFinding] = []
        for company in company_rows:
            matches = legal_index.get((company["scope"], company["dimension"]), [])
            if not matches:
                findings.append(
                    ConflictFinding(
                        company_requirement_id=company["id"],
                        status="missing_legal_baseline",
                        scope=company["scope"],
                        dimension=company["dimension"],
                        summary="Şirket standardı mevcut ancak aynı kapsam ve boyutta doğrulanmış yasal baz bulunamadı.",
                        company_value=self._fmt(company),
                        requires_human_review=False,
                    )
                )
                continue
            for legal in matches:
                status = self._compare(legal, company)
                summaries = {
                    "company_stricter": "Şirket standardı doğrulanmış yasal asgari gereklilikten daha sıkı.",
                    "aligned": "Şirket standardı doğrulanmış yasal gereklilik ile uyumlu.",
                    "company_weaker_conflict": "Şirket standardı doğrulanmış yasal gereklilikten daha zayıf veya onunla çelişiyor.",
                    "incomparable": "Kurallar aynı boyutta olsa da operatör/değer/birim farkı nedeniyle otomatik kıyaslanamadı.",
                }
                findings.append(
                    ConflictFinding(
                        legal_requirement_id=legal["id"],
                        company_requirement_id=company["id"],
                        status=status,
                        scope=company["scope"],
                        dimension=company["dimension"],
                        summary=summaries[status],
                        legal_value=self._fmt(legal),
                        company_value=self._fmt(company),
                        requires_human_review=status in {"company_weaker_conflict", "incomparable"},
                    )
                )
        return findings
