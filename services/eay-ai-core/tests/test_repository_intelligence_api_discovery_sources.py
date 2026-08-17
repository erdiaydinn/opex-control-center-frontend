from app.repository_intelligence import load_repository_registry


def test_api_discovery_sources_are_cumulative_and_pinned():
    registry = load_repository_registry()
    assert registry.version >= 3
    by_id = registry.by_id()

    expected = {
        "microsoft-playwright": ("microsoft/playwright", "04fb72b4f0f77e50c88689d436980f68f4c40a98", "Apache-2.0"),
        "microsoft-playwright-python": ("microsoft/playwright-python", "154f67ced51ada646b0fcf8574897d96c9712aa3", "Apache-2.0"),
        "chrome-devtools-mcp": ("ChromeDevTools/chrome-devtools-mcp", "fadbf41d96db84cea12e379592bc13b005c053b4", "Apache-2.0"),
        "mitmproxy": ("mitmproxy/mitmproxy", "bae1a7e179da7f9e516ba1b9fe0743f4fd758894", "MIT"),
        "mitmproxy2swagger": ("alufers/mitmproxy2swagger", "f432acafa5907258f0f529ff582c75fefdca00d7", "MIT"),
        "keploy": ("keploy/keploy", "f5f402bbb1171dd67ac7db265e9a5f60dca3e41e", "Apache-2.0"),
        "akto-api-security": ("akto-api-security/akto", "0d6c2d084e354bd61ca93511f8de6ab3445c7416", "MIT"),
    }

    for repo_id, (identity, commit, license_name) in expected.items():
        entry = by_id[repo_id]
        assert entry.classification == "DISCOVERED"
        assert entry.identity == identity
        assert entry.review.commit == commit
        assert entry.review.license == license_name
        assert entry.review.commercial_use


def test_api_auto_discovery_domain_remains_required():
    registry = load_repository_registry()
    assert "api-auto-discovery-and-computer-use" in registry.required_discovery_domains
