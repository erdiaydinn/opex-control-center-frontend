from datetime import UTC, datetime, timedelta

import pytest

from app.hierarchical_agent_delegation import (
    AgentCandidate,
    AgentDelegationPolicy,
    AgentDelegationRequest,
    DelegatedAgentState,
    admit_agent_delegation,
)
from app.parallel_mission_scheduler import LaneSchedulingClass
from app.swarm_worker_registry import SwarmWorkerClass

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def candidate(agent_id, provider, *, tenant="YS_TR", expires=None, state=DelegatedAgentState.AVAILABLE):
    return AgentCandidate(
        agent_id=agent_id,
        tenant_id=tenant,
        worker_class=SwarmWorkerClass.RESEARCH,
        scheduling_classes=(LaneSchedulingClass.RESEARCH,),
        capability_refs=("capability://research",),
        provider_key=provider,
        attestation_ref=f"attestation://{agent_id}",
        attestation_fingerprint=("a" if provider == "local-a" else "b") * 64,
        attested_until=expires or NOW + timedelta(hours=1),
        state=state,
        authority_scope_refs=("scope://company-read",),
    )


def request(**changes):
    values = {
        "objective_ref": "objective://jarvis/research",
        "tenant_id": "YS_TR",
        "parent_session_ref": "session://jarvis/1",
        "parent_agent_id": "jarvis-root",
        "delegation_depth": 1,
        "requested_agent_count": 2,
        "required_worker_classes": (SwarmWorkerClass.RESEARCH,),
        "required_capability_refs": ("capability://research",),
        "allowed_authority_scope_refs": ("scope://company-read",),
        "subtree_cost_budget": 101,
        "subtree_transition_budget": 21,
        "user_command_evidence_ref": "evidence://user-command/1",
        "cancellation_token_ref": "cancel://jarvis/1",
    }
    values.update(changes)
    return AgentDelegationRequest(**values)


def test_user_command_hires_parallel_agents_with_bounded_child_budgets():
    result = admit_agent_delegation(
        request=request(),
        candidates=(candidate("agent-b", "local-b"), candidate("agent-a", "local-a")),
        policy=AgentDelegationPolicy(),
        now=NOW,
    )
    assert {item.child_agent_id for item in result.leases} == {"agent-a", "agent-b"}
    assert sum(item.child_cost_budget for item in result.leases) == 101
    assert sum(item.child_transition_budget for item in result.leases) == 21
    assert {item.worker_id for item in result.registry.workers} == {"agent-a", "agent-b"}
    assert all(item.business_execution_authority_granted is False for item in result.leases)


def test_recursive_spawn_is_denied_by_default_and_depth_is_bounded():
    with pytest.raises(ValueError, match="agent_recursive_delegation_forbidden"):
        admit_agent_delegation(
            request=request(children_may_delegate=True),
            candidates=(candidate("a", "local-a"), candidate("b", "local-b")),
            policy=AgentDelegationPolicy(),
            now=NOW,
        )
    with pytest.raises(ValueError, match="agent_delegation_depth_exceeded"):
        admit_agent_delegation(
            request=request(delegation_depth=4),
            candidates=(candidate("a", "local-a"), candidate("b", "local-b")),
            policy=AgentDelegationPolicy(max_depth=3),
            now=NOW,
        )


def test_cross_tenant_expired_revoked_and_scope_amplifying_agents_are_ineligible():
    candidates = (
        candidate("foreign", "local-a", tenant="tenant-b"),
        candidate("expired", "local-b", expires=NOW),
        candidate("revoked", "local-c", state=DelegatedAgentState.REVOKED),
    )
    with pytest.raises(ValueError, match="insufficient_attested_candidates"):
        admit_agent_delegation(
            request=request(requested_agent_count=1),
            candidates=candidates,
            policy=AgentDelegationPolicy(),
            now=NOW,
        )


def test_multiple_children_require_independent_provider_diversity():
    with pytest.raises(ValueError, match="provider_diversity_required"):
        admit_agent_delegation(
            request=request(),
            candidates=(candidate("a", "local-a"), candidate("b", "local-a")),
            policy=AgentDelegationPolicy(),
            now=NOW,
        )


def test_parent_cannot_hide_business_execution_authority_in_spawn_request():
    with pytest.raises(ValueError, match="never_grants_business_execution_authority"):
        request(business_execution_authority_granted=True)
