from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import base64
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

class IdentityRuleError(RuntimeError):
    pass


DB_PATH = Path(os.getenv("IDENTITY_DB", str(Path(__file__).resolve().parents[3] / "data" / "identity_v23.db")))
PBKDF2_ITERATIONS = 600_000
ACCESS_MINUTES = 15
REFRESH_DAYS = 7


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    return db


def _now() -> datetime:
    return datetime.now(UTC)


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(32)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _password_ok(password: str, encoded: str) -> bool:
    try:
        _, iterations, salt, expected = encoded.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def _secret() -> str:
    value = os.getenv("OPEX_LOCAL_JWT_SECRET", "")
    if len(value) < 48:
        raise IdentityRuleError("OPEX_LOCAL_JWT_SECRET en az 48 karakter olmalıdır.")
    return value


def initialize() -> None:
    with closing(_connect()) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS warehouses(
          id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
          server_group TEXT NOT NULL, active INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users(
          id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
          password_hash TEXT NOT NULL, roles TEXT NOT NULL, active INTEGER NOT NULL,
          force_password_change INTEGER NOT NULL, failed_attempts INTEGER NOT NULL DEFAULT 0,
          locked_until TEXT, token_version INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_warehouses(
          user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          warehouse_id TEXT NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
          PRIMARY KEY(user_id,warehouse_id)
        );
        CREATE TABLE IF NOT EXISTS refresh_tokens(
          token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          device_id TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS identity_audit(
          sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, at TEXT NOT NULL,
          actor TEXT NOT NULL, event TEXT NOT NULL, target TEXT, details TEXT NOT NULL
        );
        CREATE TRIGGER IF NOT EXISTS identity_audit_no_update BEFORE UPDATE ON identity_audit
        BEGIN SELECT RAISE(ABORT, 'identity audit is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS identity_audit_no_delete BEFORE DELETE ON identity_audit
        BEGIN SELECT RAISE(ABORT, 'identity audit is append-only'); END;
        """)
        db.commit()


def _audit(db: sqlite3.Connection, actor: str, event: str, target: str | None, **details) -> None:
    db.execute("INSERT INTO identity_audit VALUES(NULL,?,?,?,?,?,?)",
               (str(uuid4()), _now().isoformat(), actor, event, target, json.dumps(details, ensure_ascii=False, sort_keys=True)))


def _warehouse_scope(db: sqlite3.Connection, user_id: str) -> list[str]:
    return [row["code"] for row in db.execute(
        "SELECT w.code FROM warehouses w JOIN user_warehouses uw ON uw.warehouse_id=w.id "
        "WHERE uw.user_id=? AND w.active=1 ORDER BY w.code", (user_id,))]


def _public_user(db: sqlite3.Connection, row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "username": row["username"], "name": row["name"],
        "roles": json.loads(row["roles"]), "active": bool(row["active"]),
        "force_password_change": bool(row["force_password_change"]),
        "warehouse_scope": _warehouse_scope(db, row["id"]),
    }


def _access_token(db: sqlite3.Connection, row: sqlite3.Row) -> str:
    issued = _now()
    claims = {
        "iss": "opex-local", "aud": "opex-control-center", "sub": row["id"],
        "email": row["username"], "name": row["name"], "roles": json.loads(row["roles"]),
        "permissions": [], "warehouse_scope": _warehouse_scope(db, row["id"]),
        "force_password_change": bool(row["force_password_change"]),
        "token_version": row["token_version"], "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(minutes=ACCESS_MINUTES)).timestamp()),
    }
    encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b"=").decode()
    header = encode(b'{"alg":"HS256","typ":"JWT"}')
    payload = encode(json.dumps(claims, separators=(",", ":"), ensure_ascii=False).encode())
    signature = encode(hmac.new(_secret().encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def _issue_session(db: sqlite3.Connection, row: sqlite3.Row, device_id: str) -> dict:
    raw = secrets.token_urlsafe(64)
    db.execute("INSERT INTO refresh_tokens VALUES(?,?,?,?,?,?)", (
        hashlib.sha256(raw.encode()).hexdigest(), row["id"], device_id,
        (_now() + timedelta(days=REFRESH_DAYS)).isoformat(), None, _now().isoformat()))
    return {"access_token": _access_token(db, row), "refresh_token": raw, "token_type": "bearer",
            "expires_in": ACCESS_MINUTES * 60, "user": _public_user(db, row)}


def login(username: str, password: str, device_id: str) -> dict:
    with closing(_connect()) as db:
        row = db.execute("SELECT * FROM users WHERE lower(username)=lower(?)", (username.strip(),)).fetchone()
        locked = row and row["locked_until"] and datetime.fromisoformat(row["locked_until"]) > _now()
        if not row or not row["active"] or locked or not _password_ok(password, row["password_hash"]):
            if row and not locked:
                attempts = row["failed_attempts"] + 1
                until = (_now() + timedelta(minutes=15)).isoformat() if attempts >= 5 else None
                db.execute("UPDATE users SET failed_attempts=?,locked_until=? WHERE id=?", (attempts, until, row["id"]))
                _audit(db, username, "LOGIN_FAILED", row["id"], device_id=device_id)
                db.commit()
            raise IdentityRuleError("Kullanıcı adı veya parola hatalı; hesap geçici olarak kilitlenmiş olabilir.")
        db.execute("UPDATE users SET failed_attempts=0,locked_until=NULL WHERE id=?", (row["id"],))
        result = _issue_session(db, row, device_id)
        _audit(db, row["id"], "LOGIN_SUCCEEDED", row["id"], device_id=device_id)
        db.commit()
        return result


def refresh(raw_token: str, device_id: str) -> dict:
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    with closing(_connect()) as db:
        token = db.execute("SELECT * FROM refresh_tokens WHERE token_hash=?", (digest,)).fetchone()
        if not token or token["revoked_at"] or token["device_id"] != device_id or datetime.fromisoformat(token["expires_at"]) <= _now():
            raise IdentityRuleError("Yenileme oturumu geçersiz veya süresi dolmuş.")
        row = db.execute("SELECT * FROM users WHERE id=? AND active=1", (token["user_id"],)).fetchone()
        if not row:
            raise IdentityRuleError("Kullanıcı pasif.")
        db.execute("UPDATE refresh_tokens SET revoked_at=? WHERE token_hash=?", (_now().isoformat(), digest))
        result = _issue_session(db, row, device_id)
        db.commit()
        return result


def list_users() -> list[dict]:
    with closing(_connect()) as db:
        return [_public_user(db, row) for row in db.execute("SELECT * FROM users ORDER BY username")]


def list_warehouses() -> list[dict]:
    with closing(_connect()) as db:
        return [dict(row) | {"active": bool(row["active"])} for row in db.execute("SELECT * FROM warehouses ORDER BY name")]


def create_warehouse(payload: dict, actor: str) -> dict:
    warehouse_id = f"WH-{uuid4().hex[:12]}"
    with closing(_connect()) as db:
        try:
            db.execute("INSERT INTO warehouses VALUES(?,?,?,?,?,?)", (warehouse_id, payload["code"].upper(), payload["name"],
                       payload["server_group"], int(payload["active"]), _now().isoformat()))
            _audit(db, actor, "WAREHOUSE_CREATED", warehouse_id, code=payload["code"].upper())
            db.commit()
        except sqlite3.IntegrityError as error:
            raise IdentityRuleError("Depo kodu zaten kullanılıyor.") from error
    return {"id": warehouse_id, **payload, "code": payload["code"].upper()}


def create_user(payload: dict, actor: str) -> dict:
    user_id = f"USR-{uuid4().hex[:16]}"
    with closing(_connect()) as db:
        warehouse_rows = list(db.execute(
            f"SELECT id FROM warehouses WHERE id IN ({','.join('?' for _ in payload['warehouse_ids'])}) AND active=1",
            payload["warehouse_ids"])) if payload["warehouse_ids"] else []
        if len(warehouse_rows) != len(set(payload["warehouse_ids"])):
            raise IdentityRuleError("Depo eşleşmelerinden biri geçersiz veya pasif.")
        at = _now().isoformat()
        try:
            db.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
                user_id, payload["username"].lower(), payload["name"], _password_hash(payload["password"]),
                json.dumps(sorted(set(payload["roles"]))), int(payload["active"]), int(payload["force_password_change"]),
                0, None, 1, at, at))
            db.executemany("INSERT INTO user_warehouses VALUES(?,?)", [(user_id, value) for value in payload["warehouse_ids"]])
            _audit(db, actor, "USER_CREATED", user_id, roles=payload["roles"], warehouses=payload["warehouse_ids"])
            db.commit()
        except sqlite3.IntegrityError as error:
            raise IdentityRuleError("Kullanıcı adı zaten kullanılıyor.") from error
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return _public_user(db, row)


def update_user(user_id: str, payload: dict, actor: str) -> dict:
    values = {key: value for key, value in payload.items() if value is not None}
    with closing(_connect()) as db:
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise IdentityRuleError("Kullanıcı bulunamadı.")
        if "name" in values:
            db.execute("UPDATE users SET name=? WHERE id=?", (values["name"], user_id))
        if "roles" in values:
            db.execute("UPDATE users SET roles=? WHERE id=?", (json.dumps(sorted(set(values["roles"]))), user_id))
        if "active" in values:
            db.execute("UPDATE users SET active=?,token_version=token_version+1 WHERE id=?", (int(values["active"]), user_id))
        if "password" in values:
            db.execute("UPDATE users SET password_hash=?,token_version=token_version+1 WHERE id=?", (_password_hash(values["password"]), user_id))
        if "force_password_change" in values:
            db.execute("UPDATE users SET force_password_change=? WHERE id=?", (int(values["force_password_change"]), user_id))
        if "warehouse_ids" in values:
            valid = list(db.execute(f"SELECT id FROM warehouses WHERE id IN ({','.join('?' for _ in values['warehouse_ids'])})",
                                    values["warehouse_ids"])) if values["warehouse_ids"] else []
            if len(valid) != len(set(values["warehouse_ids"])):
                raise IdentityRuleError("Geçersiz depo eşleşmesi.")
            db.execute("DELETE FROM user_warehouses WHERE user_id=?", (user_id,))
            db.executemany("INSERT INTO user_warehouses VALUES(?,?)", [(user_id, value) for value in values["warehouse_ids"]])
        db.execute("UPDATE users SET updated_at=? WHERE id=?", (_now().isoformat(), user_id))
        _audit(db, actor, "USER_UPDATED", user_id, fields=sorted(values))
        db.commit()
        return _public_user(db, db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())


def reset_password_by_admin(username: str, actor: str) -> dict:
    """Rotate a local user's password and invalidate every existing session.

    The temporary password is returned once to the authenticated administrator.
    It is never persisted or written to the audit trail in plaintext.
    """
    clean_username = username.strip().lower()
    temporary_password = f"Opex!{secrets.token_urlsafe(18)}"
    with closing(_connect()) as db:
        row = db.execute(
            "SELECT * FROM users WHERE lower(username)=lower(?)", (clean_username,)
        ).fetchone()
        if not row:
            raise IdentityRuleError("Kullanıcı sunucu kimlik sisteminde bulunamadı.")
        if not row["active"]:
            raise IdentityRuleError("Pasif kullanıcının parolası sıfırlanamaz; önce hesabı aktifleştirin.")

        db.execute(
            "UPDATE users SET password_hash=?,force_password_change=1,failed_attempts=0,"
            "locked_until=NULL,token_version=token_version+1,updated_at=? WHERE id=?",
            (_password_hash(temporary_password), _now().isoformat(), row["id"]),
        )
        db.execute(
            "UPDATE refresh_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
            (_now().isoformat(), row["id"]),
        )
        _audit(db, actor, "PASSWORD_RESET_BY_ADMIN", row["id"], username=row["username"])
        db.commit()
        return {
            "username": row["username"],
            "temporary_password": temporary_password,
            "force_password_change": True,
        }


def change_password(user_id: str, current_password: str, new_password: str, device_id: str) -> dict:
    with closing(_connect()) as db:
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row or not row["active"]:
            raise IdentityRuleError("Kullanıcı bulunamadı veya pasif.")
        if not _password_ok(current_password, row["password_hash"]):
            raise IdentityRuleError("Mevcut parola hatalı.")
        if _password_ok(new_password, row["password_hash"]):
            raise IdentityRuleError("Yeni parola mevcut paroladan farklı olmalıdır.")

        db.execute(
            "UPDATE users SET password_hash=?,force_password_change=0,failed_attempts=0,"
            "locked_until=NULL,token_version=token_version+1,updated_at=? WHERE id=?",
            (_password_hash(new_password), _now().isoformat(), user_id),
        )
        db.execute(
            "UPDATE refresh_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
            (_now().isoformat(), user_id),
        )
        updated = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        result = _issue_session(db, updated, device_id)
        _audit(db, user_id, "PASSWORD_CHANGED", user_id, device_id=device_id)
        db.commit()
        return result


def bootstrap_admin() -> bool:
    username = os.getenv("OPEX_BOOTSTRAP_ADMIN_USERNAME", "")
    password = os.getenv("OPEX_BOOTSTRAP_ADMIN_PASSWORD", "")
    if not username or not password:
        return False
    with closing(_connect()) as db:
        if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return False
    create_user({"username": username, "name": "OPEX Bootstrap Admin", "password": password,
                 "roles": ["super_admin"], "warehouse_ids": [], "active": True,
                 "force_password_change": True}, "system-bootstrap")
    return True


def validate_local_claims(claims: dict) -> dict:
    with closing(_connect()) as db:
        row = db.execute("SELECT active,token_version FROM users WHERE id=?", (str(claims.get("sub", "")),)).fetchone()
        if not row or not row["active"] or int(row["token_version"]) != int(claims.get("token_version", -1)):
            raise IdentityRuleError("Oturum iptal edilmiş veya kullanıcı pasif.")
    return claims
