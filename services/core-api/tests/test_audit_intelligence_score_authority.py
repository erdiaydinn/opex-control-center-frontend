from __future__ import annotations

import inspect

from app.modules.audit.intelligence import build_audit_intelligence_receipt


def test_official_compliance_score_surfaces_are_fenced_from_focus_scores() -> None:
    """Regression guard: focus/quick/custom scores must never move compliance KPIs."""

    source = inspect.getsource(build_audit_intelligence_receipt)

    assert source.count("WHERE official_compliance_eligible IS TRUE") >= 2
    assert "FROM official_scored_runs" in source
    assert "AS average_completed_score" in source
    assert "latest_score AS" in source
    assert '"calculation_version": "audit.intelligence.summary.v2"' in source
    assert '"official_compliance_only": True' in source
    assert '"eligibility_column": "audit_runs.official_compliance_eligible"' in source
