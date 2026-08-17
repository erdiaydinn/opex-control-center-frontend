from pathlib import Path
from app.sre.governance import AcceptanceEvidence, external_gate_satisfied, load_sre_registry

ROOT=Path(__file__).resolve().parents[3]

def test_every_service_has_owner_slo_and_external_load_boundary():
    data=load_sre_registry(ROOT/'docs/governance/eay_sre_service_registry.json')
    assert len(data['services'])>=9
    assert all(item['owner'] for item in data['services'])


def test_repository_and_synthetic_results_do_not_satisfy_scale_or_dr():
    assert not external_gate_satisfied(AcceptanceEvidence('load','REPOSITORY','ci',True,'run:1'))
    assert not external_gate_satisfied(AcceptanceEvidence('load','SYNTHETIC','ci',True,'run:2'))
    assert external_gate_satisfied(AcceptanceEvidence('load','MANAGED_STAGING','staging',True,'run:3'))
    assert not external_gate_satisfied(AcceptanceEvidence('dr','MANAGED_STAGING','staging',False,'run:4'))
