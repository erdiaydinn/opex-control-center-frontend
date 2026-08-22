"""Local-first production inference composition for Jarvis.

The production decision order is:
1. select a license-cleared, benchmarked, reachable local specialist;
2. optionally use evidence-bound historical efficiency to break ties only inside
   a narrow quality band;
3. for certification-required tasks, require a fresh exact engine/domain
   capability admission before local execution;
4. invoke that exact local engine with no paid-token ledger activity;
5. only when no qualified local specialist exists, enter the existing
   platform-admin governed paid-frontier runtime.

The local-pool decision never authorizes spend. Efficiency evidence never rewrites
benchmark quality and never grants execution authority. Paid escalation remains
subject to the exact user/tenant/provider/model grant and billing controls already
implemented by ProductionEngineRuntime/AdminGovernedEngineGateway.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import httpx
from pydantic import BaseModel, model_validator

from .engine_candidate_admission import EngineCandidateAdmission
from .engine_efficiency_intelligence import (
    EngineEfficiencyLedgerSnapshot,
    EngineEfficiencyRoutingPolicy,
    select_local_model_with_efficiency,
)
from .engine_gateway import (
    EngineEndpoint,
    EngineGateway,
    EngineInvocationReceipt,
    EngineProvider,
    RegisteredEngine,
)
from .intelligence_router import (
    IntelligenceTask,
    route_intelligence,
)
from .local_model_pool import (
    LocalModelCatalog,
    LocalModelDeployment,
    LocalModelSelection,
    LocalModelTask,
    select_local_model,
)
from .paid_token_engine_gateway import (
    GovernedEngineInvocationReceipt,
    PaidTokenExecutionContext,
)
from .production_engine_runtime import ProductionEngineRuntime

LOCAL_FIRST_ENGINE_RUNTIME_CONTRACT = "eay-local-first-engine-runtime-v1"

TransportFactory = Callable[
    [EngineEndpoint], httpx.AsyncBaseTransport | None
]


class LocalFirstInvocationReceipt(BaseModel):
    contract: str = LOCAL_FIRST_ENGINE_RUNTIME_CONTRACT
    selection: LocalModelSelection
    local_receipt: EngineInvocationReceipt | None = None
    frontier_receipt: GovernedEngineInvocationReceipt | None = None
    paid_frontier_used: bool = False

    @model_validator(mode="after")
    def exactly_one_execution_path(self) -> "LocalFirstInvocationReceipt":
        local = self.local_receipt is not None
        frontier = self.frontier_receipt is not None
        if local == frontier:
            raise ValueError(
                "local_first_runtime_requires_exactly_one_execution_path"
            )
        if local:
            if (
                not self.selection.local_execution_available
                or self.paid_frontier_used
            ):
                raise ValueError(
                    "local_first_local_receipt_state_mismatch"
                )
            if (
                self.local_receipt
                and self.local_receipt.external_processing
            ):
                raise ValueError(
                    "local_first_local_receipt_cannot_be_external"
                )
        else:
            if not self.selection.paid_frontier_escalation_required:
                raise ValueError(
                    "local_first_frontier_receipt_requires_local_escalation"
                )
            if not self.paid_frontier_used:
                raise ValueError(
                    "local_first_frontier_receipt_must_mark_paid_path"
                )
        return self


@dataclass(frozen=True)
class LocalFirstProductionRuntime:
    catalog: LocalModelCatalog
    deployments: tuple[LocalModelDeployment, ...]
    local_registrations: tuple[RegisteredEngine, ...]
    frontier_runtime: ProductionEngineRuntime
    transport_factory: TransportFactory | None = None
    environ: dict[str, str] | None = None
    efficiency_snapshot: EngineEfficiencyLedgerSnapshot | None = None
    efficiency_policy: EngineEfficiencyRoutingPolicy | None = None
    candidate_admission: EngineCandidateAdmission | None = None

    def __post_init__(self) -> None:
        local_ids = [
            item.profile.engine_id for item in self.local_registrations
        ]
        if len(local_ids) != len(set(local_ids)):
            raise ValueError(
                "local_first_runtime_duplicate_local_engine"
            )
        for item in self.local_registrations:
            if (
                item.endpoint.provider is not EngineProvider.OLLAMA
                or not item.profile.local_processing
            ):
                raise ValueError(
                    "local_first_runtime_local_registration_must_be_ollama"
                )
        deployment_ids = {
            item.deployment_id for item in self.deployments
        }
        missing = set(local_ids) - deployment_ids
        if missing:
            raise ValueError(
                "local_first_runtime_registration_without_deployment"
            )

    def _registration(self, deployment_id: str) -> RegisteredEngine:
        matches = [
            item
            for item in self.local_registrations
            if item.profile.engine_id == deployment_id
        ]
        if len(matches) != 1:
            raise ValueError(
                "local_first_runtime_selected_deployment_registration_missing"
            )
        return matches[0]

    def _admitted_local_ids(
        self,
        *,
        task: IntelligenceTask,
        context: PaidTokenExecutionContext,
    ) -> frozenset[str] | None:
        if not task.requires_fresh_certification:
            return None
        if self.candidate_admission is None:
            return frozenset()
        return frozenset(
            item.profile.engine_id
            for item in self.local_registrations
            if self.candidate_admission.is_admitted(
                task=task,
                registration=item,
                requested_at=context.requested_at,
                tenant_ref=context.tenant_ref,
                company_ref=context.company_ref,
            )
        )

    def _select_local(
        self,
        *,
        local_task: LocalModelTask,
        task: IntelligenceTask,
        context: PaidTokenExecutionContext,
    ) -> LocalModelSelection:
        deployments = self.deployments
        admitted_ids = self._admitted_local_ids(
            task=task,
            context=context,
        )
        if admitted_ids is not None:
            deployments = tuple(
                item
                for item in deployments
                if item.deployment_id in admitted_ids
            )

        if self.efficiency_snapshot is None:
            return select_local_model(
                task=local_task,
                deployments=deployments,
                catalog=self.catalog,
            )
        return select_local_model_with_efficiency(
            task=local_task,
            deployments=deployments,
            catalog=self.catalog,
            ledger=self.efficiency_snapshot,
            tenant_id=context.tenant_ref,
            as_of=context.requested_at,
            policy=self.efficiency_policy,
        )

    async def invoke_primary(
        self,
        *,
        local_task: LocalModelTask,
        task: IntelligenceTask,
        prompt: str,
        context: PaidTokenExecutionContext,
    ) -> LocalFirstInvocationReceipt:
        selection = self._select_local(
            local_task=local_task,
            task=task,
            context=context,
        )
        if selection.local_execution_available:
            registration = self._registration(
                selection.deployment_id or ""
            )
            if registration.endpoint.model_id != selection.model_id:
                raise ValueError(
                    "local_first_runtime_model_identity_mismatch"
                )

            certified_ids: frozenset[str] | None = None
            certification_ref: str | None = None
            if task.requires_fresh_certification:
                if self.candidate_admission is None:
                    raise ValueError(
                        "local_first_fresh_certification_admission_missing"
                    )
                certified_ids = frozenset(
                    {registration.profile.engine_id}
                )
                certification_ref = (
                    self.candidate_admission.receipt_ref(
                        task=task,
                        requested_at=context.requested_at,
                        tenant_ref=context.tenant_ref,
                        company_ref=context.company_ref,
                    )
                )
            plan = route_intelligence(
                task,
                [registration.profile],
                certified_engine_ids=certified_ids,
                certification_admission_ref=certification_ref,
            )
            if not plan.execution_permitted:
                raise ValueError(
                    "local_first_selected_engine_not_routable:"
                    + ",".join(plan.blockers)
                )

            local_gateway = EngineGateway(
                [registration],
                transport_factory=self.transport_factory,
                environ=self.environ,
            )
            receipt = await local_gateway._invoke_registered(
                task=task,
                prompt=prompt,
                plan=plan,
                registration=registration,
            )
            return LocalFirstInvocationReceipt(
                selection=selection,
                local_receipt=receipt,
                paid_frontier_used=False,
            )

        frontier = await self.frontier_runtime.invoke_primary(
            task=task,
            prompt=prompt,
            context=context,
        )
        return LocalFirstInvocationReceipt(
            selection=selection,
            frontier_receipt=frontier,
            paid_frontier_used=True,
        )
