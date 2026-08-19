"""Fail-closed deployment factory for EAY Jarvis Platform authorization.

This module is the only runtime composition point that reads machine-identity
and Platform Core transport settings from the environment. It does not expose
an HTTP token-issuance endpoint and never accepts tenant/user/scope inputs.
"""

from __future__ import annotations

import os

from .jarvis_service_identity import (
    JarvisServiceIdentitySettings,
    JarvisServiceIdentitySigner,
)
from .platform_tool_authorizer import (
    PlatformToolAuthorizer,
    PlatformToolAuthorizerSettings,
)


class JarvisRuntimeConfigurationError(RuntimeError):
    """Jarvis runtime cannot be enabled safely with the supplied config."""


def platform_authorizer_settings_from_environment() -> PlatformToolAuthorizerSettings:
    base_url = os.getenv("EAY_PLATFORM_CORE_BASE_URL", "").strip()
    timeout_raw = os.getenv(
        "EAY_PLATFORM_CORE_AUTH_TIMEOUT_SECONDS",
        "5",
    ).strip()

    if not base_url:
        raise JarvisRuntimeConfigurationError(
            "EAY_PLATFORM_CORE_BASE_URL is required"
        )

    try:
        timeout_seconds = float(timeout_raw)
    except ValueError as exc:
        raise JarvisRuntimeConfigurationError(
            "Platform Core authorization timeout is invalid"
        ) from exc

    try:
        return PlatformToolAuthorizerSettings(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    except ValueError as exc:
        raise JarvisRuntimeConfigurationError(str(exc)) from exc


def build_platform_tool_authorizer() -> PlatformToolAuthorizer:
    """Build the governed AI Core -> Platform Core authorization client."""

    try:
        identity_settings = (
            JarvisServiceIdentitySettings.from_environment()
        )
        signer = JarvisServiceIdentitySigner(identity_settings)
    except (ValueError, RuntimeError) as exc:
        raise JarvisRuntimeConfigurationError(
            "Jarvis machine identity is unavailable"
        ) from exc

    return PlatformToolAuthorizer(
        platform_authorizer_settings_from_environment(),
        signer,
    )
