from app.repository_intelligence_agent_sources import (
    load_repository_registry_with_agent_sources,
)


def test_agent_source_supplement_is_cumulative_and_license_governed():
    registry = load_repository_registry_with_agent_sources()
    entries = registry.by_id()

    assert registry.version == 4
    assert "microsoft-playwright" in entries
    assert "microsoft-playwright-python" in entries
    assert "chrome-devtools-mcp" in entries
    assert "vercel-agent-browser" in entries
    assert "e2b-awesome-ai-agents" in entries

    agent_browser = entries["vercel-agent-browser"]
    assert agent_browser.identity == "vercel-labs/agent-browser"
    assert agent_browser.decision == "adopt"
    assert agent_browser.review.commit == "548b159b30eef119ccf6846c8bc807d0eaa3f6f8"
    assert agent_browser.review.license == "Apache-2.0"

    catalog = entries["e2b-awesome-ai-agents"]
    assert catalog.identity == "e2b-dev/awesome-ai-agents"
    assert catalog.decision == "reference"
    assert catalog.review.commit == "999f3c390b8a373ed243ee297ff32a433cd0d68b"
    assert catalog.review.license == "CC-BY-NC-SA-4.0"
    assert catalog.review.commercial_use.startswith("reference-only")

    assert "agent-browser-harnesses" in registry.required_discovery_domains
    assert "agent-runtime-landscape" in registry.required_discovery_domains
    registry.assert_external_license_gate()
