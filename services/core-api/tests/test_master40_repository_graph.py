import pytest
from app.repository_intelligence.graph import RepoSnapshot,build_impact_edges,repo_question_context

def snap(rid,repo,sha,contracts,license_status='REVIEWED'):
    return RepoSnapshot(rid,repo,sha,'main',('service.py',),('Handler',),contracts,('platform',),license_status)

def test_impact_graph_is_exact_sha_and_contract_bound():
    a=snap('a','owner/a','a'*40,('tenant-contract','orders-v2')); b=snap('b','owner/b','b'*40,('orders-v2',))
    edges=build_impact_edges((a,b))
    assert any(e.contract=='orders-v2' and e.source_registry_id=='a' and e.target_registry_id=='b' for e in edges)
    assert repo_question_context(snapshots=(a,b),question_terms=('tenant-contract',))==(a,)

def test_unverified_or_license_blocked_snapshot_cannot_enter_repo_context():
    with pytest.raises(ValueError): repo_question_context(snapshots=(snap('x','owner/x','bad',()),),question_terms=('x',))
    with pytest.raises(ValueError): build_impact_edges((snap('x','owner/x','c'*40,(),'BLOCKED_UNTIL_IDENTITY_RESOLVED'),))
