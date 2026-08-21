import pytest

from app.license_gate import assert_model_license_allowed


def test_default_allowlist_accepts_apache_2():
    assert_model_license_allowed("apache-2.0")


def test_unknown_model_license_is_blocked():
    with pytest.raises(ValueError, match="model_license_not_allowlisted"):
        assert_model_license_allowed("custom-research-only")
