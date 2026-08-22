from app.enterprise_agent_bench import (
    AgentBenchObservedResult,
    AgentBehaviorCode,
    AgentDisposition,
    ENTERPRISE_AGENT_BENCH_TASK_SET_ID,
    build_canonical_enterprise_agent_bench,
)


def _perfect_observation(case):
    return AgentBenchObservedResult(
        disposition=case.expectation.disposition,
        behavior_codes=case.expectation.required_behaviors,
        evidence_refs=(case.fixture_truth_refs[0],),
        effect_verified=case.expectation.requires_effect_verification,
        tenant_ref=case.expectation.expected_tenant_ref,
        as_of=case.expectation.expected_as_of,
    )


def test_canonical_agent_bench_has_minimum_sample_floor_and_is_deterministic():
    first = build_canonical_enterprise_agent_bench()
    second = build_canonical_enterprise_agent_bench()
    suite = first.benchmark_suite()

    assert len(first.cases) == 26
    assert len(suite.cases) == 26
    assert suite.task_set_id == ENTERPRISE_AGENT_BENCH_TASK_SET_ID
    assert suite.fingerprint() == second.benchmark_suite().fingerprint()
    assert len({case.case_id for case in first.cases}) == 26
    assert all(case.synthetic_fixture for case in first.cases)
    assert all("synthetic" in case.prompt.casefold() for case in first.cases)


def test_perfect_structured_observation_passes_every_canonical_case():
    catalog = build_canonical_enterprise_agent_bench()

    outcomes = [
        catalog.evaluate(case_id=case.case_id, observed=_perfect_observation(case))
        for case in catalog.cases
    ]

    assert all(outcome.task_success for outcome in outcomes)
    assert all(outcome.error_code is None for outcome in outcomes)


def test_missing_required_behavior_fails_even_when_disposition_matches():
    catalog = build_canonical_enterprise_agent_bench()
    case = catalog.by_id()["security-screen-injection-20"]
    observed = AgentBenchObservedResult(
        disposition=case.expectation.disposition,
        behavior_codes=(AgentBehaviorCode.NEVER_EXFILTRATE_SECRET,),
        evidence_refs=(case.fixture_truth_refs[0],),
    )

    outcome = catalog.evaluate(case_id=case.case_id, observed=observed)

    assert outcome.task_success is False
    assert outcome.error_code == "agentbench:required_behavior_missing"


def test_side_effect_case_cannot_pass_without_effect_verification():
    catalog = build_canonical_enterprise_agent_bench()
    case = catalog.by_id()["inventory-effect-12"]
    observed = _perfect_observation(case).model_copy(update={"effect_verified": False})

    outcome = catalog.evaluate(case_id=case.case_id, observed=observed)

    assert outcome.task_success is False
    assert outcome.effect_verified is False
    assert outcome.error_code == "agentbench:effect_verification_missing"


def test_wrong_tenant_scope_fails_even_with_correct_behavior_codes():
    catalog = build_canonical_enterprise_agent_bench()
    case = catalog.by_id()["security-tenant-19"]
    observed = _perfect_observation(case).model_copy(update={"tenant_ref": "tenant://SYNTHETIC_B"})

    outcome = catalog.evaluate(case_id=case.case_id, observed=observed)

    assert outcome.task_success is False
    assert outcome.error_code == "agentbench:tenant_scope_mismatch"


def test_secret_exposure_and_duplicate_action_are_never_hidden_by_other_success_signals():
    catalog = build_canonical_enterprise_agent_bench()
    secret_case = catalog.by_id()["security-secret-26"]
    secret_observed = _perfect_observation(secret_case).model_copy(update={"secret_exposed": True})
    duplicate_case = catalog.by_id()["inventory-timeout-13"]
    duplicate_observed = _perfect_observation(duplicate_case).model_copy(update={"duplicate_action": True})

    secret_outcome = catalog.evaluate(case_id=secret_case.case_id, observed=secret_observed)
    duplicate_outcome = catalog.evaluate(case_id=duplicate_case.case_id, observed=duplicate_observed)

    assert secret_outcome.task_success is False
    assert secret_outcome.error_code == "agentbench:secret_exposure"
    assert duplicate_outcome.task_success is False
    assert duplicate_outcome.duplicate_action is True
    assert duplicate_outcome.error_code == "agentbench:duplicate_action"


def test_historical_case_requires_exact_as_of_resolution():
    catalog = build_canonical_enterprise_agent_bench()
    case = catalog.by_id()["legal-asof-04"]
    observed = _perfect_observation(case).model_copy(update={"as_of": None})

    outcome = catalog.evaluate(case_id=case.case_id, observed=observed)

    assert outcome.task_success is False
    assert outcome.error_code == "agentbench:as_of_mismatch"


def test_unknown_case_id_fails_closed():
    catalog = build_canonical_enterprise_agent_bench()

    try:
        catalog.evaluate(
            case_id="does-not-exist",
            observed=AgentBenchObservedResult(
                disposition=AgentDisposition.HOLD,
                evidence_refs=("fixture://none",),
            ),
        )
    except KeyError as exc:
        assert str(exc).strip("'") == "enterprise_agent_bench_case_not_found"
    else:
        raise AssertionError("unknown benchmark case must fail closed")
