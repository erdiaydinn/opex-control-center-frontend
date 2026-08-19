"""Company-scoped defensive attack-path and blast-radius intelligence.

This contract models how a compromise could *potentially* traverse reviewed company
configuration and reach privileged/crown-jewel surfaces. It is defensive only:
- graph reachability never proves compromise or incident causality;
- ATT&CK technique IDs are descriptive metadata, never executable steps;
- control-cut simulation never mutates company infrastructure;
- no path, graph, or assessment grants execution authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.company_context_boundary import CompanyIdentity
from app.cyber_defense_intelligence import AssetCriticality, DefensivePriority

CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT = "eay-cyber-attack-path-intelligence-v1"

_MAX_NODES = 2048
_MAX_RELATIONS = 8192
_MAX_HOPS = 8
_MAX_PATHS = 512

_SECRET_OR_OFFENSIVE_REF = re.compile(
    r"(?i)(?:authorization|bearer|api[_-]?key|token|password|passwd|secret|"
    r"session(?:id)?|cookie|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|"
    r"persistence[_-]?payload|ransomware[_-]?payload|shellcode)"
)


class CyberSurfaceKind(str, Enum):
    INTERNET_EDGE = "internet_edge"
    APPLICATION = "application"
    SERVICE = "service"
    ENDPOINT = "endpoint"
    IDENTITY = "identity"
    SERVICE_ACCOUNT = "service_account"
    CLOUD_RESOURCE = "cloud_resource"
    DATA_STORE = "data_store"
    ADMIN_PLANE = "admin_plane"
    THIRD_PARTY = "third_party"
    AI_AGENT = "ai_agent"


class CyberRelationKind(str, Enum):
    NETWORK_REACHABILITY = "network_reachability"
    TRUST_RELATIONSHIP = "trust_relationship"
    CREDENTIAL_USE = "credential_use"
    ROLE_ASSUME = "role_assume"
    API_ACCESS = "api_access"
    DATA_ACCESS = "data_access"
    DEPENDENCY = "dependency"
    CONTROL_PLANE_ACCESS = "control_plane_access"


class RelationEvidenceStrength(str, Enum):
    INFERRED = "inferred"
    OBSERVED = "observed"
    VERIFIED_CONFIGURATION = "verified_configuration"


class AttackPathStatus(str, Enum):
    HYPOTHETICAL = "hypothetical"
    EVIDENCE_SUPPORTED = "evidence_supported"
    CONFIGURATION_VERIFIED = "configuration_verified"


class CompanyCyberNode(BaseModel):
    contract: str = CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT
    node_ref: str = Field(min_length=1)
    identity: CompanyIdentity
    surface_kind: CyberSurfaceKind
    criticality: AssetCriticality
    internet_reachable: bool = False
    privileged: bool = False
    crown_jewel: bool = False
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    firm_truth_authority_granted: bool = False
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    exploit_execution_allowed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def node_is_integral_and_defensive(self) -> CompanyCyberNode:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _aware(self.observed_at, "cyber_attack_node_observed_at_requires_timezone")
        _aware(self.recorded_at, "cyber_attack_node_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("cyber_attack_node_recorded_at_predates_observation")
        _unique(self.evidence_refs, "cyber_attack_node_evidence_refs_must_be_unique")
        if self.firm_truth_authority_granted:
            raise ValueError("cyber_attack_node_never_grants_firm_truth_authority")
        if self.incident_confirmation_granted:
            raise ValueError("cyber_attack_node_never_confirms_incident")
        if self.execution_authority_granted or self.exploit_execution_allowed:
            raise ValueError("cyber_attack_node_never_grants_execution_authority")
        for ref in (self.node_ref, *self.evidence_refs):
            _safe_ref(ref, "cyber_attack_node_unsafe_reference_forbidden")
        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("cyber_attack_node_fingerprint_mismatch")
        return self


class CompanyCyberRelation(BaseModel):
    contract: str = CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT
    relation_id: str = Field(min_length=1)
    identity: CompanyIdentity
    from_node_ref: str = Field(min_length=1)
    to_node_ref: str = Field(min_length=1)
    relation_kind: CyberRelationKind
    evidence_strength: RelationEvidenceStrength
    attack_technique_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observed_at: datetime
    recorded_at: datetime
    attack_success_proven: bool = False
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    exploit_execution_allowed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def relation_is_integral_and_non_executing(self) -> CompanyCyberRelation:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _aware(self.observed_at, "cyber_attack_relation_observed_at_requires_timezone")
        _aware(self.recorded_at, "cyber_attack_relation_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("cyber_attack_relation_recorded_at_predates_observation")
        if self.from_node_ref == self.to_node_ref:
            raise ValueError("cyber_attack_relation_self_loop_forbidden")
        _unique(self.attack_technique_ids, "cyber_attack_technique_ids_must_be_unique")
        _unique(self.evidence_refs, "cyber_attack_relation_evidence_refs_must_be_unique")
        if self.attack_success_proven:
            raise ValueError("cyber_attack_relation_never_proves_attack_success")
        if self.incident_confirmation_granted:
            raise ValueError("cyber_attack_relation_never_confirms_incident")
        if self.execution_authority_granted or self.exploit_execution_allowed:
            raise ValueError("cyber_attack_relation_never_grants_execution_authority")
        for ref in (
            self.relation_id,
            self.from_node_ref,
            self.to_node_ref,
            *self.attack_technique_ids,
            *self.evidence_refs,
        ):
            _safe_ref(ref, "cyber_attack_relation_unsafe_reference_forbidden")
        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("cyber_attack_relation_fingerprint_mismatch")
        return self


class CompanyAttackGraphSnapshot(BaseModel):
    contract: str = CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT
    identity: CompanyIdentity
    as_of: datetime
    nodes: tuple[CompanyCyberNode, ...]
    relations: tuple[CompanyCyberRelation, ...]
    attack_success_proven: bool = False
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    exploit_execution_allowed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def graph_is_exact_company_and_time_bound(self) -> CompanyAttackGraphSnapshot:
        identity = CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _aware(self.as_of, "cyber_attack_graph_as_of_requires_timezone")
        if len(self.nodes) > _MAX_NODES:
            raise ValueError("cyber_attack_graph_node_limit_exceeded")
        if len(self.relations) > _MAX_RELATIONS:
            raise ValueError("cyber_attack_graph_relation_limit_exceeded")
        if self.attack_success_proven or self.incident_confirmation_granted:
            raise ValueError("cyber_attack_graph_never_confirms_attack_or_incident")
        if self.execution_authority_granted or self.exploit_execution_allowed:
            raise ValueError("cyber_attack_graph_never_grants_execution_authority")

        node_by_ref: dict[str, CompanyCyberNode] = {}
        for node in self.nodes:
            node = CompanyCyberNode.model_validate(node.model_dump(mode="json"))
            _same_identity(
                expected=identity,
                actual=node.identity,
                error="cyber_attack_graph_cross_company_node",
            )
            if node.node_ref in node_by_ref:
                raise ValueError("cyber_attack_graph_duplicate_node_ref")
            if node.observed_at > self.as_of or node.recorded_at > self.as_of:
                raise ValueError("cyber_attack_graph_contains_future_known_node")
            node_by_ref[node.node_ref] = node

        relation_ids: set[str] = set()
        for relation in self.relations:
            relation = CompanyCyberRelation.model_validate(
                relation.model_dump(mode="json")
            )
            _same_identity(
                expected=identity,
                actual=relation.identity,
                error="cyber_attack_graph_cross_company_relation",
            )
            if relation.relation_id in relation_ids:
                raise ValueError("cyber_attack_graph_duplicate_relation_id")
            relation_ids.add(relation.relation_id)
            if (
                relation.observed_at > self.as_of
                or relation.recorded_at > self.as_of
            ):
                raise ValueError("cyber_attack_graph_contains_future_known_relation")
            if (
                relation.from_node_ref not in node_by_ref
                or relation.to_node_ref not in node_by_ref
            ):
                raise ValueError("cyber_attack_graph_relation_endpoint_missing")

        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("cyber_attack_graph_fingerprint_mismatch")
        return self


class DefensiveAttackPath(BaseModel):
    contract: str = CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT
    path_id: str = Field(min_length=1)
    identity: CompanyIdentity
    node_refs: tuple[str, ...] = Field(min_length=2)
    relation_ids: tuple[str, ...] = Field(min_length=1)
    status: AttackPathStatus
    attack_technique_ids: tuple[str, ...]
    internet_entry: bool
    reaches_privileged_surface: bool
    reaches_crown_jewel: bool
    hop_count: int = Field(ge=1, le=_MAX_HOPS)
    attack_success_proven: bool = False
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    exploit_execution_allowed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def path_is_advisory_only(self) -> DefensiveAttackPath:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        if len(self.relation_ids) != len(self.node_refs) - 1:
            raise ValueError("cyber_attack_path_topology_mismatch")
        if len(self.node_refs) != len(set(self.node_refs)):
            raise ValueError("cyber_attack_path_cycle_forbidden")
        _unique(self.relation_ids, "cyber_attack_path_relation_ids_must_be_unique")
        _unique(self.attack_technique_ids, "cyber_attack_path_techniques_must_be_unique")
        if self.hop_count != len(self.relation_ids):
            raise ValueError("cyber_attack_path_hop_count_mismatch")
        if self.attack_success_proven or self.incident_confirmation_granted:
            raise ValueError("cyber_attack_path_never_confirms_attack_or_incident")
        if self.execution_authority_granted or self.exploit_execution_allowed:
            raise ValueError("cyber_attack_path_never_grants_execution_authority")
        for ref in (
            self.path_id,
            *self.node_refs,
            *self.relation_ids,
            *self.attack_technique_ids,
        ):
            _safe_ref(ref, "cyber_attack_path_unsafe_reference_forbidden")
        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("cyber_attack_path_fingerprint_mismatch")
        return self


class DefensiveAttackPathSet(BaseModel):
    contract: str = CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT
    identity: CompanyIdentity
    graph_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    as_of: datetime
    entry_node_refs: tuple[str, ...] = Field(min_length=1)
    paths: tuple[DefensiveAttackPath, ...]
    max_hops: int = Field(ge=1, le=_MAX_HOPS)
    max_paths: int = Field(ge=1, le=_MAX_PATHS)
    truncated: bool = False
    attack_success_proven: bool = False
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    exploit_execution_allowed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def path_set_is_integral_and_non_authoritative(self) -> DefensiveAttackPathSet:
        identity = CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _aware(self.as_of, "cyber_attack_path_set_as_of_requires_timezone")
        _unique(self.entry_node_refs, "cyber_attack_path_entries_must_be_unique")
        path_ids: set[str] = set()
        for path in self.paths:
            path = DefensiveAttackPath.model_validate(path.model_dump(mode="json"))
            _same_identity(
                expected=identity,
                actual=path.identity,
                error="cyber_attack_path_set_cross_company_path",
            )
            if path.path_id in path_ids:
                raise ValueError("cyber_attack_path_set_duplicate_path_id")
            path_ids.add(path.path_id)
        if self.attack_success_proven or self.incident_confirmation_granted:
            raise ValueError("cyber_attack_path_set_never_confirms_attack_or_incident")
        if self.execution_authority_granted or self.exploit_execution_allowed:
            raise ValueError("cyber_attack_path_set_never_grants_execution_authority")
        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("cyber_attack_path_set_fingerprint_mismatch")
        return self


class BlastRadiusAssessment(BaseModel):
    contract: str = CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT
    identity: CompanyIdentity
    graph_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    path_set_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    priority: DefensivePriority
    score: int = Field(ge=0, le=100)
    reachable_node_refs: tuple[str, ...]
    reachable_privileged_refs: tuple[str, ...]
    reachable_crown_jewel_refs: tuple[str, ...]
    dangerous_path_count: int = Field(ge=0)
    defensive_chokepoint_relation_refs: tuple[str, ...]
    reason_codes: tuple[str, ...]
    advisory_only: bool = True
    attack_success_proven: bool = False
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    exploit_execution_allowed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def assessment_is_defensive_only(self) -> BlastRadiusAssessment:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        for values in (
            self.reachable_node_refs,
            self.reachable_privileged_refs,
            self.reachable_crown_jewel_refs,
            self.defensive_chokepoint_relation_refs,
            self.reason_codes,
        ):
            if len(values) != len(set(values)):
                raise ValueError("cyber_blast_radius_duplicate_reference")
        if not self.advisory_only:
            raise ValueError("cyber_blast_radius_must_remain_advisory")
        if self.attack_success_proven or self.incident_confirmation_granted:
            raise ValueError("cyber_blast_radius_never_confirms_attack_or_incident")
        if self.execution_authority_granted or self.exploit_execution_allowed:
            raise ValueError("cyber_blast_radius_never_grants_execution_authority")
        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("cyber_blast_radius_fingerprint_mismatch")
        return self


class ControlCutSimulation(BaseModel):
    contract: str = CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT
    identity: CompanyIdentity
    relation_id: str = Field(min_length=1)
    baseline_dangerous_path_count: int = Field(ge=0)
    remaining_dangerous_path_count: int = Field(ge=0)
    dangerous_paths_reduced: int = Field(ge=0)
    baseline_crown_jewel_refs: tuple[str, ...]
    remaining_crown_jewel_refs: tuple[str, ...]
    mutation_applied: bool = False
    advisory_only: bool = True
    execution_authority_granted: bool = False
    exploit_execution_allowed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def simulation_never_mutates_or_authorizes(self) -> ControlCutSimulation:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        if self.mutation_applied:
            raise ValueError("cyber_control_cut_simulation_never_mutates")
        if not self.advisory_only:
            raise ValueError("cyber_control_cut_simulation_must_remain_advisory")
        if self.execution_authority_granted or self.exploit_execution_allowed:
            raise ValueError("cyber_control_cut_simulation_never_grants_execution_authority")
        if self.dangerous_paths_reduced != max(
            0,
            self.baseline_dangerous_path_count
            - self.remaining_dangerous_path_count,
        ):
            raise ValueError("cyber_control_cut_reduction_mismatch")
        _safe_ref(self.relation_id, "cyber_control_cut_unsafe_reference_forbidden")
        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("cyber_control_cut_fingerprint_mismatch")
        return self


def build_company_cyber_node(
    *,
    identity: CompanyIdentity,
    node_ref: str,
    surface_kind: CyberSurfaceKind,
    criticality: AssetCriticality,
    evidence_refs: tuple[str, ...],
    observed_at: datetime,
    recorded_at: datetime,
    internet_reachable: bool = False,
    privileged: bool = False,
    crown_jewel: bool = False,
) -> CompanyCyberNode:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    draft = {
        "contract": CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT,
        "node_ref": node_ref,
        "identity": identity.model_dump(mode="json"),
        "surface_kind": surface_kind.value,
        "criticality": criticality.value,
        "internet_reachable": internet_reachable,
        "privileged": privileged,
        "crown_jewel": crown_jewel,
        "evidence_refs": list(evidence_refs),
        "observed_at": _iso(observed_at),
        "recorded_at": _iso(recorded_at),
        "firm_truth_authority_granted": False,
        "incident_confirmation_granted": False,
        "execution_authority_granted": False,
        "exploit_execution_allowed": False,
    }
    return CompanyCyberNode.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def build_company_cyber_relation(
    *,
    identity: CompanyIdentity,
    relation_id: str,
    from_node_ref: str,
    to_node_ref: str,
    relation_kind: CyberRelationKind,
    evidence_strength: RelationEvidenceStrength,
    evidence_refs: tuple[str, ...],
    observed_at: datetime,
    recorded_at: datetime,
    attack_technique_ids: tuple[str, ...] = (),
) -> CompanyCyberRelation:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    draft = {
        "contract": CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT,
        "relation_id": relation_id,
        "identity": identity.model_dump(mode="json"),
        "from_node_ref": from_node_ref,
        "to_node_ref": to_node_ref,
        "relation_kind": relation_kind.value,
        "evidence_strength": evidence_strength.value,
        "attack_technique_ids": list(attack_technique_ids),
        "evidence_refs": list(evidence_refs),
        "observed_at": _iso(observed_at),
        "recorded_at": _iso(recorded_at),
        "attack_success_proven": False,
        "incident_confirmation_granted": False,
        "execution_authority_granted": False,
        "exploit_execution_allowed": False,
    }
    return CompanyCyberRelation.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def build_company_attack_graph_snapshot(
    *,
    identity: CompanyIdentity,
    nodes: tuple[CompanyCyberNode, ...],
    relations: tuple[CompanyCyberRelation, ...],
    as_of: datetime,
) -> CompanyAttackGraphSnapshot:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    _aware(as_of, "cyber_attack_graph_as_of_requires_timezone")
    eligible_nodes: list[CompanyCyberNode] = []
    for raw in nodes:
        node = CompanyCyberNode.model_validate(raw.model_dump(mode="json"))
        _same_identity(
            expected=identity,
            actual=node.identity,
            error="cyber_attack_graph_cross_company_node",
        )
        if node.observed_at <= as_of and node.recorded_at <= as_of:
            eligible_nodes.append(node)

    node_refs = {node.node_ref for node in eligible_nodes}
    eligible_relations: list[CompanyCyberRelation] = []
    for raw in relations:
        relation = CompanyCyberRelation.model_validate(raw.model_dump(mode="json"))
        _same_identity(
            expected=identity,
            actual=relation.identity,
            error="cyber_attack_graph_cross_company_relation",
        )
        if relation.observed_at <= as_of and relation.recorded_at <= as_of:
            if (
                relation.from_node_ref not in node_refs
                or relation.to_node_ref not in node_refs
            ):
                raise ValueError("cyber_attack_graph_relation_endpoint_missing")
            eligible_relations.append(relation)

    draft = {
        "contract": CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT,
        "identity": identity.model_dump(mode="json"),
        "as_of": _iso(as_of),
        "nodes": [node.model_dump(mode="json") for node in eligible_nodes],
        "relations": [
            relation.model_dump(mode="json") for relation in eligible_relations
        ],
        "attack_success_proven": False,
        "incident_confirmation_granted": False,
        "execution_authority_granted": False,
        "exploit_execution_allowed": False,
    }
    return CompanyAttackGraphSnapshot.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def enumerate_defensive_attack_paths(
    *,
    snapshot: CompanyAttackGraphSnapshot,
    entry_node_refs: tuple[str, ...],
    max_hops: int = 6,
    max_paths: int = _MAX_PATHS,
) -> DefensiveAttackPathSet:
    snapshot = CompanyAttackGraphSnapshot.model_validate(
        snapshot.model_dump(mode="json")
    )
    if not 1 <= max_hops <= _MAX_HOPS:
        raise ValueError("cyber_attack_path_max_hops_out_of_range")
    if not 1 <= max_paths <= _MAX_PATHS:
        raise ValueError("cyber_attack_path_max_paths_out_of_range")
    _unique(entry_node_refs, "cyber_attack_path_entries_must_be_unique")

    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    for ref in entry_node_refs:
        _safe_ref(ref, "cyber_attack_path_unsafe_reference_forbidden")
        if ref not in node_by_ref:
            raise ValueError("cyber_attack_path_entry_node_missing")

    outgoing: dict[str, list[CompanyCyberRelation]] = defaultdict(list)
    relation_by_id = {relation.relation_id: relation for relation in snapshot.relations}
    for relation in snapshot.relations:
        outgoing[relation.from_node_ref].append(relation)
    for relations in outgoing.values():
        relations.sort(key=lambda item: item.relation_id)

    paths: list[DefensiveAttackPath] = []
    truncated = False
    queue: deque[tuple[tuple[str, ...], tuple[str, ...]]] = deque(
        ((entry,), ()) for entry in sorted(entry_node_refs)
    )
    while queue:
        node_refs, relation_ids = queue.popleft()
        if len(relation_ids) >= max_hops:
            continue
        current = node_refs[-1]
        for relation in outgoing.get(current, ()):
            next_ref = relation.to_node_ref
            if next_ref in node_refs:
                continue
            next_nodes = (*node_refs, next_ref)
            next_relations = (*relation_ids, relation.relation_id)
            target = node_by_ref[next_ref]
            if target.privileged or target.crown_jewel:
                if len(paths) >= max_paths:
                    truncated = True
                    queue.clear()
                    break
                paths.append(
                    _build_path(
                        snapshot=snapshot,
                        node_refs=next_nodes,
                        relation_ids=next_relations,
                        node_by_ref=node_by_ref,
                        relation_by_id=relation_by_id,
                    )
                )
            if len(next_relations) < max_hops:
                queue.append((next_nodes, next_relations))

    draft = {
        "contract": CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT,
        "identity": snapshot.identity.model_dump(mode="json"),
        "graph_fingerprint": snapshot.fingerprint,
        "as_of": _iso(snapshot.as_of),
        "entry_node_refs": sorted(entry_node_refs),
        "paths": [path.model_dump(mode="json") for path in paths],
        "max_hops": max_hops,
        "max_paths": max_paths,
        "truncated": truncated,
        "attack_success_proven": False,
        "incident_confirmation_granted": False,
        "execution_authority_granted": False,
        "exploit_execution_allowed": False,
    }
    return DefensiveAttackPathSet.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def assess_blast_radius(
    *,
    snapshot: CompanyAttackGraphSnapshot,
    path_set: DefensiveAttackPathSet,
) -> BlastRadiusAssessment:
    snapshot = CompanyAttackGraphSnapshot.model_validate(
        snapshot.model_dump(mode="json")
    )
    path_set = DefensiveAttackPathSet.model_validate(
        path_set.model_dump(mode="json")
    )
    _same_identity(
        expected=snapshot.identity,
        actual=path_set.identity,
        error="cyber_blast_radius_company_identity_mismatch",
    )
    if path_set.graph_fingerprint != snapshot.fingerprint:
        raise ValueError("cyber_blast_radius_graph_fingerprint_mismatch")

    node_by_ref = {node.node_ref: node for node in snapshot.nodes}
    reachable = _reachable_nodes(
        snapshot=snapshot,
        entry_node_refs=path_set.entry_node_refs,
        max_hops=path_set.max_hops,
    )
    privileged = tuple(
        sorted(ref for ref in reachable if node_by_ref[ref].privileged)
    )
    crown_jewels = tuple(
        sorted(ref for ref in reachable if node_by_ref[ref].crown_jewel)
    )
    internet_entry = any(
        node_by_ref[ref].internet_reachable for ref in path_set.entry_node_refs
    )

    score = 0
    reasons: list[str] = []
    if crown_jewels:
        score += 50
        reasons.append("crown_jewel_reachable")
    if privileged:
        score += 25
        reasons.append("privileged_surface_reachable")
    if internet_entry:
        score += 15
        reasons.append("internet_reachable_entry")
    if len(path_set.paths) >= 5:
        score += 10
        reasons.append("multiple_dangerous_paths")
    if path_set.truncated:
        reasons.append("path_enumeration_truncated")
    score = min(100, score)

    if score >= 80:
        priority = DefensivePriority.CRITICAL
    elif score >= 60:
        priority = DefensivePriority.HIGH
    elif score >= 30:
        priority = DefensivePriority.MEDIUM
    else:
        priority = DefensivePriority.LOW

    coverage: dict[str, int] = defaultdict(int)
    for path in path_set.paths:
        target = node_by_ref[path.node_refs[-1]]
        weight = 2 if target.crown_jewel else 1
        for relation_id in path.relation_ids:
            coverage[relation_id] += weight
    chokepoints = tuple(
        relation_id
        for relation_id, _score in sorted(
            coverage.items(),
            key=lambda item: (-item[1], item[0]),
        )[:10]
    )

    draft = {
        "contract": CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT,
        "identity": snapshot.identity.model_dump(mode="json"),
        "graph_fingerprint": snapshot.fingerprint,
        "path_set_fingerprint": path_set.fingerprint,
        "priority": priority.value,
        "score": score,
        "reachable_node_refs": sorted(reachable),
        "reachable_privileged_refs": list(privileged),
        "reachable_crown_jewel_refs": list(crown_jewels),
        "dangerous_path_count": len(path_set.paths),
        "defensive_chokepoint_relation_refs": list(chokepoints),
        "reason_codes": reasons,
        "advisory_only": True,
        "attack_success_proven": False,
        "incident_confirmation_granted": False,
        "execution_authority_granted": False,
        "exploit_execution_allowed": False,
    }
    return BlastRadiusAssessment.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def simulate_relation_control_cut(
    *,
    snapshot: CompanyAttackGraphSnapshot,
    path_set: DefensiveAttackPathSet,
    relation_id: str,
) -> ControlCutSimulation:
    snapshot = CompanyAttackGraphSnapshot.model_validate(
        snapshot.model_dump(mode="json")
    )
    path_set = DefensiveAttackPathSet.model_validate(
        path_set.model_dump(mode="json")
    )
    if path_set.graph_fingerprint != snapshot.fingerprint:
        raise ValueError("cyber_control_cut_graph_fingerprint_mismatch")
    _same_identity(
        expected=snapshot.identity,
        actual=path_set.identity,
        error="cyber_control_cut_company_identity_mismatch",
    )
    _safe_ref(relation_id, "cyber_control_cut_unsafe_reference_forbidden")
    if relation_id not in {relation.relation_id for relation in snapshot.relations}:
        raise ValueError("cyber_control_cut_relation_missing")

    baseline = assess_blast_radius(snapshot=snapshot, path_set=path_set)
    reduced_graph = build_company_attack_graph_snapshot(
        identity=snapshot.identity,
        nodes=snapshot.nodes,
        relations=tuple(
            relation
            for relation in snapshot.relations
            if relation.relation_id != relation_id
        ),
        as_of=snapshot.as_of,
    )
    reduced_paths = enumerate_defensive_attack_paths(
        snapshot=reduced_graph,
        entry_node_refs=path_set.entry_node_refs,
        max_hops=path_set.max_hops,
        max_paths=path_set.max_paths,
    )
    reduced = assess_blast_radius(
        snapshot=reduced_graph,
        path_set=reduced_paths,
    )
    draft = {
        "contract": CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT,
        "identity": snapshot.identity.model_dump(mode="json"),
        "relation_id": relation_id,
        "baseline_dangerous_path_count": baseline.dangerous_path_count,
        "remaining_dangerous_path_count": reduced.dangerous_path_count,
        "dangerous_paths_reduced": max(
            0,
            baseline.dangerous_path_count - reduced.dangerous_path_count,
        ),
        "baseline_crown_jewel_refs": list(baseline.reachable_crown_jewel_refs),
        "remaining_crown_jewel_refs": list(reduced.reachable_crown_jewel_refs),
        "mutation_applied": False,
        "advisory_only": True,
        "execution_authority_granted": False,
        "exploit_execution_allowed": False,
    }
    return ControlCutSimulation.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def _build_path(
    *,
    snapshot: CompanyAttackGraphSnapshot,
    node_refs: tuple[str, ...],
    relation_ids: tuple[str, ...],
    node_by_ref: dict[str, CompanyCyberNode],
    relation_by_id: dict[str, CompanyCyberRelation],
) -> DefensiveAttackPath:
    relations = [relation_by_id[ref] for ref in relation_ids]
    strengths = {relation.evidence_strength for relation in relations}
    if RelationEvidenceStrength.INFERRED in strengths:
        status = AttackPathStatus.HYPOTHETICAL
    elif RelationEvidenceStrength.OBSERVED in strengths:
        status = AttackPathStatus.EVIDENCE_SUPPORTED
    else:
        status = AttackPathStatus.CONFIGURATION_VERIFIED
    techniques = tuple(
        sorted(
            {
                technique
                for relation in relations
                for technique in relation.attack_technique_ids
            }
        )
    )
    target = node_by_ref[node_refs[-1]]
    seed = "|".join((*node_refs, *relation_ids))
    path_id = f"path:{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"
    draft = {
        "contract": CYBER_ATTACK_PATH_INTELLIGENCE_CONTRACT,
        "path_id": path_id,
        "identity": snapshot.identity.model_dump(mode="json"),
        "node_refs": list(node_refs),
        "relation_ids": list(relation_ids),
        "status": status.value,
        "attack_technique_ids": list(techniques),
        "internet_entry": node_by_ref[node_refs[0]].internet_reachable,
        "reaches_privileged_surface": target.privileged,
        "reaches_crown_jewel": target.crown_jewel,
        "hop_count": len(relation_ids),
        "attack_success_proven": False,
        "incident_confirmation_granted": False,
        "execution_authority_granted": False,
        "exploit_execution_allowed": False,
    }
    return DefensiveAttackPath.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def _reachable_nodes(
    *,
    snapshot: CompanyAttackGraphSnapshot,
    entry_node_refs: tuple[str, ...],
    max_hops: int,
) -> set[str]:
    outgoing: dict[str, list[str]] = defaultdict(list)
    for relation in snapshot.relations:
        outgoing[relation.from_node_ref].append(relation.to_node_ref)
    for refs in outgoing.values():
        refs.sort()

    reached = set(entry_node_refs)
    queue: deque[tuple[str, int]] = deque((ref, 0) for ref in entry_node_refs)
    while queue:
        current, depth = queue.popleft()
        if depth >= max_hops:
            continue
        for next_ref in outgoing.get(current, ()):
            if next_ref in reached:
                continue
            reached.add(next_ref)
            queue.append((next_ref, depth + 1))
    return reached


def _same_identity(
    *,
    expected: CompanyIdentity,
    actual: CompanyIdentity,
    error: str,
) -> None:
    expected = CompanyIdentity.model_validate(expected.model_dump(mode="json"))
    actual = CompanyIdentity.model_validate(actual.model_dump(mode="json"))
    if actual.fingerprint != expected.fingerprint:
        raise ValueError(error)


def _safe_ref(value: str, error: str) -> None:
    if _SECRET_OR_OFFENSIVE_REF.search(value):
        raise ValueError(error)


def _unique(values: tuple[str, ...], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _iso(value: datetime) -> str:
    _aware(value, "cyber_attack_datetime_requires_timezone")
    return value.isoformat().replace("+00:00", "Z")


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
