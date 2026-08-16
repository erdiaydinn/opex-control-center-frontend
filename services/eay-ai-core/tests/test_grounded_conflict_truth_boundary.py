from dataclasses import dataclass

import app.grounded_chat as grounded
from app.main import ChatRequest


@dataclass
class _Finding:
    value: str

    def model_dump(self) -> dict[str, str]:
        return {"value": self.value}


def test_production_global_request_never_projects_unscoped_company_conflicts(
    monkeypatch,
):
    monkeypatch.setenv("EAY_ENVIRONMENT", "production")

    def forbidden_compare(_as_of):
        raise AssertionError("unscoped company conflicts must not be queried")

    monkeypatch.setattr(
        grounded.legal_engine,
        "compare_company_to_law",
        forbidden_compare,
    )

    request = ChatRequest(
        message="What regulation applies?",
        layers=["legal", "standard"],
    )

    assert grounded._company_conflicts_for_response(request) == []


def test_production_company_projection_stays_closed_even_if_called_directly(
    monkeypatch,
):
    monkeypatch.setenv("EAY_ENVIRONMENT", "production")

    def forbidden_compare(_as_of):
        raise AssertionError("production conflict store is not tenant-scoped")

    monkeypatch.setattr(
        grounded.legal_engine,
        "compare_company_to_law",
        forbidden_compare,
    )

    request = ChatRequest(
        message="Compare law with company policy",
        layers=["legal", "company"],
    )

    assert grounded._company_conflicts_for_response(request) == []


def test_development_conflicts_require_explicit_company_layer(monkeypatch):
    monkeypatch.setenv("EAY_ENVIRONMENT", "development")
    calls = []

    def compare(as_of):
        calls.append(as_of)
        return [_Finding("scoped-local-research")]

    monkeypatch.setattr(
        grounded.legal_engine,
        "compare_company_to_law",
        compare,
    )

    global_request = ChatRequest(
        message="What regulation applies?",
        layers=["legal"],
    )
    assert grounded._company_conflicts_for_response(global_request) == []
    assert calls == []

    company_request = ChatRequest(
        message="Compare with company policy",
        layers=["legal", "company"],
    )
    assert grounded._company_conflicts_for_response(company_request) == [
        {"value": "scoped-local-research"}
    ]
    assert calls == [company_request.as_of]
