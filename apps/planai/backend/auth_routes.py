from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import hashlib
import base64
import hmac
import json
import os
import re
import secrets

from security import issue_token, require_roles, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)
USERS_PATH = DATA_DIR / "users.json"
STORES_PATH = DATA_DIR / "stores_master.json"
RESET_TOKENS: Dict[str, Dict[str, Any]] = {}

AUTO_APPROVED_ROLES = {"USER", "VIEWER"}
APPROVAL_REQUIRED_ROLES = {"STORE_MANAGER", "REGIONAL_MANAGER", "ADMIN", "SUPER_USER"}
VALID_ROLES = AUTO_APPROVED_ROLES | APPROVAL_REQUIRED_ROLES


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def normalize_role(role: str) -> str:
    r = str(role or "USER").strip().upper().replace("SUPERUSER", "SUPER_USER")
    return r if r in VALID_ROLES else "USER"


def read_json(path: Path, default):
    if not path.exists():
        write_json(path, default)
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def hash_password(password: str) -> str:
    raw = str(password or "").encode("utf-8")
    iterations = 310_000
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw, salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    value = str(stored or "")
    if value.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt_b64, digest_b64 = value.split("$", 3)
            salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
            expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
            actual = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt, int(iterations))
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False

    # One-time compatibility for old local users.json files.  Successful
    # login upgrades the record to PBKDF2 in the login handler.
    legacy = hashlib.sha256(str(password or "").encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, value)


def load_users() -> Dict[str, Any]:
    users = read_json(USERS_PATH, {})
    # Bootstrap is explicit and never contains a source-controlled password.
    # Existing legacy users are kept so an upgrade does not lock out a local
    # installation; their hash is upgraded after the next successful login.
    bootstrap_password = os.getenv("PLONAGRAM_BOOTSTRAP_PASSWORD", "")
    if not users and bootstrap_password:
        users["erdi"] = {
            "username": "erdi",
            "email": "erdi@plonagram.local",
            "password_hash": hash_password(bootstrap_password),
            "role": "ADMIN",
            "status": "ACTIVE",
            "assigned_stores": ["*"],
            "default_store": "*",
            "created_at": now_iso(),
            "approved_by": "system",
            "approved_at": now_iso(),
        }
        write_json(USERS_PATH, users)
    return users


def save_users(users: Dict[str, Any]):
    write_json(USERS_PATH, users)


def load_stores() -> List[Dict[str, Any]]:
    stores = read_json(STORES_PATH, [])
    return [s for s in stores if s.get("store_code")]


def find_store(code: str) -> Optional[Dict[str, Any]]:
    c = str(code or "").strip().lower()
    for s in load_stores():
        if str(s.get("store_code", "")).lower() == c or str(s.get("vendor_id", "")).lower() == c:
            return s
    return None


def public_user(u: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "username": u.get("username"),
        "email": u.get("email"),
        "role": normalize_role(u.get("role")),
        "status": u.get("status", "PENDING_APPROVAL"),
        "assigned_stores": u.get("assigned_stores", []),
        "default_store": u.get("default_store"),
        "store": u.get("store"),
        "created_at": u.get("created_at"),
        "approved_by": u.get("approved_by"),
        "approved_at": u.get("approved_at"),
    }


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "USER"
    store_code: str
    full_name: Optional[str] = None
    reason: Optional[str] = ""


class ForgotPasswordRequest(BaseModel):
    email: str


class ApproveUserRequest(BaseModel):
    username: str
    approve: bool = True
    approver_username: Optional[str] = None
    role_override: Optional[str] = None


class OpexBridgeRequest(BaseModel):
    user: Dict[str, Any]
    permissions: Dict[str, Any]
    scope: Dict[str, Any] = {}


