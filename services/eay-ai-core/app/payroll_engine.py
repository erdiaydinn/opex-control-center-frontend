from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from .employment_intelligence import DB_PATH
from .enterprise_domain_registry import SourceAuthority, classify_official_tr_source


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _dec(value: object) -> Decimal:
    return Decimal(str(value))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class IncomeTaxBracket:
    upper_bound: Decimal | None
    rate: Decimal

    def validate(self) -> None:
        if self.upper_bound is not None and self.upper_bound <= 0:
            raise ValueError("payroll_income_tax_bracket_bound_invalid")
        if self.rate <= 0 or self.rate >= 1:
            raise ValueError("payroll_income_tax_bracket_rate_invalid")


class IncomeTaxBracketInput(BaseModel):
    upper_bound: float | None = Field(default=None, gt=0)
    rate: float = Field(gt=0, lt=1)


class PayrollParameterSetCreate(BaseModel):
    parameter_set_id: str = Field(min_length=3, max_length=180)
    version: str = Field(min_length=1, max_length=80)
    effective_from: date
    effective_to: date | None = None
    monthly_minimum_gross: float = Field(gt=0)
    monthly_pek_floor: float = Field(gt=0)
    monthly_pek_ceiling: float = Field(gt=0)
    employee_sgk_rate: float = Field(gt=0, lt=1)
    employee_unemployment_rate: float = Field(ge=0, lt=1)
    stamp_tax_rate: float = Field(ge=0, lt=0.1)
    minimum_wage_income_tax_exemption: bool = True
    minimum_wage_stamp_tax_exemption: bool = True
    income_tax_brackets: list[IncomeTaxBracketInput] = Field(min_length=2)
    source_urls: list[str] = Field(min_length=2)
    deterministic_calculation_id: str = Field(default="tr-payroll-standard-4a-full-month-v1", min_length=8, max_length=180)

    @model_validator(mode="after")
    def validate_contract(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("payroll_parameter_effective_range_invalid")
        if self.monthly_pek_ceiling < self.monthly_pek_floor:
            raise ValueError("payroll_parameter_pek_range_invalid")
        if self.monthly_minimum_gross != self.monthly_pek_floor:
            # This v1 calculator deliberately supports the ordinary private-sector
            # 4/a full-month case only. Partial month/public-sector edge cases must
            # use a different deterministic contract rather than silently guessing.
            raise ValueError("payroll_parameter_v1_minimum_gross_must_equal_pek_floor")
        bounds = [item.upper_bound for item in self.income_tax_brackets if item.upper_bound is not None]
        if bounds != sorted(bounds) or len(bounds) != len(set(bounds)):
            raise ValueError("payroll_income_tax_brackets_not_strictly_increasing")
        if self.income_tax_brackets[-1].upper_bound is not None:
            raise ValueError("payroll_income_tax_last_bracket_must_be_open")
        authorities = []
        for url in self.source_urls:
            authorities.extend(classify_official_tr_source(url))
        if not authorities or any(
            authority not in {SourceAuthority.BINDING_LAW, SourceAuthority.OFFICIAL_GUIDANCE}
            for authority in authorities
        ):
            raise ValueError("payroll_parameter_official_sources_required")
        return self


class PayrollParameterApproval(BaseModel):
    approved_by: str = Field(min_length=2, max_length=200)
    approval_reference: str = Field(min_length=3, max_length=300)


@dataclass(frozen=True)
class PayrollParameterSet:
    id: str
    parameter_set_id: str
    version: str
    effective_from: str
    effective_to: str | None
    monthly_minimum_gross: Decimal
    monthly_pek_floor: Decimal
    monthly_pek_ceiling: Decimal
    employee_sgk_rate: Decimal
    employee_unemployment_rate: Decimal
    stamp_tax_rate: Decimal
    minimum_wage_income_tax_exemption: bool
    minimum_wage_stamp_tax_exemption: bool
    income_tax_brackets: tuple[IncomeTaxBracket, ...]
    source_urls: tuple[str, ...]
    source_manifest_fingerprint: str
    deterministic_calculation_id: str
    status: str
    approval_reference: str | None
    fingerprint: str

    def payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "parameter_set_id": self.parameter_set_id,
            "version": self.version,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "monthly_minimum_gross": str(self.monthly_minimum_gross),
            "monthly_pek_floor": str(self.monthly_pek_floor),
            "monthly_pek_ceiling": str(self.monthly_pek_ceiling),
            "employee_sgk_rate": str(self.employee_sgk_rate),
            "employee_unemployment_rate": str(self.employee_unemployment_rate),
            "stamp_tax_rate": str(self.stamp_tax_rate),
            "minimum_wage_income_tax_exemption": self.minimum_wage_income_tax_exemption,
            "minimum_wage_stamp_tax_exemption": self.minimum_wage_stamp_tax_exemption,
            "income_tax_brackets": [
                {"upper_bound": str(item.upper_bound) if item.upper_bound is not None else None, "rate": str(item.rate)}
                for item in self.income_tax_brackets
            ],
            "source_urls": self.source_urls,
            "source_manifest_fingerprint": self.source_manifest_fingerprint,
            "deterministic_calculation_id": self.deterministic_calculation_id,
            "status": self.status,
            "approval_reference": self.approval_reference,
        }

    def validate(self) -> None:
        for bracket in self.income_tax_brackets:
            bracket.validate()
        if _sha256(self.payload()) != self.fingerprint:
            raise ValueError("payroll_parameter_fingerprint_drift")


