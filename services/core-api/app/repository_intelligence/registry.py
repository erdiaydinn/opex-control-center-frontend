from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Classification = Literal['OWN','IMPORTED','DISCOVERED']
IdentityStatus = Literal['VERIFIED','UNRESOLVED']

@dataclass(frozen=True)
class RepositoryEntry:
    registry_id: str
    classification: Classification
    repository: str | None
    identity_status: IdentityStatus
    canonical_upstream: str | None
    relation: str
    license_status: str
    security_relevance: str
    archive_name: str | None = None

    @property
    def usable_as_code_source(self) -> bool:
        return self.identity_status == 'VERIFIED' and not self.license_status.startswith('BLOCKED_')


def load_registry(path: Path) -> tuple[RepositoryEntry, ...]:
    raw=json.loads(path.read_text(encoding='utf-8'))
    if raw.get('schema_version') != 1:
        raise ValueError('unsupported repository registry schema')
    entries=[]
    seen=set()
    for item in raw.get('entries',[]):
        rid=str(item['registry_id']).strip()
        if not rid or rid in seen:
            raise ValueError('duplicate or empty registry id')
        seen.add(rid)
        entry=RepositoryEntry(
            registry_id=rid,classification=item['classification'],repository=item.get('repository'),
            identity_status=item['identity_status'],canonical_upstream=item.get('canonical_upstream'),
            relation=str(item['relation']),license_status=str(item['license_status']),
            security_relevance=str(item['security_relevance']),archive_name=item.get('archive_name'))
        if entry.identity_status == 'VERIFIED' and not entry.repository:
            raise ValueError(f'verified entry requires repository: {rid}')
        if entry.identity_status == 'UNRESOLVED' and not entry.archive_name:
            raise ValueError(f'unresolved entry requires explicit archive identity: {rid}')
        if entry.identity_status == 'UNRESOLVED' and entry.usable_as_code_source:
            raise ValueError(f'unresolved entry cannot be usable: {rid}')
        entries.append(entry)
    return tuple(entries)


def assert_registry_preserves_required_seeds(entries: tuple[RepositoryEntry,...]) -> None:
    required={
      'own:opex-control-center-frontend','own:planai-audit','own:adaronya',
      'imported:council-of-high-intelligence','imported:cl4r1t4s','imported:computer-lab-automation',
      'imported:deep-learning-tutorials','imported:impeccable','imported:image-understanding','imported:jarvis-archives',
      'discovered:superset','discovered:superset-tr'}
    current={item.registry_id for item in entries}
    missing=sorted(required-current)
    if missing:
        raise ValueError('repository registry silently dropped required seeds: '+','.join(missing))
