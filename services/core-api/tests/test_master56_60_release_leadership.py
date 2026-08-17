import pytest
from app.release.category_leadership import BenchmarkSignal,ReleaseState,ReleaseTruth,StabilizationIssue,category_leadership_backlog,next_state,stabilization_backlog

def full_truth():
    return ReleaseTruth(True,{i:True for i in range(45,49)},{i:True for i in range(49,56)},{k:True for k in ('error_budget','task_success','latency','reconciliation','support_cases','device_issues','user_feedback','rollback_criteria')},{k:True for k in ('security','dr','identity','real_data','module_owner')})

def test_repository_green_alone_can_never_create_rc():
    with pytest.raises(ValueError): next_state(ReleaseState.DEVELOPMENT,ReleaseTruth(True,{},{}))

def test_release_chain_requires_pilot_and_controlled_tenant_module_activation():
    t=full_truth(); assert next_state(ReleaseState.DEVELOPMENT,t)==ReleaseState.PRODUCTION_CANDIDATE
    assert next_state(ReleaseState.PRODUCTION_CANDIDATE,t)==ReleaseState.PILOT
    assert next_state(ReleaseState.PILOT,t)==ReleaseState.PILOT_ACCEPTED
    with pytest.raises(ValueError): next_state(ReleaseState.PILOT_ACCEPTED,t)
    with pytest.raises(ValueError): next_state(ReleaseState.PILOT_ACCEPTED,t,tenant_ids=('*',),modules=('all',))
    assert next_state(ReleaseState.PILOT_ACCEPTED,t,tenant_ids=('pilot-tenant',),modules=('workforce',))==ReleaseState.PRODUCTION_ACTIVE

def test_evidence_revocation_blocks_pilot_start_even_after_rc_was_previously_created():
    revoked=ReleaseTruth(True,{i:True for i in range(45,49)},{i:(i!=54) for i in range(49,56)})
    with pytest.raises(ValueError): next_state(ReleaseState.PRODUCTION_CANDIDATE,revoked)

def test_stabilization_prioritizes_provenance_bound_p0_p1():
    issues=(StabilizationIssue('support','friction','slow approval','ticket:2','P1'),StabilizationIssue('monitoring','slow_queries','timeout','trace:1','P0'),StabilizationIssue('rumor','bugs','unknown','','P0'))
    backlog=stabilization_backlog(issues)
    assert [(i.priority,i.source) for i in backlog]==[('P0','monitoring'),('P1','support')]

def test_category_leadership_backlog_is_provenance_bound():
    signals=(BenchmarkSignal('competitor','planogram','new solver','release:1'),BenchmarkSignal('rumor','jarvis','unverified',''))
    assert [s.source for s in category_leadership_backlog(signals)]==['competitor']