class PayrollCalculationRequest(BaseModel):
    as_of: date
    gross_pay: float = Field(gt=0)
    cumulative_tax_base_before: float = Field(default=0, ge=0)
    cumulative_minimum_wage_tax_base_before: float = Field(default=0, ge=0)


@dataclass(frozen=True)
class PayrollCalculationResult:
    as_of: str
    deterministic_calculation_id: str
    parameter_set_fingerprint: str
    gross_pay: Decimal
    social_security_base: Decimal
    employee_sgk: Decimal
    employee_unemployment: Decimal
    income_tax_base: Decimal
    gross_income_tax: Decimal
    minimum_wage_income_tax_exemption: Decimal
    income_tax_payable: Decimal
    stamp_tax_payable: Decimal
    net_pay: Decimal
    cumulative_tax_base_after: Decimal
    cumulative_minimum_wage_tax_base_after: Decimal
    fingerprint: str

    def payload(self) -> dict[str, object]:
        values = asdict(self)
        values.pop("fingerprint")
        return {key: str(value) if isinstance(value, Decimal) else value for key, value in values.items()}

    def validate(self) -> None:
        if _sha256(self.payload()) != self.fingerprint:
            raise ValueError("payroll_calculation_fingerprint_drift")


def _progressive_tax(base: Decimal, brackets: tuple[IncomeTaxBracket, ...]) -> Decimal:
    if base <= 0:
        return Decimal("0")
    tax = Decimal("0")
    lower = Decimal("0")
    remaining = base
    for bracket in brackets:
        upper = bracket.upper_bound
        if upper is None:
            tax += max(Decimal("0"), remaining) * bracket.rate
            remaining = Decimal("0")
            break
        width = upper - lower
        taxable = min(max(Decimal("0"), remaining), width)
        tax += taxable * bracket.rate
        remaining -= taxable
        lower = upper
        if remaining <= 0:
            break
    if remaining > 0:
        raise ValueError("payroll_income_tax_open_bracket_missing")
    return _money(tax)


