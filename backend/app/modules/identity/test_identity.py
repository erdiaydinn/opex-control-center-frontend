import os
import tempfile
from pathlib import Path

os.environ["OPEX_LOCAL_JWT_SECRET"] = "test-only-secret-" + ("x" * 64)

from app.modules.identity import service


def run() -> None:
    with tempfile.TemporaryDirectory() as folder:
        service.DB_PATH = Path(folder) / "identity.db"
        service.initialize()
        warehouse = service.create_warehouse(
            {"code": "FULYA", "name": "Fulya", "server_group": "primary", "active": True}, "test-admin"
        )
        user = service.create_user({
            "username": "counter.1@example.com", "name": "Counter 1", "password": "VeryStrong-Test-Password-123!",
            "roles": ["counter"], "warehouse_ids": [warehouse["id"]], "active": True,
            "force_password_change": True,
        }, "test-admin")
        assert user["warehouse_scope"] == ["FULYA"]
        session = service.login("counter.1@example.com", "VeryStrong-Test-Password-123!", "ZEBRA-1")
        assert session["access_token"] and session["refresh_token"]
        rotated = service.refresh(session["refresh_token"], "ZEBRA-1")
        assert rotated["refresh_token"] != session["refresh_token"]
        try:
            service.refresh(session["refresh_token"], "ZEBRA-1")
            raise AssertionError("Rotated refresh token reused")
        except service.IdentityRuleError:
            pass
        reset = service.reset_password_by_admin("counter.1@example.com", "test-admin")
        assert reset["force_password_change"] is True
        assert len(reset["temporary_password"]) >= 12
        try:
            service.login("counter.1@example.com", "VeryStrong-Test-Password-123!", "ZEBRA-1")
            raise AssertionError("Old password accepted after admin reset")
        except service.IdentityRuleError:
            pass
        temporary_session = service.login(
            "counter.1@example.com", reset["temporary_password"], "ZEBRA-1"
        )
        assert temporary_session["user"]["force_password_change"] is True
        changed = service.change_password(
            user["id"], reset["temporary_password"], "Different-Strong-Password-456!", "ZEBRA-1"
        )
        assert changed["user"]["force_password_change"] is False
        try:
            service.refresh(temporary_session["refresh_token"], "ZEBRA-1")
            raise AssertionError("Pre-change refresh token remained active")
        except service.IdentityRuleError:
            pass
        service.update_user(user["id"], {"active": False}, "test-admin")
        try:
            service.login("counter.1@example.com", "VeryStrong-Test-Password-123!", "ZEBRA-1")
            raise AssertionError("Disabled user logged in")
        except service.IdentityRuleError:
            pass
    print("identity tests passed")


if __name__ == "__main__":
    run()
