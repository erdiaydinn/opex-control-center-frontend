from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.company_context_boundary import build_company_identity
from app.cyber_attack_path_intelligence import (
    AttackPathStatus,
    CompanyAttackGraphSnapshot,
    CyberRelationKind,
    CyberSurfaceKind,
    RelationEvidenceStrength,
    assess_blast_radius,
    build_company_attack_graph_snapshot,
    build_company_cyber_node,
    build_company_cyber_relation,
    enumerate_defensive_attack_paths,
    simulate_relation_control_cut,
)
from app.cyber_defense_intelligence import AssetCriticality, DefensivePriority

T1 = datetime(2026, 8, 18, 8, tzinfo=UTC)
T2 = datetime(2026, 8, 19, 8, tzinfo=UTC)
T3 = datetime(2026, 8, 20, 8, tzinfo=UTC)


def _company(
    *,
    tenant: str = "tenant-a",
    company: str = "company-a",
    revision: str = "rev-1",
):
    return build_company_identity(
        tenant_id=tenant,
        company_id=company,
        company_slug=company,
        profile_revision=revision,
        environment="production",
    )


def _node(
    identity,
    ref: str,
    kind: CyberSurfaceKind,
    *,
    internet: bool = False,
    privileged: bool = False,
    crown: bool = False,
    observed_at: datetime = T1,
    recorded_at: datetime = T1,
):
    return build_company_cyber_node(
        identity=identity,
        node_ref=ref,
        surface_kind=kind,
        criticality=(
            AssetCriticality.CRITICAL
            if privileged or crown
            else AssetCriticality.HIGH
        ),
        internet_reachable=internet,
        privileged=privileged,
        crown_jewel=crown,
        evidence_refs=(f"evidence:inventory:{ref}",),
        observed_at=observed_at,
        recorded_at=recorded_at,
    )


def _relation(
    identity,
    relation_id: str,
    source: str,
    target: str,
    *,
    strength: RelationEvidenceStrength = RelationEvidenceStrength.VERIFIED_CONFIGURATION,
    technique: str = "T1021",
):
    return build_company_cyber_relation(
        identity=identity,
        relation_id=relation_id,
        from_node_ref=source,
        to_node_ref=target,
        relation_kind=CyberRelationKind.NETWORK_REACHABILITY,
        evidence_strength=strength,
        attack_technique_ids=(technique,),
        evidence_refs=(f"evidence:config:{relation_id}",),
        observed_at=T1,
        recorded_at=T1,
    )


def _dangerous_graph(identity=None):
    identity = identity or _company()
    nodes = (
        _node(
            identity,
            "asset:edge",
            CyberSurfaceKind.INTERNET_EDGE,
            internet=True,
        ),
        _node(identity, "asset:app", CyberSurfaceKind.APPLICATION),
        _node(
            identity,
            "identity:svc-orders",
            CyberSurfaceKind.SERVICE_ACCOUNT,
            privileged=True,
        ),
        _node(
            identity,
            "data:company-warehouse",
            CyberSurfaceKind.DATA_STORE,
            crown=True,
        ),
    )
    relations = (
        _relation(identity, "rel:edge-app", "asset:edge", "asset:app"),
        _relation(
            identity,
            "rel:app-service-account",
            "asset:app",
            "identity:svc-orders",
            technique="T1078",
        ),
        _relation(
            identity,
            "rel:service-account-data",
            "identity:svc-orders",
            "data:company-warehouse",
            technique="T1530",
        ),
    )
    return build_company_attack_graph_snapshot(
        identity=identity,
        nodes=nodes,
        relations=relations,
        as_of=T2,
    )


def test_attack_graph_is_exact_company_bound_even_inside_same_tenant() -> None:
    company_a = _company(tenant="tenant-shared", company="company-a")
    company_b = _company(tenant="tenant-shared", company="company-b")
    node_a = _node(company_a, "asset:a", CyberSurfaceKind.APPLICATION)
    node_b = _node(company_b, "asset:b", CyberSurfaceKind.APPLICATION)

    with pytest.raises(ValueError, match="cyber_attack_graph_cross_company_node"):
        build_company_attack_graph_snapshot(
            identity=company_a,
            nodes=(node_a, node_b),
            relations=(),
            as_of=T2,
        )


