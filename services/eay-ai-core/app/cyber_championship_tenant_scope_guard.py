"""Fail-closed vendor tenant/resource scope guard for real championship admission.

This authority runs before the broader external championship preflight. It never
loads raw vendor credentials. It validates only signed/sealed authorization and
credential-binding metadata and requires the tenant, resource, workload identity
and exact read-only common-harness operation to be mutually bound.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.cyber_championship_execution import (
    CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
    CompetitorKind,
)
from app.cyber_championship_external_authority import VendorCredentialBindingReceipt
from app.cyber_championship_vendor_adapters import CompetitorRunnerAuthorization

_ALLOWED_OPERATION = "operation://read-only/common-harness"
_REQUIRED_VENDORS = frozenset(
    {
        CompetitorKind.CROWDSTRIKE_CHARLOTTE_AI,
        CompetitorKind.GOOGLE_SECURITY_OPERATIONS_GEMINI,
        CompetitorKind.MICROSOFT_SECURITY_COPILOT,
    }
)
_STEMS = {
    CompetitorKind.CROWDSTRIKE_CHARLOTTE_AI: "crowdstrike",
    CompetitorKind.GOOGLE_SECURITY_OPERATIONS_GEMINI: "google",
    CompetitorKind.MICROSOFT_SECURITY_COPILOT: "microsoft",
}


class VendorScopeGuardStatus(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"


class VendorScopeGuardReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT
    competitor: CompetitorKind
    authorization_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    credential_binding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: VendorScopeGuardStatus
    blockers: tuple[str, ...] = ()
    raw_credentials_observed: bool = False
    production_mutation_authority: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def scope_guard_is_consistent(self) -> VendorScopeGuardReceipt:
        if self.raw_credentials_observed or self.production_mutation_authority:
            raise ValueError("vendor_scope_guard_forbidden_authority")
        if self.status is VendorScopeGuardStatus.READY and self.blockers:
            raise ValueError("vendor_scope_guard_ready_cannot_have_blockers")
        if self.status is VendorScopeGuardStatus.BLOCKED and not self.blockers:
            raise ValueError("vendor_scope_guard_blocked_requires_reason")
        _verify(self, "vendor_scope_guard_fingerprint_mismatch")
        return self


def evaluate_vendor_scope_guard(
    *,
    authorization: CompetitorRunnerAuthorization,
    binding: VendorCredentialBindingReceipt,
) -> VendorScopeGuardReceipt:
    authorization = CompetitorRunnerAuthorization.model_validate(
        authorization.model_dump(mode="json")
    )
    binding = VendorCredentialBindingReceipt.model_validate(binding.model_dump(mode="json"))
    blockers: list[str] = []

    if authorization.competitor is not binding.competitor:
        blockers.append("vendor_scope_competitor_mismatch")
    if authorization.organization_ref != binding.organization_ref:
        blockers.append("vendor_scope_organization_mismatch")
    if binding.tenant_ref not in authorization.resource_binding_refs:
        blockers.append("vendor_scope_tenant_not_authorized")
    if binding.resource_ref not in authorization.resource_binding_refs:
        blockers.append("vendor_scope_resource_not_authorized")
    if set(authorization.resource_binding_refs) != {
        binding.tenant_ref,
        binding.resource_ref,
    }:
        blockers.append("vendor_scope_resource_set_not_least_privilege")
    if binding.workload_identity_ref not in authorization.identity_binding_refs:
        blockers.append("vendor_scope_identity_not_authorized")
    if binding.allowed_operation_refs != (_ALLOWED_OPERATION,):
        blockers.append("vendor_scope_operation_not_exact_read_only_harness")

    unique_blockers = tuple(dict.fromkeys(blockers))
    return _seal_model(
        VendorScopeGuardReceipt,
        {
            "contract": CYBER_CHAMPIONSHIP_EXECUTION_CONTRACT,
            "competitor": binding.competitor,
            "authorization_fingerprint": authorization.fingerprint,
            "credential_binding_fingerprint": binding.fingerprint,
            "status": (
                VendorScopeGuardStatus.BLOCKED
                if unique_blockers
                else VendorScopeGuardStatus.READY
            ),
            "blockers": unique_blockers,
            "raw_credentials_observed": False,
            "production_mutation_authority": False,
        },
    )


def assess_evidence_directory(evidence_dir: Path) -> dict[str, object]:
    receipts: list[VendorScopeGuardReceipt] = []
    blockers: list[str] = []
    for competitor, stem in _STEMS.items():
        auth_path = evidence_dir / f"{stem}_runner_authorization.json"
        binding_path = evidence_dir / f"{stem}_credential_binding.json"
        if not auth_path.is_file():
            blockers.append(f"vendor_scope_receipt_missing:{stem}_runner_authorization.json")
            continue
        if not binding_path.is_file():
            blockers.append(f"vendor_scope_receipt_missing:{stem}_credential_binding.json")
            continue
        try:
            authorization = CompetitorRunnerAuthorization.model_validate(_load(auth_path))
            binding = VendorCredentialBindingReceipt.model_validate(_load(binding_path))
            if authorization.competitor is not competitor or binding.competitor is not competitor:
                blockers.append(f"vendor_scope_expected_competitor_mismatch:{stem}")
                continue
            receipt = evaluate_vendor_scope_guard(
                authorization=authorization,
                binding=binding,
            )
        except (KeyError, TypeError, ValueError):
            blockers.append(f"vendor_scope_receipt_validation_failed:{stem}")
            continue
        receipts.append(receipt)
        blockers.extend(f"{stem}:{item}" for item in receipt.blockers)

    if {item.competitor for item in receipts} != _REQUIRED_VENDORS:
        blockers.append("vendor_scope_all_required_vendors_not_verified")
    unique_blockers = tuple(dict.fromkeys(blockers))
    return {
        "status": "blocked" if unique_blockers else "ready",
        "blockers": unique_blockers,
        "receipt_fingerprints": tuple(sorted(item.fingerprint for item in receipts)),
        "raw_credentials_observed": False,
        "production_mutation_authority": False,
        "secrets_or_ground_truth_printed": False,
    }


def _load(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError("vendor_scope_receipt_must_be_json_object")
    return value


def _payload(model: BaseModel) -> dict[str, Any]:
    value = model.model_dump(mode="json")
    value.pop("fingerprint", None)
    return value


def _verify(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_payload(model)):
        raise ValueError(error)


def _seal_model(model_cls: type[BaseModel], values: dict[str, Any]):
    draft = model_cls.model_construct(**values, fingerprint="0" * 64)
    payload = draft.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return model_cls.model_validate({**payload, "fingerprint": _fingerprint(payload)})


def _fingerprint(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    if not args.evidence_dir.is_dir():
        report = {
            "status": "blocked",
            "blockers": ("vendor_scope_evidence_directory_missing",),
            "receipt_fingerprints": (),
            "raw_credentials_observed": False,
            "production_mutation_authority": False,
            "secrets_or_ground_truth_printed": False,
        }
    else:
        report = assess_evidence_directory(args.evidence_dir)
    print(json.dumps(report, sort_keys=True))
    if args.strict and report["status"] != "ready":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