class PayrollParameterRegistry:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS payroll_parameter_sets (
                id TEXT PRIMARY KEY,
                parameter_set_id TEXT NOT NULL,
                version TEXT NOT NULL,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                approved_by TEXT,
                approval_reference TEXT,
                created_at TEXT NOT NULL,
                approved_at TEXT,
                UNIQUE(parameter_set_id, version)
                )"""
            )

    @staticmethod
    def _from_payload(payload: dict[str, object], *, status: str, approval_reference: str | None) -> PayrollParameterSet:
        brackets = tuple(
            IncomeTaxBracket(
                upper_bound=_dec(item["upper_bound"]) if item["upper_bound"] is not None else None,
                rate=_dec(item["rate"]),
            )
            for item in payload["income_tax_brackets"]
        )
        values = {
            "id": str(payload["id"]),
            "parameter_set_id": str(payload["parameter_set_id"]),
            "version": str(payload["version"]),
            "effective_from": str(payload["effective_from"]),
            "effective_to": str(payload["effective_to"]) if payload["effective_to"] is not None else None,
            "monthly_minimum_gross": _dec(payload["monthly_minimum_gross"]),
            "monthly_pek_floor": _dec(payload["monthly_pek_floor"]),
            "monthly_pek_ceiling": _dec(payload["monthly_pek_ceiling"]),
            "employee_sgk_rate": _dec(payload["employee_sgk_rate"]),
            "employee_unemployment_rate": _dec(payload["employee_unemployment_rate"]),
            "stamp_tax_rate": _dec(payload["stamp_tax_rate"]),
            "minimum_wage_income_tax_exemption": bool(payload["minimum_wage_income_tax_exemption"]),
            "minimum_wage_stamp_tax_exemption": bool(payload["minimum_wage_stamp_tax_exemption"]),
            "income_tax_brackets": brackets,
            "source_urls": tuple(str(value) for value in payload["source_urls"]),
            "source_manifest_fingerprint": str(payload["source_manifest_fingerprint"]),
            "deterministic_calculation_id": str(payload["deterministic_calculation_id"]),
            "status": status,
            "approval_reference": approval_reference,
        }
        record = PayrollParameterSet(**values, fingerprint=_sha256({
            **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in values.items() if k != "income_tax_brackets"},
            "income_tax_brackets": [
                {"upper_bound": str(item.upper_bound) if item.upper_bound is not None else None, "rate": str(item.rate)}
                for item in brackets
            ],
        }))
        # Re-seal from the public payload to keep one canonical fingerprint contract.
        record = PayrollParameterSet(**{**record.__dict__, "fingerprint": _sha256(record.payload())})
        record.validate()
        return record

    def create(self, item: PayrollParameterSetCreate) -> PayrollParameterSet:
        item.validate_contract()
        record_id = str(uuid.uuid4())
        source_urls = tuple(sorted(set(item.source_urls)))
        payload = {
            "id": record_id,
            "parameter_set_id": item.parameter_set_id,
            "version": item.version,
            "effective_from": item.effective_from.isoformat(),
            "effective_to": item.effective_to.isoformat() if item.effective_to else None,
            "monthly_minimum_gross": str(_dec(item.monthly_minimum_gross)),
            "monthly_pek_floor": str(_dec(item.monthly_pek_floor)),
            "monthly_pek_ceiling": str(_dec(item.monthly_pek_ceiling)),
            "employee_sgk_rate": str(_dec(item.employee_sgk_rate)),
            "employee_unemployment_rate": str(_dec(item.employee_unemployment_rate)),
            "stamp_tax_rate": str(_dec(item.stamp_tax_rate)),
            "minimum_wage_income_tax_exemption": item.minimum_wage_income_tax_exemption,
            "minimum_wage_stamp_tax_exemption": item.minimum_wage_stamp_tax_exemption,
            "income_tax_brackets": [
                {"upper_bound": str(_dec(b.upper_bound)) if b.upper_bound is not None else None, "rate": str(_dec(b.rate))}
                for b in item.income_tax_brackets
            ],
            "source_urls": source_urls,
            "source_manifest_fingerprint": _sha256(source_urls),
            "deterministic_calculation_id": item.deterministic_calculation_id,
        }
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    "INSERT INTO payroll_parameter_sets(id,parameter_set_id,version,effective_from,effective_to,payload_json,status,created_at) VALUES (?,?,?,?,?,?, 'draft', ?)",
                    (record_id,item.parameter_set_id,item.version,item.effective_from.isoformat(),item.effective_to.isoformat() if item.effective_to else None,json.dumps(payload,sort_keys=True,separators=(",",":")),_utc_now()),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("payroll_parameter_version_already_exists") from exc
        return self.require(record_id)

    def approve(self, record_id: str, approval: PayrollParameterApproval) -> PayrollParameterSet:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT status FROM payroll_parameter_sets WHERE id=?", (record_id,)).fetchone()
            if row is None:
                raise KeyError("payroll_parameter_not_found")
            if row[0] != "draft":
                raise ValueError("payroll_parameter_not_draft")
            conn.execute(
                "UPDATE payroll_parameter_sets SET status='approved',approved_by=?,approval_reference=?,approved_at=? WHERE id=?",
                (approval.approved_by,approval.approval_reference,_utc_now(),record_id),
            )
        return self.require(record_id)

    def require(self, record_id: str) -> PayrollParameterSet:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT payload_json,status,approval_reference FROM payroll_parameter_sets WHERE id=?", (record_id,)).fetchone()
        if row is None:
            raise KeyError("payroll_parameter_not_found")
        return self._from_payload(json.loads(row[0]), status=row[1], approval_reference=row[2])

    def require_as_of(self, as_of: date) -> PayrollParameterSet:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT id FROM payroll_parameter_sets
                WHERE status='approved' AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?)
                ORDER BY effective_from DESC""",
                (as_of.isoformat(),as_of.isoformat()),
            ).fetchall()
        if not rows:
            raise ValueError("payroll_parameter_approved_as_of_missing")
        if len(rows) > 1:
            raise ValueError("payroll_parameter_ambiguous_active_versions")
        return self.require(rows[0][0])


