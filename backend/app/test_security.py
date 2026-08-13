import os
import sys
import types
import unittest
from unittest.mock import patch

try:
    from fastapi import HTTPException
except ModuleNotFoundError:  # Keeps the identity boundary unit-test runnable without web extras.
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            self.status_code = status_code
            self.detail = detail
    fastapi = types.ModuleType("fastapi")
    fastapi.HTTPException = HTTPException
    fastapi.Request = object
    fastapi.status = types.SimpleNamespace(HTTP_401_UNAUTHORIZED=401, HTTP_403_FORBIDDEN=403)
    sys.modules["fastapi"] = fastapi
    starlette = types.ModuleType("starlette")
    middleware = types.ModuleType("starlette.middleware")
    middleware_base = types.ModuleType("starlette.middleware.base")
    middleware_base.BaseHTTPMiddleware = object
    sys.modules.update({"starlette": starlette, "starlette.middleware": middleware, "starlette.middleware.base": middleware_base})

from .security import identity_from_request


def request(headers: list[tuple[bytes, bytes]]):
    return types.SimpleNamespace(headers={key.decode(): value.decode() for key, value in headers})


class ProductionIdentityTests(unittest.TestCase):
    def test_production_rejects_spoofable_legacy_headers(self):
        with patch.dict(os.environ, {"DOCKOS_ENV": "production", "OPEX_ALLOW_LEGACY_HEADERS": "false"}, clear=False):
            with self.assertRaises(HTTPException) as error:
                identity_from_request(request([(b"x-opex-role", b"super_admin"), (b"x-opex-user", b"spoofed")]))
        self.assertEqual(error.exception.status_code, 401)

    def test_verified_oidc_employee_id_becomes_workforce_identity(self):
        claims = {"sub": "oidc-subject", "email": "picker@example.com", "name": "Pilot Picker", "roles": ["picker"], "permissions": [], "employee_id": "EMP-42"}
        with patch("app.security._decode_bearer", return_value=claims):
            identity = identity_from_request(request([(b"authorization", b"Bearer signed.jwt")]))
        self.assertEqual(identity.subject, "oidc-subject")
        self.assertEqual(identity.employee_id, "EMP-42")

    def test_employee_id_claim_name_is_configurable_for_production_idp(self):
        claims = {"sub": "oidc-subject", "roles": ["picker"], "corp_employee_no": "EMP-99"}
        with patch.dict(os.environ, {"OPEX_OIDC_EMPLOYEE_ID_CLAIM": "corp_employee_no"}, clear=False), patch("app.security._decode_bearer", return_value=claims):
            identity = identity_from_request(request([(b"authorization", b"Bearer signed.jwt")]))
        self.assertEqual(identity.employee_id, "EMP-99")


if __name__ == "__main__":
    unittest.main()
