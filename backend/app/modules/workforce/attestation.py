"""Fail-closed adapters for Apple App Attest and Google Play Integrity.

Vendor cryptography is delegated to a dedicated verification endpoint so keys
and Apple/Google service credentials never enter the browser application. The
endpoint must return JSON ``{"valid": true, ...}``.
"""

from __future__ import annotations

import os

class AttestationError(ValueError):
    pass


def verify(provider: str, token: str, *, person_id: str, device_id: str, key_id: str) -> dict:
    import httpx
    development = os.getenv("OPEX_ATTESTATION_MODE", "production").lower() == "development"
    if development and os.getenv("DOCKOS_ENV", "development").lower() != "production":
        return {"valid": True, "environment": "development", "provider": provider}

    env_key = "APPLE_APP_ATTEST_VERIFY_URL" if provider == "APPLE_APP_ATTEST" else "GOOGLE_PLAY_INTEGRITY_VERIFY_URL"
    url = os.getenv(env_key, "").strip()
    if not url:
        raise AttestationError(f"{provider} sunucu doğrulama servisi yapılandırılmamış.")
    secret = os.getenv("OPEX_ATTESTATION_GATEWAY_TOKEN", "")
    try:
        response = httpx.post(
            url,
            json={"token": token, "person_id": person_id, "device_id": device_id, "key_id": key_id},
            headers={"Authorization": f"Bearer {secret}"} if secret else {},
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()
    except Exception as error:
        raise AttestationError("Cihaz bütünlük servisine ulaşılamadı.") from error
    if result.get("valid") is not True:
        raise AttestationError(str(result.get("reason") or "Cihaz bütünlük kanıtı reddedildi."))
    return result
