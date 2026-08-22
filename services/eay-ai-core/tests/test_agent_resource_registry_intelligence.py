from datetime import datetime, timezone

import pytest

from app.agent_resource_registry import (
    AgentResourceAdmissionPolicy,
    AgentResourceEvaluation,
    AgentResourceKind,
    AgentResourceLifecycle,
    AgentResourceRecord,
    AgentResourceSecurity,
    discover_agent_resources,
    evaluate_agent_resource_admission,
    transition_agent_resource,
)

NOW = datetime(2026, 8, 18, 18, 30, tzinfo=timezone.utc)


def _eval(category: str, score: float, suffix: str) -> AgentResourceEvaluation:
    return AgentResourceEvaluation(
        category=category,
        benchmark=f"jarvis-{category}",
        provider="eay-ci",
        score=score,
        evidence_ref=f"evidence://{category}/{suffix}",
        environment_fingerprint="env-fingerprint-2026-08-18",
        observed_at=NOW,
    )


def _record(*, mutating: bool = False, lifecycle: AgentResourceLifecycle = AgentResourceLifecycle.APPROVED) -> AgentResourceRecord:
    return AgentResourceRecord(
        namespace="eay",
        name="inventory-helper",
        version="1.0.0",
        kind=AgentResourceKind.MCP_SERVER,
        source_ref="https://github.com/example/inventory-helper",
        source_commit="a" * 40,
        content_digest="b" * 64,
        capabilities=frozenset({"inventory-read", "stock-adjustment"}),
        protocols=frozenset({"mcp"}),
        lifecycle=lifecycle,
        security=AgentResourceSecurity(
            license_approved=True,
            supply_chain_verified=True,
            source_signature_verified=True,
            mutating=mutating,
            idempotent_write=not mutating,
            authoritative_effect_verification=not mutating,
        ),
        evaluations=(
            _eval("safety", 0.98, "safe"),
            _eval("reliability", 0.97, "reliable"),
        ),
        reviewed_at=NOW,
    )


def test_resource_identity_requires_pinned_commit() -> None:
    # Use a 40-character non-hex value so field-length validation passes and
    # the domain-specific pinned-SHA validator is exercised deterministically.
    with pytest.raises(ValueError, match="agent_resource_source_commit_must_be_pinned_sha"):
        AgentResourceRecord(
            namespace="eay",
            name="bad-agent",
            version="latest",
            kind=AgentResourceKind.A2A_AGENT,
            source_ref="https://example.invalid/agent",
            source_commit="g" * 40,
            content_digest="c" * 64,
            capabilities=frozenset({"research"}),
            protocols=frozenset({"a2a"}),
            reviewed_at=NOW,
        )


def test_mutating_resource_fails_closed_without_write_proof() -> None:
    record = _record(mutating=True)
    decision = evaluate_agent_resource_admission(
        record=record,
        policy=AgentResourceAdmissionPolicy(),
        now=NOW,
    )
    assert not decision.admitted
    assert "agent_resource_mutating_write_not_idempotent" in decision.blockers
    assert "agent_resource_mutating_effect_verification_missing" in decision.blockers
    assert decision.execution_authority_granted is False


def test_approved_readonly_resource_is_discoverable_but_never_authority() -> None:
    record = _record(mutating=False)
    decision = evaluate_agent_resource_admission(
        record=record,
        policy=AgentResourceAdmissionPolicy(),
        now=NOW,
    )
    assert decision.admitted
    assert decision.discovery_only
    assert decision.execution_authority_granted is False
    matches = discover_agent_resources(
        records=(record,),
        query="inventory read",
        policy=AgentResourceAdmissionPolicy(),
        now=NOW,
    )
    assert matches == (record,)


def test_lifecycle_cannot_jump_from_discovered_to_published() -> None:
    record = _record(lifecycle=AgentResourceLifecycle.DISCOVERED)
    with pytest.raises(ValueError, match="agent_resource_invalid_lifecycle_transition"):
        transition_agent_resource(record, target=AgentResourceLifecycle.PUBLISHED)


def test_stepwise_promotion_preserves_pinned_identity() -> None:
    record = _record(lifecycle=AgentResourceLifecycle.DISCOVERED)
    evaluated = transition_agent_resource(record, target=AgentResourceLifecycle.EVALUATED)
    approved = transition_agent_resource(evaluated, target=AgentResourceLifecycle.APPROVED)
    published = transition_agent_resource(approved, target=AgentResourceLifecycle.PUBLISHED)
    assert published.source_commit == record.source_commit
    assert published.content_digest == record.content_digest
    assert published.lifecycle is AgentResourceLifecycle.PUBLISHED
