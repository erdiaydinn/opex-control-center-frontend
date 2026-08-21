from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal, Mapping, Sequence

InboundKind = Literal["ST_CDC", "ST_OTHER", "PO"]


@dataclass(frozen=True)
class PutawaySlaContract:
    contract_id: str
    version: str
    effective_from: date
    effective_to: date | None
    st_cdc_minutes: int = 240
    st_other_minutes: int = 960
    po_minutes: int = 240
    city_offsets_minutes: Mapping[str, int] = field(default_factory=dict)
    schema_evidence_fingerprint: str | None = None
    reviewed: bool = False
    reviewer: str | None = None

    @property
    def fingerprint(self) -> str:
        payload = {
            "contract_id": self.contract_id,
            "version": self.version,
            "effective_from": self.effective_from.isoformat(),
            "effective_to": self.effective_to.isoformat() if self.effective_to else None,
            "st_cdc_minutes": self.st_cdc_minutes,
            "st_other_minutes": self.st_other_minutes,
            "po_minutes": self.po_minutes,
            "city_offsets_minutes": {
                str(city).strip().casefold(): int(offset)
                for city, offset in sorted(self.city_offsets_minutes.items())
            },
            "schema_evidence_fingerprint": self.schema_evidence_fingerprint,
            "reviewed": self.reviewed,
            "reviewer": self.reviewer,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PutawaySlaEvaluation:
    contract_id: str
    contract_version: str
    contract_fingerprint: str
    inbound_kind: InboundKind
    city: str | None
    threshold_minutes: int
    elapsed_minutes: Decimal
    compliant: bool


def _validate_sha256(value: str | None, field: str) -> None:
    if value is None:
        return
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"putaway_sla_invalid_fingerprint:{field}")


def validate_putaway_sla_contract(contract: PutawaySlaContract) -> None:
    if not contract.contract_id.strip() or not contract.version.strip():
        raise ValueError("putaway_sla_identity_required")
    if contract.effective_to is not None and contract.effective_to < contract.effective_from:
        raise ValueError("putaway_sla_invalid_effective_window")
    if not contract.reviewed or not (contract.reviewer or "").strip():
        raise ValueError("putaway_sla_human_review_required")
    for field_name, minutes in (
        ("st_cdc_minutes", contract.st_cdc_minutes),
        ("st_other_minutes", contract.st_other_minutes),
        ("po_minutes", contract.po_minutes),
    ):
        if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes <= 0:
            raise ValueError(f"putaway_sla_invalid_threshold:{field_name}")
    for city, offset in contract.city_offsets_minutes.items():
        if not str(city).strip():
            raise ValueError("putaway_sla_blank_city_offset")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError(f"putaway_sla_invalid_city_offset:{city}")
    _validate_sha256(contract.schema_evidence_fingerprint, "schema_evidence")


def resolve_putaway_sla_contract(
    contracts: Sequence[PutawaySlaContract], *, as_of: date
) -> PutawaySlaContract:
    active: list[PutawaySlaContract] = []
    for contract in contracts:
        validate_putaway_sla_contract(contract)
        if contract.effective_from <= as_of and (
            contract.effective_to is None or as_of <= contract.effective_to
        ):
            active.append(contract)
    if not active:
        raise ValueError("putaway_sla_no_effective_contract")
    if len(active) != 1:
        raise ValueError("putaway_sla_ambiguous_effective_contract")
    return active[0]


def putaway_threshold_minutes(
    contract: PutawaySlaContract,
    *,
    inbound_kind: InboundKind,
    city: str | None = None,
) -> int:
    validate_putaway_sla_contract(contract)
    if inbound_kind == "ST_CDC":
        return contract.st_cdc_minutes
    if inbound_kind == "PO":
        return contract.po_minutes
    if inbound_kind != "ST_OTHER":
        raise ValueError(f"putaway_sla_unsupported_inbound_kind:{inbound_kind}")

    base = contract.st_other_minutes
    if city is None:
        return base
    normalized = city.strip().casefold()
    offsets = {str(name).strip().casefold(): offset for name, offset in contract.city_offsets_minutes.items()}
    return base + int(offsets.get(normalized, 0))


def evaluate_putaway_sla(
    contracts: Sequence[PutawaySlaContract],
    *,
    as_of: date,
    inbound_kind: InboundKind,
    elapsed_minutes: object,
    city: str | None = None,
) -> PutawaySlaEvaluation:
    contract = resolve_putaway_sla_contract(contracts, as_of=as_of)
    try:
        elapsed = Decimal(str(elapsed_minutes))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("putaway_sla_elapsed_non_numeric") from exc
    if not elapsed.is_finite() or elapsed < 0:
        raise ValueError("putaway_sla_elapsed_invalid")
    threshold = putaway_threshold_minutes(
        contract,
        inbound_kind=inbound_kind,
        city=city,
    )
    return PutawaySlaEvaluation(
        contract_id=contract.contract_id,
        contract_version=contract.version,
        contract_fingerprint=contract.fingerprint,
        inbound_kind=inbound_kind,
        city=city,
        threshold_minutes=threshold,
        elapsed_minutes=elapsed,
        compliant=elapsed <= Decimal(threshold),
    )
