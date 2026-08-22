from __future__ import annotations

from pathlib import Path


def test_authorized_championship_workflow_has_no_network_runtime_install() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = (
        root / ".github/workflows/jarvis-cyber-championship-run.yml"
    ).read_text(encoding="utf-8")

    assert "EAY_CHAMPIONSHIP_PYTHON_BIN" in workflow
    assert "PREPROVISIONED" in workflow
    assert "CHAMPIONSHIP_RUNTIME_NETWORK_INSTALL=false" in workflow
    assert "actions/setup-python" not in workflow
    assert "pip install" not in workflow
    assert "pip install --upgrade" not in workflow
    assert "curl " not in workflow
    assert "wget " not in workflow
    assert "python -m pip" not in workflow
    assert 'test -x "$EAY_CHAMPIONSHIP_PYTHON_BIN"' in workflow
    assert "championship_verifier_requires_python_3_12" in workflow
    assert '"$EAY_CHAMPIONSHIP_PYTHON_BIN" -m app.cyber_championship_signature_guard' in workflow
    assert '"$EAY_CHAMPIONSHIP_PYTHON_BIN" -m app.cyber_championship_tenant_scope_guard' in workflow
    assert '"$EAY_CHAMPIONSHIP_PYTHON_BIN" scripts/run_cyber_championship_external_preflight.py' in workflow


def test_authorized_championship_workflow_keeps_runtime_and_evidence_external() -> None:
    root = Path(__file__).resolve().parents[3]
    workflow = (
        root / ".github/workflows/jarvis-cyber-championship-run.yml"
    ).read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "runs-on: [self-hosted, eay-championship]" in workflow
    assert "environment: cyber-championship" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "EAY_CHAMPIONSHIP_EVIDENCE_DIR" in workflow
    assert "EAY_CHAMPIONSHIP_TRUST_DIR" in workflow
    assert "secrets." not in workflow