def calculate_standard_4a_full_month(
    *,
    parameters: PayrollParameterSet,
    request: PayrollCalculationRequest,
) -> PayrollCalculationResult:
    parameters.validate()
    if parameters.status != "approved" or not parameters.approval_reference:
        raise ValueError("payroll_calculation_approved_parameters_required")
    if parameters.deterministic_calculation_id != "tr-payroll-standard-4a-full-month-v1":
        raise ValueError("payroll_calculation_contract_not_supported")
    if not (parameters.effective_from <= request.as_of.isoformat() and (parameters.effective_to is None or parameters.effective_to >= request.as_of.isoformat())):
        raise ValueError("payroll_calculation_parameter_period_mismatch")

    gross = _money(_dec(request.gross_pay))
    if gross < parameters.monthly_minimum_gross:
        raise ValueError("payroll_calculation_partial_or_below_minimum_month_not_supported")

    social_base = min(max(gross, parameters.monthly_pek_floor), parameters.monthly_pek_ceiling)
    employee_sgk = _money(social_base * parameters.employee_sgk_rate)
    employee_unemployment = _money(social_base * parameters.employee_unemployment_rate)
    tax_base = _money(gross - employee_sgk - employee_unemployment)

    prior = _dec(request.cumulative_tax_base_before)
    gross_tax = _money(_progressive_tax(prior + tax_base, parameters.income_tax_brackets) - _progressive_tax(prior, parameters.income_tax_brackets))

    minimum_tax_base = _money(
        parameters.monthly_minimum_gross
        - parameters.monthly_minimum_gross * parameters.employee_sgk_rate
        - parameters.monthly_minimum_gross * parameters.employee_unemployment_rate
    )
    prior_min = _dec(request.cumulative_minimum_wage_tax_base_before)
    minimum_exemption = Decimal("0")
    if parameters.minimum_wage_income_tax_exemption:
        minimum_exemption = _money(
            _progressive_tax(prior_min + minimum_tax_base, parameters.income_tax_brackets)
            - _progressive_tax(prior_min, parameters.income_tax_brackets)
        )
        minimum_exemption = min(gross_tax, minimum_exemption)
    income_tax_payable = _money(max(Decimal("0"), gross_tax - minimum_exemption))

    stamp_tax = _money(gross * parameters.stamp_tax_rate)
    if parameters.minimum_wage_stamp_tax_exemption:
        stamp_tax = _money(max(Decimal("0"), stamp_tax - parameters.monthly_minimum_gross * parameters.stamp_tax_rate))

    net = _money(gross - employee_sgk - employee_unemployment - income_tax_payable - stamp_tax)
    payload = {
        "as_of": request.as_of.isoformat(),
        "deterministic_calculation_id": parameters.deterministic_calculation_id,
        "parameter_set_fingerprint": parameters.fingerprint,
        "gross_pay": str(gross),
        "social_security_base": str(_money(social_base)),
        "employee_sgk": str(employee_sgk),
        "employee_unemployment": str(employee_unemployment),
        "income_tax_base": str(tax_base),
        "gross_income_tax": str(gross_tax),
        "minimum_wage_income_tax_exemption": str(minimum_exemption),
        "income_tax_payable": str(income_tax_payable),
        "stamp_tax_payable": str(stamp_tax),
        "net_pay": str(net),
        "cumulative_tax_base_after": str(_money(prior + tax_base)),
        "cumulative_minimum_wage_tax_base_after": str(_money(prior_min + minimum_tax_base)),
    }
    result = PayrollCalculationResult(
        as_of=request.as_of.isoformat(),
        deterministic_calculation_id=parameters.deterministic_calculation_id,
        parameter_set_fingerprint=parameters.fingerprint,
        gross_pay=gross,
        social_security_base=_money(social_base),
        employee_sgk=employee_sgk,
        employee_unemployment=employee_unemployment,
        income_tax_base=tax_base,
        gross_income_tax=gross_tax,
        minimum_wage_income_tax_exemption=minimum_exemption,
        income_tax_payable=income_tax_payable,
        stamp_tax_payable=stamp_tax,
        net_pay=net,
        cumulative_tax_base_after=_money(prior + tax_base),
        cumulative_minimum_wage_tax_base_after=_money(prior_min + minimum_tax_base),
        fingerprint=_sha256(payload),
    )
    result.validate()
    return result


registry = PayrollParameterRegistry(DB_PATH)
router = APIRouter(prefix="/v1/payroll", tags=["payroll"])


@router.post("/parameter-sets")
def create_parameter_set(payload: PayrollParameterSetCreate):
    try:
        return registry.create(payload).__dict__
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/parameter-sets/{record_id}/approve")
def approve_parameter_set(record_id: str, payload: PayrollParameterApproval):
    try:
        return registry.approve(record_id, payload).__dict__
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Payroll parameter set not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/calculate")
def calculate_payroll(payload: PayrollCalculationRequest):
    try:
        parameters = registry.require_as_of(payload.as_of)
        return calculate_standard_4a_full_month(parameters=parameters, request=payload).__dict__
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
