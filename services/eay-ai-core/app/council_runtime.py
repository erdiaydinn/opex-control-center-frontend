"""Independent multi-engine council synthesis for Jarvis.

Frontier models are treated as fallible reasoning engines, not authorities.
Council synthesis counts independent provider families rather than duplicate
samples from one provider, preserves disagreements, and binds accepted claims
to evidence. It does not execute recommended actions.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

COUNCIL_RUNTIME_CONTRACT = "eay-multi-engine-council-v1"


class ClaimStance(str, Enum):
    SUPPORT = "support"
    REFUTE = "refute"
    UNCERTAIN = "uncertain"


class CritiqueSeverity(str, Enum):
    INFO = "info"
    MATERIAL = "material"
    CRITICAL = "critical"


class EngineClaim(BaseModel):
    claim_key: str = Field(min_length=1)
    statement: str = Field(min_length=3)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class EngineProposal(BaseModel):
    proposal_id: str = Field(min_length=1)
    engine_id: str = Field(min_length=1)
    provider_key: str = Field(min_length=1)
    answer_ref: str = Field(min_length=1)
    claims: tuple[EngineClaim, ...] = Field(min_length=1)
    proposed_action_refs: tuple[str, ...] = ()


class EngineCritique(BaseModel):
    critique_id: str = Field(min_length=1)
    critic_engine_id: str = Field(min_length=1)
    critic_provider_key: str = Field(min_length=1)
    target_claim_key: str = Field(min_length=1)
    stance: ClaimStance
    severity: CritiqueSeverity
    reasoning_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class CouncilClaimResult(BaseModel):
    claim_key: str
    accepted: bool
    contested: bool
    independent_supporters: int = Field(ge=0)
    independent_refuters: int = Field(ge=0)
    weighted_confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()


class CouncilSynthesis(BaseModel):
    contract: str = COUNCIL_RUNTIME_CONTRACT
    claim_results: tuple[CouncilClaimResult, ...]
    accepted_action_refs: tuple[str, ...]
    provider_diversity: int = Field(ge=0)
    decision_ready: bool
    execution_allowed: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def council_never_executes(self) -> "CouncilSynthesis":
        if self.execution_allowed:
            raise ValueError("council_synthesis_never_authorizes_execution")
        return self


def synthesize_council(
    *,
    proposals: list[EngineProposal],
    critiques: list[EngineCritique],
    minimum_independent_supporters: int = 2,
    maximum_accept_confidence: float = 0.97,
) -> CouncilSynthesis:
    if minimum_independent_supporters < 1:
        raise ValueError("council_minimum_supporters_invalid")
    if not 0.5 <= maximum_accept_confidence <= 1.0:
        raise ValueError("council_confidence_cap_out_of_range")
    if not proposals:
        return CouncilSynthesis(
            claim_results=(),
            accepted_action_refs=(),
            provider_diversity=0,
            decision_ready=False,
            blockers=("council_proposals_missing",),
        )

    claims_by_key: dict[str, list[tuple[EngineProposal, EngineClaim]]] = {}
    for proposal in proposals:
        for claim in proposal.claims:
            claims_by_key.setdefault(claim.claim_key, []).append((proposal, claim))

    critiques_by_key: dict[str, list[EngineCritique]] = {}
    for critique in critiques:
        critiques_by_key.setdefault(critique.target_claim_key, []).append(critique)

    results: list[CouncilClaimResult] = []
    global_blockers: list[str] = []
    for claim_key in sorted(claims_by_key):
        claim_entries = claims_by_key[claim_key]
        best_by_provider: dict[str, EngineClaim] = {}
        for proposal, claim in claim_entries:
            existing = best_by_provider.get(proposal.provider_key)
            if existing is None or claim.confidence > existing.confidence:
                best_by_provider[proposal.provider_key] = claim

        support_providers = set(best_by_provider)
        refute_providers = {
            critique.critic_provider_key
            for critique in critiques_by_key.get(claim_key, [])
            if critique.stance is ClaimStance.REFUTE
        }
        critical_refute = any(
            critique.stance is ClaimStance.REFUTE and critique.severity is CritiqueSeverity.CRITICAL
            for critique in critiques_by_key.get(claim_key, [])
        )
        material_refute = any(
            critique.stance is ClaimStance.REFUTE and critique.severity in {CritiqueSeverity.MATERIAL, CritiqueSeverity.CRITICAL}
            for critique in critiques_by_key.get(claim_key, [])
        )

        blockers: list[str] = []
        if len(support_providers) < minimum_independent_supporters:
            blockers.append("council_independent_support_quorum_missing")
        contested = bool(refute_providers)
        if critical_refute:
            blockers.append("council_critical_refutation_present")
        elif material_refute:
            blockers.append("council_material_refutation_unresolved")

        confidences = [claim.confidence for claim in best_by_provider.values()]
        weighted_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        if contested:
            weighted_confidence *= max(0.25, 1.0 - 0.20 * len(refute_providers))
        weighted_confidence = min(weighted_confidence, maximum_accept_confidence)

        evidence_refs = tuple(
            dict.fromkeys(
                [ref for claim in best_by_provider.values() for ref in claim.evidence_refs]
                + [
                    ref
                    for critique in critiques_by_key.get(claim_key, [])
                    for ref in critique.evidence_refs
                ]
            )
        )
        accepted = not blockers and weighted_confidence >= 0.60
        if not accepted:
            global_blockers.append(f"council_claim_not_accepted:{claim_key}")
        results.append(
            CouncilClaimResult(
                claim_key=claim_key,
                accepted=accepted,
                contested=contested,
                independent_supporters=len(support_providers),
                independent_refuters=len(refute_providers),
                weighted_confidence=round(weighted_confidence, 6),
                evidence_refs=evidence_refs,
                blockers=tuple(blockers),
            )
        )

    accepted_claim_keys = {item.claim_key for item in results if item.accepted}
    all_claim_keys = set(claims_by_key)
    decision_ready = bool(results) and accepted_claim_keys == all_claim_keys

    action_support: dict[str, set[str]] = {}
    for proposal in proposals:
        if not all(claim.claim_key in accepted_claim_keys for claim in proposal.claims):
            continue
        for action_ref in proposal.proposed_action_refs:
            action_support.setdefault(action_ref, set()).add(proposal.provider_key)
    accepted_actions = tuple(
        sorted(
            action_ref
            for action_ref, providers in action_support.items()
            if len(providers) >= minimum_independent_supporters
        )
    )

    provider_diversity = len({proposal.provider_key for proposal in proposals})
    if provider_diversity < minimum_independent_supporters:
        global_blockers.append("council_provider_diversity_insufficient")
        decision_ready = False

    return CouncilSynthesis(
        claim_results=tuple(results),
        accepted_action_refs=accepted_actions,
        provider_diversity=provider_diversity,
        decision_ready=decision_ready,
        blockers=tuple(dict.fromkeys(global_blockers)),
    )
