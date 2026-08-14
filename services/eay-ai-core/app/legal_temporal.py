from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .legal_relations import LegalRelationStore


@dataclass(frozen=True)
class TemporalRelationEvent:
    relation_id: str
    source_instrument_id: str
    relation_type: str
    target_instrument_id: str
    effective_from: str
    relation_fingerprint: str


@dataclass(frozen=True)
class LegalTemporalState:
    as_of: str
    active_instrument_ids: tuple[str, ...]
    inactive_instrument_ids: tuple[str, ...]
    applied_relation_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    resolution_fingerprint: str

    @property
    def resolved(self) -> bool:
        return not self.blockers

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["resolved"] = self.resolved
        return payload


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LegalTemporalResolver:
    """Resolve historically active legal instruments from reviewed temporal evidence.

    Approved legal relations are treated as legal events whose effective date is the
    verified source instrument's `effective_from`. This deliberately avoids inventing
    a second relation date that could drift away from the exact-instrument verification.

    `repeals` and `supersedes` deactivate their target on and after that event date.
    `amends` records a version relationship but does not deactivate the target by
    itself. The resolver never mutates legal records and fails closed on ambiguous or
    incomplete graph evidence.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _is_in_own_window(row: sqlite3.Row, as_of: date) -> bool:
        effective_from = row["effective_from"]
        effective_to = row["effective_to"]
        if effective_from is None:
            return False
        if effective_from > as_of.isoformat():
            return False
        if effective_to is not None and effective_to < as_of.isoformat():
            return False
        return True

    @staticmethod
    def _detect_cycle(events: list[TemporalRelationEvent]) -> bool:
        adjacency: dict[str, set[str]] = {}
        for event in events:
            adjacency.setdefault(event.source_instrument_id, set()).add(event.target_instrument_id)

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            for target in adjacency.get(node, set()):
                if visit(target):
                    return True
            visiting.remove(node)
            visited.add(node)
            return False

        return any(visit(node) for node in tuple(adjacency))

    def resolve(self, as_of: date) -> LegalTemporalState:
        blockers: list[str] = []
        with self._connect() as conn:
            LegalRelationStore.ensure_schema(conn)
            instruments = conn.execute(
                """
                SELECT id, verification_status, publication_date, effective_from, effective_to
                FROM legal_instruments
                WHERE verification_status IN ('verified', 'superseded', 'repealed')
                ORDER BY id ASC
                """
            ).fetchall()
            relations = conn.execute(
                """
                SELECT id, source_instrument_id, relation_type, target_instrument_id,
                       relation_fingerprint
                FROM legal_instrument_relations
                WHERE status='approved'
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()

        instrument_index = {row["id"]: row for row in instruments}
        candidate_active: set[str] = set()
        for row in instruments:
            if row["effective_from"] is None:
                blockers.append(f"missing_effective_from:{row['id']}")
                continue
            if row["publication_date"] is None:
                blockers.append(f"missing_publication_date:{row['id']}")
                continue
            if row["publication_date"] > row["effective_from"]:
                blockers.append(f"publication_after_effective_from:{row['id']}")
                continue
            if self._is_in_own_window(row, as_of):
                candidate_active.add(row["id"])

        events: list[TemporalRelationEvent] = []
        for relation in relations:
            source = instrument_index.get(relation["source_instrument_id"])
            target = instrument_index.get(relation["target_instrument_id"])
            if source is None:
                blockers.append(f"relation_source_not_temporally_verifiable:{relation['id']}")
                continue
            if target is None:
                blockers.append(f"relation_target_not_temporally_verifiable:{relation['id']}")
                continue
            source_effective = source["effective_from"]
            if source_effective is None:
                blockers.append(f"relation_missing_effective_from:{relation['id']}")
                continue
            if source_effective > as_of.isoformat():
                continue
            events.append(
                TemporalRelationEvent(
                    relation_id=relation["id"],
                    source_instrument_id=relation["source_instrument_id"],
                    relation_type=relation["relation_type"],
                    target_instrument_id=relation["target_instrument_id"],
                    effective_from=source_effective,
                    relation_fingerprint=relation["relation_fingerprint"],
                )
            )

        if self._detect_cycle(events):
            blockers.append("approved_legal_relation_cycle")

        superseders: dict[str, set[str]] = {}
        for event in events:
            if event.relation_type == "supersedes":
                superseders.setdefault(event.target_instrument_id, set()).add(event.source_instrument_id)
        for target, sources in superseders.items():
            if len(sources) > 1:
                blockers.append(
                    "ambiguous_multiple_superseders:"
                    + target
                    + ":"
                    + ",".join(sorted(sources))
                )

        inactive: set[str] = set()
        if not blockers:
            for event in events:
                if event.relation_type in {"repeals", "supersedes"}:
                    inactive.add(event.target_instrument_id)

        active = candidate_active - inactive if not blockers else set()
        payload = {
            "as_of": as_of.isoformat(),
            "candidate_active": sorted(candidate_active),
            "inactive": sorted(inactive),
            "events": [asdict(event) for event in events],
            "blockers": sorted(set(blockers)),
        }
        return LegalTemporalState(
            as_of=as_of.isoformat(),
            active_instrument_ids=tuple(sorted(active)),
            inactive_instrument_ids=tuple(sorted(inactive)),
            applied_relation_ids=tuple(event.relation_id for event in events),
            blockers=tuple(sorted(set(blockers))),
            resolution_fingerprint=_fingerprint(payload),
        )
