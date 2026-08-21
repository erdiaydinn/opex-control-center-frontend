from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from app.core.ai_query_contract_policy import (
    AI_QUERY_CONTRACT_POLICIES,
    AiQueryContractNotReady,
    AiQueryContractPolicy,
    ai_execution_scope_fingerprint,
    ai_query_contract_policy_fingerprint,
    expected_query_contract_review_fingerprint,
    require_ai_query_contract_ready,
)
from app.core.ai_tool_authorization import TOOL_REQUIRED_SCOPES
from app.core.ai_tool_grants import RedisAiToolGrantStore


def test_registry_covers_every_reviewed_tool_without_default_allow() -> None:
    assert set(AI_QUERY_CONTRACT_POLICIES) == set(
        TOOL_REQUIRED_SCOPES
    )

    for tool, policy in AI_QUERY_CONTRACT_POLICIES.items():
        assert policy.tool == tool
        assert policy.production_ready is False
        assert policy.blockers


def test_current_tools_are_blocked_in_staging_and_production() -> None:
    for environment in ("staging", "production"):
        for tool in AI_QUERY_CONTRACT_POLICIES:
            with pytest.raises(AiQueryContractNotReady):
                require_ai_query_contract_ready(
                    tool=tool,  # type: ignore[arg-type]
                    environment=environment,
                )


def test_development_and_test_do_not_claim_production_readiness() -> None:
    for environment in ("development", "test"):
        policy = require_ai_query_contract_ready(
            tool="ops_kpi_query",
            environment=environment,
        )
        assert policy.production_ready is False
        assert "tenant_discriminator_not_reviewed" in policy.blockers


def test_production_ready_policy_requires_all_security_evidence() -> None:
    with pytest.raises(ValidationError):
        AiQueryContractPolicy(
            tool="ops_kpi_query",
            contract_id="ops.kpi.orders.v2",
            contract_revision=2,
            data_scope_argument="stores",
            production_ready=True,
            blockers=(),
        )

    with pytest.raises(ValidationError):
        AiQueryContractPolicy(
            tool="ops_kpi_query",
            contract_id="ops.kpi.orders.v2",
            contract_revision=2,
            data_scope_argument="stores",
            tenant_discriminator_parameter="entity_id",
            query_template_sha256="a" * 64,
            review_fingerprint="b" * 64,
            production_ready=True,
            blockers=("still_blocked",),
        )


def test_review_and_execution_fingerprints_bind_all_security_fields() -> None:
    review_candidate = AiQueryContractPolicy(
        tool="ops_kpi_query",
        contract_id="ops.kpi.orders.v2",
        contract_revision=2,
        data_scope_argument="stores",
        tenant_discriminator_parameter="entity_id",
        query_template_sha256="a" * 64,
        review_fingerprint=None,
        production_ready=False,
        blockers=("pending_review",),
    )
    expected_review = expected_query_contract_review_fingerprint(
        review_candidate
    )

    ready = AiQueryContractPolicy(
        tool="ops_kpi_query",
        contract_id="ops.kpi.orders.v2",
        contract_revision=2,
        data_scope_argument="stores",
        tenant_discriminator_parameter="entity_id",
        query_template_sha256="a" * 64,
        review_fingerprint=expected_review,
        production_ready=True,
        blockers=(),
    )

    assert expected_query_contract_review_fingerprint(ready) == expected_review

    policy_fingerprint = ai_query_contract_policy_fingerprint(ready)
    first = ai_execution_scope_fingerprint(
        query_contract_fingerprint=policy_fingerprint,
        data_scope_fingerprint="c" * 64,
        tenant_query_context_fingerprint="e" * 64,
    )
    changed_scope = ai_execution_scope_fingerprint(
        query_contract_fingerprint=policy_fingerprint,
        data_scope_fingerprint="d" * 64,
        tenant_query_context_fingerprint="e" * 64,
    )
    changed_tenant_context = ai_execution_scope_fingerprint(
        query_contract_fingerprint=policy_fingerprint,
        data_scope_fingerprint="c" * 64,
        tenant_query_context_fingerprint="f" * 64,
    )

    assert len(policy_fingerprint) == 64
    assert len(first) == 64
    assert first != changed_scope
    assert first != changed_tenant_context


def test_grant_store_accepts_no_caller_selected_query_or_tenant_authority() -> None:
    for method_name in (
        "issue",
        "consume",
        "consume_authorized_invocation",
    ):
        parameters = inspect.signature(
            getattr(RedisAiToolGrantStore, method_name)
        ).parameters
        assert "query_policy" not in parameters
        assert "query_contract_fingerprint" not in parameters
        assert "query_template_sha256" not in parameters
        assert "tenant_discriminator_parameter" not in parameters
        assert "tenant_query_context" not in parameters
        assert "tenant_query_context_fingerprint" not in parameters
        assert "entity_ids" not in parameters
