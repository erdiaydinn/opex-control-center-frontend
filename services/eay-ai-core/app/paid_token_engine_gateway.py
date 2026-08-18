"""Admin-governed paid-token composition for the Jarvis engine gateway.

This is the application-facing gateway for paid frontier execution. Local
Ollama execution remains free/default. Any external frontier invocation first
requires an exact platform-admin grant, an active rate card, budget headroom and
an exact user/tenant billing context. Successful provider usage is settled into
a chargeback receipt using actual provider-reported token counts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from pydantic import BaseModel, Field, model_validator

from .engine_gateway import (
    EngineGateway,
    EngineGatewayError,
    EngineInvocationReceipt,
    EngineProvider,
    RegisteredEngine,
)
from .intelligence_router import IntelligenceTask
from .paid_token_governance import (
    PaidTokenDecision,
    PaidTokenGrant,
    PaidTokenInvocationRequest,
    PaidTokenLedgerSnapshot,
    PaidTokenUsageReceipt,
    ProviderRateCard,
    authorize_paid_token_invocation,
    settle_paid_token_usage,
)

PAID_TOKEN_ENGINE_GATEWAY_CONTRACT = "eay-paid-token-engine-gateway-v1"


class PaidTokenExecutionContext(BaseModel):
    subject_user_ref: str = Field(min_length=1)
    tenant_ref: str = Field(min_length=1)
    billing_cycle_ref: str = Field(min_length=1)
    requested_at: datetime

    @model_validator(mode="after")
    def context_requires_timezone(self) -> "PaidTokenExecutionContext":
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("paid_token_execution_context_requires_timezone")
        return self


class GovernedEngineInvocationReceipt(BaseModel):
    contract: str = PAID_TOKEN_ENGINE_GATEWAY_CONTRACT
    engine_receipt: EngineInvocationReceipt
    paid_usage: PaidTokenUsageReceipt | None = None
    local_free_execution: bool = False

    @model_validator(mode="after")
    def receipt_matches_execution_class(self) -> "GovernedEngineInvocationReceipt":
        if self.engine_receipt.external_processing:
            if self.local_free_execution or self.paid_usage is None:
                raise ValueError("external_engine_execution_requires_paid_usage_receipt")
        elif not self.local_free_execution or self.paid_usage is not None:
            raise ValueError("local_engine_execution_must_be_free_and_unbilled")
        return self


LedgerReader = Callable[[PaidTokenExecutionContext, str], PaidTokenLedgerSnapshot | None]
UsageWriter = Callable[[PaidTokenUsageReceipt], None]


class AdminGovernedEngineGateway:
    def __init__(
        self,
        *,
        engine_gateway: EngineGateway,
        registrations: tuple[RegisteredEngine, ...],
        grants: tuple[PaidTokenGrant, ...],
        rate_cards: tuple[ProviderRateCard, ...],
        ledger_reader: LedgerReader,
        usage_writer: UsageWriter,
    ) -> None:
        ids = [item.profile.engine_id for item in registrations]
        if len(ids) != len(set(ids)):
            raise ValueError("paid_token_gateway_duplicate_engine_registration")
        self._engine_gateway = engine_gateway
        self._registrations = {item.profile.engine_id: item for item in registrations}
        self._grants = grants
        self._rate_cards = rate_cards
        self._ledger_reader = ledger_reader
        self._usage_writer = usage_writer

    @staticmethod
    def _conservative_input_token_reservation(prompt: str) -> int:
        # Frontier tokenizers operate over encoded text. UTF-8 byte length is a
        # deliberately conservative provider-independent reservation quantity;
        # actual provider usage remains the billing truth after execution.
        return max(1, len(prompt.encode("utf-8")))

    def _matching_grant(self, grant_id: str) -> PaidTokenGrant:
        matches = [item for item in self._grants if item.grant_id == grant_id]
        if len(matches) != 1:
            raise EngineGatewayError("paid_token_settlement_grant_not_unique")
        return matches[0]

    def _matching_rate_card(self, rate_card_ref: str) -> ProviderRateCard:
        matches = [item for item in self._rate_cards if item.rate_card_ref == rate_card_ref]
        if len(matches) != 1:
            raise EngineGatewayError("paid_token_settlement_rate_card_not_unique")
        return matches[0]

    async def invoke_primary(
        self,
        *,
        task: IntelligenceTask,
        prompt: str,
        context: PaidTokenExecutionContext,
    ) -> GovernedEngineInvocationReceipt:
        if not prompt.strip():
            raise ValueError("engine_gateway_prompt_required")
        plan = self._engine_gateway.plan(task)
        if not plan.execution_permitted or not plan.primary_engine_id:
            raise EngineGatewayError("engine_routing_plan_not_executable:" + ",".join(plan.blockers))
        registration = self._registrations.get(plan.primary_engine_id)
        if registration is None:
            raise EngineGatewayError("paid_token_gateway_selected_engine_not_registered")
        endpoint = registration.endpoint

        if endpoint.provider is EngineProvider.OLLAMA:
            receipt = await self._engine_gateway.invoke_primary(task=task, prompt=prompt)
            return GovernedEngineInvocationReceipt(
                engine_receipt=receipt,
                local_free_execution=True,
            )

        ledger = self._ledger_reader(context, endpoint.engine_id)
        request = PaidTokenInvocationRequest(
            subject_user_ref=context.subject_user_ref,
            tenant_ref=context.tenant_ref,
            provider=endpoint.provider.value,
            model_id=endpoint.model_id,
            estimated_input_tokens=self._conservative_input_token_reservation(prompt),
            requested_max_output_tokens=endpoint.max_output_tokens,
            billing_cycle_ref=context.billing_cycle_ref,
            requested_at=context.requested_at,
        )
        authorization = authorize_paid_token_invocation(
            request=request,
            grants=self._grants,
            rate_cards=self._rate_cards,
            ledger=ledger,
        )
        if authorization.decision is not PaidTokenDecision.ALLOW:
            raise EngineGatewayError(
                "paid_token_not_authorized:" + ",".join(authorization.blockers)
            )

        receipt = await self._engine_gateway.invoke_primary(task=task, prompt=prompt)
        if receipt.engine_id != endpoint.engine_id or receipt.provider is not endpoint.provider:
            raise EngineGatewayError("paid_token_engine_changed_after_authorization")
        if receipt.input_tokens is None or receipt.output_tokens is None:
            raise EngineGatewayError("paid_token_provider_usage_missing")
        if receipt.input_tokens + receipt.output_tokens > self._matching_grant(
            authorization.grant_id or ""
        ).max_total_tokens_per_request:
            raise EngineGatewayError("paid_token_actual_total_tokens_exceeded_authorized_limit")

        grant = self._matching_grant(authorization.grant_id or "")
        rate_card = self._matching_rate_card(authorization.rate_card_ref or "")
        usage = settle_paid_token_usage(
            authorization=authorization,
            grant=grant,
            rate_card=rate_card,
            input_tokens=receipt.input_tokens,
            output_tokens=receipt.output_tokens,
            settled_at=context.requested_at,
            provider_response_ref=receipt.provider_response_id,
        )
        self._usage_writer(usage)
        return GovernedEngineInvocationReceipt(
            engine_receipt=receipt,
            paid_usage=usage,
            local_free_execution=False,
        )