def test_profile_revision_mismatch_is_rejected() -> None:
    rev_1 = _company(company="company-a", revision="rev-1")
    rev_2 = _company(company="company-a", revision="rev-2")
    node = _node(rev_1, "asset:a", CyberSurfaceKind.APPLICATION)
    with pytest.raises(ValueError, match="cyber_attack_graph_cross_company_node"):
        build_company_attack_graph_snapshot(
            identity=rev_2,
            nodes=(node,),
            relations=(),
            as_of=T2,
        )


def test_relation_endpoint_must_exist_in_same_time_cutoff_snapshot() -> None:
    identity = _company()
    edge = _node(
        identity,
        "asset:edge",
        CyberSurfaceKind.INTERNET_EDGE,
        internet=True,
    )
    future_target = _node(
        identity,
        "asset:future",
        CyberSurfaceKind.APPLICATION,
        observed_at=T3,
        recorded_at=T3,
    )
    relation = _relation(
        identity,
        "rel:future",
        "asset:edge",
        "asset:future",
    )
    with pytest.raises(
        ValueError,
        match="cyber_attack_graph_relation_endpoint_missing",
    ):
        build_company_attack_graph_snapshot(
            identity=identity,
            nodes=(edge, future_target),
            relations=(relation,),
            as_of=T2,
        )


def test_future_known_node_is_not_visible_in_historical_snapshot() -> None:
    identity = _company()
    past = _node(identity, "asset:past", CyberSurfaceKind.APPLICATION)
    future = _node(
        identity,
        "asset:future",
        CyberSurfaceKind.APPLICATION,
        observed_at=T3,
        recorded_at=T3,
    )
    snapshot = build_company_attack_graph_snapshot(
        identity=identity,
        nodes=(past, future),
        relations=(),
        as_of=T2,
    )
    assert tuple(node.node_ref for node in snapshot.nodes) == ("asset:past",)


def test_configuration_verified_path_still_never_proves_attack_or_incident() -> None:
    graph = _dangerous_graph()
    path_set = enumerate_defensive_attack_paths(
        snapshot=graph,
        entry_node_refs=("asset:edge",),
    )
    assert path_set.paths
    crown_path = next(path for path in path_set.paths if path.reaches_crown_jewel)
    assert crown_path.status is AttackPathStatus.CONFIGURATION_VERIFIED
    assert crown_path.attack_success_proven is False
    assert crown_path.incident_confirmation_granted is False
    assert crown_path.execution_authority_granted is False
    assert crown_path.exploit_execution_allowed is False


@pytest.mark.parametrize(
    ("strength", "expected"),
    [
        (RelationEvidenceStrength.INFERRED, AttackPathStatus.HYPOTHETICAL),
        (
            RelationEvidenceStrength.OBSERVED,
            AttackPathStatus.EVIDENCE_SUPPORTED,
        ),
    ],
)
def test_path_status_tracks_weakest_relation_evidence(strength, expected) -> None:
    identity = _company()
    edge = _node(
        identity,
        "asset:edge",
        CyberSurfaceKind.INTERNET_EDGE,
        internet=True,
    )
    admin = _node(
        identity,
        "admin:plane",
        CyberSurfaceKind.ADMIN_PLANE,
        privileged=True,
    )
    relation = _relation(
        identity,
        "rel:edge-admin",
        "asset:edge",
        "admin:plane",
        strength=strength,
    )
    graph = build_company_attack_graph_snapshot(
        identity=identity,
        nodes=(edge, admin),
        relations=(relation,),
        as_of=T2,
    )
    path_set = enumerate_defensive_attack_paths(
        snapshot=graph,
        entry_node_refs=("asset:edge",),
    )
    assert len(path_set.paths) == 1
    assert path_set.paths[0].status is expected


