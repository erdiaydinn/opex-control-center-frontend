from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_sha256(value: str | None) -> bool:
    return bool(value) and len(str(value)) == 64 and all(ch in "0123456789abcdef" for ch in str(value))


@dataclass(frozen=True)
class GovernedToolExecutionProof:
    tool: str
    query_id: str
    execution_id: str
    status: str
    sql_sha256: str
    activation_provenance_fingerprint: str | None
    result_contract_fingerprint: str | None
    legal_grounding_fingerprint: str | None
    fingerprint: str


@dataclass(frozen=True)
class GovernedVoiceToolResult:
    """Transient tool output plus immutable governed execution proof.

    ``content`` may be used by the live response pipeline, but callers must persist only
    its hash. The proof fingerprint binds the voice result to the already-governed tool
    execution/KPI/legal provenance chain.
    """

    content: str
    execution_proof: GovernedToolExecutionProof


def seal_tool_execution_proof(result: Any) -> GovernedToolExecutionProof:
    """Seal a TemplateToolExecutionResult-like object for the voice runtime.

    KPI results require activation + result-contract provenance. Regulatory-impact
    results require legal grounding. Every result must expose the underlying execution
    id and exact SQL fingerprint so a voice answer cannot be authorized by an arbitrary
    result hash alone.
    """

    tool = str(getattr(result, "tool", "") or "")
    query_id = str(getattr(result, "query_id", "") or "")
    execution = getattr(result, "execution", None)
    if len(tool) < 3 or len(query_id) < 3 or execution is None:
        raise ValueError("voice_tool_execution_result_shape_invalid")

    execution_id = str(getattr(execution, "execution_id", "") or "")
    status = str(getattr(execution, "status", "") or "")
    sql_sha256 = str(getattr(execution, "sql_sha256", "") or "")
    if len(execution_id) < 3 or not status:
        raise ValueError("voice_tool_execution_identity_required")
    if not _valid_sha256(sql_sha256):
        raise ValueError("voice_tool_execution_sql_fingerprint_invalid")

    activation = getattr(result, "activation_provenance_fingerprint", None)
    result_contract = getattr(result, "result_contract_fingerprint", None)
    if tool == "ops_kpi_query":
        if not _valid_sha256(activation):
            raise ValueError("voice_tool_kpi_activation_provenance_required")
        if not _valid_sha256(result_contract):
            raise ValueError("voice_tool_kpi_result_contract_required")

    legal_grounding = getattr(result, "legal_grounding", None)
    legal_fp: str | None = None
    if tool == "regulatory_impact_query":
        if not isinstance(legal_grounding, Mapping) or not legal_grounding:
            raise ValueError("voice_tool_legal_grounding_required")
        legal_fp = _sha256(dict(legal_grounding))

    payload = {
        "tool": tool,
        "query_id": query_id,
        "execution_id": execution_id,
        "status": status,
        "sql_sha256": sql_sha256,
        "activation_provenance_fingerprint": activation,
        "result_contract_fingerprint": result_contract,
        "legal_grounding_fingerprint": legal_fp,
    }
    return GovernedToolExecutionProof(
        tool=tool,
        query_id=query_id,
        execution_id=execution_id,
        status=status,
        sql_sha256=sql_sha256,
        activation_provenance_fingerprint=activation,
        result_contract_fingerprint=result_contract,
        legal_grounding_fingerprint=legal_fp,
        fingerprint=_sha256(payload),
    )
