from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from .legal_engine import ConflictFinding, LegalEngine
from .legal_temporal import LegalTemporalResolver


class TemporalResolutionBlocked(ValueError):
    def __init__(self, blockers: tuple[str, ...], resolution_fingerprint: str):
        self.blockers = blockers
        self.resolution_fingerprint = resolution_fingerprint
        super().__init__("legal_temporal_resolution_blocked:" + ",".join(blockers))


class TemporalConflictEngine:
    """Compare company rules only against legal requirements active in temporal graph."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.resolver = LegalTemporalResolver(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _legal_requirements(self, as_of: date, active_source_ids: tuple[str, ...]) -> list[sqlite3.Row]:
        if not active_source_ids:
            return []
        placeholders = ",".join("?" for _ in active_source_ids)
        params: list[object] = [*active_source_ids, as_of.isoformat(), as_of.isoformat()]
        with self._connect() as conn:
            return conn.execute(
                f"""
                SELECT * FROM normalized_requirements
                WHERE authority='legal'
                  AND source_id IN ({placeholders})
                  AND (effective_from IS NULL OR effective_from <= ?)
                  AND (effective_to IS NULL OR effective_to >= ?)
                ORDER BY scope, dimension, id
                """,
                params,
            ).fetchall()

    def _company_requirements(self, as_of: date) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT * FROM normalized_requirements
                WHERE authority='company'
                  AND (effective_from IS NULL OR effective_from <= ?)
                  AND (effective_to IS NULL OR effective_to >= ?)
                ORDER BY scope, dimension, id
                """,
                (as_of.isoformat(), as_of.isoformat()),
            ).fetchall()

    def compare_company_to_law(self, as_of: date) -> tuple[list[ConflictFinding], str]:
        temporal = self.resolver.resolve(as_of)
        if not temporal.resolved:
            raise TemporalResolutionBlocked(temporal.blockers, temporal.resolution_fingerprint)

        legal_rows = self._legal_requirements(as_of, temporal.active_instrument_ids)
        company_rows = self._company_requirements(as_of)
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
                        summary=(
                            "Şirket standardı mevcut ancak istenen tarihte temporal graph tarafından "
                            "aktif kabul edilen aynı kapsam ve boyutta doğrulanmış yasal baz bulunamadı."
                        ),
                        company_value=LegalEngine._fmt(company),
                        requires_human_review=False,
                    )
                )
                continue
            for legal in matches:
                status = LegalEngine._compare(legal, company)
                summaries = {
                    "company_stricter": "Şirket standardı o tarihte aktif doğrulanmış yasal asgari gereklilikten daha sıkı.",
                    "aligned": "Şirket standardı o tarihte aktif doğrulanmış yasal gereklilik ile uyumlu.",
                    "company_weaker_conflict": "Şirket standardı o tarihte aktif doğrulanmış yasal gereklilikten daha zayıf veya onunla çelişiyor.",
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
                        legal_value=LegalEngine._fmt(legal),
                        company_value=LegalEngine._fmt(company),
                        requires_human_review=status in {"company_weaker_conflict", "incomparable"},
                    )
                )
        return findings, temporal.resolution_fingerprint
