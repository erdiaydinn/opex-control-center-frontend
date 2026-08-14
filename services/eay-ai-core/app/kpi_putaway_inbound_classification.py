from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


_ALLOWED_KINDS = {"ST_CDC", "ST_OTHER", "PO"}


@dataclass(frozen=True)
class PutawayInboundClassificationContract:
    contract_id: str
    raw_to_kind: Mapping[str, str]
    reviewed_at: str
    reviewer: str | None = None
    reviewed: bool = False

    @property
    def canonical_mapping(self) -> dict[str, str]:
        return {
            str(raw).strip().casefold(): str(kind).strip().upper()
            for raw, kind in sorted(self.raw_to_kind.items(), key=lambda item: str(item[0]).casefold())
        }

    @property
    def fingerprint(self) -> str:
        payload = {
            "contract_id": self.contract_id,
            "raw_to_kind": self.canonical_mapping,
            "reviewed_at": self.reviewed_at,
            "reviewer": self.reviewer,
            "reviewed": self.reviewed,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_review(contract: PutawayInboundClassificationContract) -> None:
    if not contract.contract_id.strip():
        raise ValueError("putaway_inbound_classification_contract_id_required")
    if not contract.reviewed or not (contract.reviewer or "").strip():
        raise ValueError("putaway_inbound_classification_human_review_required")
    try:
        reviewed_at = datetime.fromisoformat(contract.reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("putaway_inbound_classification_invalid_review_time") from exc
    if reviewed_at.tzinfo is None:
        raise ValueError("putaway_inbound_classification_timezone_required")
    if reviewed_at.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("putaway_inbound_classification_future_review_time")


def verify_putaway_inbound_classification_contract(
    contract: PutawayInboundClassificationContract,
) -> dict[str, object]:
    _validate_review(contract)
    mapping = contract.canonical_mapping
    if not mapping:
        raise ValueError("putaway_inbound_classification_mapping_required")
    if any(not raw for raw in mapping):
        raise ValueError("putaway_inbound_classification_blank_raw_value")
    invalid_kinds = sorted({kind for kind in mapping.values() if kind not in _ALLOWED_KINDS})
    if invalid_kinds:
        raise ValueError(
            "putaway_inbound_classification_invalid_kind:" + ",".join(invalid_kinds)
        )
    return {
        "contract_id": contract.contract_id,
        "mapping": mapping,
        "classification_fingerprint": contract.fingerprint,
        "reviewer": contract.reviewer,
        "reviewed_at": contract.reviewed_at,
        "verified": True,
    }


def classify_putaway_inbound(
    raw_value: object,
    *,
    verified_contract: Mapping[str, object],
) -> str:
    if verified_contract.get("verified") is not True:
        raise ValueError("putaway_inbound_classification_verified_contract_required")
    mapping = verified_contract.get("mapping")
    if not isinstance(mapping, Mapping):
        raise ValueError("putaway_inbound_classification_mapping_required")
    raw = str(raw_value or "").strip().casefold()
    if not raw:
        raise ValueError("putaway_inbound_classification_raw_value_required")
    kind = mapping.get(raw)
    if kind is None:
        raise ValueError(f"putaway_inbound_classification_unknown_raw_value:{raw}")
    normalized = str(kind).upper()
    if normalized not in _ALLOWED_KINDS:
        raise ValueError(f"putaway_inbound_classification_invalid_kind:{normalized}")
    return normalized
