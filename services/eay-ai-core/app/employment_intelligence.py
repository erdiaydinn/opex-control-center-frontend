from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from .enterprise_domain_registry import EnterpriseDomain, SourceAuthority, classify_official_tr_source

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
RuleKind = Literal["labor_law", "payroll", "benefit"]
RuleStatus = Literal["draft", "approved", "superseded", "retired"]


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EmploymentRuleCreate(BaseModel):
    rule_id: str = Field(min_length=3, max_length=180)
    kind: RuleKind
    title: str = Field(min_length=3, max_length=500)
    version: str = Field(min_length=1, max_length=80)
    statement: str = Field(min_length=10, max_length=8000)
    source_url: str | None = Field(default=None, max_length=2000)
    company: str | None = Field(default=None, max_length=160)
    effective_from: date
    effective_to: date | None = None
    employee_groups: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    grades: list[str] = Field(default_factory=list)
    contract_types: list[str] = Field(default_factory=list)
    deterministic_calculation_id: str | None = Field(default=None, max_length=180)
    owner: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_contract(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("employment_rule_effective_range_invalid")
        if self.kind in {"labor_law", "payroll"} and not self.source_url:
            raise ValueError("employment_rule_official_source_required")
        if self.kind == "benefit" and not self.company:
            raise ValueError("employment_benefit_company_required")
        if self.kind == "payroll" and not self.deterministic_calculation_id:
            raise ValueError("employment_payroll_calculation_contract_required")
        return self


class EmploymentRuleApproval(BaseModel):
    approved_by: str = Field(min_length=2, max_length=200)
    approval_reference: str = Field(min_length=3, max_length=300)


class EmployeeContext(BaseModel):
    employee_group: str | None = Field(default=None, max_length=160)
    location: str | None = Field(default=None, max_length=160)
    grade: str | None = Field(default=None, max_length=80)
    contract_type: str | None = Field(default=None, max_length=120)


class EmploymentResolutionRequest(BaseModel):
    question_kind: RuleKind
    as_of: date
    company: str | None = Field(default=None, max_length=160)
    employee: EmployeeContext | None = None


@dataclass(frozen=True)
class EmploymentRuleRecord:
    id: str
    rule_id: str
    kind: str
    title: str
    version: str
    statement_sha256: str
    source_url: str | None
    source_authority: str
    company: str | None
    effective_from: str
    effective_to: str | None
    employee_groups: tuple[str, ...]
    locations: tuple[str, ...]
    grades: tuple[str, ...]
    contract_types: tuple[str, ...]
    deterministic_calculation_id: str | None
    status: str
    approval_reference: str | None
    fingerprint: str

    def payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "kind": self.kind,
            "title": self.title,
            "version": self.version,
            "statement_sha256": self.statement_sha256,
            "source_url": self.source_url,
            "source_authority": self.source_authority,
            "company": self.company,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "employee_groups": self.employee_groups,
            "locations": self.locations,
            "grades": self.grades,
            "contract_types": self.contract_types,
            "deterministic_calculation_id": self.deterministic_calculation_id,
            "status": self.status,
            "approval_reference": self.approval_reference,
        }

    def validate(self) -> None:
        if _sha256(self.payload()) != self.fingerprint:
            raise ValueError("employment_rule_fingerprint_drift")


@dataclass(frozen=True)
class EmploymentResolution:
    domain: str
    question_kind: str
    as_of: str
    legal_rule_fingerprints: tuple[str, ...]
    company_rule_fingerprints: tuple[str, ...]
    deterministic_calculation_ids: tuple[str, ...]
    blockers: tuple[str, ...]
    requires_employee_context: bool
    fingerprint: str


class EmploymentIntelligenceStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS employment_rule_versions (
                    id TEXT PRIMARY KEY,
                    rule_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    version TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    statement_sha256 TEXT NOT NULL,
                    source_url TEXT,
                    source_authority TEXT NOT NULL,
                    company TEXT,
                    effective_from TEXT NOT NULL,
                    effective_to TEXT,
                    employee_groups_json TEXT NOT NULL,
                    locations_json TEXT NOT NULL,
                    grades_json TEXT NOT NULL,
                    contract_types_json TEXT NOT NULL,
                    deterministic_calculation_id TEXT,
                    owner TEXT,
                    status TEXT NOT NULL DEFAULT 'draft',
                    approved_by TEXT,
                    approval_reference TEXT,
                    created_at TEXT NOT NULL,
                    approved_at TEXT,
                    UNIQUE(rule_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_employment_rule_effective
                ON employment_rule_versions(kind, company, status, effective_from, effective_to);
                """
            )

    @staticmethod
    def _authority(payload: EmploymentRuleCreate) -> str:
        if payload.kind == "benefit":
            return SourceAuthority.COMPANY_POLICY.value
        assert payload.source_url is not None
        authorities = classify_official_tr_source(payload.source_url)
        if payload.kind == "labor_law" and SourceAuthority.BINDING_LAW in authorities:
            return SourceAuthority.BINDING_LAW.value
        return SourceAuthority.OFFICIAL_GUIDANCE.value

    @staticmethod
    def _record(row: sqlite3.Row) -> EmploymentRuleRecord:
        values = {
            "id": row["id"],
            "rule_id": row["rule_id"],
            "kind": row["kind"],
            "title": row["title"],
            "version": row["version"],
            "statement_sha256": row["statement_sha256"],
            "source_url": row["source_url"],
            "source_authority": row["source_authority"],
            "company": row["company"],
            "effective_from": row["effective_from"],
            "effective_to": row["effective_to"],
            "employee_groups": tuple(json.loads(row["employee_groups_json"])),
            "locations": tuple(json.loads(row["locations_json"])),
            "grades": tuple(json.loads(row["grades_json"])),
            "contract_types": tuple(json.loads(row["contract_types_json"])),
            "deterministic_calculation_id": row["deterministic_calculation_id"],
            "status": row["status"],
            "approval_reference": row["approval_reference"],
        }
        record = EmploymentRuleRecord(**values, fingerprint=_sha256(values))
        record.validate()
        return record

    def create(self, payload: EmploymentRuleCreate) -> EmploymentRuleRecord:
        authority = self._authority(payload)
        record_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            try:
                conn.execute(
                    """INSERT INTO employment_rule_versions(
                    id,rule_id,kind,title,version,statement,statement_sha256,source_url,source_authority,
                    company,effective_from,effective_to,employee_groups_json,locations_json,grades_json,
                    contract_types_json,deterministic_calculation_id,owner,status,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?)""",
                    (
                        record_id,payload.rule_id,payload.kind,payload.title,payload.version,payload.statement,
                        hashlib.sha256(payload.statement.encode("utf-8")).hexdigest(),payload.source_url,authority,
                        payload.company,payload.effective_from.isoformat(),payload.effective_to.isoformat() if payload.effective_to else None,
                        json.dumps(sorted(set(payload.employee_groups)),ensure_ascii=False),
                        json.dumps(sorted(set(payload.locations)),ensure_ascii=False),
                        json.dumps(sorted(set(payload.grades)),ensure_ascii=False),
                        json.dumps(sorted(set(payload.contract_types)),ensure_ascii=False),
                        payload.deterministic_calculation_id,payload.owner,_utc_now(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("employment_rule_version_already_exists") from exc
            row = conn.execute("SELECT * FROM employment_rule_versions WHERE id=?", (record_id,)).fetchone()
        assert row is not None
        return self._record(row)

    def approve(self, record_id: str, payload: EmploymentRuleApproval) -> EmploymentRuleRecord:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM employment_rule_versions WHERE id=?", (record_id,)).fetchone()
            if row is None:
                raise KeyError("employment_rule_not_found")
            if row["status"] != "draft":
                raise ValueError("employment_rule_not_draft")
            conn.execute(
                "UPDATE employment_rule_versions SET status='approved',approved_by=?,approval_reference=?,approved_at=? WHERE id=?",
                (payload.approved_by,payload.approval_reference,_utc_now(),record_id),
            )
            row = conn.execute("SELECT * FROM employment_rule_versions WHERE id=?", (record_id,)).fetchone()
        assert row is not None
        return self._record(row)

    @staticmethod
    def _matches_scope(record: EmploymentRuleRecord, employee: EmployeeContext | None) -> bool:
        selectors = (
            (record.employee_groups, employee.employee_group if employee else None),
            (record.locations, employee.location if employee else None),
            (record.grades, employee.grade if employee else None),
            (record.contract_types, employee.contract_type if employee else None),
        )
        for allowed, actual in selectors:
            if allowed and actual not in allowed:
                return False
        return True

    def resolve(self, request: EmploymentResolutionRequest) -> EmploymentResolution:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM employment_rule_versions
                WHERE status='approved' AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?)
                  AND (kind=? OR (?='payroll' AND kind='labor_law'))
                ORDER BY kind,rule_id,effective_from DESC""",
                (request.as_of.isoformat(),request.as_of.isoformat(),request.question_kind,request.question_kind),
            ).fetchall()
        records = tuple(self._record(row) for row in rows)
        legal = tuple(item for item in records if item.source_authority in {SourceAuthority.BINDING_LAW.value, SourceAuthority.OFFICIAL_GUIDANCE.value})
        company = tuple(
            item for item in records
            if item.source_authority == SourceAuthority.COMPANY_POLICY.value
            and (request.company is None or item.company == request.company)
            and self._matches_scope(item, request.employee)
        )
        blockers: list[str] = []
        requires_employee = False
        if request.question_kind in {"labor_law", "payroll"} and not legal:
            blockers.append("employment_resolution_verified_official_rule_missing")
        if request.question_kind == "benefit":
            if request.company is None:
                blockers.append("employment_resolution_company_required")
            if not company:
                blockers.append("employment_resolution_approved_company_benefit_missing")
        scoped_company = tuple(item for item in records if item.source_authority == SourceAuthority.COMPANY_POLICY.value and any((item.employee_groups,item.locations,item.grades,item.contract_types)))
        if scoped_company and request.employee is None:
            requires_employee = True
            blockers.append("employment_resolution_employee_context_required")
        if request.question_kind == "payroll" and any(item.deterministic_calculation_id is None for item in records if item.kind == "payroll"):
            blockers.append("employment_resolution_payroll_calculation_contract_missing")
        calc_ids = tuple(sorted({item.deterministic_calculation_id for item in records if item.deterministic_calculation_id}))
        legal_fps = tuple(sorted(item.fingerprint for item in legal))
        company_fps = tuple(sorted(item.fingerprint for item in company))
        payload = {
            "domain": EnterpriseDomain.PAYROLL_LABOR_LAW.value if request.question_kind in {"labor_law","payroll"} else EnterpriseDomain.PEOPLE_HR.value,
            "question_kind": request.question_kind,
            "as_of": request.as_of.isoformat(),
            "legal_rule_fingerprints": legal_fps,
            "company_rule_fingerprints": company_fps,
            "deterministic_calculation_ids": calc_ids,
            "blockers": tuple(sorted(set(blockers))),
            "requires_employee_context": requires_employee,
        }
        return EmploymentResolution(**payload, fingerprint=_sha256(payload))


store = EmploymentIntelligenceStore(DB_PATH)
router = APIRouter(prefix="/v1/employment-intelligence", tags=["employment-intelligence"])


@router.post("/rules")
def create_rule(payload: EmploymentRuleCreate):
    try:
        return store.create(payload).__dict__
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/rules/{record_id}/approve")
def approve_rule(record_id: str, payload: EmploymentRuleApproval):
    try:
        return store.approve(record_id, payload).__dict__
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Employment rule not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/resolve")
def resolve_employment(request: EmploymentResolutionRequest):
    return store.resolve(request).__dict__


@router.get("/authority-check")
def authority_check(source_url: str = Query(min_length=8, max_length=2000)):
    try:
        authorities = classify_official_tr_source(source_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"source_url": source_url, "authorities": [item.value for item in authorities]}
