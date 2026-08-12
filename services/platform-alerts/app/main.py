from __future__ import annotations

import json
import os
import smtplib
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import httpx


HEALTH_URL = os.getenv(
    "OPEX_PLATFORM_HEALTH_URL",
    "http://core-api:8000/v1/platform/health",
)
POLL_SECONDS = int(os.getenv("OPEX_ALERT_POLL_SECONDS", "300"))
COOLDOWN_HOURS = float(os.getenv("OPEX_ALERT_COOLDOWN_HOURS", "6"))
STATE_FILE = Path(os.getenv("OPEX_ALERT_STATE_FILE", "/state/alert-state.json"))

EMAIL_ENABLED = (
    os.getenv("OPEX_ALERT_EMAIL_ENABLED", "false").strip().lower() == "true"
)

SMTP_HOST = os.getenv("OPEX_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("OPEX_SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("OPEX_SMTP_USERNAME", "")
def read_secret(environment_name: str, file_environment_name: str) -> str:
    direct_value = os.getenv(environment_name, "").strip()
    secret_file = os.getenv(file_environment_name, "").strip()

    if direct_value and secret_file:
        raise RuntimeError(
            f"{environment_name} and {file_environment_name} cannot both be set"
        )

    if secret_file:
        try:
            value = Path(secret_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(
                f"{file_environment_name} cannot be read"
            ) from exc

        if not value:
            raise RuntimeError(
                f"{file_environment_name} is empty"
            )

        return value

    return direct_value

SMTP_PASSWORD = read_secret(
    "OPEX_SMTP_PASSWORD",
    "OPEX_SMTP_PASSWORD_FILE",
)
SMTP_FROM = os.getenv("OPEX_SMTP_FROM", "EAY OneOps Alerts")
SMTP_STARTTLS = (
    os.getenv("OPEX_SMTP_STARTTLS", "true").strip().lower() == "true"
)
RECIPIENTS = [
    item.strip()
    for item in os.getenv("OPEX_ALERT_RECIPIENTS", "").split(",")
    if item.strip()
]

ENVIRONMENT = os.getenv("OPEX_ENVIRONMENT", "development").strip().lower()


AUTH_MODE = os.getenv(
    "OPEX_PLATFORM_HEALTH_AUTH_MODE",
    "development",
).strip().lower()

AUTH_TOKEN = read_secret(
    "OPEX_PLATFORM_HEALTH_TOKEN",
    "OPEX_PLATFORM_HEALTH_TOKEN_FILE",
)

OIDC_TOKEN_URL = os.getenv("OPEX_ALERT_OIDC_TOKEN_URL", "").strip()
OIDC_CLIENT_ID = os.getenv("OPEX_ALERT_OIDC_CLIENT_ID", "").strip()
OIDC_CLIENT_SECRET = read_secret(
    "OPEX_ALERT_OIDC_CLIENT_SECRET",
    "OPEX_ALERT_OIDC_CLIENT_SECRET_FILE",
)
OIDC_SCOPE = os.getenv("OPEX_ALERT_OIDC_SCOPE", "").strip()
OIDC_AUDIENCE = os.getenv("OPEX_ALERT_OIDC_AUDIENCE", "").strip()

if ENVIRONMENT in {"staging", "production"}:
    forbidden_secret_environment = [
        name
        for name in (
            "OPEX_PLATFORM_HEALTH_TOKEN",
            "OPEX_ALERT_OIDC_CLIENT_SECRET",
            "OPEX_SMTP_PASSWORD",
        )
        if os.getenv(name, "").strip()
    ]

    if forbidden_secret_environment:
        raise RuntimeError(
            "Secrets must not be supplied directly through environment "
            "variables in staging or production"
        )

TOKEN_CACHE: dict[str, Any] = {
    "access_token": "",
    "expires_at": 0.0,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(STATE_FILE)


def send_email(subject: str, body: str, html: str | None = None) -> None:
    if not EMAIL_ENABLED:
        print(f"[alerts] E-mail disabled. Subject: {subject}")
        print(body)
        return

    if not SMTP_HOST or not RECIPIENTS:
        raise RuntimeError("SMTP host or alert recipients are not configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = SMTP_FROM
    message["To"] = ", ".join(RECIPIENTS)
    message.set_content(body)

    if html:
        message.add_alternative(html, subtype="html")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
        if SMTP_STARTTLS:
            smtp.starttls()

        if SMTP_USERNAME:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)

        smtp.send_message(message)


def get_access_token() -> str:
    if AUTH_MODE == "development":
        if ENVIRONMENT in {"staging", "production"}:
            raise RuntimeError(
                "Static development authentication is forbidden "
                "in staging and production"
            )

        if not AUTH_TOKEN:
            raise RuntimeError(
                "Platform health development token is not configured"
            )

        return AUTH_TOKEN

    if AUTH_MODE != "oidc":
        raise RuntimeError("Unsupported platform health authentication mode")

    if not OIDC_TOKEN_URL or not OIDC_CLIENT_ID or not OIDC_CLIENT_SECRET:
        raise RuntimeError("OIDC service identity configuration is incomplete")

    if (
        ENVIRONMENT in {"staging", "production"}
        and not OIDC_TOKEN_URL.startswith("https://")
    ):
        raise RuntimeError(
            "OIDC token endpoint must use HTTPS in staging and production"
        )

    now = time.monotonic()
    cached_token = str(TOKEN_CACHE.get("access_token", ""))
    expires_at = float(TOKEN_CACHE.get("expires_at", 0.0))

    if cached_token and now < expires_at:
        return cached_token

    data = {"grant_type": "client_credentials"}

    if OIDC_SCOPE:
        data["scope"] = OIDC_SCOPE

    if OIDC_AUDIENCE:
        data["audience"] = OIDC_AUDIENCE

    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            OIDC_TOKEN_URL,
            data=data,
            auth=httpx.BasicAuth(
                OIDC_CLIENT_ID,
                OIDC_CLIENT_SECRET,
            ),
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()

    access_token = str(payload.get("access_token", "")).strip()
    token_type = str(payload.get("token_type", "Bearer")).strip()

    if not access_token or token_type.lower() != "bearer":
        raise RuntimeError("OIDC provider returned an invalid access token")

    try:
        expires_in = int(payload.get("expires_in", 300))
    except (TypeError, ValueError):
        expires_in = 300

    TOKEN_CACHE["access_token"] = access_token
    TOKEN_CACHE["expires_at"] = now + max(5, expires_in - 60)

    return access_token


def fetch_health() -> dict[str, Any]:
    token = get_access_token()

    with httpx.Client(timeout=10.0) as client:
        response = client.get(
            HEALTH_URL,
            headers={"Authorization": f"Bearer {token}"},
        )

        if response.status_code not in {200, 503}:
            response.raise_for_status()

        return response.json()


def classify_problem(health: dict[str, Any]) -> dict[str, str] | None:
    backup = health.get("checks", {}).get("backup", {})
    status = backup.get("status", "unavailable")
    details = backup.get("details", {})

    if status == "ok":
        return None

    age = details.get("age_hours")
    completed_at = details.get("completed_at") or "bilinmiyor"
    filename = details.get("filename") or "bilinmiyor"
    message = details.get("message") or "Açıklama bulunamadı"

    if status == "warning":
        severity = "UYARI"
        explanation = (
            f"Veritabanı yedeği {age} saattir yenilenmedi. "
            "Uyarı eşiği aşıldı."
        )
    elif status == "stale":
        severity = "KRİTİK"
        explanation = (
            f"Veritabanı yedeği {age} saattir yenilenmedi. "
            "Kritik yaş eşiği aşıldı."
        )
    elif status == "failed":
        severity = "KRİTİK"
        explanation = "Son yedekleme veya arşiv doğrulama işlemi başarısız oldu."
    else:
        severity = "KRİTİK"
        explanation = "Yedek sağlık bilgisine ulaşılamıyor."

    return {
        "key": f"backup:{status}",
        "severity": severity,
        "status": status,
        "explanation": explanation,
        "completed_at": str(completed_at),
        "filename": str(filename),
        "message": str(message),
    }


def alert_html(problem: dict[str, str]) -> str:
    severity = problem["severity"]
    status = problem["status"]

    accent = "#dc2626" if severity == "KRİTİK" else "#d97706"
    badge_background = "#fee2e2" if severity == "KRİTİK" else "#fef3c7"
    badge_text = "#991b1b" if severity == "KRİTİK" else "#92400e"

    return f"""<!doctype html>
<html lang="tr">
<body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,sans-serif;color:#111827;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f4f6;padding:24px;">
    <tr>
      <td align="center">
        <table role="presentation" width="680" cellspacing="0" cellpadding="0" style="max-width:680px;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e5e7eb;">
          <tr>
            <td style="background:#0f172a;padding:22px 28px;">
              <div style="font-size:20px;font-weight:700;color:#ffffff;">EAY OneOps</div>
              <div style="font-size:13px;color:#cbd5e1;margin-top:4px;">Platform Alarm Merkezi</div>
            </td>
          </tr>

          <tr>
            <td style="padding:28px;">
              <div style="display:inline-block;background:{badge_background};color:{badge_text};font-size:12px;font-weight:700;padding:6px 10px;border-radius:999px;">
                {severity}
              </div>

              <h1 style="font-size:24px;line-height:1.3;margin:18px 0 8px;">
                Veritabanı yedekleme sorunu
              </h1>

              <p style="font-size:15px;line-height:1.6;color:#4b5563;margin:0 0 22px;">
                {problem["explanation"]}
              </p>

              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;margin-bottom:24px;">
                <tr>
                  <td style="padding:12px;border:1px solid #e5e7eb;background:#f9fafb;color:#6b7280;width:38%;">Durum</td>
                  <td style="padding:12px;border:1px solid #e5e7eb;font-weight:700;">{status}</td>
                </tr>
                <tr>
                  <td style="padding:12px;border:1px solid #e5e7eb;background:#f9fafb;color:#6b7280;">Son başarılı yedek</td>
                  <td style="padding:12px;border:1px solid #e5e7eb;">{problem["completed_at"]}</td>
                </tr>
                <tr>
                  <td style="padding:12px;border:1px solid #e5e7eb;background:#f9fafb;color:#6b7280;">Yedek dosyası</td>
                  <td style="padding:12px;border:1px solid #e5e7eb;">{problem["filename"]}</td>
                </tr>
                <tr>
                  <td style="padding:12px;border:1px solid #e5e7eb;background:#f9fafb;color:#6b7280;">Sistem mesajı</td>
                  <td style="padding:12px;border:1px solid #e5e7eb;">{problem["message"]}</td>
                </tr>
              </table>

              <div style="border-left:4px solid {accent};background:#f9fafb;padding:18px 20px;border-radius:8px;">
                <div style="font-size:14px;font-weight:700;margin-bottom:10px;">Önerilen aksiyon</div>
                <ol style="margin:0;padding-left:20px;color:#374151;font-size:14px;line-height:1.7;">
                  <li>postgres-backup container loglarını kontrol edin.</li>
                  <li>PostgreSQL bağlantısını doğrulayın.</li>
                  <li>Son dump dosyasını pg_restore --list ile test edin.</li>
                  <li>Sorun sürüyorsa yeni manuel yedek alın.</li>
                </ol>
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding:16px 28px;background:#f8fafc;border-top:1px solid #e5e7eb;font-size:12px;color:#64748b;">
              Bu mesaj EAY OneOps otomatik alarm servisi tarafından gönderildi.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def resolved_html(now_iso: str, active_key: str) -> str:
    return f"""<!doctype html>
<html lang="tr">
<body style="margin:0;padding:24px;background:#f3f4f6;font-family:Arial,sans-serif;">
  <div style="max-width:680px;margin:auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;">
    <div style="background:#0f172a;padding:22px 28px;color:#ffffff;">
      <div style="font-size:20px;font-weight:700;">EAY OneOps</div>
      <div style="font-size:13px;color:#cbd5e1;margin-top:4px;">Platform Alarm Merkezi</div>
    </div>
    <div style="padding:28px;color:#111827;">
      <div style="display:inline-block;background:#dcfce7;color:#166534;font-size:12px;font-weight:700;padding:6px 10px;border-radius:999px;">
        ÇÖZÜLDÜ
      </div>
      <h1 style="font-size:24px;margin:18px 0 8px;">
        Veritabanı yedekleme durumu normale döndü
      </h1>
      <p style="color:#4b5563;line-height:1.6;">
        Platform alarmı kapatıldı. Yedekleme servisi yeniden sağlıklı durumda.
      </p>
      <table width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;margin-top:22px;">
        <tr>
          <td style="padding:12px;border:1px solid #e5e7eb;background:#f9fafb;width:38%;">Çözülme zamanı</td>
          <td style="padding:12px;border:1px solid #e5e7eb;">{now_iso}</td>
        </tr>
        <tr>
          <td style="padding:12px;border:1px solid #e5e7eb;background:#f9fafb;">Önceki alarm</td>
          <td style="padding:12px;border:1px solid #e5e7eb;">{active_key}</td>
        </tr>
      </table>
    </div>
    <div style="padding:16px 28px;background:#f8fafc;border-top:1px solid #e5e7eb;font-size:12px;color:#64748b;">
      Bu mesaj EAY OneOps otomatik alarm servisi tarafından gönderildi.
    </div>
  </div>
</body>
</html>"""


def alert_body(problem: dict[str, str]) -> str:
    return (
        f"EAY OneOps platform alarmı\n\n"
        f"Seviye: {problem['severity']}\n"
        f"Durum: {problem['status']}\n"
        f"Sorun: {problem['explanation']}\n"
        f"Son başarılı yedek: {problem['completed_at']}\n"
        f"Yedek dosyası: {problem['filename']}\n"
        f"Sistem mesajı: {problem['message']}\n\n"
        "Önerilen aksiyon:\n"
        "1. postgres-backup container loglarını kontrol edin.\n"
        "2. PostgreSQL bağlantısını doğrulayın.\n"
        "3. Son dump dosyasını pg_restore --list ile test edin.\n"
        "4. Sorun sürüyorsa yeni manuel yedek alın.\n"
    )


def process_health(health: dict[str, Any]) -> None:
    state = load_state()
    problem = classify_problem(health)
    now = utc_now()

    active_key = state.get("active_key")
    last_sent_at = state.get("last_sent_at")

    if problem is None:
        if active_key:
            send_email(
                "[EAY OneOps] ÇÖZÜLDÜ - Veritabanı yedekleme alarmı",
                (
                    "Veritabanı yedekleme durumu yeniden sağlıklı hale geldi.\n\n"
                    f"Çözülme zamanı: {now.isoformat()}\n"
                    f"Önceki alarm: {active_key}\n"
                ),
                resolved_html(now.isoformat(), active_key),
            )

        save_state(
            {
                "active_key": None,
                "last_sent_at": None,
                "last_status": "ok",
                "updated_at": now.isoformat(),
            }
        )
        return

    should_send = problem["key"] != active_key

    if not should_send and last_sent_at:
        try:
            previous = datetime.fromisoformat(last_sent_at)
            elapsed_hours = (now - previous).total_seconds() / 3600
            should_send = elapsed_hours >= COOLDOWN_HOURS
        except ValueError:
            should_send = True

    if should_send:
        send_email(
            f"[EAY OneOps] {problem['severity']} - Veritabanı yedekleme sorunu",
            alert_body(problem),
            alert_html(problem),
        )
        last_sent_at = now.isoformat()

    save_state(
        {
            "active_key": problem["key"],
            "last_sent_at": last_sent_at,
            "last_status": problem["status"],
            "updated_at": now.isoformat(),
        }
    )


def main() -> None:
    print("[alerts] Platform alert worker started.")

    while True:
        try:
            health = fetch_health()
            process_health(health)
        except Exception as exc:
            print(f"[alerts] Health check failed: {type(exc).__name__}")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
