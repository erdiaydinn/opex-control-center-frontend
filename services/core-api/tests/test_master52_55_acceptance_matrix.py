from pathlib import Path
from app.acceptance.matrix import load_acceptance_matrix
ROOT=Path(__file__).resolve().parents[3]

def test_items_52_55_have_complete_standalone_cross_security_and_language_matrices():
    d=load_acceptance_matrix(ROOT/'docs/governance/eay_real_acceptance_matrix.json')
    assert 'dockos_standalone' in d['module_uat']
    assert 'jarvis_all_entitled_modules' in d['cross_module_uat']
    assert 'signed_url_replay' in d['security_penetration']
    assert 'screen_reader' in d['accessibility_language'] and 'mobile_ergonomics' in d['accessibility_language']
