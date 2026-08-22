"""Production-only engine composition for Jarvis.

The low-level :class:`EngineGateway` remains useful for adapter tests and
benchmark harnesses, but production application code must receive only this
runtime. The raw gateway is created inside the builder and is never exposed by
its public API. Every user invocation carries an exact user/tenant/billing
context and therefore reaches external frontier providers only through
``AdminGovernedEngineGateway``. Local Ollama remains free/default.

For certification-required tasks, a candidate-admission policy may be injected
at the composition root. That policy can only remove engines; it never grants
spend or execution authority. Frontier councils additionally require the
canonical agent-budget ledger; production never exposes the low-level routed
multi-engine bypass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import httpx

from .agent_budget_ledger import AgentBudgetLedgerPort
from .engine_candidate_admission import EngineCandidateAdmission
from .engine_gateway import EngineEndpoint, EngineGateway, EngineGatewayError, RegisteredEngine
from .frontier_supremacy_intelligence import SupremacyRequest
from .governed_frontier_council_runtime import (
    FrontierCouncilBudgetBinding,
    GovernedFrontierCouncilResult,
    execute_governed_frontier_supremacy,
)
from .intelligence_router import IntelligenceTask
from .paid_token_engine_gateway import (
    AdminGovernedEngineGateway,
    GovernedEngineInvocationReceipt,
    LedgerReader,
    PaidTokenExecutionContext,
    UsageWriter,
)
from .paid_token_governance import PaidTokenGrant, ProviderRateCard

PRODUCTION_ENGINE_RUNTIME_CONTRACT = "eay-production-engine-runtime-v2"

TransportFactory = Callable[
    [EngineEndpoint], httpx.AsyncBaseTransport | None
]


@dataclass(frozen=True)
class ProductionEngineRuntime:
    """Application-facing Jarvis inference runtime."""

    _governed_gateway: AdminGovernedEngineGateway
    _budget_ledger: AgentBudgetLedgerPort | None = None
    contract: str = PRODUCTION_ENGINE_RUNTIME_CONTRACT

    async def invoke_primary(
        self,
        *,
        task: IntelligenceTask,
        prompt: str,
        context: PaidTokenExecutionContext,
    ) -> GovernedEngineInvocationReceipt:
        return await self._governed_gateway.invoke_primary(
            task=task,
            prompt=prompt,
            context=context,
        )

    async def execute_frontier_council(
        self,
        *,
        request: SupremacyRequest,
        context: PaidTokenExecutionContext,
        budget: FrontierCouncilBudgetBinding,
    ) -> GovernedFrontierCouncilResult:
        """Execute Frontier deliberation without exposing raw routed engines."""

        if self._budget_ledger is None:
            raise EngineGatewayError(
                "production_frontier_council_budget_ledger_required"
            )
        return await execute_governed_frontier_supremacy(
            gateway=self._governed_gateway,
            request=request,
            context=context,
            budget_ledger=self._budget_ledger,
            budget=budget,
        )

    @property
    def raw_gateway_exposed(self) -> bool:
        return False

    @property
    def governed_frontier_council_enabled(self) -> bool:
        return self._budget_ledger is not None


def build_production_engine_runtime(
    *,
    registrations: tuple[RegisteredEngine, ...],
    grants: tuple[PaidTokenGrant, ...],
    rate_cards: tuple[ProviderRateCard, ...],
    ledger_reader: LedgerReader,
    usage_writer: UsageWriter,
    transport_factory: TransportFactory | None = None,
    environ: dict[str, str] | None = None,
    candidate_admission: EngineCandidateAdmission | None = None,
    budget_ledger: AgentBudgetLedgerPort | None = None,
) -> ProductionEngineRuntime:
    """Build the only supported production user-execution composition.

    External provider registrations may exist without an active user grant;
    that is safe because ``AdminGovernedEngineGateway`` authorizes the exact
    selected provider/model/user/tenant/billing context before the low-level
    gateway is invoked. For certification-required tasks, unadmitted engines are
    removed before paid authorization and provider traffic. Multi-engine
    Frontier execution is enabled only when a durable agent-budget ledger is
    injected and remains behind ``execute_frontier_council``.
    """

    low_level_gateway = EngineGateway(
        list(registrations),
        transport_factory=transport_factory,
        environ=environ,
    )
    governed_gateway = AdminGovernedEngineGateway(
        engine_gateway=low_level_gateway,
        registrations=registrations,
        grants=grants,
        rate_cards=rate_cards,
        ledger_reader=ledger_reader,
        usage_writer=usage_writer,
        candidate_admission=candidate_admission,
    )
    return ProductionEngineRuntime(
        _governed_gateway=governed_gateway,
        _budget_ledger=budget_ledger,
    )
