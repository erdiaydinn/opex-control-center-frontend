import pytest

from app.kpi_activation_gate import KpiNsfrActivationBundle
from app.kpi_nsfr_production_activation import seal_nsfr_production_activation
from app.kpi_query_candidate import KpiQueryTemplateCandidate


FP_A = "a" * 64
FP_B = "b" * 64
FP_C = "c" * 64
FP_D = "d" * 64
FP_E = "e" * 64
FP_F = "f" * 64
FP_1 = "1" * 64
FP_2 = "2" * 64


def activation(**overrides):
    data = dict(
        metric="nsfr",
        semantic_fingerprint=FP_1,
        schema_fingerprint=FP_2,
        schema_evidence_fingerprint=FP_A,
        semantic_mapping_fingerprint=FP_D,
        result_contract_fingerprint=FP_F,
    )
    data.update(overrides)
    return KpiNsfrActivationBundle(**data)


def manifest(**overrides):
    data = {
        "verified": True,
        "table_id": "report_dmart_ops_nsfr_global_overview",
        "evidence_fingerprint": FP_A,
        "manifest_fingerprint": FP_B,
        "approval_fingerprint": FP_C,
    }
    data.update(overrides)
    return data


def semantic_mapping(**overrides):
    data = {
        "verified": True,
        "metric_family": "nsfr_family",
        "schema_evidence_fingerprint": FP_A,
        "mapping_fingerprint": FP_D,
    }
    data.update(overrides)
    return data


def dimensions(**overrides):
    data = {
        "verified": True,
        "metric_family": "nsfr_family",
        "schema_evidence_fingerprint": FP_A,
        "mapping_fingerprint": FP_E,
    }
    data.update(overrides)
    return data


def candidate(**overrides):
    data = dict(
        candidate_id="nsfr-prod-candidate-001",
        metric_family="nsfr_family",
        table_id="report_dmart_ops_nsfr_global_overview",
        sql="SELECT 1",
        parameter_names=("start_date", "end_date", "stores", "stores_empty"),
        schema_manifest_fingerprint=FP_B,
        schema_approval_fingerprint=FP_C,
        semantic_mapping_fingerprint=FP_D,
        dimension_mapping_fingerprint=FP_E,
        executable=False,
    )
    data.update(overrides)
    return KpiQueryTemplateCandidate(**data)


def seal(**overrides):
    data = dict(
        metric="nsfr",
        activation=activation(),
        manifest_approval=manifest(),
        semantic_mapping=semantic_mapping(),
        dimension_mapping=dimensions(),
        candidate=candidate(),
        reviewer="metric-owner",
        reviewed_at="2026-08-11T06:40:00Z",
        approval_reference="KPI-REVIEW-001",
    )
    data.update(overrides)
    return seal_nsfr_production_activation(**data)


def test_production_activation_seals_full_lineage_without_enabling_execution():
    artifact = seal()
    assert artifact.approved_for_registry_review is True
    assert artifact.executable is False
    assert artifact.schema_evidence_fingerprint == FP_A
    assert artifact.schema_manifest_fingerprint == FP_B
    assert artifact.schema_approval_fingerprint == FP_C
    assert artifact.semantic_mapping_fingerprint == FP_D
    assert artifact.dimension_mapping_fingerprint == FP_E
    assert artifact.result_contract_fingerprint == FP_F
    assert artifact.candidate_fingerprint == candidate().fingerprint
    assert len(artifact.fingerprint) == 64


def test_production_activation_rejects_stale_dimension_lineage():
    with pytest.raises(ValueError, match="nsfr_production_activation_dimension_schema_mismatch"):
        seal(dimension_mapping=dimensions(schema_evidence_fingerprint="9" * 64))


def test_production_activation_rejects_candidate_from_other_mapping():
    with pytest.raises(ValueError, match="nsfr_production_activation_candidate_dimension_mapping_mismatch"):
        seal(candidate=candidate(dimension_mapping_fingerprint="9" * 64))


def test_production_activation_rejects_unscoped_candidate_parameters():
    with pytest.raises(ValueError, match="nsfr_production_activation_candidate_parameter_contract_mismatch"):
        seal(candidate=candidate(parameter_names=()))


def test_production_activation_rejects_executable_candidate():
    with pytest.raises(ValueError, match="nsfr_production_activation_candidate_must_be_non_executable"):
        seal(candidate=candidate(executable=True))


def test_production_activation_requires_human_approval_reference():
    with pytest.raises(ValueError, match="nsfr_production_activation_human_approval_required"):
        seal(approval_reference="")
