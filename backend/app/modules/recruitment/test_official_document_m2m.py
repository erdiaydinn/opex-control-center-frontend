from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.modules.recruitment.official_document_m2m import (
    AuthorizedOfficialM2MAdapter,
    OfficialM2MConfig,
    OfficialM2MError,
    build_detached_signature_verifier_from_environment,
)


class FakeClient:
    def __init__(self, *, body: dict | None = None, token_type: str = "Bearer", signature: str = "verified"):
        self.calls = []
        self.body = body or {
            "official_receipt_id": "r1",
            "result": "VERIFIED",
            "subject_match": "MATCH",
            "document_type": "RESIDENCE",
            "evidence_sha256": "a" * 64,
        }
        self.token_type = token_type
        self.signature = signature

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/token"):
            return httpx.Response(
                200,
                json={"access_token": "secret", "token_type": self.token_type},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            200,
            content=json.dumps(self.body).encode(),
            headers={"X-Provider-Signature": self.signature},
            request=httpx.Request("POST", url),
        )


def config() -> OfficialM2MConfig:
    return OfficialM2MConfig(
        endpoint="https://institutional.example.gov.tr/verify",
        token_url="https://institutional.example.gov.tr/token",
        client_id="client",
        client_secret="secret",
        mtls_cert="/client.crt",
        mtls_key="/client.key",
        allowed_hosts=("institutional.example.gov.tr",),
        contract_id="v1",
    )


class OfficialM2MTests(unittest.TestCase):
    def adapter(self, client: FakeClient) -> AuthorizedOfficialM2MAdapter:
        return AuthorizedOfficialM2MAdapter(
            config(),
            response_verifier=lambda _raw, headers: headers.get("x-provider-signature") == "verified",
            response_mapper=lambda payload: payload,
            client=client,
        )

    def test_signed_exact_binding(self):
        result = self.adapter(FakeClient()).verify_document(
            evidence_sha256="a" * 64,
            document_type="RESIDENCE",
            barcode="barcode",
            subject_reference="subject-ref",
            correlation_id="correlation",
        )
        self.assertTrue(result["provider_signature_verified"])
        self.assertEqual(result["verification_method"], "AUTHORIZED_OFFICIAL_API")
        self.assertEqual(result["truth_boundary"], "AUTHORIZED_MACHINE_TO_MACHINE")

    def test_public_portal_rejected(self):
        public_portal = OfficialM2MConfig(
            endpoint="https://www.turkiye.gov.tr/belge-dogrulama",
            token_url="https://www.turkiye.gov.tr/token",
            client_id="client",
            client_secret="secret",
            mtls_cert="/client.crt",
            mtls_key="/client.key",
            allowed_hosts=("www.turkiye.gov.tr",),
            contract_id="v1",
        )
        with self.assertRaises(OfficialM2MError):
            AuthorizedOfficialM2MAdapter(
                public_portal,
                response_verifier=lambda *_: True,
                response_mapper=lambda payload: payload,
                client=FakeClient(),
            )

    def test_unsigned_response_fails(self):
        with self.assertRaises(OfficialM2MError):
            self.adapter(FakeClient(signature="forged")).verify_document(
                evidence_sha256="a" * 64,
                document_type="RESIDENCE",
                barcode="barcode",
                subject_reference="subject-ref",
                correlation_id="correlation",
            )

    def test_exact_evidence_binding_and_internal_enums_are_enforced(self):
        mismatch = FakeClient(
            body={
                "official_receipt_id": "r2",
                "result": "VERIFIED",
                "subject_match": "MATCH",
                "document_type": "RESIDENCE",
                "evidence_sha256": "b" * 64,
            }
        )
        with self.assertRaises(OfficialM2MError):
            self.adapter(mismatch).verify_document(
                evidence_sha256="a" * 64,
                document_type="RESIDENCE",
                barcode="barcode",
                subject_reference="subject-ref",
                correlation_id="correlation",
            )

        unsupported = FakeClient(
            body={
                "official_receipt_id": "r3",
                "result": "NOT_VERIFIED",
                "subject_match": "UNKNOWN",
                "document_type": "RESIDENCE",
                "evidence_sha256": "a" * 64,
            }
        )
        with self.assertRaises(OfficialM2MError):
            self.adapter(unsupported).verify_document(
                evidence_sha256="a" * 64,
                document_type="RESIDENCE",
                barcode="barcode",
                subject_reference="subject-ref",
                correlation_id="correlation",
            )

    def test_non_bearer_token_fails(self):
        with self.assertRaises(OfficialM2MError):
            self.adapter(FakeClient(token_type="MAC")).verify_document(
                evidence_sha256="a" * 64,
                document_type="RESIDENCE",
                barcode="barcode",
                subject_reference="subject-ref",
                correlation_id="correlation",
            )

    def test_real_detached_rsa_pss_response_signature_profile(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        raw = b'{"result":"VERIFIED"}'
        signature = private_key.sign(
            raw,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        with tempfile.TemporaryDirectory() as directory:
            public_path = Path(directory) / "provider-public.pem"
            public_path.write_bytes(public_pem)
            with patch.dict(
                os.environ,
                {
                    "RECRUITMENT_OFFICIAL_M2M_SIGNATURE_PROFILE": "RSA_PSS_SHA256",
                    "RECRUITMENT_OFFICIAL_M2M_PROVIDER_PUBLIC_KEY_FILE": str(public_path),
                    "RECRUITMENT_OFFICIAL_M2M_SIGNATURE_HEADER": "X-Provider-Signature",
                },
                clear=False,
            ):
                verifier = build_detached_signature_verifier_from_environment()
                headers = {"x-provider-signature": base64.b64encode(signature).decode()}
                self.assertTrue(verifier(raw, headers))
                self.assertFalse(verifier(raw + b"tampered", headers))


if __name__ == "__main__":
    unittest.main()
