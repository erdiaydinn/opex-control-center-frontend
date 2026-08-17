from pathlib import Path


APP_ROOT = Path("backend/app")
ALLOWED_DIRECT_RESOLUTION = {
    Path("backend/app/platform/business_glossary/resolver.py"),
    Path("backend/app/platform/business_glossary/semantic_consumers.py"),
}


def test_product_consumers_cannot_bypass_shared_semantic_authority() -> None:
    violations: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        if path in ALLOWED_DIRECT_RESOLUTION:
            continue
        source = path.read_text(encoding="utf-8")
        if "resolve_term(" in source or "import resolve_term" in source:
            violations.append(str(path))
    assert not violations, (
        "Business Glossary consumers must route through semantic_consumers so Jarvis, "
        "Insight, Academy and help cannot silently diverge: " + ", ".join(violations)
    )


def test_shared_semantic_authority_exports_all_required_product_consumers() -> None:
    source = Path(
        "backend/app/platform/business_glossary/semantic_consumers.py"
    ).read_text(encoding="utf-8")
    for consumer in (
        "SemanticConsumer.JARVIS",
        "SemanticConsumer.INSIGHT",
        "SemanticConsumer.ACADEMY",
        "SemanticConsumer.HELP",
    ):
        assert consumer in source
    assert source.count("resolve_term(") == 1
