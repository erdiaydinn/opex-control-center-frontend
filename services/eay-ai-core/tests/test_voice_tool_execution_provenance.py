from types import SimpleNamespace

import pytest

from app.voice_tool_execution_provenance import seal_tool_execution_proof


def _execution():
    return SimpleNamespace(
        execution_id="exec-123",
        status="executed",
        sql_sha256="a" * 64,
    )


def test_kpi_voice_proof_requires_activation_and_result_contract_lineage():
    result = SimpleNamespace(
        tool="ops_kpi_query",
        query_id="ops-kpi-v1",
        execution=_execution(),
        activation_provenance_fingerprint="b" * 64,
        result_contract_fingerprint="c" * 64,
        legal_grounding=None,
    )
    proof = seal_tool_execution_proof(result)
    assert proof.tool == "ops_kpi_query"
    assert proof.activation_provenance_fingerprint == "b" * 64
    assert proof.result_contract_fingerprint == "c" * 64
    assert len(proof.fingerprint) == 64


def test_kpi_voice_proof_rejects_result_without_governed_activation():
    result = SimpleNamespace(
        tool="ops_kpi_query",
        query_id="ops-kpi-v1",
        execution=_execution(),
        activation_provenance_fingerprint=None,
        result_contract_fingerprint="c" * 64,
        legal_grounding=None,
    )
    with pytest.raises(ValueError, match="voice_tool_kpi_activation_provenance_required"):
        seal_tool_execution_proof(result)


def test_regulatory_voice_proof_binds_legal_grounding():
    result = SimpleNamespace(
        tool="regulatory_impact_query",
        query_id="reg-impact-v1",
        execution=_execution(),
        activation_provenance_fingerprint=None,
        result_contract_fingerprint=None,
        legal_grounding={
            "instrument_id": "rg-1",
            "source_url": "https://www.resmigazete.gov.tr/example",
            "citation_ids": ["citation-1"],
            "topics": ["labeling"],
            "as_of": "2026-08-11",
        },
    )
    proof = seal_tool_execution_proof(result)
    assert proof.legal_grounding_fingerprint is not None
    assert len(proof.legal_grounding_fingerprint) == 64
    assert len(proof.fingerprint) == 64


def test_regulatory_voice_proof_rejects_missing_legal_grounding():
    result = SimpleNamespace(
        tool="regulatory_impact_query",
        query_id="reg-impact-v1",
        execution=_execution(),
        activation_provenance_fingerprint=None,
        result_contract_fingerprint=None,
        legal_grounding=None,
    )
    with pytest.raises(ValueError, match="voice_tool_legal_grounding_required"):
        seal_tool_execution_proof(result)
