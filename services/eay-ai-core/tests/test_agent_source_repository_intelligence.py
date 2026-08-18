from app.repository_intelligence_agent_sources import (
    load_repository_registry_with_agent_sources,
)


def test_agent_source_supplement_is_cumulative_and_license_governed():
    registry = load_repository_registry_with_agent_sources()
    entries = registry.by_id()

    assert registry.version == 5
    assert "microsoft-playwright" in entries
    assert "microsoft-playwright-python" in entries
    assert "chrome-devtools-mcp" in entries
    assert "vercel-agent-browser" in entries
    assert "e2b-awesome-ai-agents" in entries
    assert "agentops" in entries
    assert "openinterpreter" in entries
    assert "e2b-sandbox" in entries
    assert "aiwaves-agents" in entries

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

    agentops = entries["agentops"]
    assert agentops.identity == "AgentOps-AI/agentops"
    assert agentops.review.commit == "f8e907b92dabe47232978023fdcb01e2a7d4b752"
    assert agentops.review.license == "MIT"
    assert agentops.decision == "reference"

    interpreter = entries["openinterpreter"]
    assert interpreter.identity == "openinterpreter/openinterpreter"
    assert interpreter.review.commit == "5a8f33ee6c82aee2ffbbf2e998b5f3e4995459a2"
    assert interpreter.review.license == "Apache-2.0"

    sandbox = entries["e2b-sandbox"]
    assert sandbox.identity == "e2b-dev/E2B"
    assert sandbox.review.commit == "f5d702a520de52ac0e5d4dda3ca0d5fca01d7993"
    assert sandbox.review.license == "Apache-2.0"

    learning = entries["aiwaves-agents"]
    assert learning.identity == "aiwaves-cn/agents"
    assert learning.review.commit == "e8c4e3c2d19739d3dff59e577d1c97090cc15f59"
    assert learning.review.license == "Apache-2.0"
    assert learning.review.commercial_use.startswith("reference-only-stale-upstream")

    for domain in (
        "agent-browser-harnesses",
        "agent-runtime-landscape",
        "agent-observability-and-replay",
        "isolated-agent-sandboxes",
        "offline-agent-learning",
    ):
        assert domain in registry.required_discovery_domains
    registry.assert_external_license_gate()
