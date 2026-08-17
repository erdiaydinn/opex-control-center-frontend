from pathlib import Path
from app.sre.chaos_dr import ChaosResult,DrResult,chaos_result_accepted,dr_result_accepted,load_chaos_dr_contract
ROOT=Path(__file__).resolve().parents[3]

def test_all_master47_scenarios_are_present_and_synthetic_cannot_pass():
    c=load_chaos_dr_contract(ROOT/'docs/governance/eay_chaos_dr_acceptance.json')
    assert {'db_restart','redis_unavailable','bigquery_denial','retry_storm'}<=set(c['chaos_scenarios'])
    result=ChaosResult('db_restart','ci',True,tuple(c['required_invariants']),'ci:1')
    assert not chaos_result_accepted(c,result)

def test_dr_requires_measured_rpo_rto_in_managed_environment():
    assert not dr_result_accepted(DrResult('ci',True,0,20,'run:1'))
    assert not dr_result_accepted(DrResult('staging',True,None,20,'run:2'))
    assert dr_result_accepted(DrResult('managed-staging',True,30,180,'restore:approved'))
