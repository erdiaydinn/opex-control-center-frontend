"""Bridge reviewed company reads into the canonical Jarvis mission runtime.

The bridge turns one already-reviewed read-only source route into a capability
handler. The collector may run off-thread so large swarms do not block the async
mission loop. Collection evidence is persisted by an injected evidence writer.

This layer never promotes collection to live truth and never grants execution
authority. LiveSourceAttestation remains the only promotion path.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Mapping

from .company_source_adapter_execution import (
    CompanySourceExecutionReceipt,
    CompanySourceRuntimeBinding,
    execute_registered_company_read,
)
from .company_source_adapter_registry import CompanySourceAdapterRegistry
from .live_company_reality import LiveSourceBindingPolicy
from .live_company_source_runtime import ReadOnlySourcePlan
from .mission_execution import CapabilityExecutionOutcome, CapabilityHandler
from .mission_runtime import MissionDefinition, MissionStep, StepCheckpoint

COMPANY_READ_MISSION_BRIDGE_CONTRACT = "eay-company-read-mission-bridge-v1"

CompanyReadEvidenceWriter = Callable[[CompanySourceExecutionReceipt], str]


@dataclass(frozen=True)
class CompanyReadMissionBinding:
    capability_ref: str
    registry: CompanySourceAdapterRegistry
    plan: ReadOnlySourcePlan
    policy: LiveSourceBindingPolicy
    adapter_ref: str
    runtime_bindings: Mapping[str, CompanySourceRuntimeBinding]
    evidence_writer: CompanyReadEvidenceWriter


def build_company_read_capability_handler(
    binding: CompanyReadMissionBinding,
) -> CapabilityHandler:
    """Return a read-only mission handler backed by one exact reviewed route."""

    if not binding.capability_ref.strip():
        raise ValueError("company_read_bridge_requires_capability_ref")

    async def handler(
        definition: MissionDefinition,
        step: MissionStep,
        _state: StepCheckpoint,
        _idempotency_key: str,
    ) -> CapabilityExecutionOutcome:
        if definition.tenant_id != binding.plan.tenant_id:
            raise ValueError("company_read_bridge_tenant_mismatch")
        if step.side_effect:
            raise ValueError("company_read_bridge_forbids_side_effect_step")

        receipt = await asyncio.to_thread(
            execute_registered_company_read,
            registry=binding.registry,
            plan=binding.plan,
            policy=binding.policy,
            adapter_ref=binding.adapter_ref,
            runtime_bindings=binding.runtime_bindings,
        )
        if receipt.truth_promoted or receipt.execution_authority_granted:
            raise ValueError("company_read_bridge_authority_escalation_detected")

        evidence_ref = binding.evidence_writer(receipt)
        if not evidence_ref.strip():
            raise ValueError("company_read_bridge_evidence_writer_returned_empty_ref")

        batch = receipt.collection.batch
        route_ref = (
            "company-source-route://"
            + receipt.route.adapter_ref.removeprefix("adapter://")
            + "/"
            + receipt.route.operation_ref
        )
        return CapabilityExecutionOutcome(
            succeeded=True,
            effect_verified=False,
            evidence_refs=tuple(
                dict.fromkeys(
                    (
                        evidence_ref,
                        batch.evidence_ref,
                        batch.source_receipt_ref,
                        route_ref,
                    )
                )
            ),
        )

    return handler