def _opex_dev_bridge_enabled() -> bool:
    if os.getenv("PLONAGRAM_ENV", "development").strip().lower() == "production":
        return False
    return os.getenv("PLONAGRAM_OPEX_DEV_BRIDGE", "true").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _local_auth_enabled() -> bool:
    if os.getenv("PLONAGRAM_ENV", "development").strip().lower() == "production":
        return False
    return os.getenv("PLONAGRAM_LOCAL_AUTH", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _require_local_auth() -> None:
    if not _local_auth_enabled():
        raise HTTPException(
            status_code=404,
            detail="Planogram yerel kullanıcı sistemi kapalı; OPEX oturumu kullanılmalıdır.",
        )


def _allowed_opex_origins() -> set[str]:
    return {
        origin.strip()
        for origin in os.getenv(
            "PLONAGRAM_OPEX_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
        ).split(",")
        if origin.strip()
    }


@router.get("/stores")
def list_stores(q: str = "", city: str = "", region: str = "", store_type: str = "", limit: int = 500):
    stores = load_stores()
    ql = str(q or "").lower().strip()
    city_l = str(city or "").lower().strip()
    region_l = str(region or "").lower().strip()
    type_l = str(store_type or "").lower().strip()

    def ok(s):
        hay = " ".join(str(s.get(k, "")) for k in [
            "store_code", "vendor_id", "store_name", "display_name", "city", "district", "region", "zone"
        ]).lower()
        if ql and ql not in hay:
            return False
        if city_l and city_l not in str(s.get("city", "")).lower():
            return False
        if region_l and region_l not in str(s.get("region", "")).lower():
            return False
        if type_l and type_l not in str(s.get("store_type", "")).lower():
            return False
        return True

    filtered = [s for s in stores if ok(s)][:max(1, min(limit, 1000))]
    cities = sorted({s.get("city") for s in stores if s.get("city")})
    regions = sorted({s.get("region") for s in stores if s.get("region")})
    return {"success": True, "total": len(stores), "stores": filtered, "cities": cities, "regions": regions}


@router.get("/stores/{store_code}")
def get_store(store_code: str):
    store = find_store(store_code)
    if not store:
        raise HTTPException(status_code=404, detail="Depo bulunamadı.")
    return {"success": True, "store": store}


@router.post("/register")
def register(req: RegisterRequest):
    _require_local_auth()
    username = str(req.username or "").strip().lower()
    email = str(req.email or "").strip().lower()
    password = str(req.password or "")
    role = normalize_role(req.role)
    store_code = str(req.store_code or "").strip().lower()

    if not username or not re.match(r"^[a-zA-Z0-9_.-]{3,50}$", username):
        raise HTTPException(status_code=400, detail="Kullanıcı adı 3-50 karakter olmalı; harf, rakam, nokta, tire veya alt tire içermeli.")
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Geçerli e-posta zorunlu.")
    if len(password) < 12:
        raise HTTPException(status_code=400, detail="Şifre en az 12 karakter olmalı.")

    store = find_store(store_code)
    if not store:
        raise HTTPException(status_code=400, detail="Geçerli bir depo seçmelisiniz.")

    users = load_users()
    if username in users:
        raise HTTPException(status_code=409, detail="Bu kullanıcı adı zaten kayıtlı.")
    if any(str(u.get("email", "")).lower() == email for u in users.values()):
        raise HTTPException(status_code=409, detail="Bu e-posta zaten kayıtlı.")

    status = "ACTIVE" if role in AUTO_APPROVED_ROLES else "PENDING_APPROVAL"
    user = {
        "username": username,
        "full_name": req.full_name or username,
        "email": email,
        "password_hash": hash_password(password),
        "role": role,
        "status": status,
        "assigned_stores": [store["store_code"]],
        "default_store": store["store_code"],
        "store": store,
        "request_reason": req.reason or "",
        "created_at": now_iso(),
        "approved_by": "system" if status == "ACTIVE" else None,
        "approved_at": now_iso() if status == "ACTIVE" else None,
    }
    users[username] = user
    save_users(users)

    if status == "ACTIVE":
        message = "Kayıt tamamlandı. USER/VIEWER rolü otomatik aktif edildi."
    else:
        message = "Kayıt talebi alındı. Bu rol admin onayı gerektiriyor."

    return {"success": True, "status": status, "message": message, "user": public_user(user)}


@router.post("/login")
def login(req: LoginRequest):
    _require_local_auth()
    ident = str(req.username or "").strip().lower()
    users = load_users()
    user = users.get(ident)
    if not user:
        user = next((u for u in users.values() if str(u.get("email", "")).lower() == ident), None)
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Kullanıcı adı/e-posta veya şifre hatalı.")
    if user.get("status") != "ACTIVE":
        return {"success": False, "status": user.get("status"), "message": "Hesabınız admin onayı bekliyor.", "user": public_user(user)}
    if not str(user.get("password_hash", "")).startswith("pbkdf2_sha256$"):
        user["password_hash"] = hash_password(req.password)
        save_users(users)
    return {"success": True, **issue_token(user), "user": public_user(user), "message": "Giriş başarılı."}


@router.post("/opex-dev-exchange")
def opex_dev_exchange(req: OpexBridgeRequest, request: Request):
    """Create a short-lived Planogram token for the local OPEX bridge.

    This endpoint is deliberately unavailable in production. Production must
    pass a centrally issued bearer token through the OPEX host; an unsigned
    browser payload is never accepted there.
    """
    if not _opex_dev_bridge_enabled():
        raise HTTPException(status_code=404, detail="OPEX geliştirme köprüsü kapalı.")

    origin = str(request.headers.get("origin") or "").rstrip("/")
    if origin not in _allowed_opex_origins():
        raise HTTPException(status_code=403, detail="OPEX origin izinli değil.")

    user = req.user or {}
    permissions = req.permissions or {}
    email = str(user.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Geçerli OPEX kullanıcı kimliği gerekli.")
    if not bool(permissions.get("view")):
        raise HTTPException(status_code=403, detail="Planogram görüntüleme yetkisi yok.")

    actions = permissions.get("actions") or {}
    opex_role = str(user.get("role") or "viewer").strip().lower()
    if opex_role == "super_admin":
        role = "SUPER_USER"
    elif permissions.get("admin") or actions.get("approve") or actions.get("delete"):
        role = "ADMIN"
    elif actions.get("edit") or actions.get("create"):
        role = "STORE_MANAGER"
    else:
        role = "VIEWER"

    scope = req.scope or {}
    scope_type = str(scope.get("type") or "none").lower()
    assigned_stores = ["*"] if scope_type == "all" else [
        str(value).strip()
        for value in (scope.get("warehouses") or [])
        if str(value).strip()
    ]
    if scope_type == "warehouse" and not assigned_stores:
        raise HTTPException(status_code=403, detail="Planogram depo kapsamı boş.")

    token_user = {
        "username": email,
        "email": email,
        "name": user.get("name") or email,
        "role": role,
        "assigned_stores": assigned_stores,
        "default_store": assigned_stores[0] if assigned_stores else None,
        "permissions": permissions,
        "scope": scope,
        "issuer": "opex-dev-bridge",
    }
    return {
        "success": True,
        **issue_token(token_user),
        "user": {
            "username": email,
            "email": email,
            "name": token_user["name"],
            "role": role,
            "assigned_stores": assigned_stores,
            "default_store": token_user["default_store"],
            "permissions": permissions,
            "scope": scope,
        },
    }


@router.get("/me")
def current_session(current_user: Dict[str, Any] = Depends(get_current_user)):
    if str(current_user.get("issuer") or "").startswith("opex"):
        return {
            "success": True,
            "user": {
                "username": current_user.get("username") or current_user.get("sub"),
                "email": current_user.get("email"),
                "name": current_user.get("name"),
                "role": current_user.get("role"),
                "assigned_stores": current_user.get("assigned_stores") or [],
                "default_store": current_user.get("default_store"),
                "permissions": current_user.get("permissions") or {},
                "scope": current_user.get("scope") or {},
            },
        }
    username = str(current_user.get("username") or current_user.get("sub") or "").lower()
    user = load_users().get(username)
    if not user or user.get("status") != "ACTIVE":
        raise HTTPException(status_code=401, detail="Kullanıcı oturumu artık aktif değil.")
    return {"success": True, "user": public_user(user)}


@router.get("/pending-users")
def pending_users(current_user: Dict[str, Any] = Depends(require_roles("ADMIN", "SUPER_USER"))):
    _require_local_auth()
    users = load_users()
    pending = [public_user(u) for u in users.values() if u.get("status") == "PENDING_APPROVAL"]
    return {"success": True, "pending": pending, "count": len(pending)}


@router.post("/approve-user")
def approve_user(req: ApproveUserRequest, current_user: Dict[str, Any] = Depends(require_roles("ADMIN", "SUPER_USER"))):
    _require_local_auth()
    users = load_users()
    target = str(req.username or "").strip().lower()
    user = users.get(target)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    if req.approve:
        if req.role_override:
            user["role"] = normalize_role(req.role_override)
        user["status"] = "ACTIVE"
        user["approved_by"] = current_user.get("username")
        user["approved_at"] = now_iso()
        message = "Kullanıcı onaylandı."
    else:
        user["status"] = "REJECTED"
        user["approved_by"] = current_user.get("username")
        user["approved_at"] = now_iso()
        message = "Kullanıcı reddedildi."
    users[target] = user
    save_users(users)
    return {"success": True, "message": message, "user": public_user(user)}


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    _require_local_auth()
    email = str(req.email or "").lower().strip()
    users = load_users()
    user = next((u for u in users.values() if str(u.get("email", "")).lower() == email), None)
    # Do not reveal whether an account exists and never print reset tokens to
    # logs.  A mail provider can consume RESET_TOKENS in the deployment layer.
    if user:
        token = secrets.token_urlsafe(32)
        RESET_TOKENS[token] = {"email": email, "expires_at": datetime.utcnow() + timedelta(minutes=30)}
    return {"success": True, "message": "Varsa şifre sıfırlama bağlantısı gönderildi."}
