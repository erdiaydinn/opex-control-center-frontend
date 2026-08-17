from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class RepoSnapshot:
    registry_id:str; repository:str; commit_sha:str; branch_or_tag:str; paths:tuple[str,...]; symbols:tuple[str,...]; contracts:tuple[str,...]; owners:tuple[str,...]; license_status:str
@dataclass(frozen=True)
class ImpactEdge:
    source_registry_id:str; target_registry_id:str; contract:str; reason:str


def validate_snapshot(snapshot:RepoSnapshot)->None:
    if not snapshot.repository or len(snapshot.commit_sha)!=40 or any(c not in '0123456789abcdef' for c in snapshot.commit_sha.lower()):
        raise ValueError('repository snapshot requires exact repository and commit SHA')
    if snapshot.license_status.startswith('BLOCKED_'):
        raise ValueError('license-blocked repository cannot become analysis source')


def build_impact_edges(snapshots:Iterable[RepoSnapshot])->tuple[ImpactEdge,...]:
    items=tuple(snapshots)
    for item in items: validate_snapshot(item)
    edges=[]
    for source in items:
        source_contracts=set(source.contracts)
        for target in items:
            if source.registry_id==target.registry_id: continue
            shared=sorted(source_contracts & set(target.contracts))
            edges.extend(ImpactEdge(source.registry_id,target.registry_id,c,'shared_contract') for c in shared)
    return tuple(sorted(edges,key=lambda e:(e.contract,e.source_registry_id,e.target_registry_id)))


def repo_question_context(*,snapshots:Iterable[RepoSnapshot],question_terms:tuple[str,...])->tuple[RepoSnapshot,...]:
    terms={t.lower() for t in question_terms if t.strip()}
    selected=[]
    for snap in snapshots:
        validate_snapshot(snap)
        haystack=' '.join((snap.repository,*snap.paths,*snap.symbols,*snap.contracts)).lower()
        if terms and any(term in haystack for term in terms): selected.append(snap)
    return tuple(sorted(selected,key=lambda s:(s.repository,s.commit_sha)))
