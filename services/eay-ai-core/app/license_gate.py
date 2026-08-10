from __future__ import annotations

import os

DEFAULT_ALLOWED = "apache-2.0,mit,bsd-3-clause"


def allowed_model_licenses() -> set[str]:
    raw = os.getenv("EAY_ALLOWED_MODEL_LICENSES", DEFAULT_ALLOWED)
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def assert_model_license_allowed(license_id: str) -> None:
    normalized = license_id.strip().lower()
    if normalized not in allowed_model_licenses():
        raise ValueError(f"model_license_not_allowlisted:{license_id}")
