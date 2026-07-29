"""Small, dependency-free security boundary for the PlanAI API.

This is intentionally a signed session token rather than a home-grown
password/session database.  It keeps the local deployment installable without
another package while making the API fail closed when authentication is
enabled.  For production, the same dependency boundary can be replaced by an
OIDC/JWT provider without changing endpoint signatures.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from fastapi import Depends, Header, HTTPException, status


BACKEND_ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("PLONAGRAM_DATA_DIR", str(BACKEND_ROOT / "data")))
TOKEN_TTL_SECONDS = max(300, int(os.getenv("PLONAGRAM_TOKEN_TTL_SECONDS", "28800")))
VALID_ROLES = {
    "USER",
    "VIEWER",
    "STORE_MANAGER",
    "REGIONAL_MANAGER",
    "ADMIN",
    "SUPER_USER",
}


def auth_required() -> bool:
    value = os.getenv("PLONAGRAM_AUTH_REQUIRED", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _secret() -> bytes:
    configured = os.getenv("PLONAGRAM_AUTH_SECRET", "").strip()
    if configured:
        return configured.encode("utf-8")

    if os.getenv("PLONAGRAM_ENV", "development").strip().lower() == "production":
        raise RuntimeError("PLONAGRAM_AUTH_SECRET production ortamında zorunludur.")

    # Local-only fallback survives restarts but is not source-controlled.
    path = DATA_DIR / ".auth_secret"
    try:
        if path.exists():
            return path.read_bytes()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        value = secrets.token_bytes(48)
        path.write_bytes(value)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return value
    except OSError:
        # Read-only containers still get a per-process secret in development.
        return hashlib.sha256(f"{os.getpid()}:{secrets.token_urlsafe(32)}".encode()).digest()


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_token(user: Dict[str, Any]) -> Dict[str, Any]:
    now = int(time.time())
    payload = {
        "sub": str(user.get("username") or ""),
        "role": str(user.get("role") or "USER").upper(),
        "assigned_stores": user.get("assigned_stores") or [],
        "default_store": user.get("default_store"),
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "jti": secrets.token_urlsafe(12),
    }
    header = {"alg": "HS256", "typ": "PLONAGRAM"}
    encoded_header = _b64(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    unsigned = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = _b64(hmac.new(_secret(), unsigned, hashlib.sha256).digest())
    return {
        "access_token": f"{encoded_header}.{encoded_payload}.{signature}",
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SECONDS,
    }


def decode_token(token: str) -> Dict[str, Any]:
    try:
        encoded_header, encoded_payload, received_signature = str(token).split(".", 2)
        unsigned = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected_signature = _b64(hmac.new(_secret(), unsigned, hashlib.sha256).digest())
        if not hmac.compare_digest(received_signature, expected_signature):
            raise ValueError("signature")
        header = json.loads(_unb64(encoded_header).decode("utf-8"))
        payload = json.loads(_unb64(encoded_payload).decode("utf-8"))
        if header.get("alg") != "HS256" or header.get("typ") != "PLONAGRAM":
            raise ValueError("header")
        if not payload.get("sub") or int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("expired")
        payload["role"] = str(payload.get("role") or "USER").upper()
        if payload["role"] not in VALID_ROLES:
            raise ValueError("role")
        return payload
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Oturum geçersiz veya süresi dolmuş.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _development_user() -> Dict[str, Any]:
    return {
        "sub": "development",
        "username": "development",
        "role": "ADMIN",
        "assigned_stores": ["*"],
        "default_store": "*",
        "development_bypass": True,
    }


def authenticate_authorization(authorization: Optional[str]) -> Dict[str, Any]:
    if not authorization:
        if not auth_required():
            return _development_user()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token gerekli.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization: Bearer <token> formatı gerekli.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decode_token(token.strip())
    claims["username"] = claims.get("sub")
    return claims


def get_current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    return authenticate_authorization(authorization)


def require_roles(*roles: str) -> Callable:
    allowed = {str(role).upper() for role in roles}

    def dependency(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user.get("role") not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu işlem için rol yetkiniz yok.")
        return user

    return dependency


def ensure_store_access(user: Dict[str, Any], store_code: Optional[str]) -> None:
    if not store_code:
        return
    assigned = {str(x).lower() for x in (user.get("assigned_stores") or [])}
    if "*" in assigned or str(store_code).lower() in assigned:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu depo için erişim yetkiniz yok.")
