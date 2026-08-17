from pathlib import Path
from app.repository_intelligence.registry import assert_registry_preserves_required_seeds,load_registry


def registry_path() -> Path:
    return Path(__file__).resolve().parents[3]/'docs/governance/eay_repository_intelligence_registry.json'


def test_registry_preserves_all_seed_sources_and_unresolved_identities():
    entries=load_registry(registry_path()); assert_registry_preserves_required_seeds(entries)
    assert {e.classification for e in entries} == {'OWN','IMPORTED','DISCOVERED'}
    unresolved=[e for e in entries if e.identity_status=='UNRESOLVED']
    assert unresolved and all(not e.usable_as_code_source for e in unresolved)
    pending=[e for e in entries if e.license_status=='PENDING_REVIEW']
    assert pending and all(not e.usable_as_code_source for e in pending)
    own_frontend=next(e for e in entries if e.registry_id=='own:opex-control-center-frontend')
    assert own_frontend.usable_as_code_source


def test_superset_canonical_and_localization_derivative_are_not_conflated():
    entries={e.registry_id:e for e in load_registry(registry_path())}
    assert entries['discovered:superset'].repository=='apache/superset'
    assert entries['discovered:superset-tr'].canonical_upstream=='apache/superset'
    assert entries['discovered:superset-tr'].relation=='LOCALIZATION_VENDOR_DERIVATIVE'
