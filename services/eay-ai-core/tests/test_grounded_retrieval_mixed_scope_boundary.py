from fastapi import HTTPException
import pytest

from app.grounded_chat import _enforce_grounded_retrieval_truth_boundary
from app.main import ChatRequest


def test_production_mixed_global_and_company_layers_fail_closed(monkeypatch):
    monkeypatch.setenv("EAY_ENVIRONMENT", "production")
    request = ChatRequest(
        message="Compare the law with our company policy",
        layers=["legal", "standard", "company"],
    )

    with pytest.raises(HTTPException) as exc_info:
        _enforce_grounded_retrieval_truth_boundary(request)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == (
        "tenant_scoped_retrieval_not_production_ready"
    )
    assert exc_info.value.detail["layers"] == ["company"]


def test_production_mixed_global_and_operational_layers_fail_closed(monkeypatch):
    monkeypatch.setenv("EAY_ENVIRONMENT", "production")
    request = ChatRequest(
        message="Compare the standard with current operational guidance",
        layers=["standard", "operational"],
    )

    with pytest.raises(HTTPException) as exc_info:
        _enforce_grounded_retrieval_truth_boundary(request)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["layers"] == ["operational"]


def test_production_duplicate_scoped_layers_do_not_weaken_boundary(monkeypatch):
    monkeypatch.setenv("EAY_ENVIRONMENT", "production")
    request = ChatRequest(
        message="Show company guidance",
        layers=["company", "legal", "company"],
    )

    with pytest.raises(HTTPException) as exc_info:
        _enforce_grounded_retrieval_truth_boundary(request)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["layers"] == ["company"]
