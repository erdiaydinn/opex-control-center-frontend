"""Admin-governed paid-token composition for the Jarvis engine gateway.

This is the application-facing gateway for paid frontier execution. Local
Ollama execution remains free/default. Any external frontier invocation first
requires an exact platform-admin grant, an active rate card, budget headroom and
an exact user/tenant billing context. Successful provider usage is settled into
a chargeback receipt using actual provider-reported token counts.

Routing is local-first before model selection. If the canonical intelligence
router can produce an executable plan from local engines alone, frontier grants,
ledgers and provider candidates are not consulted. Only when local execution is
insufficient may frontier engines enter the candidate set, and each such engine
must pass paid-token authorization before canonical routing can select it. This
prevents a higher benchmark score from turning an otherwise serviceable local
request into an unauthorized/over-budget frontier failure.
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
from .intelligence_router import IntelligenceRoutingPlan, IntelligenceTask, route_intelligence
from .paid_token_governance import (
    PaidTokenAuthorization,
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

    def _plan_for_engine_ids(
        self,
        *,
        task: IntelligenceTask,
        engine_ids: tuple[str, ...],
    ) -> IntelligenceRoutingPlan:
        unknown = set(engine_ids) - set(self._registrations)
        if unknown:
            raise EngineGatewayError(
                "paid_token_candidate_engine_not_registered:" + ",".join(sorted(unknown))
            )
        profiles = [self._registrations[engine_id].profile for engine_id in engine_ids]
        return route_intelligence(task, profiles)

    def _authorization_request(
        self,
        *,
        registration: RegisteredEngine,
        prompt: str,
        context: PaidTokenExecutionContext,
    ) -> PaidTokenInvocationRequest:
        endpoint = registration.endpoint
        return PaidTokenInvocationRequest(
            subject_user_ref=context.subject_user_ref,
            tenant_ref=context.tenant_ref,
            provider=endpoint.provider.value,
            model_id=endpoint.model_id,
            estimated_input_tokens=self._conservative_input_token_reservation(prompt),
            requested_max_output_tokens=endpoint.max_output_tokens,
            billing_cycle_ref=context.billing_cycle_ref,
            requested_at=context.requested_at,
        )

    def _authorize_frontier_candidate(
        self,
        *,
        registration: RegisteredEngine,
        prompt: str,
        context: PaidTokenExecutionContext,
    ) -> PaidTokenAuthorization:
        endpoint = registration.endpoint
        if endpoint.provider is EngineProvider.OLLAMA:
            raise ValueError("paid_token_local_engine_does_not_require_authorization")
        ledger = self._ledger_reader(context, endpoint.engine_id)
        return authorize_paid_token_invocation(
            request=self._authorization_request(
                registration=registration,
                prompt=prompt,
                context=context,
            ),
            grants=self._grants,
            rate_cards=self._rate_cards,
            ledger=ledger,
        )

    async def _invoke_exact_plan_primary(
        self,
        *,
        task: IntelligenceTask,
        prompt: str,
        plan: IntelligenceRoutingPlan,
    ) -> EngineInvocationReceipt:
        engine_id = plan.primary_engine_id or ""
        registration = self._registrations.get(engine_id)
        if registration is None:
            raise EngineGatewayError("paid_token_gateway_selected_engine_not_registered")
        # The governed wrapper has already restricted the candidate set and the
        # canonical router produced `plan`. Invoke that exact registration so a
        # second unrestricted route cannot drift to an unauthorized frontier.
        return await self._engine_gateway._invoke_registered(
            task=task,
            prompt=prompt,
            plan=plan,
            registration=registration,
        )

    @staticmethod
    def _routing_error(plan: IntelligenceRoutingPlan) -> EngineGatewayError:
        return EngineGatewayError(
            "engine_routing_plan_not_executable:" + ",".join(plan.blockers)
        )

    async def invoke_primary(
        self,
        *,
        task: IntelligenceTask,
        prompt: str,
        context: PaidTokenExecutionContext,
    ) -> GovernedEngineInvocationReceipt:
        if not prompt.strip():
            raise ValueError("engine_gateway_prompt_required")

        local_ids = tuple(
            sorted(
                engine_id
                for engine_id, registration in self._registrations.items()
                if registration.endpoint.provider is EngineProvider.OLLAMA
            )
        )
        local_plan = self._plan_for_engine_ids(task=task, engine_ids=local_ids)
        if local_plan.execution_permitted and local_plan.primary_engine_id:
            receipt = await self._invoke_exact_plan_primary(
                task=task,
                prompt=prompt,
                plan=local_plan,
            )
            if receipt.external_processing:
                raise EngineGatewayError("paid_token_local_plan_resolved_external_engine")
            return GovernedEngineInvocationReceipt(
                engine_receipt=receipt,
                local_free_execution=True,
            )

        authorizations: dict[str, PaidTokenAuthorization] = {}
        denied_blockers: list[str] = []
        frontier_ids = tuple(
            sorted(
                engine_id
                for engine_id, registration in self._registrations.items()
                if registration.endpoint.provider is not EngineProvider.OLLAMA
            )
        )
        for engine_id in frontier_ids:
            authorization = self._authorize_frontier_candidate(
                registration=self._registrations[engine_id],
                prompt=prompt,
                context=context,
            )
            if authorization.decision is PaidTokenDecision.ALLOW:
                authorizations[engine_id] = authorization
            else:
                denied_blockers.extend(authorization.blockers)

        governed_candidate_ids = tuple((*local_ids, *sorted(authorizations)))
        governed_plan = self._plan_for_engine_ids(
            task=task,
            engine_ids=governed_candidate_ids,
        )
        if not governed_plan.execution_permitted or not governed_plan.primary_engine_id:
            if not authorizations and denied_blockers:
                raise EngineGatewayError(
                    "paid_token_not_authorized:"
                    + ",".join(dict.fromkeys(denied_blockers))
                )
            raise self._routing_error(governed_plan)

        selected = self._registrations.get(governed_plan.primary_engine_id)
        if selected is None:
            raise EngineGatewayError("paid_token_gateway_selected_engine_not_registered")
        endpoint = selected.endpoint
        if endpoint.provider is EngineProvider.OLLAMA:
            receipt = await self._invoke_exact_plan_primary(
                task=task,
                prompt=prompt,
                plan=governed_plan,
            )
            if receipt.external_processing:
                raise EngineGatewayError("paid_token_local_plan_resolved_external_engine")
            return GovernedEngineInvocationReceipt(
                engine_receipt=receipt,
                local_free_execution=True,
            )

        authorization = authorizations.get(endpoint.engine_id)
        if authorization is None or authorization.decision is not PaidTokenDecision.ALLOW:
            raise EngineGatewayError("paid_token_selected_frontier_missing_pre_authorization")

        receipt = await self._invoke_exact_plan_primary(
            task=task,
            prompt=prompt,
            plan=governed_plan,
        )
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
