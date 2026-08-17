from pathlib import Path
import pytest
from app.sre.observability import TelemetryEvent,load_observability_contract,load_profiles,validate_telemetry_event
ROOT=Path(__file__).resolve().parents[3]

def test_unified_observability_has_all_master45_signal_families_and_no_raw_secret_dimensions():
    c=load_observability_contract(ROOT/'docs/governance/eay_observability_contract.json')
    assert {'logs','traces','metrics','audit','ai_tool_calls','business_workflow_health'}<=set(c['required_signals'])
    validate_telemetry_event(c,TelemetryEvent('traces','budget','staging','invoice','post','ok',{'tenant_safe_hash':'abc'}))
    with pytest.raises(ValueError): validate_telemetry_event(c,TelemetryEvent('traces','budget','staging','invoice','post','ok',{'raw_secret':'x'}))

def test_load_profiles_cover_master46_shapes_and_require_managed_or_real_evidence():
    profiles=load_profiles(ROOT/'docs/governance/eay_production_shape_load_profiles.json')
    by={p['key']:p for p in profiles}
    assert by['portal_3000']['concurrency']==3000 and by['inventory_400_terminals']['concurrency']==400 and by['academy_1200_media']['concurrency']==1200
    assert all(p['evidence_class'] not in {'SYNTHETIC','REPOSITORY'} for p in profiles)
