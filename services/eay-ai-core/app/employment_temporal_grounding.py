from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .employment_intelligence import (
    DB_PATH,
    EmploymentIntelligenceStore,
    EmploymentResolutionRequest,
)
from .enterprise_domain_registry import SourceAuthority
from .legal_temporal import LegalTemporalResolver


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EmploymentLegalBindingCreate(BaseModel):
    employment_rule_record_id: str = Field(min_length=3, max_length=180)
    legal_instrument_id: str = Field(min_length=3, max_length=180)
    legal_requirement_ids: list[str] = Field(min_length=1)
    reviewed_by: str = Field(min_length=2, max_length=200)
    approval_reference: str = Field(min_length=3, max_length=300)


@dataclass(frozen=True)
class EmploymentLegalBinding:
    id: str
    employment_rule_record_id: str
    employment_rule_fingerprint: str
    legal_instrument_id: str
    legal_requirement_ids: tuple[str, ...]
    legal_requirement_fingerprints: tuple[str, ...]
    reviewed_by: str
    approval_reference: str
    created_at: str
    fingerprint: str

    def payload(self) -> dict[str, object]:
        values = asdict(self)
        values.pop("fingerprint")
        return values

    def validate(self) -> None:
        if _sha256(self.payload()) != self.fingerprint:
            raise ValueError("employment_legal_binding_fingerprint_drift")


@dataclass(frozen=True)
class GroundedEmploymentResolution:
    question_kind: str
    as_of: str
    employment_resolution_fingerprint: str
    legal_temporal_resolution_fingerprint: str | None
    active_legal_instrument_ids: tuple[str, ...]
    legal_binding_fingerprints: tuple[str, ...]
    legal_rule_fingerprints: tuple[str, ...]
    company_rule_fingerprints: tuple[str, ...]
    deterministic_calculation_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    fingerprint: str

    @property
    def resolved(self) -> bool:
        return not self.blockers


