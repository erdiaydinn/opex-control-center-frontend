from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import unittest

from app.modules.recruitment.scanner_receipt import (
    ScannerReceipt, ScannerReceiptError, hmac_sha256_verifier, verify_scanner_receipt,
)


class ReplaySet:
    def __init__(self):
        self.seen = set()

    def claim(self, tenant_id, provider, receipt_id):
        key = (tenant_id, provider, receipt_id)
        if key in self.seen:
            return False
        self.seen.add(key)
        return True


class ScannerReceiptBoundaryTests(unittest.TestCase):
    now = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    key = b"test-only-key-material-not-a-production-secret"

    def setUp(self):
        self.replays = ReplaySet()
        self.payload = {
            "tenant_id": "tenant-a", "candidate_id": "candidate-1",
            "evidence_id": "evidence-1", "evidence_sha256": "a" * 64,
            "provider": "scanner-provider", "engine": "engine-v1", "key_id": "kid-2026-08",
            "receipt_id": "receipt-1", "nonce": "nonce-1", "result": "CLEAN",
            "issued_at": self.now.isoformat(),
        }
        self.verifier = hmac_sha256_verifier(lambda kid: self.key if kid == "kid-2026-08" else None)

    def sign(self, payload=None):
        receipt = ScannerReceipt(**(payload or self.payload))
        digest = hmac.new(self.key, receipt.canonical_bytes(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    def verify(self, payload=None, signature=None, **kwargs):
        return verify_scanner_receipt(
            payload or self.payload, signature or self.sign(payload), verifier=self.verifier,
            replay_authority=self.replays, expected_tenant_id="tenant-a",
            expected_candidate_id="candidate-1", expected_evidence_id="evidence-1",
            expected_evidence_sha256="a" * 64, now=self.now, **kwargs,
        )

    def test_accepts_fresh_exact_signed_receipt_once(self):
        self.assertEqual(self.verify().result, "CLEAN")
        with self.assertRaisesRegex(ScannerReceiptError, "replay"):
            self.verify()

    def test_tampering_exact_hash_fails_before_replay_claim(self):
        tampered = dict(self.payload, evidence_sha256="b" * 64)
        with self.assertRaisesRegex(ScannerReceiptError, "exact evidence"):
            self.verify(tampered, self.sign(tampered))
        self.assertFalse(self.replays.seen)

    def test_signature_covers_result_and_all_bindings(self):
        tampered = dict(self.payload, result="INFECTED")
        with self.assertRaisesRegex(ScannerReceiptError, "signature verification"):
            self.verify(tampered, self.sign(self.payload))

    def test_unknown_key_and_unsigned_claim_fail_closed(self):
        unknown = dict(self.payload, key_id="unknown")
        with self.assertRaises(ScannerReceiptError):
            self.verify(unknown, self.sign(unknown))
        with self.assertRaises(ScannerReceiptError):
            self.verify(signature="not-a-signature")

    def test_stale_future_and_timezone_free_receipts_are_rejected(self):
        for issued in (
            (self.now - timedelta(minutes=6)).isoformat(),
            (self.now + timedelta(seconds=31)).isoformat(),
            "2026-08-20T12:00:00",
        ):
            payload = dict(self.payload, issued_at=issued)
            with self.assertRaises(ScannerReceiptError):
                self.verify(payload, self.sign(payload))

    def test_extra_fields_and_weak_keys_are_rejected(self):
        with self.assertRaisesRegex(ScannerReceiptError, "invalid contract"):
            self.verify(dict(self.payload, trusted=True), self.sign())
        weak = hmac_sha256_verifier(lambda _kid: b"weak")
        with self.assertRaisesRegex(ScannerReceiptError, "verification failed"):
            verify_scanner_receipt(
                self.payload, self.sign(), verifier=weak, replay_authority=self.replays,
                expected_tenant_id="tenant-a", expected_candidate_id="candidate-1",
                expected_evidence_id="evidence-1", expected_evidence_sha256="a" * 64, now=self.now,
            )


if __name__ == "__main__":
    unittest.main()
