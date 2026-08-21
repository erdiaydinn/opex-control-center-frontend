import pytest


@pytest.fixture(autouse=True)
def _eay_voice_runtime_test_mode(monkeypatch):
    """Tests must opt into production mode explicitly when exercising release gates."""
    monkeypatch.setenv("EAY_VOICE_RUNTIME_MODE", "test")
