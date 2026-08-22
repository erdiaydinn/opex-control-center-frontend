"""Production-governed Frontier council execution for Jarvis.

This module is an adapter over the existing ``AdminGovernedEngineGateway`` and
canonical ``AgentBudgetLedgerPort``.  It deliberately does not implement a new
router, provider gateway, scheduler, or billing truth.

A Frontier deliberation binds one immutable routing plan.  Before the first
external provider call, the maximum bounded deliberation envelope is reserved
atomically in the canonical agent budget ledger.  Every invocation is then
revalidated against current certification, provider registration, credential,
admin-grant and rate-card state.  Actual provider usage is settled through the
existing paid-token ledger and consumed from the reservation.  Unused budget is
released; uncertain provider effects keep the remainder conservatively held.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agent_budget_ledger import (
    AgentBudgetLedgerPort,
    BudgetAccount,
    BudgetMutation,
    BudgetMutationKind,
    BudgetTransaction,
    BudgetVector,
    execute_budget_transaction,
)
from .engine_gateway import (
    EngineGatewayError,
    EngineInvocationReceipt,
    EngineProvider,
    RegisteredEngine,
)
from .frontier_supremacy_intelligence import (
    SupremacyRequest,
    SupremacyResult,
    execute_frontier_supremacy,
)
from .intelligence_router import IntelligenceRoutingPlan, IntelligenceTask
from .paid_token_engine_gateway import (
    AdminGovernedEngineGateway,
    PaidTokenExecutionContext,
)
from .paid_token_governance import (
    PaidTokenAuthorization,
    PaidTokenDecision,
    PaidTokenUsageReceipt,
    settle_paid_token_usage,
)

GOVERNED_FRONTIER_COUNCIL_CONTRACT = "eay-governed-frontier-council-runtime-v1"
_SCOPE = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$"

# frontier_supremacy_intelligence has at most solver+synthesis+repair direct
# primary calls and attack+verify+second-verify routed waves.  The session also
# enforces these limits at runtime, so a future protocol expansion fails closed
# until this reservation envelope is intentionally upgraded.
_MAX_DIRECT_PRIMARY_CALLS = 3
_MAX_ROUTED_WAVES = 3


class FrontierCouncilBudgetBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_ref: str = Field(pattern=_SCOPE)
    tenant_id: str = Field(pattern=_SCOPE)
    root_account_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)


class FrontierCouncilRuntimeReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract: str = GOVERNED_FRONTIER_COUNCIL_CONTRACT
    session_ref: str
    task_id: str
    selected_engine_ids: tuple[str, ...]
    reservation_ref: str | None = None
    reserved_budget: BudgetVector = Field(default_factory=BudgetVector)
    consumed_budget: BudgetVector = Field(default_factory=BudgetVector)
    uncertain_effect_held: bool = False
    finalized: bool
    execution_authority_granted: bool = False
    company_truth_promoted: bool = False
    provider_authority_granted: bool = False

    @model_validator(mode="after")
    def never_mints_authority(self) -> "FrontierCouncilRuntimeReceipt":
        if (
            self.execution_authority_granted
            or self.company_truth_promoted
            or self.provider_authority_granted
        ):
            raise ValueError("frontier_council_runtime_never_mints_authority")
        return self


class GovernedFrontierCouncilResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract: str = GOVERNED_FRONTIER_COUNCIL_CONTRACT
    result: SupremacyResult
    runtime: FrontierCouncilRuntimeReceipt


Clock = Callable[[], datetime]


def _seal(value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _plus(left: BudgetVector, right: BudgetVector) -> BudgetVector:
    return left.plus(right)


def _micro_cost(*, tokens: int, rate_per_million: int) -> int:
    if tokens <= 0 or rate_per_million <= 0:
        return 0
    return (tokens * rate_per_million + 999_999) // 1_000_000


def _billable(*, provider_cost: int, multiplier_basis_points: int) -> int:
    if provider_cost <= 0 or multiplier_basis_points <= 0:
        return 0
    return (provider_cost * multiplier_basis_points + 9_999) // 10_000


def _task_fingerprint(task: IntelligenceTask) -> str:
    return _seal(task.model_dump(mode="json"))


def _registration_fingerprint(registration: RegisteredEngine) -> str:
    return _seal(registration.model_dump(mode="json"))


class GovernedFrontierCouncilSession:
    """Bound gateway protocol consumed by ``execute_frontier_supremacy``.

    The class only composes already-authoritative layers.  The canonical router
    still chooses the engines and the canonical paid-token gateway still owns
    provider authorization/accounting.
    """

    def __init__(
        self,
        *,
        gateway: AdminGovernedEngineGateway,
        context: PaidTokenExecutionContext,
        budget_ledger: AgentBudgetLedgerPort,
        budget: FrontierCouncilBudgetBinding,
        clock: Clock | None = None,
    ) -> None:
        if budget.tenant_id != context.tenant_ref:
            raise ValueError("frontier_council_budget_tenant_mismatch")
        self._gateway = gateway
        self._context = context
        self._budget_ledger = budget_ledger
        self._budget = budget
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._plan: IntelligenceRoutingPlan | None = None
        self._task_fingerprint: str | None = None
        self._selected: tuple[str, ...] = ()
        self._registration_fingerprints: dict[str, str] = {}
        self._preflight_authorizations: dict[str, PaidTokenAuthorization] = {}
        self._certification_ref: str | None = None
        self._reservation_ref: str | None = None
        self._reserved = BudgetVector()
        self._consumed = BudgetVector()
        self._direct_primary_calls = 0
        self._routed_waves = 0
        self._uncertain_effect = False
        self._finalized = False

    def _live_context(self) -> PaidTokenExecutionContext:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("frontier_council_clock_requires_timezone")
        return self._context.model_copy(update={"requested_at": now})

    def _scope_guard(self, task: IntelligenceTask) -> None:
        if task.tenant_id != self._context.tenant_ref:
            raise EngineGatewayError("frontier_council_task_tenant_mismatch")
        if self._context.company_ref is None or task.company_id != self._context.company_ref:
            raise EngineGatewayError("frontier_council_task_company_mismatch")

    def _credential_ready(self, registration: RegisteredEngine) -> bool:
        endpoint = registration.endpoint
        if endpoint.provider is EngineProvider.OLLAMA:
            return True
        secret_ref = endpoint.secret_ref or ""
        if not secret_ref.startswith("env:"):
            return False
        key = secret_ref.removeprefix("env:").strip()
        environ = getattr(self._gateway._engine_gateway, "_environ", {})
        return bool(key and isinstance(environ, dict) and environ.get(key, ""))

    def _block_plan(
        self, plan: IntelligenceRoutingPlan, *blockers: str
    ) -> IntelligenceRoutingPlan:
        combined = tuple(dict.fromkeys((*plan.blockers, *blockers)))
        return plan.model_copy(
            update={
                "primary_engine_id": None,
                "critic_engine_ids": (),
                "execution_permitted": False,
                "human_review_required": True,
                "blockers": combined,
            }
        )

    def _reservation_budget(
        self,
        *,
        selected: tuple[str, ...],
        authorizations: dict[str, PaidTokenAuthorization],
    ) -> BudgetVector:
        total = BudgetVector()
        primary = selected[0] if selected else ""
        for engine_id in selected:
            registration = self._gateway._registrations[engine_id]
            if registration.endpoint.provider is EngineProvider.OLLAMA:
                continue
            authorization = authorizations[engine_id]
            grant = self._gateway._matching_grant(authorization.grant_id or "")
            rate_card = self._gateway._matching_rate_card(
                authorization.rate_card_ref or ""
            )
            calls = _MAX_ROUTED_WAVES + (
                _MAX_DIRECT_PRIMARY_CALLS if engine_id == primary else 0
            )
            max_tokens = grant.max_total_tokens_per_request
            provider_cost = _micro_cost(
                tokens=max_tokens,
                rate_per_million=max(
                    rate_card.input_cost_microunits_per_million_tokens,
                    rate_card.output_cost_microunits_per_million_tokens,
                ),
            )
            billable = _billable(
                provider_cost=provider_cost,
                multiplier_basis_points=grant.chargeback_multiplier_basis_points,
            )
            total = _plus(
                total,
                BudgetVector(
                    tokens=max_tokens * calls,
                    cost_units=max(provider_cost, billable) * calls,
                    wall_time_seconds=math.ceil(registration.endpoint.timeout_seconds)
                    * calls,
                    tool_calls=calls,
                ),
            )
        return total

    def _account(self) -> BudgetAccount:
        account = self._budget_ledger.get_account(
            tenant_id=self._budget.tenant_id,
            account_id=self._budget.account_id,
        )
        if account is None:
            raise EngineGatewayError("frontier_council_budget_account_missing")
        if account.root_account_id != self._budget.root_account_id:
            raise EngineGatewayError("frontier_council_budget_root_mismatch")
        return account

    def _transact(
        self,
        *,
        kind: BudgetMutationKind,
        amount: BudgetVector,
        operation: str,
    ) -> None:
        if amount.is_zero():
            return
        # CAS conflicts are expected under concurrent sessions.  Re-read the
        # account and retry the same idempotent logical operation a bounded
        # number of times; all other failures remain fail-closed.
        last_error: Exception | None = None
        fingerprint = _seal(
            {
                "session": self._budget.session_ref,
                "operation": operation,
                "kind": kind.value,
                "amount": amount.model_dump(mode="json"),
                "reservation": self._reservation_ref,
            }
        )
        for attempt in range(8):
            account = self._account()
            transaction = BudgetTransaction(
                transaction_id=f"frontier-council-txn:{self._budget.session_ref}:{operation}",
                idempotency_key=f"frontier-council:{self._budget.session_ref}:{operation}",
                request_fingerprint=fingerprint,
                tenant_id=self._budget.tenant_id,
                root_account_id=self._budget.root_account_id,
                mutations=(
                    BudgetMutation(
                        kind=kind,
                        account_id=self._budget.account_id,
                        expected_version=account.version,
                        amount=amount,
                        reservation_ref=self._reservation_ref,
                    ),
                ),
            )
            try:
                execute_budget_transaction(
                    port=self._budget_ledger, transaction=transaction
                )
                return
            except ValueError as exc:
                last_error = exc
                if "agent_budget_version_conflict" not in str(exc) or attempt == 7:
                    raise
        if last_error is not None:
            raise last_error

    def _reserve(self, amount: BudgetVector) -> None:
        if amount.is_zero():
            return
        self._reservation_ref = (
            f"frontier-council-reservation:{self._budget.session_ref}"
        )
        self._transact(
            kind=BudgetMutationKind.RESERVE,
            amount=amount,
            operation="reserve",
        )
        self._reserved = amount

    def _current_registration(self, engine_id: str) -> RegisteredEngine:
        registration = self._gateway._registrations.get(engine_id)
        if registration is None:
            raise EngineGatewayError("frontier_council_engine_removed_after_binding")
        if _registration_fingerprint(registration) != self._registration_fingerprints.get(
            engine_id
        ):
            raise EngineGatewayError("frontier_council_engine_registration_drift")
        return registration

    def _revalidate_binding(self, task: IntelligenceTask) -> PaidTokenExecutionContext:
        if self._plan is None or self._task_fingerprint is None:
            raise EngineGatewayError("frontier_council_plan_not_bound")
        self._scope_guard(task)
        if _task_fingerprint(task) != self._task_fingerprint:
            raise EngineGatewayError("frontier_council_task_changed_after_binding")
        live = self._live_context()
        if task.requires_fresh_certification:
            admitted, receipt_ref = self._gateway._certification_state(
                task=task,
                engine_ids=self._selected,
                context=live,
            )
            if admitted is None or any(
                engine_id not in admitted for engine_id in self._selected
            ):
                raise EngineGatewayError(
                    "frontier_council_certification_revoked_after_binding"
                )
            if receipt_ref != self._certification_ref:
                raise EngineGatewayError(
                    "frontier_council_certification_receipt_changed_after_binding"
                )
        for engine_id in self._selected:
            registration = self._current_registration(engine_id)
            if not self._credential_ready(registration):
                raise EngineGatewayError(
                    "frontier_council_credential_missing_after_binding"
                )
        return live

    def plan(self, task: IntelligenceTask) -> IntelligenceRoutingPlan:
        self._scope_guard(task)
        fingerprint = _task_fingerprint(task)
        if self._plan is not None:
            if fingerprint != self._task_fingerprint:
                raise EngineGatewayError("frontier_council_task_changed_after_binding")
            return self._plan
        if self._finalized:
            raise EngineGatewayError("frontier_council_session_already_finalized")

        live = self._live_context()
        engine_ids = tuple(sorted(self._gateway._registrations))
        certified_ids, certification_ref = self._gateway._certification_state(
            task=task,
            engine_ids=engine_ids,
            context=live,
        )
        candidate_ids: list[str] = []
        authorizations: dict[str, PaidTokenAuthorization] = {}
        preflight_blockers: list[str] = []
        for engine_id in engine_ids:
            registration = self._gateway._registrations[engine_id]
            if task.requires_fresh_certification and (
                certified_ids is None or engine_id not in certified_ids
            ):
                continue
            if not self._credential_ready(registration):
                preflight_blockers.append(
                    f"frontier_council_credential_missing:{engine_id}"
                )
                continue
            if registration.endpoint.provider is EngineProvider.OLLAMA:
                candidate_ids.append(engine_id)
                continue
            authorization = self._gateway._authorize_frontier_candidate(
                registration=registration,
                prompt="frontier council bounded preflight",
                context=live,
            )
            if authorization.decision is not PaidTokenDecision.ALLOW:
                preflight_blockers.extend(authorization.blockers)
                continue
            authorizations[engine_id] = authorization
            candidate_ids.append(engine_id)

        plan = self._gateway._plan_for_engine_ids(
            task=task,
            engine_ids=tuple(candidate_ids),
            context=live,
            certified_engine_ids=certified_ids,
            certification_admission_ref=certification_ref,
        )
        if not plan.execution_permitted or not plan.primary_engine_id:
            self._plan = self._block_plan(plan, *preflight_blockers)
            self._task_fingerprint = fingerprint
            return self._plan

        selected = tuple(
            dict.fromkeys((plan.primary_engine_id, *plan.critic_engine_ids))
        )
        for engine_id in selected:
            registration = self._gateway._registrations[engine_id]
            if (
                registration.endpoint.provider is not EngineProvider.OLLAMA
                and engine_id not in authorizations
            ):
                self._plan = self._block_plan(
                    plan,
                    f"frontier_council_selected_engine_not_pre_authorized:{engine_id}",
                )
                self._task_fingerprint = fingerprint
                return self._plan

        reservation = self._reservation_budget(
            selected=selected, authorizations=authorizations
        )
        self._reservation_ref = (
            f"frontier-council-reservation:{self._budget.session_ref}"
            if not reservation.is_zero()
            else None
        )
        try:
            self._reserve(reservation)
        except (ValueError, EngineGatewayError) as exc:
            self._reservation_ref = None
            self._plan = self._block_plan(
                plan, f"frontier_council_budget_reservation_failed:{type(exc).__name__}"
            )
            self._task_fingerprint = fingerprint
            return self._plan

        self._plan = plan
        self._task_fingerprint = fingerprint
        self._selected = selected
        self._certification_ref = certification_ref
        self._preflight_authorizations = {
            engine_id: authorization
            for engine_id, authorization in authorizations.items()
            if engine_id in selected
        }
        self._registration_fingerprints = {
            engine_id: _registration_fingerprint(
                self._gateway._registrations[engine_id]
            )
            for engine_id in selected
        }
        return plan

    def _consume_budget(self, usage: PaidTokenUsageReceipt, *, operation: str) -> None:
        amount = BudgetVector(
            tokens=usage.input_tokens + usage.output_tokens,
            cost_units=max(
                usage.provider_cost_microunits, usage.billable_microunits
            ),
            tool_calls=1,
        )
        self._transact(
            kind=BudgetMutationKind.CONSUME,
            amount=amount,
            operation=operation,
        )
        self._consumed = self._consumed.plus(amount)

    async def _invoke_engine(
        self,
        *,
        engine_id: str,
        task: IntelligenceTask,
        prompt: str,
        operation: str,
    ) -> EngineInvocationReceipt:
        live = self._revalidate_binding(task)
        registration = self._current_registration(engine_id)
        endpoint = registration.endpoint
        if endpoint.provider is EngineProvider.OLLAMA:
            receipt = await self._gateway._engine_gateway._invoke_registered(
                task=task,
                prompt=prompt,
                plan=self._plan,
                registration=registration,
            )
            if receipt.external_processing or receipt.engine_id != engine_id:
                raise EngineGatewayError("frontier_council_local_engine_identity_changed")
            return receipt

        authorization = self._gateway._authorize_frontier_candidate(
            registration=registration,
            prompt=prompt,
            context=live,
        )
        original = self._preflight_authorizations.get(engine_id)
        if (
            authorization.decision is not PaidTokenDecision.ALLOW
            or original is None
            or authorization.grant_id != original.grant_id
            or authorization.rate_card_ref != original.rate_card_ref
        ):
            raise EngineGatewayError(
                "frontier_council_paid_authority_changed_after_binding"
            )
        try:
            receipt = await self._gateway._engine_gateway._invoke_registered(
                task=task,
                prompt=prompt,
                plan=self._plan,
                registration=registration,
            )
        except Exception:
            self._uncertain_effect = True
            raise
        if (
            receipt.engine_id != engine_id
            or receipt.provider is not endpoint.provider
            or receipt.model_id != endpoint.model_id
        ):
            self._uncertain_effect = True
            raise EngineGatewayError("frontier_council_provider_identity_changed")
        if receipt.input_tokens is None or receipt.output_tokens is None:
            self._uncertain_effect = True
            raise EngineGatewayError("frontier_council_provider_usage_missing")
        grant = self._gateway._matching_grant(authorization.grant_id or "")
        if receipt.input_tokens + receipt.output_tokens > grant.max_total_tokens_per_request:
            self._uncertain_effect = True
            raise EngineGatewayError(
                "frontier_council_actual_total_tokens_exceeded_authorized_limit"
            )
        rate_card = self._gateway._matching_rate_card(
            authorization.rate_card_ref or ""
        )
        usage = settle_paid_token_usage(
            authorization=authorization,
            grant=grant,
            rate_card=rate_card,
            input_tokens=receipt.input_tokens,
            output_tokens=receipt.output_tokens,
            settled_at=live.requested_at,
            provider_response_ref=receipt.provider_response_id,
        )
        try:
            self._gateway._usage_writer(usage)
            self._consume_budget(usage, operation=operation)
        except Exception:
            # External processing already happened; never free the remaining
            # reservation on an uncertain accounting boundary.
            self._uncertain_effect = True
            raise
        return receipt

    async def invoke_primary(
        self, *, task: IntelligenceTask, prompt: str
    ) -> EngineInvocationReceipt:
        if not prompt.strip():
            raise ValueError("engine_gateway_prompt_required")
        if self._plan is None:
            self.plan(task)
        if self._plan is None or not self._plan.execution_permitted or not self._selected:
            raise EngineGatewayError("frontier_council_plan_not_executable")
        if self._direct_primary_calls >= _MAX_DIRECT_PRIMARY_CALLS:
            raise EngineGatewayError("frontier_council_primary_call_envelope_exceeded")
        self._direct_primary_calls += 1
        return await self._invoke_engine(
            engine_id=self._selected[0],
            task=task,
            prompt=prompt,
            operation=f"primary-{self._direct_primary_calls}",
        )

    async def invoke_routed_engines(
        self, *, task: IntelligenceTask, prompt: str
    ) -> tuple[EngineInvocationReceipt, ...]:
        if not prompt.strip():
            raise ValueError("engine_gateway_prompt_required")
        if self._plan is None:
            self.plan(task)
        if self._plan is None or not self._plan.execution_permitted or not self._selected:
            raise EngineGatewayError("frontier_council_plan_not_executable")
        if self._routed_waves >= _MAX_ROUTED_WAVES:
            raise EngineGatewayError("frontier_council_routed_wave_envelope_exceeded")
        self._routed_waves += 1
        receipts: list[EngineInvocationReceipt] = []
        for position, engine_id in enumerate(self._selected, start=1):
            receipts.append(
                await self._invoke_engine(
                    engine_id=engine_id,
                    task=task,
                    prompt=prompt,
                    operation=f"wave-{self._routed_waves}-engine-{position}",
                )
            )
        return tuple(receipts)

    def finalize(self) -> FrontierCouncilRuntimeReceipt:
        if self._finalized:
            return self.runtime_receipt()
        remaining = self._reserved.minus(self._consumed)
        if self._reservation_ref and not remaining.is_zero():
            if self._uncertain_effect:
                self._transact(
                    kind=BudgetMutationKind.HOLD_UNKNOWN_EFFECT,
                    amount=remaining,
                    operation="hold-unknown-effect",
                )
            else:
                self._transact(
                    kind=BudgetMutationKind.RELEASE,
                    amount=remaining,
                    operation="release-unused",
                )
        self._finalized = True
        return self.runtime_receipt()

    def runtime_receipt(self) -> FrontierCouncilRuntimeReceipt:
        return FrontierCouncilRuntimeReceipt(
            session_ref=self._budget.session_ref,
            task_id=self._plan.task_id if self._plan else "unbound",
            selected_engine_ids=self._selected,
            reservation_ref=self._reservation_ref,
            reserved_budget=self._reserved,
            consumed_budget=self._consumed,
            uncertain_effect_held=self._uncertain_effect,
            finalized=self._finalized,
        )


async def execute_governed_frontier_supremacy(
    *,
    gateway: AdminGovernedEngineGateway,
    request: SupremacyRequest,
    context: PaidTokenExecutionContext,
    budget_ledger: AgentBudgetLedgerPort,
    budget: FrontierCouncilBudgetBinding,
    clock: Clock | None = None,
) -> GovernedFrontierCouncilResult:
    """Run the existing Frontier deliberation through production governance."""

    session = GovernedFrontierCouncilSession(
        gateway=gateway,
        context=context,
        budget_ledger=budget_ledger,
        budget=budget,
        clock=clock,
    )
    try:
        result = await execute_frontier_supremacy(gateway=session, request=request)
    finally:
        runtime = session.finalize()
    return GovernedFrontierCouncilResult(result=result, runtime=runtime)