def test_blast_radius_prioritizes_internet_to_privileged_crown_jewel_chain() -> None:
    graph = _dangerous_graph()
    path_set = enumerate_defensive_attack_paths(
        snapshot=graph,
        entry_node_refs=("asset:edge",),
    )
    assessment = assess_blast_radius(snapshot=graph, path_set=path_set)

    assert assessment.priority is DefensivePriority.CRITICAL
    assert assessment.score >= 90
    assert assessment.reachable_crown_jewel_refs == ("data:company-warehouse",)
    assert assessment.reachable_privileged_refs == ("identity:svc-orders",)
    assert "crown_jewel_reachable" in assessment.reason_codes
    assert "internet_reachable_entry" in assessment.reason_codes
    assert assessment.advisory_only is True
    assert assessment.execution_authority_granted is False


def test_non_privileged_non_crown_reachability_stays_low_priority() -> None:
    identity = _company()
    edge = _node(
        identity,
        "asset:edge",
        CyberSurfaceKind.INTERNET_EDGE,
        internet=True,
    )
    app = _node(identity, "asset:app", CyberSurfaceKind.APPLICATION)
    graph = build_company_attack_graph_snapshot(
        identity=identity,
        nodes=(edge, app),
        relations=(_relation(identity, "rel:edge-app", "asset:edge", "asset:app"),),
        as_of=T2,
    )
    paths = enumerate_defensive_attack_paths(
        snapshot=graph,
        entry_node_refs=("asset:edge",),
    )
    assessment = assess_blast_radius(snapshot=graph, path_set=paths)
    assert paths.paths == ()
    assert assessment.score == 15
    assert assessment.priority is DefensivePriority.LOW


def test_cycles_are_bounded_and_never_appear_inside_a_path() -> None:
    identity = _company()
    edge = _node(
        identity,
        "asset:edge",
        CyberSurfaceKind.INTERNET_EDGE,
        internet=True,
    )
    app = _node(identity, "asset:app", CyberSurfaceKind.APPLICATION)
    service = _node(identity, "asset:service", CyberSurfaceKind.SERVICE)
    crown = _node(
        identity,
        "data:crown",
        CyberSurfaceKind.DATA_STORE,
        crown=True,
    )
    relations = (
        _relation(identity, "rel:1", "asset:edge", "asset:app"),
        _relation(identity, "rel:2", "asset:app", "asset:service"),
        _relation(identity, "rel:3", "asset:service", "asset:app"),
        _relation(identity, "rel:4", "asset:service", "data:crown"),
    )
    graph = build_company_attack_graph_snapshot(
        identity=identity,
        nodes=(edge, app, service, crown),
        relations=relations,
        as_of=T2,
    )
    paths = enumerate_defensive_attack_paths(
        snapshot=graph,
        entry_node_refs=("asset:edge",),
        max_hops=8,
    )
    assert len(paths.paths) == 1
    assert len(paths.paths[0].node_refs) == len(set(paths.paths[0].node_refs))


def test_control_cut_simulation_reduces_paths_without_mutating_or_authorizing() -> None:
    graph = _dangerous_graph()
    paths = enumerate_defensive_attack_paths(
        snapshot=graph,
        entry_node_refs=("asset:edge",),
    )
    simulation = simulate_relation_control_cut(
        snapshot=graph,
        path_set=paths,
        relation_id="rel:edge-app",
    )
    assert simulation.dangerous_paths_reduced == paths.paths.__len__()
    assert simulation.remaining_dangerous_path_count == 0
    assert simulation.remaining_crown_jewel_refs == ()
    assert simulation.mutation_applied is False
    assert simulation.execution_authority_granted is False
    assert simulation.exploit_execution_allowed is False


