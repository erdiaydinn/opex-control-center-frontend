from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import hashlib
import json
import re
import secrets

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
    raw = str(password or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_users() -> Dict[str, Any]:
    users = read_json(USERS_PATH, {})
    # First-run admin bootstrap. Keeps old demo access working.
    if "erdi" not in users:
        users["erdi"] = {
            "username": "erdi",
            "email": "erdi@plonagram.local",
            "password_hash": hash_password("1234"),
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
    approver_username: str = "erdi"
    role_override: Optional[str] = None


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
    username = str(req.username or "").strip().lower()
    email = str(req.email or "").strip().lower()
    password = str(req.password or "")
    role = normalize_role(req.role)
    store_code = str(req.store_code or "").strip().lower()

    if not username or not re.match(r"^[a-zA-Z0-9_.-]{3,50}$", username):
        raise HTTPException(status_code=400, detail="Kullanıcı adı 3-50 karakter olmalı; harf, rakam, nokta, tire veya alt tire içermeli.")
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Geçerli e-posta zorunlu.")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Şifre en az 4 karakter olmalı.")

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
    ident = str(req.username or "").strip().lower()
    users = load_users()
    user = users.get(ident)
    if not user:
        user = next((u for u in users.values() if str(u.get("email", "")).lower() == ident), None)
    if not user or user.get("password_hash") != hash_password(req.password):
        raise HTTPException(status_code=401, detail="Kullanıcı adı/e-posta veya şifre hatalı.")
    if user.get("status") != "ACTIVE":
        return {"success": False, "status": user.get("status"), "message": "Hesabınız admin onayı bekliyor.", "user": public_user(user)}
    return {"success": True, "user": public_user(user), "message": "Giriş başarılı."}


@router.get("/pending-users")
def pending_users():
    users = load_users()
    pending = [public_user(u) for u in users.values() if u.get("status") == "PENDING_APPROVAL"]
    return {"success": True, "pending": pending, "count": len(pending)}


@router.post("/approve-user")
def approve_user(req: ApproveUserRequest):
    users = load_users()
    target = str(req.username or "").strip().lower()
    user = users.get(target)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    if req.approve:
        if req.role_override:
            user["role"] = normalize_role(req.role_override)
        user["status"] = "ACTIVE"
        user["approved_by"] = req.approver_username
        user["approved_at"] = now_iso()
        message = "Kullanıcı onaylandı."
    else:
        user["status"] = "REJECTED"
        user["approved_by"] = req.approver_username
        user["approved_at"] = now_iso()
        message = "Kullanıcı reddedildi."
    users[target] = user
    save_users(users)
    return {"success": True, "message": message, "user": public_user(user)}


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    email = str(req.email or "").lower().strip()
    users = load_users()
    user = next((u for u in users.values() if str(u.get("email", "")).lower() == email), None)
    if not user:
        raise HTTPException(status_code=404, detail="Bu mail adresi kayıtlı değil.")
    token = secrets.token_urlsafe(32)
    RESET_TOKENS[token] = {"email": email, "expires_at": datetime.utcnow() + timedelta(minutes=30)}
    print(f"[PASSWORD_RESET] email={email} token={token}")
    return {"success": True, "message": "Şifre sıfırlama maili gönderildi."}
