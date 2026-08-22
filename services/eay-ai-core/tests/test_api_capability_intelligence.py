from app.api_capability_intelligence import (
    ApiCapabilityEvidence,
    CapabilityState,
    IdempotencyStrategy,
    ValidationEnvironment,
    evaluate_api_capability,
)
from app.api_discovery_intelligence import (
    CaptureSource,
    ObservedHttpExchange,
    discover_api_candidates,
)


def _candidate(method: str = "POST"):
    exchange = ObservedHttpExchange(
        application_id="carsiportal",
        capture_source=CaptureSource.CHROME_DEVTOOLS,
        method=method,
        url="https://carsi.example.com/api/inventory/adjustments",
        status_code=200,
        resource_type="fetch",
        request_content_type="application/json",
        response_content_type="application/json",
        user_action_ref="ui-stock-adjust-1" if method != "GET" else None,
        auth_context_ref="managed-session:carsiportal",
        tenant_scope_ref="warehouse:fulya",
        authorization_header_present=True,
    )
    return discover_api_candidates([exchange], allowed_hosts={"carsi.example.com"})[0]


def _fingerprint(char: str) -> str:
    return char * 64


def test_mutating_endpoint_cannot_activate_from_production_observation_alone():
    evidence = ApiCapabilityEvidence(
        candidate=_candidate(),
        capability_name="inventory.adjust_stock",
        business_object="inventory_stock",
        request_schema_fingerprint=_fingerprint("a"),
        response_schema_fingerprint=_fingerprint("b"),
        semantic_mapping_verified=True,
        authorization_scope_verified=True,
        tenant_scope_verified=True,
        schema_stability_verified=True,
        validation_environment=ValidationEnvironment.OBSERVATION_ONLY,
        non_destructive_validation_passed=True,
        gui_api_equivalence_verified=True,
        effect_verifier_defined=True,
        effect_verifier_ref="inventory.read_stock_after_adjustment",
        idempotency_strategy=IdempotencyStrategy.EXACT_EFFECT_DEDUP,
        audit_contract_ref="eay-action-result-v1",
        rollback_or_compensation_ref="inventory.compensating_adjustment",
    )

    decision = evaluate_api_capability(evidence)
    assert decision.production_execution_permitted is False
    assert decision.state is CapabilityState.BLOCKED
    assert "api_write_requires_non_production_validation_environment" in decision.blockers


def test_mutating_endpoint_requires_effect_verification_and_idempotency():
    evidence = ApiCapabilityEvidence(
        candidate=_candidate(),
        capability_name="inventory.adjust_stock",
        business_object="inventory_stock",
        request_schema_fingerprint=_fingerprint("a"),
        response_schema_fingerprint=_fingerprint("b"),
        semantic_mapping_verified=True,
        authorization_scope_verified=True,
        tenant_scope_verified=True,
        schema_stability_verified=True,
        validation_environment=ValidationEnvironment.STAGING,
        non_destructive_validation_passed=True,
        gui_api_equivalence_verified=True,
        audit_contract_ref="eay-action-result-v1",
        rollback_or_compensation_ref="inventory.compensating_adjustment",
    )

    decision = evaluate_api_capability(evidence)
    assert "api_write_effect_verifier_missing" in decision.blockers
    assert "api_write_idempotency_strategy_missing" in decision.blockers
    assert decision.production_execution_permitted is False


def test_fully_validated_mutating_capability_can_become_active():
    evidence = ApiCapabilityEvidence(
        candidate=_candidate(),
        capability_name="inventory.adjust_stock",
        business_object="inventory_stock",
        request_schema_fingerprint=_fingerprint("a"),
        response_schema_fingerprint=_fingerprint("b"),
        semantic_mapping_verified=True,
        authorization_scope_verified=True,
        tenant_scope_verified=True,
        schema_stability_verified=True,
        validation_environment=ValidationEnvironment.STAGING,
        non_destructive_validation_passed=True,
        gui_api_equivalence_verified=True,
        effect_verifier_defined=True,
        effect_verifier_ref="inventory.read_stock_after_adjustment",
        idempotency_strategy=IdempotencyStrategy.EXACT_EFFECT_DEDUP,
        audit_contract_ref="eay-action-result-v1",
        rollback_or_compensation_ref="inventory.compensating_adjustment",
    )

    decision = evaluate_api_capability(evidence)
    assert decision.state is CapabilityState.ACTIVE
    assert decision.production_execution_permitted is True
    assert "postcondition_effect_verification" in decision.required_runtime_guards
    assert "duplicate_effect_detection" in decision.required_runtime_guards


def test_approval_required_capability_stays_blocked_until_approval_evidence_exists():
    evidence = ApiCapabilityEvidence(
        candidate=_candidate(),
        capability_name="inventory.adjust_stock_high_value",
        business_object="inventory_stock",
        request_schema_fingerprint=_fingerprint("a"),
        response_schema_fingerprint=_fingerprint("b"),
        semantic_mapping_verified=True,
        authorization_scope_verified=True,
        tenant_scope_verified=True,
        schema_stability_verified=True,
        validation_environment=ValidationEnvironment.SANDBOX,
        non_destructive_validation_passed=True,
        gui_api_equivalence_verified=True,
        effect_verifier_defined=True,
        effect_verifier_ref="inventory.read_stock_after_adjustment",
        idempotency_strategy=IdempotencyStrategy.IDEMPOTENCY_KEY,
        approval_required=True,
        audit_contract_ref="eay-action-result-v1",
        rollback_or_compensation_ref="inventory.compensating_adjustment",
    )

    decision = evaluate_api_capability(evidence)
    assert decision.production_execution_permitted is False
    assert "api_capability_required_approval_missing" in decision.blockers


def test_read_capability_still_requires_schema_auth_tenant_and_audit_truth():
    evidence = ApiCapabilityEvidence(
        candidate=_candidate(method="GET"),
        capability_name="inventory.read_stock",
        business_object="inventory_stock",
        request_schema_fingerprint=_fingerprint("c"),
        response_schema_fingerprint=_fingerprint("d"),
        semantic_mapping_verified=True,
        authorization_scope_verified=True,
        tenant_scope_verified=True,
        schema_stability_verified=True,
        validation_environment=ValidationEnvironment.OBSERVATION_ONLY,
        audit_contract_ref="eay-action-result-v1",
    )

    decision = evaluate_api_capability(evidence)
    assert decision.state is CapabilityState.ACTIVE
    assert decision.production_execution_permitted is True
    assert decision.risk == "read_only"
