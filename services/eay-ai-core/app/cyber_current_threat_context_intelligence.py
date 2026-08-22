"""Freshness-gated global cyber context for EAY Jarvis.

Threat enrichment and source freshness are intentionally separate canonical
artifacts. This gate composes them at reasoning time. If ATT&CK context is present,
Jarvis may call it current only when an exact freshness receipt proves the ingested
release matches the independently observed authoritative release.

A stale or unknown ATT&CK release does not delete global threat evidence; it blocks
only the claim that ATT&CK-derived context is current. Company exposure and incident
truth remain outside this global contract.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.cyber_threat_enrichment_intelligence import GlobalThreatEnrichmentReceipt
from app.cyber_threat_source_freshness_intelligence import (
    ThreatSourceFreshnessReceipt,
    ThreatSourceFreshnessStatus,
)

CURRENT_THREAT_CONTEXT_CONTRACT = "eay-cyber-current-threat-context-v1"

_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key|password|passwd|"
    r"session[_-]?(?:token|cookie|id)(?:[-_: ]|$)|access[_-]?token|"
    r"refresh[_-]?token|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|shellcode)"
)


class CurrentThreatContextReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CURRENT_THREAT_CONTEXT_CONTRACT
    context_id: str = Field(min_length=1)
    global_enrichment_receipt_id: str = Field(min_length=1)
    global_enrichment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    attack_context_present: bool
    attack_freshness_receipt_id: str | None = None
    attack_freshness_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    attack_release_current: bool
    current_global_reasoning_allowed: bool
    reason_codes: tuple[str, ...] = Field(min_length=1)
    company_exposure_granted: bool = False
    company_truth_granted: bool = False
    incident_confirmation_granted: bool = False
    exploit_generation_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def context_is_freshness_gated_and_non_authoritative(
        self,
    ) -> CurrentThreatContextReceipt:
        if self.attack_context_present:
            if (
                not self.attack_freshness_receipt_id
                or not self.attack_freshness_fingerprint
            ) and self.attack_release_current:
                raise ValueError("current_threat_attack_current_requires_freshness_receipt")
            if self.current_global_reasoning_allowed != self.attack_release_current:
                raise ValueError("current_threat_attack_context_requires_current_release")
        else:
            if self.attack_freshness_receipt_id or self.attack_freshness_fingerprint:
                raise ValueError("current_threat_no_attack_context_cannot_bind_attack_freshness")
            if not self.attack_release_current:
                raise ValueError("current_threat_no_attack_context_is_not_blocked_by_attack_release")
            if not self.current_global_reasoning_allowed:
                raise ValueError("current_threat_no_attack_context_should_remain_usable")
        if self.company_exposure_granted:
            raise ValueError("current_threat_context_never_grants_company_exposure")
        if self.company_truth_granted:
            raise ValueError("current_threat_context_never_grants_company_truth")
        if self.incident_confirmation_granted:
            raise ValueError("current_threat_context_never_confirms_incident")
        if self.exploit_generation_permitted:
            raise ValueError("current_threat_context_exploit_generation_forbidden")
        if self.execution_authority_granted:
            raise ValueError("current_threat_context_never_grants_execution_authority")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("current_threat_reason_codes_must_be_unique")
        for ref in (
            self.context_id,
            self.global_enrichment_receipt_id,
            self.attack_freshness_receipt_id,
            *self.reason_codes,
        ):
            if ref is not None:
                _safe_ref(ref, "current_threat_context_unsafe_reference_forbidden")
        _verify(self, "current_threat_context_fingerprint_mismatch")
        return self


def build_current_threat_context(
    *,
    global_enrichment: GlobalThreatEnrichmentReceipt,
    attack_freshness: ThreatSourceFreshnessReceipt | None = None,
) -> CurrentThreatContextReceipt:
    enrichment = GlobalThreatEnrichmentReceipt.model_validate(
        global_enrichment.model_dump(mode="json")
    )
    attack_present = bool(
        enrichment.attack_technique_ids
        or enrichment.detection_strategy_ids
        or enrichment.data_component_ids
    )

    freshness_id: str | None = None
    freshness_fingerprint: str | None = None
    if attack_present:
        if attack_freshness is None:
            attack_current = False
            allowed = False
            reasons = ["attack_context_present_but_release_freshness_missing"]
        else:
            freshness = ThreatSourceFreshnessReceipt.model_validate(
                attack_freshness.model_dump(mode="json")
            )
            freshness_id = freshness.receipt_id
            freshness_fingerprint = freshness.fingerprint
            attack_current = (
                freshness.status is ThreatSourceFreshnessStatus.CURRENT
                and freshness.freshness_confirmed
                and freshness.global_threat_use_allowed
            )
            allowed = attack_current
            reasons = [
                "attack_release_current"
                if attack_current
                else f"attack_release_not_current:{freshness.status.value}"
            ]
    else:
        if attack_freshness is not None:
            raise ValueError("current_threat_attack_freshness_without_attack_context")
        attack_current = True
        allowed = True
        reasons = ["global_context_has_no_attack_release_dependency"]

    if enrichment.epss_score is not None and not enrichment.epss_current:
        reasons.append("epss_present_but_stale_not_used_for_current_priority")
    if enrichment.epss_current:
        reasons.append("epss_current")

    seed = {
        "global_enrichment": enrichment.fingerprint,
        "attack_freshness": freshness_fingerprint,
    }
    context_id = f"current-threat-context:{_fingerprint(seed)[:24]}"
    draft = {
        "contract": CURRENT_THREAT_CONTEXT_CONTRACT,
        "context_id": context_id,
        "global_enrichment_receipt_id": enrichment.receipt_id,
        "global_enrichment_fingerprint": enrichment.fingerprint,
        "attack_context_present": attack_present,
        "attack_freshness_receipt_id": freshness_id,
        "attack_freshness_fingerprint": freshness_fingerprint,
        "attack_release_current": attack_current,
        "current_global_reasoning_allowed": allowed,
        "reason_codes": reasons,
        "company_exposure_granted": False,
        "company_truth_granted": False,
        "incident_confirmation_granted": False,
        "exploit_generation_permitted": False,
        "execution_authority_granted": False,
    }
    return CurrentThreatContextReceipt.model_validate(_sealed(draft))


def verify_current_threat_context(*, receipt: CurrentThreatContextReceipt) -> None:
    CurrentThreatContextReceipt.model_validate(receipt.model_dump(mode="json"))


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _verify(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_payload(model)):
        raise ValueError(error)


def _sealed(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "fingerprint": _fingerprint(payload)}


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
