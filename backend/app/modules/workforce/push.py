"""APNs/FCM delivery adapters used only by the background worker."""

from __future__ import annotations

from datetime import UTC, datetime
import os

import httpx


class PushError(RuntimeError):
    pass


def _apns_token() -> str:
    import jwt

    private_key_path = os.getenv("APNS_PRIVATE_KEY_PATH", "")
    if not private_key_path:
        raise PushError("APNS_PRIVATE_KEY_PATH eksik")
    with open(private_key_path, encoding="utf-8") as handle:
        private_key = handle.read()
    return jwt.encode(
        {"iss": os.environ["APNS_TEAM_ID"], "iat": int(datetime.now(UTC).timestamp())},
        private_key,
        algorithm="ES256",
        headers={"kid": os.environ["APNS_KEY_ID"]},
    )


def _send_apns(token: str, payload: dict, live_activity: bool = False) -> None:
    topic = os.environ["APNS_BUNDLE_ID"]
    headers = {
        "authorization": f"bearer {_apns_token()}",
        "apns-topic": f"{topic}.push-type.liveactivity" if live_activity else topic,
        "apns-push-type": "liveactivity" if live_activity else "alert",
        "apns-priority": "10",
    }
    body = payload if live_activity else {
        "aps": {"alert": {"title": payload.get("title", "OPEX Workforce"), "body": payload.get("message", "")}, "sound": "default"},
        "data": payload,
    }
    host = "https://api.sandbox.push.apple.com" if os.getenv("APNS_ENV", "production") == "sandbox" else "https://api.push.apple.com"
    response = httpx.post(f"{host}/3/device/{token}", headers=headers, json=body, timeout=15, http2=True)
    if response.status_code != 200:
        raise PushError(f"APNs {response.status_code}: {response.text[:500]}")


def _send_fcm(token: str, payload: dict) -> None:
    from google.auth import default
    from google.auth.transport.requests import Request

    project_id = os.getenv("FCM_PROJECT_ID", "")
    if not project_id:
        raise PushError("FCM_PROJECT_ID eksik")
    credentials, _ = default(scopes=["https://www.googleapis.com/auth/firebase.messaging"])
    credentials.refresh(Request())
    response = httpx.post(
        f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
        headers={"Authorization": f"Bearer {credentials.token}"},
        json={"message": {"token": token, "notification": {"title": payload.get("title", "OPEX Workforce"), "body": payload.get("message", "")}, "data": {key: str(value) for key, value in payload.items() if value is not None}}},
        timeout=15,
    )
    if response.status_code >= 300:
        raise PushError(f"FCM {response.status_code}: {response.text[:500]}")


def deliver(job: dict) -> None:
    platform = str(job.get("platform") or "").upper()
    token = job.get("push_token")
    if not token:
        raise PushError("Kayıtlı push token yok")
    payload = job.get("payload") or {}
    if platform == "IOS":
        _send_apns(token, payload, live_activity=job.get("type") == "LIVE_ACTIVITY")
    elif platform == "ANDROID":
        _send_fcm(token, payload)
    else:
        raise PushError(f"Desteklenmeyen platform: {platform or 'boş'}")