def test_shared_chokepoint_is_ranked_before_branch_specific_relations() -> None:
    identity = _company()
    edge = _node(
        identity,
        "asset:edge",
        CyberSurfaceKind.INTERNET_EDGE,
        internet=True,
    )
    gateway = _node(identity, "asset:gateway", CyberSurfaceKind.SERVICE)
    crown_a = _node(
        identity,
        "data:crown-a",
        CyberSurfaceKind.DATA_STORE,
        crown=True,
    )
    crown_b = _node(
        identity,
        "data:crown-b",
        CyberSurfaceKind.DATA_STORE,
        crown=True,
    )
    graph = build_company_attack_graph_snapshot(
        identity=identity,
        nodes=(edge, gateway, crown_a, crown_b),
        relations=(
            _relation(identity, "rel:shared", "asset:edge", "asset:gateway"),
            _relation(identity, "rel:a", "asset:gateway", "data:crown-a"),
            _relation(identity, "rel:b", "asset:gateway", "data:crown-b"),
        ),
        as_of=T2,
    )
    paths = enumerate_defensive_attack_paths(
        snapshot=graph,
        entry_node_refs=("asset:edge",),
    )
    assessment = assess_blast_radius(snapshot=graph, path_set=paths)
    assert assessment.defensive_chokepoint_relation_refs[0] == "rel:shared"


def test_secret_or_offensive_payload_references_are_rejected() -> None:
    identity = _company()
    with pytest.raises(ValueError, match="cyber_attack_node_unsafe_reference_forbidden"):
        build_company_cyber_node(
            identity=identity,
            node_ref="asset:edge",
            surface_kind=CyberSurfaceKind.INTERNET_EDGE,
            criticality=AssetCriticality.HIGH,
            evidence_refs=("evidence:reverse_shell:raw",),
            observed_at=T1,
            recorded_at=T1,
        )

    with pytest.raises(
        ValueError,
        match="cyber_attack_relation_unsafe_reference_forbidden",
    ):
        build_company_cyber_relation(
            identity=identity,
            relation_id="rel:unsafe",
            from_node_ref="asset:a",
            to_node_ref="asset:b",
            relation_kind=CyberRelationKind.NETWORK_REACHABILITY,
            evidence_strength=RelationEvidenceStrength.OBSERVED,
            evidence_refs=("authorization:bearer-material",),
            observed_at=T1,
            recorded_at=T1,
        )


def test_path_limits_fail_closed_and_do_not_allow_unbounded_graph_walk() -> None:
    graph = _dangerous_graph()
    with pytest.raises(ValueError, match="cyber_attack_path_max_hops_out_of_range"):
        enumerate_defensive_attack_paths(
            snapshot=graph,
            entry_node_refs=("asset:edge",),
            max_hops=9,
        )
    with pytest.raises(ValueError, match="cyber_attack_path_max_paths_out_of_range"):
        enumerate_defensive_attack_paths(
            snapshot=graph,
            entry_node_refs=("asset:edge",),
            max_paths=513,
        )


def test_tampered_graph_fingerprint_fails_closed() -> None:
    graph = _dangerous_graph()
    tampered = graph.model_copy(update={"as_of": T3})
    with pytest.raises(ValueError, match="cyber_attack_graph_fingerprint_mismatch"):
        CompanyAttackGraphSnapshot.model_validate(tampered.model_dump(mode="json"))


def test_one_hundred_company_graphs_remain_isolated() -> None:
    graphs = []
    for index in range(100):
        identity = _company(
            tenant="tenant-shared",
            company=f"company-{index}",
        )
        node = _node(
            identity,
            f"asset:company-{index}",
            CyberSurfaceKind.APPLICATION,
        )
        graphs.append(
            build_company_attack_graph_snapshot(
                identity=identity,
                nodes=(node,),
                relations=(),
                as_of=T2,
            )
        )

    assert len({graph.identity.fingerprint for graph in graphs}) == 100
    with pytest.raises(ValueError, match="cyber_attack_graph_cross_company_node"):
        build_company_attack_graph_snapshot(
            identity=graphs[0].identity,
            nodes=(graphs[1].nodes[0],),
            relations=(),
            as_of=T2,
        )
