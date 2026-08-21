import sqlite3

from app.observability import metrics_snapshot


def test_extended_metrics_count_safety_gates(tmp_path):
    db = tmp_path / "eay.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE bigquery_execution_audit(id TEXT, status TEXT);
            CREATE TABLE vision_audits(id TEXT, decision TEXT);
            CREATE TABLE model_registry(id TEXT, status TEXT);
            CREATE TABLE regulatory_changes(id TEXT, status TEXT);
            """
        )
        conn.execute("INSERT INTO bigquery_execution_audit VALUES ('b1', 'executed')")
        conn.execute("INSERT INTO bigquery_execution_audit VALUES ('b2', 'rejected_cost')")
        conn.execute("INSERT INTO vision_audits VALUES ('v1', 'pending')")
        conn.execute("INSERT INTO model_registry VALUES ('m1', 'candidate')")
        conn.execute("INSERT INTO model_registry VALUES ('m2', 'canary')")
        conn.execute("INSERT INTO regulatory_changes VALUES ('r1', 'pending')")
    snapshot = metrics_snapshot(db)
    assert snapshot.bigquery_executions == 1
    assert snapshot.bigquery_cost_rejections == 1
    assert snapshot.vision_audits_pending == 1
    assert snapshot.model_candidates == 1
    assert snapshot.model_canaries == 1
    assert snapshot.regulatory_changes_pending == 1
