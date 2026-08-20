from __future__ import annotations

from hashlib import sha256
import hmac
import unittest

from app.modules.recruitment.scanner_key_authority import (
    AwsKmsHmacKeyAuthority,
    ScannerKeyAuthorityError,
)


class FakeKms:
    def __init__(self) -> None:
        self.secrets = {
            "arn:old": b"old-kms-hmac-material-for-test-only",
            "arn:active": b"active-kms-hmac-material-for-test",
        }
        self.states = {"arn:old": "Enabled", "arn:active": "Enabled"}

    def describe_key(self, **kwargs):
        key_id = kwargs["KeyId"]
        return {
            "KeyMetadata": {
                "Arn": key_id,
                "KeyState": self.states[key_id],
                "KeyUsage": "GENERATE_VERIFY_MAC",
                "KeySpec": "HMAC_256",
            }
        }

    def _mac(self, key_id: str, message: bytes) -> bytes:
        return hmac.new(self.secrets[key_id], message, sha256).digest()

    def generate_mac(self, **kwargs):
        return {"Mac": self._mac(kwargs["KeyId"], kwargs["Message"])}

    def verify_mac(self, **kwargs):
        expected = self._mac(kwargs["KeyId"], kwargs["Message"])
        return {"MacValid": hmac.compare_digest(expected, kwargs["Mac"])}


class ScannerKeyAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kms = FakeKms()

    def test_live_kms_preflight_checks_every_rotation_key(self):
        authority = AwsKmsHmacKeyAuthority(
            active_key_id="2026-08",
            verify_keys={"2026-07": "arn:old", "2026-08": "arn:active"},
            kms_client=self.kms,
        )
        result = authority.preflight()
        self.assertEqual(result["active_kid"], "2026-08")
        self.assertEqual(result["verified_key_count"], 2)
        self.kms.states["arn:old"] = "Disabled"
        with self.assertRaisesRegex(ScannerKeyAuthorityError, "Enabled durumda değil"):
            authority.preflight()

    def test_rotation_accepts_prior_receipt_but_only_active_key_signs(self):
        before_rotation = AwsKmsHmacKeyAuthority(
            active_key_id="2026-07",
            verify_keys={"2026-07": "arn:old"},
            kms_client=self.kms,
        )
        old_signature = before_rotation.sign("2026-07", b"receipt")

        after_rotation = AwsKmsHmacKeyAuthority(
            active_key_id="2026-08",
            verify_keys={"2026-07": "arn:old", "2026-08": "arn:active"},
            kms_client=self.kms,
        )
        self.assertTrue(after_rotation.verify("2026-07", b"receipt", old_signature))
        new_signature = after_rotation.sign("2026-08", b"receipt")
        self.assertTrue(after_rotation.verify("2026-08", b"receipt", new_signature))
        self.assertFalse(after_rotation.verify("2026-07", b"receipt", new_signature))
        with self.assertRaises(ScannerKeyAuthorityError):
            after_rotation.sign("2026-07", b"receipt")

    def test_retired_and_unknown_keys_fail_closed(self):
        old_authority = AwsKmsHmacKeyAuthority(
            active_key_id="2026-07",
            verify_keys={"2026-07": "arn:old"},
            kms_client=self.kms,
        )
        old_signature = old_authority.sign("2026-07", b"receipt")
        retired = AwsKmsHmacKeyAuthority(
            active_key_id="2026-08",
            verify_keys={"2026-08": "arn:active"},
            kms_client=self.kms,
        )
        self.assertFalse(retired.verify("2026-07", b"receipt", old_signature))
        self.assertFalse(retired.verify("unknown", b"receipt", b"signature"))

    def test_duplicate_kms_mapping_and_unbounded_window_are_rejected(self):
        with self.assertRaises(ScannerKeyAuthorityError):
            AwsKmsHmacKeyAuthority(
                active_key_id="new",
                verify_keys={"old": "arn:active", "new": "arn:active"},
                kms_client=self.kms,
            )
        with self.assertRaises(ScannerKeyAuthorityError):
            AwsKmsHmacKeyAuthority(
                active_key_id="k5",
                verify_keys={f"k{i}": f"arn:{i}" for i in range(1, 6)},
                kms_client=self.kms,
            )


if __name__ == "__main__":
    unittest.main()
