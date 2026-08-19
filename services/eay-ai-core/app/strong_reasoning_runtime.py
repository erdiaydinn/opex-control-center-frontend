"""Execute Jarvis reasoning-strength plans through canonical model runtimes.

The Intelligence Supremacy planner decides *how much* reasoning is justified.
This module makes that recommendation executable without creating a second
provider or payment gateway. Local council work uses the existing EngineGateway
with local-only registrations. Any escalation attempt uses the existing
ProductionEngineRuntime, so platform-admin grant, rate-card, budget, billing and
privacy controls remain canonical.

Model responses are constrained to a small JSON claim/critique envelope. Raw
prompts are never returned and model chain-of-thought is neither requested nor
persisted. The council remains advisory and cannot execute tools or business
side effects.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator

from .council_runtime import (
    ClaimStance,
    CouncilSynthesis,
    CritiqueSeverity,
    EngineClaim,
    EngineCritique,
    EngineProposal,
    synthesize_council,
)
from .engine_gateway import (
    EngineGateway,
    EngineGatewayError,
    EngineInvocationReceipt,
    EngineProvider,
    RegisteredEngine,
)
from .intelligence_router import IntelligenceTask
from .intelligence_supremacy import InformationGainPlan, ReasoningMode, ReasoningStrengthPlan
from .paid_token_engine_gateway import PaidTokenExecutionContext
from .production_engine_runtime import ProductionEngineRuntime

STRONG_REASONING_RUNTIME_CONTRACT = "eay-strong-reasoning-runtime-v1"


class StrongReasoningStatus(str, Enum):
    NEEDS_INVESTIGATION = "needs_investigation"
    LOCAL_RESULT = "local_result"
    COUNCIL_RESULT = "council_result"
    ESCALATION_BLOCKED = "escalation_blocked"
    ESCALATED_RESULT = "escalated_result"
    HUMAN_REVIEW = "human_review"


class _ClaimPayload(BaseModel):
    claim_key: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class _CritiquePayload(BaseModel):
    target_claim_key: str = Field(min_length=1)
    stance: ClaimStance
    severity: CritiqueSeverity
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class _ModelCouncilPayload(BaseModel):
    claims: tuple[_ClaimPayload, ...] = ()
    critiques: tuple[_CritiquePayload, ...] = ()
    proposed_action_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def no_duplicates(self) -> "_ModelCouncilPayload":
        claim_keys = [item.claim_key for item in self.claims]
        if len(claim_keys) != len(set(claim_keys)):
            raise ValueError("strong_reasoning_duplicate_claim_key")
        critique_keys = [
            (item.target_claim_key, item.stance, item.severity)
            for item in self.critiques
        ]
        if len(critique_keys) != len(set(critique_keys)):
            raise ValueError("strong_reasoning_duplicate_critique")
        return self


class ReasoningEngineEvidence(BaseModel):
    engine_id: str
    provider_key: str
    model_id: str
    external_processing: bool
    output_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_keys: tuple[str, ...]
    critique_claim_keys: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    paid_usage_receipt_ref: str | None = None
    raw_prompt_retained: bool = False
    private_chain_of_thought_retained: bool = False

    @model_validator(mode="after")
    def evidence_is_safe(self) -> "ReasoningEngineEvidence":
        if self.raw_prompt_retained or self.private_chain_of_thought_retained:
            raise ValueError("strong_reasoning_private_reasoning_retention_forbidden")
        return self


class StrongReasoningExecution(BaseModel):
    contract: str = STRONG_REASONING_RUNTIME_CONTRACT
    task_id: str
    status: StrongReasoningStatus
    plan_mode: ReasoningMode
    engine_evidence: tuple[ReasoningEngineEvidence, ...]
    council: CouncilSynthesis | None = None
    selected_investigation_ids: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    human_review_required: bool = False
    paid_frontier_used: bool = False
    paid_frontier_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def execution_is_advisory(self) -> "StrongReasoningExecution":
        if self.paid_frontier_authority_granted:
            raise ValueError("strong_reasoning_result_never_grants_paid_authority")
        if self.execution_authority_granted:
            raise ValueError("strong_reasoning_result_never_grants_execution_authority")
        if self.status is StrongReasoningStatus.NEEDS_INVESTIGATION and self.engine_evidence:
            raise ValueError("investigate_first_must_not_invoke_engines")
        return self


@dataclass(frozen=True)
class StrongReasoningRuntime:
    local_registrations: tuple[RegisteredEngine, ...]
    frontier_runtime: ProductionEngineRuntime
    transport_factory: Any | None = None
    environ: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if not self.local_registrations:
            raise ValueError("strong_reasoning_local_registrations_required")
        ids = [item.profile.engine_id for item in self.local_registrations]
        if len(ids) != len(set(ids)):
            raise ValueError("strong_reasoning_duplicate_local_engine")
        for item in self.local_registrations:
            if item.endpoint.provider is not EngineProvider.OLLAMA or not item.profile.local_processing:
                raise ValueError("strong_reasoning_local_runtime_requires_local_ollama")

    async def execute(
        self,
        *,
        plan: ReasoningStrengthPlan,
        information_gain: InformationGainPlan,
        task: IntelligenceTask,
        prompt: str,
        claim_keys: tuple[str, ...],
        allowed_evidence_refs: tuple[str, ...],
        context: PaidTokenExecutionContext,
    ) -> StrongReasoningExecution:
        if not prompt.strip():
            raise ValueError("strong_reasoning_prompt_required")
        if not claim_keys or len(claim_keys) != len(set(claim_keys)):
            raise ValueError("strong_reasoning_unique_claim_keys_required")
        if not allowed_evidence_refs or len(allowed_evidence_refs) != len(set(allowed_evidence_refs)):
            raise ValueError("strong_reasoning_unique_evidence_refs_required")

        if plan.mode is ReasoningMode.INVESTIGATE_FIRST:
            return StrongReasoningExecution(
                task_id=task.task_id,
                status=StrongReasoningStatus.NEEDS_INVESTIGATION,
                plan_mode=plan.mode,
                engine_evidence=(),
                selected_investigation_ids=information_gain.selected_investigation_ids,
                blockers=tuple(dict.fromkeys((*plan.blockers, *information_gain.unresolved_gap_ids))),
                human_review_required=plan.human_review_required,
            )

        bounded_prompt = _build_bounded_prompt(
            prompt=prompt,
            claim_keys=claim_keys,
            allowed_evidence_refs=allowed_evidence_refs,
        )
        gateway = EngineGateway(
            list(self.local_registrations),
            transport_factory=self.transport_factory,
            environ=self.environ,
        )
        local_task = task
        if plan.local_council_required and not task.requires_independent_critique:
            local_task = task.model_copy(update={"requires_independent_critique": True})

        local_receipts: tuple[EngineInvocationReceipt, ...]
        try:
            if plan.local_council_required:
                local_receipts = await gateway.invoke_routed_engines(
                    task=local_task,
                    prompt=bounded_prompt,
                )
            else:
                local_receipts = (
                    await gateway.invoke_primary(task=local_task, prompt=bounded_prompt),
                )
        except EngineGatewayError as exc:
            local_receipts = ()
            local_error = _safe_error(exc)
        else:
            local_error = None

        parsed = _parse_receipts(
            receipts=local_receipts,
            registrations=self.local_registrations,
            allowed_claim_keys=set(claim_keys),
            allowed_evidence_refs=set(allowed_evidence_refs),
        )
        proposals = list(parsed[0])
        critiques = list(parsed[1])
        evidence = list(parsed[2])
        parse_blockers = list(parsed[3])
        if local_error:
            parse_blockers.append(local_error)

        minimum_supporters = 2 if plan.local_council_required else 1
        council = synthesize_council(
            proposals=proposals,
            critiques=critiques,
            minimum_independent_supporters=minimum_supporters,
        )

        paid_frontier_used = False
        escalated = False
        escalation_blocker: str | None = None
        if (
            plan.frontier_escalation_candidate
            and not council.decision_ready
            and plan.mode in {ReasoningMode.LOCAL_COUNCIL, ReasoningMode.HUMAN_REVIEW, ReasoningMode.FRONTIER_ESCALATION_CANDIDATE}
        ):
            try:
                governed = await self.frontier_runtime.invoke_primary(
                    task=task,
                    prompt=bounded_prompt,
                    context=context,
                )
            except EngineGatewayError as exc:
                escalation_blocker = "strong_reasoning_governed_escalation_blocked:" + _safe_error(exc)
            else:
                escalated = True
                paid_frontier_used = governed.paid_usage is not None
                frontier_registration = _registration_for_receipt(
                    governed.engine_receipt,
                    self.local_registrations,
                )
                parsed_frontier = _parse_one_receipt(
                    receipt=governed.engine_receipt,
                    provider_key=(
                        frontier_registration.profile.independent_provider_key
                        if frontier_registration is not None
                        else governed.engine_receipt.provider.value
                    ),
                    allowed_claim_keys=set(claim_keys),
                    allowed_evidence_refs=set(allowed_evidence_refs),
                    paid_usage_receipt_ref=(
                        governed.paid_usage.usage_ref
                        if governed.paid_usage is not None
                        else None
                    ),
                )
                if parsed_frontier is None:
                    parse_blockers.append("strong_reasoning_frontier_payload_invalid")
                else:
                    proposal, new_critiques, new_evidence = parsed_frontier
                    proposals.append(proposal)
                    critiques.extend(new_critiques)
                    evidence.append(new_evidence)
                    council = synthesize_council(
                        proposals=proposals,
                        critiques=critiques,
                        minimum_independent_supporters=minimum_supporters,
                    )

        blockers = list(parse_blockers)
        blockers.extend(council.blockers)
        if escalation_blocker:
            blockers.append(escalation_blocker)

        if plan.human_review_required:
            status = StrongReasoningStatus.HUMAN_REVIEW
        elif escalated:
            status = StrongReasoningStatus.ESCALATED_RESULT
        elif escalation_blocker:
            status = StrongReasoningStatus.ESCALATION_BLOCKED
        elif plan.local_council_required:
            status = StrongReasoningStatus.COUNCIL_RESULT
        else:
            status = StrongReasoningStatus.LOCAL_RESULT

        return StrongReasoningExecution(
            task_id=task.task_id,
            status=status,
            plan_mode=plan.mode,
            engine_evidence=tuple(evidence),
            council=council,
            selected_investigation_ids=information_gain.selected_investigation_ids,
            blockers=tuple(dict.fromkeys(blockers)),
            human_review_required=plan.human_review_required,
            paid_frontier_used=paid_frontier_used,
        )


def _build_bounded_prompt(
    *,
    prompt: str,
    claim_keys: tuple[str, ...],
    allowed_evidence_refs: tuple[str, ...],
) -> str:
    schema = {
        "claims": [
            {
                "claim_key": "one allowed claim key",
                "statement": "short conclusion only; no chain-of-thought",
                "confidence": 0.0,
                "evidence_refs": ["only allowed evidence refs"],
            }
        ],
        "critiques": [
            {
                "target_claim_key": "one allowed claim key",
                "stance": "support|refute|uncertain",
                "severity": "info|material|critical",
                "evidence_refs": ["only allowed evidence refs"],
            }
        ],
        "proposed_action_refs": [],
    }
    return (
        "Return JSON only. Do not provide chain-of-thought, hidden reasoning, tool calls, or credentials. "
        "For a claim you do not support, omit it from claims and add a critique. "
        f"Allowed claim keys: {json.dumps(claim_keys)}. "
        f"Allowed evidence refs: {json.dumps(allowed_evidence_refs)}. "
        f"Schema: {json.dumps(schema, separators=(',', ':'))}. "
        f"Task: {prompt.strip()}"
    )


def _parse_receipts(
    *,
    receipts: tuple[EngineInvocationReceipt, ...],
    registrations: tuple[RegisteredEngine, ...],
    allowed_claim_keys: set[str],
    allowed_evidence_refs: set[str],
) -> tuple[tuple[EngineProposal, ...], tuple[EngineCritique, ...], tuple[ReasoningEngineEvidence, ...], tuple[str, ...]]:
    proposals: list[EngineProposal] = []
    critiques: list[EngineCritique] = []
    evidence: list[ReasoningEngineEvidence] = []
    blockers: list[str] = []
    by_id = {item.profile.engine_id: item for item in registrations}
    for receipt in receipts:
        registration = by_id.get(receipt.engine_id)
        if registration is None:
            blockers.append("strong_reasoning_unregistered_local_receipt")
            continue
        parsed = _parse_one_receipt(
            receipt=receipt,
            provider_key=registration.profile.independent_provider_key,
            allowed_claim_keys=allowed_claim_keys,
            allowed_evidence_refs=allowed_evidence_refs,
        )
        if parsed is None:
            blockers.append(f"strong_reasoning_invalid_model_payload:{receipt.engine_id}")
            continue
        proposal, new_critiques, engine_evidence = parsed
        proposals.append(proposal)
        critiques.extend(new_critiques)
        evidence.append(engine_evidence)
    return tuple(proposals), tuple(critiques), tuple(evidence), tuple(blockers)


def _parse_one_receipt(
    *,
    receipt: EngineInvocationReceipt,
    provider_key: str,
    allowed_claim_keys: set[str],
    allowed_evidence_refs: set[str],
    paid_usage_receipt_ref: str | None = None,
) -> tuple[EngineProposal, tuple[EngineCritique, ...], ReasoningEngineEvidence] | None:
    try:
        raw = json.loads(receipt.output_text)
        payload = _ModelCouncilPayload.model_validate(raw)
    except (json.JSONDecodeError, TypeError, ValidationError):
        return None

    if any(item.claim_key not in allowed_claim_keys for item in payload.claims):
        return None
    if any(item.target_claim_key not in allowed_claim_keys for item in payload.critiques):
        return None
    used_evidence = {
        ref
        for item in (*payload.claims, *payload.critiques)
        for ref in item.evidence_refs
    }
    if not used_evidence or not used_evidence.issubset(allowed_evidence_refs):
        return None

    output_fingerprint = hashlib.sha256(receipt.output_text.encode("utf-8")).hexdigest()
    try:
        proposal = EngineProposal(
            proposal_id=f"proposal://{receipt.task_id}/{receipt.engine_id}/{output_fingerprint[:16]}",
            engine_id=receipt.engine_id,
            provider_key=provider_key,
            answer_ref=f"engine-answer://{output_fingerprint}",
            claims=tuple(
                EngineClaim(
                    claim_key=item.claim_key,
                    statement=item.statement,
                    confidence=item.confidence,
                    evidence_refs=item.evidence_refs,
                )
                for item in payload.claims
            ),
            proposed_action_refs=payload.proposed_action_refs,
        )
    except ValidationError:
        return None
    critiques = tuple(
        EngineCritique(
            critique_id=f"critique://{receipt.engine_id}/{index}/{output_fingerprint[:16]}",
            critic_engine_id=receipt.engine_id,
            critic_provider_key=provider_key,
            target_claim_key=item.target_claim_key,
            stance=item.stance,
            severity=item.severity,
            reasoning_ref=f"critique-evidence://{output_fingerprint}/{index}",
            evidence_refs=item.evidence_refs,
        )
        for index, item in enumerate(payload.critiques)
    )
    engine_evidence = ReasoningEngineEvidence(
        engine_id=receipt.engine_id,
        provider_key=provider_key,
        model_id=receipt.model_id,
        external_processing=receipt.external_processing,
        output_fingerprint=output_fingerprint,
        claim_keys=tuple(item.claim_key for item in payload.claims),
        critique_claim_keys=tuple(item.target_claim_key for item in payload.critiques),
        evidence_refs=tuple(sorted(used_evidence)),
        paid_usage_receipt_ref=paid_usage_receipt_ref,
    )
    return proposal, critiques, engine_evidence


def _registration_for_receipt(
    receipt: EngineInvocationReceipt,
    registrations: tuple[RegisteredEngine, ...],
) -> RegisteredEngine | None:
    matches = [item for item in registrations if item.profile.engine_id == receipt.engine_id]
    return matches[0] if len(matches) == 1 else None


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    return text[:240].replace("\n", " ")
