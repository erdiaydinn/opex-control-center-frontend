from __future__ import annotations

from hashlib import sha256
import os
import unittest
from unittest.mock import patch

from starlette.requests import Request

from app.modules.recruitment import public_capability_guard as guard


def request(path: str, *, headers: list[tuple[bytes, bytes]] | None = None, client=("10.0.0.8", 41200)) -> Request:
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
        "client": client,
        "server": ("eay.example", 443),
    })


class PublicCapabilityGuardTests(unittest.IsolatedAsyncioTestCase):
    def test_production_requires_redis(self):
        with patch.dict(os.environ, {"DOCKOS_ENV": "production", "RECRUITMENT_PUBLIC_CAPABILITY_REDIS_URL": "", "REDIS_URL": ""}, clear=False):
            with self.assertRaises(guard.PublicCapabilityGuardError):
                guard.preflight()

    def test_nonproduction_can_run_without_redis(self):
        with patch.dict(os.environ, {"DOCKOS_ENV": "test", "RECRUITMENT_PUBLIC_CAPABILITY_REDIS_URL": "", "REDIS_URL": ""}, clear=False):
            self.assertEqual(guard.preflight(), {"configured": False, "required": False})

    def test_invalid_redis_scheme_is_rejected_before_network(self):
        with patch.dict(os.environ, {"DOCKOS_ENV": "production", "RECRUITMENT_PUBLIC_CAPABILITY_REDIS_URL": "http://redis:6379"}, clear=False):
            with self.assertRaisesRegex(guard.PublicCapabilityGuardError, "URL is invalid"):
                guard.preflight()

    def test_proxy_ip_is_trusted_only_with_server_gateway_secret(self):
        headers = [(b"x-real-ip", b"203.0.113.44"), (b"x-dockos-gateway", b"server-secret")]
        req = request("/api/public/recruitment/offer", headers=headers)
        with patch.dict(os.environ, {"DOCKOS_GATEWAY_SECRET": "server-secret"}, clear=False):
            self.assertEqual(guard._source_key(req), sha256(b"203.0.113.44").hexdigest()[:24])
        with patch.dict(os.environ, {"DOCKOS_GATEWAY_SECRET": "different-secret"}, clear=False):
            self.assertEqual(guard._source_key(req), sha256(b"10.0.0.8").hexdigest()[:24])

    async def test_oversized_public_upload_is_rejected_before_redis(self):
        req = request(
            "/api/recruitment/candidate-upload/evidence",
            headers=[(b"content-length", str(13 * 1024 * 1024).encode())],
        )
        response = await guard.enforce(req)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 413)

    async def test_unrelated_path_is_not_throttled(self):
        response = await guard.enforce(request("/api/recruitment/health"))
        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
