import pytest
from app.release.category_leadership import BenchmarkSignal,ReleaseState,ReleaseTruth,category_leadership_backlog,next_state

def full_truth():
    return ReleaseTruth(True,{i:True for i in range(45,49)},{i:True for i in range(49,56)},{k:True for k in ('error_budget','task_success','latency','reconciliation','support_cases','device_issues','user_feedback','rollback_criteria')},{k:True for k in ('security','dr','identity','real_data','module_owner')})

def test_repository_green_alone_can_never_create_rc():
    with pytest.raises(ValueError): next_state(ReleaseState.DEVELOPMENT,ReleaseTruth(True,{},{}))

def test_release_chain_requires_pilot_and_controlled_tenant_module_activation():
    t=full_truth(); assert next_state(ReleaseState.DEVELOPMENT,t)==ReleaseState.PRODUCTION_CANDIDATE
    assert next_state(ReleaseState.PRODUCTION_CANDIDATE,t)==ReleaseState.PILOT
    assert next_state(ReleaseState.PILOT,t)==ReleaseState.PILOT_ACCEPTED
    with pytest.raises(ValueError): next_state(ReleaseState.PILOT_ACCEPTED,t)
    assert next_state(ReleaseState.PILOT_ACCEPTED,t,tenant_ids=('pilot-tenant',),modules=('workforce',))==ReleaseState.PRODUCTION_ACTIVE

def test_category_leadership_backlog_is_provenance_bound():
    signals=(BenchmarkSignal('competitor','planogram','new solver','release:1'),BenchmarkSignal('rumor','jarvis','unverified',''))
    assert [s.source for s in category_leadership_backlog(signals)]==['competitor']
