from datetime import datetime, timezone

from app.eval_guardrails import EvalEvidence, GuardrailEvalRequest, evaluate_guardrails
from app.observability import metrics_snapshot
from app.tool_intent import select_tool


def test_tool_intent_prioritizes_regulatory_over_catalog():
    result = select_tool("Yeni mevzuattan etkilenen SKU ve tedarikçileri getir")
    assert result.tool == "regulatory_impact_query"
    assert "legal:read" in result.required_scope
    assert result.execution_allowed is False


def test_tool_intent_routes_ops_kpi():
    result = select_tool("En kötü NSFR depolarını getir")
    assert result.tool == "ops_kpi_query"
    assert result.required_scope == ["ops:read"]


def test_tool_intent_none_for_general_chat():
    result = select_tool("Merhaba bugün nasılsın")
    assert result.tool == "none"


def test_guardrail_eval_rejects_fake_citation_and_legal_claim():
    result = evaluate_guardrails(
        GuardrailEvalRequest(
            legal_status="compliant",
            legal_citations=["fake-law"],
            all_citations=["fake-law"],
            evidence=[],
            risk="high",
            requires_human_review=False,
        )
    )
    assert result.passed is False
    assert result.score < 1.0
    failed = {item.check for item in result.checks if not item.passed}
    assert "citation_allowlist" in failed
    assert "no_definitive_law_without_binding_source" in failed
    assert "high_risk_human_gate" in failed


def test_guardrail_eval_accepts_grounded_high_risk_answer():
    result = evaluate_guardrails(
        GuardrailEvalRequest(
            legal_status="binding_requirement_found",
            legal_citations=["legal:1"],
            all_citations=["legal:1"],
            evidence=[EvalEvidence(id="legal:1", layer="legal", authority_level="binding")],
            risk="high",
            requires_human_review=True,
        )
    )
    assert result.passed is True
    assert result.score == 1.0


def test_metrics_snapshot_is_safe_on_empty_database(tmp_path):
    snapshot = metrics_snapshot(tmp_path / "empty.db")
    assert snapshot.interactions == 0
    assert snapshot.tool_calls == 0
    assert snapshot.knowledge_by_layer == {}


def test_metrics_snapshot_counts_without_exposing_content(tmp_path):
    db = tmp_path / "eay.db"
    import sqlite3
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE interactions(id TEXT, created_at TEXT);
            CREATE TABLE feedback(id INTEGER);
            CREATE TABLE learning_candidates(id TEXT, status TEXT);
            CREATE TABLE legal_instruments(id TEXT, verification_status TEXT);
            CREATE TABLE company_policy_versions(id TEXT, status TEXT);
            CREATE TABLE tool_call_audit(id TEXT, created_at TEXT);
            CREATE TABLE knowledge_documents(id TEXT, layer TEXT);
            """
        )
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT INTO interactions VALUES ('i1', ?)", (now,))
        conn.execute("INSERT INTO feedback VALUES (1)")
        conn.execute("INSERT INTO learning_candidates VALUES ('c1', 'pending')")
        conn.execute("INSERT INTO legal_instruments VALUES ('l1', 'verified')")
        conn.execute("INSERT INTO company_policy_versions VALUES ('p1', 'approved')")
        conn.execute("INSERT INTO tool_call_audit VALUES ('t1', ?)", (now,))
        conn.execute("INSERT INTO knowledge_documents VALUES ('d1', 'legal')")
    snapshot = metrics_snapshot(db)
    assert snapshot.interactions == 1
    assert snapshot.feedback == 1
    assert snapshot.learning_candidates_pending == 1
    assert snapshot.legal_verified == 1
    assert snapshot.company_approved == 1
    assert snapshot.tool_calls == 1
    assert snapshot.knowledge_by_layer == {"legal": 1}
