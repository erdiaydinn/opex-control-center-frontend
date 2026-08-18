"""Production-only engine composition for Jarvis.

The low-level :class:`EngineGateway` remains useful for adapter tests and
benchmark harnesses, but production application code must receive only this
runtime. The raw gateway is created inside the builder and is never exposed by
its public API. Every user invocation carries an exact user/tenant/billing
context and therefore reaches external frontier providers only through
``AdminGovernedEngineGateway``. Local Ollama remains free/default.

This is an application-architecture boundary, not a claim that Python private
attributes are a cryptographic sandbox. Deployment code should construct one
runtime at the composition root and inject only ``ProductionEngineRuntime``
into request handlers, agents and background workers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import httpx

from .engine_gateway import EngineEndpoint, EngineGateway, EngineInvocationReceipt, RegisteredEngine
from .intelligence_router import IntelligenceTask
from .paid_token_engine_gateway import (
    AdminGovernedEngineGateway,
    GovernedEngineInvocationReceipt,
    LedgerReader,
    PaidTokenExecutionContext,
    UsageWriter,
)
from .paid_token_governance import PaidTokenGrant, ProviderRateCard

PRODUCTION_ENGINE_RUNTIME_CONTRACT = "eay-production-engine-runtime-v1"

TransportFactory = Callable[[EngineEndpoint], httpx.AsyncBaseTransport | None]


@dataclass(frozen=True)
class ProductionEngineRuntime:
    """Application-facing Jarvis inference runtime.

    Only the governed gateway is retained. There is deliberately no public
    ``engine_gateway`` property or ungoverned invoke method.
    """

    _governed_gateway: AdminGovernedEngineGateway
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

    @property
    def raw_gateway_exposed(self) -> bool:
        return False


def build_production_engine_runtime(
    *,
    registrations: tuple[RegisteredEngine, ...],
    grants: tuple[PaidTokenGrant, ...],
    rate_cards: tuple[ProviderRateCard, ...],
    ledger_reader: LedgerReader,
    usage_writer: UsageWriter,
    transport_factory: TransportFactory | None = None,
    environ: dict[str, str] | None = None,
) -> ProductionEngineRuntime:
    """Build the only supported production user-execution composition.

    External provider registrations may exist without an active user grant;
    that is safe because ``AdminGovernedEngineGateway`` authorizes the exact
    selected provider/model/user/tenant/billing context before the low-level
    gateway is invoked. Local engines never create paid usage receipts.
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
    )
    return ProductionEngineRuntime(_governed_gateway=governed_gateway)