class EmploymentLegalBindingRegistry:
    """Human-reviewed bridge from distilled employment rules to exact legal evidence.

    A binding-law employment statement cannot become answer evidence merely because its
    URL is on an official host. It must bind to one verified legal instrument and one or
    more normalized legal requirements from that exact instrument. Runtime resolution
    then re-checks the legal temporal graph for the requested historical date.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS employment_legal_bindings (
                id TEXT PRIMARY KEY,
                employment_rule_record_id TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                fingerprint TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
                )"""
            )

    @staticmethod
    def _require_requirement_fingerprint(row: sqlite3.Row) -> str:
        payload = {
            "id": row["id"],
            "authority": row["authority"],
            "source_id": row["source_id"],
            "scope": row["scope"],
            "dimension": row["dimension"],
            "operator": row["operator"],
            "numeric_value": row["numeric_value"],
            "text_value": row["text_value"],
            "unit": row["unit"],
            "effective_from": row["effective_from"],
            "effective_to": row["effective_to"],
            "citation": row["citation"],
        }
        return _sha256(payload)

    def create(self, payload: EmploymentLegalBindingCreate) -> EmploymentLegalBinding:
        employment_store = EmploymentIntelligenceStore(self.db_path)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            employment_row = conn.execute(
                "SELECT * FROM employment_rule_versions WHERE id=?",
                (payload.employment_rule_record_id,),
            ).fetchone()
            if employment_row is None:
                raise KeyError("employment_legal_binding_rule_not_found")
            rule = employment_store._record(employment_row)
            if rule.status != "approved":
                raise ValueError("employment_legal_binding_approved_rule_required")
            if rule.source_authority != SourceAuthority.BINDING_LAW.value:
                raise ValueError("employment_legal_binding_binding_law_rule_required")

            instrument = conn.execute(
                "SELECT * FROM legal_instruments WHERE id=?",
                (payload.legal_instrument_id,),
            ).fetchone()
            if instrument is None:
                raise KeyError("employment_legal_binding_instrument_not_found")
            if instrument["verification_status"] != "verified":
                raise ValueError("employment_legal_binding_verified_instrument_required")

            requirement_ids = tuple(sorted(set(payload.legal_requirement_ids)))
            placeholders = ",".join("?" for _ in requirement_ids)
            requirement_rows = conn.execute(
                f"SELECT * FROM normalized_requirements WHERE id IN ({placeholders}) ORDER BY id ASC",
                requirement_ids,
            ).fetchall()
            if len(requirement_rows) != len(requirement_ids):
                raise ValueError("employment_legal_binding_requirement_missing")
            for row in requirement_rows:
                if row["authority"] != "legal" or row["source_id"] != payload.legal_instrument_id:
                    raise ValueError("employment_legal_binding_requirement_source_mismatch")

        requirement_fps = tuple(self._require_requirement_fingerprint(row) for row in requirement_rows)
        values = {
            "id": str(uuid.uuid4()),
            "employment_rule_record_id": payload.employment_rule_record_id,
            "employment_rule_fingerprint": rule.fingerprint,
            "legal_instrument_id": payload.legal_instrument_id,
            "legal_requirement_ids": requirement_ids,
            "legal_requirement_fingerprints": requirement_fps,
            "reviewed_by": payload.reviewed_by.strip(),
            "approval_reference": payload.approval_reference.strip(),
            "created_at": _utc_now(),
        }
        binding = EmploymentLegalBinding(**values, fingerprint=_sha256(values))
        binding.validate()
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    "INSERT INTO employment_legal_bindings(id,employment_rule_record_id,payload_json,fingerprint,created_at) VALUES (?,?,?,?,?)",
                    (binding.id,binding.employment_rule_record_id,json.dumps(binding.payload(),sort_keys=True,separators=(",",":"),ensure_ascii=False),binding.fingerprint,binding.created_at),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("employment_legal_binding_already_exists") from exc
        return binding

    def require_for_rule(self, employment_rule_record_id: str) -> EmploymentLegalBinding:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT payload_json,fingerprint FROM employment_legal_bindings WHERE employment_rule_record_id=?",
                (employment_rule_record_id,),
            ).fetchone()
        if row is None:
            raise KeyError("employment_legal_binding_not_found")
        values = json.loads(row[0])
        values["legal_requirement_ids"] = tuple(values["legal_requirement_ids"])
        values["legal_requirement_fingerprints"] = tuple(values["legal_requirement_fingerprints"])
        binding = EmploymentLegalBinding(**values, fingerprint=row[1])
        binding.validate()
        return binding

    def resolve(self, request: EmploymentResolutionRequest) -> GroundedEmploymentResolution:
        employment_store = EmploymentIntelligenceStore(self.db_path)
        base = employment_store.resolve(request)
        blockers = list(base.blockers)
        temporal_fp: str | None = None
        active_ids: tuple[str, ...] = ()
        binding_fps: list[str] = []

        if request.question_kind in {"labor_law", "payroll"}:
            temporal = LegalTemporalResolver(self.db_path).resolve(request.as_of)
            temporal_fp = temporal.resolution_fingerprint
            active_ids = temporal.active_instrument_ids
            if temporal.blockers:
                blockers.append("employment_grounding_legal_temporal_resolution_blocked")
            else:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        """SELECT * FROM employment_rule_versions
                        WHERE status='approved' AND source_authority=?
                          AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?)
                          AND (kind=? OR (?='payroll' AND kind='labor_law'))
                        ORDER BY rule_id,effective_from DESC""",
                        (
                            SourceAuthority.BINDING_LAW.value,
                            request.as_of.isoformat(),request.as_of.isoformat(),
                            request.question_kind,request.question_kind,
                        ),
                    ).fetchall()
                if not rows:
                    blockers.append("employment_grounding_binding_law_baseline_missing")
                for row in rows:
                    rule = employment_store._record(row)
                    try:
                        binding = self.require_for_rule(rule.id)
                    except KeyError:
                        blockers.append(f"employment_grounding_binding_missing:{rule.rule_id}")
                        continue
                    if binding.employment_rule_fingerprint != rule.fingerprint:
                        blockers.append(f"employment_grounding_rule_binding_drift:{rule.rule_id}")
                        continue
                    if binding.legal_instrument_id not in temporal.active_instrument_ids:
                        blockers.append(f"employment_grounding_instrument_inactive:{binding.legal_instrument_id}")
                        continue
                    binding_fps.append(binding.fingerprint)

        payload = {
            "question_kind": request.question_kind,
            "as_of": request.as_of.isoformat(),
            "employment_resolution_fingerprint": base.fingerprint,
            "legal_temporal_resolution_fingerprint": temporal_fp,
            "active_legal_instrument_ids": active_ids,
            "legal_binding_fingerprints": tuple(sorted(binding_fps)),
            "legal_rule_fingerprints": base.legal_rule_fingerprints,
            "company_rule_fingerprints": base.company_rule_fingerprints,
            "deterministic_calculation_ids": base.deterministic_calculation_ids,
            "blockers": tuple(sorted(set(blockers))),
        }
        return GroundedEmploymentResolution(**payload, fingerprint=_sha256(payload))


registry = EmploymentLegalBindingRegistry(DB_PATH)
router = APIRouter(prefix="/v1/employment-grounding", tags=["employment-grounding"])


@router.post("/bindings")
def create_binding(payload: EmploymentLegalBindingCreate):
    try:
        return registry.create(payload).__dict__
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/resolve")
def resolve_grounded_employment(payload: EmploymentResolutionRequest):
    return registry.resolve(payload).__dict__
