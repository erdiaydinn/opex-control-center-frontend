from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import unittest

from app.modules.recruitment.candidate_evidence_storage import (
    EvidenceStorageError,
    S3KmsEnvelopeEvidenceStore,
)


class FakeKms:
    def __init__(self):
        self.key = b"k" * 32
        self.context = None

    def describe_key(self, **_kwargs):
        return {
            "KeyMetadata": {
                "KeyState": "Enabled",
                "KeyUsage": "ENCRYPT_DECRYPT",
                "KeySpec": "SYMMETRIC_DEFAULT",
            }
        }

    def generate_data_key(self, **kwargs):
        self.context = kwargs["EncryptionContext"]
        return {"Plaintext": self.key, "CiphertextBlob": b"encrypted-key"}

    def decrypt(self, **kwargs):
        if (
            kwargs["EncryptionContext"] != self.context
            or kwargs["CiphertextBlob"] != b"encrypted-key"
        ):
            raise ValueError("mismatch")
        return {"Plaintext": self.key}


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.versions = {}
        self.deleted_versions = []

    def get_bucket_versioning(self, **_kwargs):
        return {"Status": "Enabled"}

    def get_object_lock_configuration(self, **_kwargs):
        return {"ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}}

    def put_object(self, **kwargs):
        key = (kwargs["Bucket"], kwargs["Key"])
        if key in self.objects:
            raise RuntimeError("PreconditionFailed")
        self.objects[key] = bytes(kwargs["Body"])
        self.versions[key] = ["version-1"]
        return {"VersionId": "version-1"}

    def get_object(self, *, Bucket, Key, VersionId=None):
        key = (Bucket, Key)
        if VersionId is not None and VersionId not in self.versions.get(key, []):
            raise KeyError(VersionId)
        return {"Body": io.BytesIO(self.objects[key])}

    def list_object_versions(self, *, Bucket, Prefix):
        key = (Bucket, Prefix)
        return {
            "IsTruncated": False,
            "Versions": [
                {"Key": Prefix, "VersionId": version_id}
                for version_id in self.versions.get(key, [])
            ],
        }

    def delete_object(self, *, Bucket, Key, VersionId):
        key = (Bucket, Key)
        if VersionId not in self.versions.get(key, []):
            raise KeyError(VersionId)
        self.deleted_versions.append((Bucket, Key, VersionId))
        self.versions[key].remove(VersionId)
        if not self.versions[key]:
            self.versions.pop(key, None)
            self.objects.pop(key, None)


class CandidateEvidenceStorageTests(unittest.TestCase):
    def setUp(self):
        self.kms = FakeKms()
        self.s3 = FakeS3()
        self.store = S3KmsEnvelopeEvidenceStore(
            bucket="bucket",
            kms_key_id="arn:test",
            kms_client=self.kms,
            s3_client=self.s3,
        )
        self.content = b"%PDF-1.7\nevidence"
        self.digest = sha256(self.content).hexdigest()
        self.key = "quarantine/eay-ci/11111111-1111-1111-1111-111111111111"

    def put(self, retention_until: datetime | None = None, *, content: bytes | None = None):
        value = self.content if content is None else content
        return self.store.put(
            tenant_id="eay-ci",
            object_key=self.key,
            plaintext=value,
            expected_sha256=sha256(value).hexdigest(),
            retention_until=retention_until or datetime.now(UTC) + timedelta(days=1),
        )

    def test_live_authority_preflight_contract(self):
        result = self.store.preflight()
        self.assertEqual(result["kms_key_state"], "Enabled")
        self.assertEqual(result["kms_key_usage"], "ENCRYPT_DECRYPT")
        self.assertEqual(result["s3_versioning"], "Enabled")
        self.assertEqual(result["s3_object_lock"], "Enabled")

    def test_round_trip_ciphertext(self):
        self.put()
        self.assertNotIn(self.content, self.s3.objects[("bucket", self.key)])
        self.assertEqual(
            self.store.get(
                tenant_id="eay-ci",
                object_key=self.key,
                expected_sha256=self.digest,
            ),
            self.content,
        )

    def test_duplicate_same_bytes_is_retry_safe_but_different_bytes_fail(self):
        retention_until = datetime.now(UTC) + timedelta(days=1)
        first = self.put(retention_until)
        second = self.put(retention_until)
        self.assertEqual(first["object_key"], second["object_key"])
        with self.assertRaises(EvidenceStorageError):
            self.put(retention_until, content=b"%PDF-1.7\ndifferent-evidence")

    def test_digest_mismatch_fails(self):
        self.put()
        with self.assertRaises(EvidenceStorageError):
            self.store.get(
                tenant_id="eay-ci",
                object_key=self.key,
                expected_sha256="0" * 64,
            )

    def test_cross_tenant_key_rejected(self):
        with self.assertRaises(EvidenceStorageError):
            self.store.put(
                tenant_id="other",
                object_key=self.key,
                plaintext=self.content,
                expected_sha256=self.digest,
                retention_until=datetime.now(UTC) + timedelta(days=1),
            )

    def test_retention_delete_is_blocked_early_then_deletes_exact_version_and_retries(self):
        retention_until = datetime.now(UTC) + timedelta(hours=1)
        self.put(retention_until)
        with self.assertRaises(EvidenceStorageError):
            self.store.delete_after_retention(
                tenant_id="eay-ci",
                object_key=self.key,
                expected_sha256=self.digest,
                retention_until=retention_until,
                now=retention_until - timedelta(seconds=1),
            )
        self.assertIn(("bucket", self.key), self.s3.objects)

        self.store.delete_after_retention(
            tenant_id="eay-ci",
            object_key=self.key,
            expected_sha256=self.digest,
            retention_until=retention_until,
            now=retention_until + timedelta(seconds=1),
        )
        self.assertEqual(
            self.s3.deleted_versions,
            [("bucket", self.key, "version-1")],
        )
        self.assertNotIn(("bucket", self.key), self.s3.objects)
        self.store.delete_after_retention(
            tenant_id="eay-ci",
            object_key=self.key,
            expected_sha256=self.digest,
            retention_until=retention_until,
            now=retention_until + timedelta(seconds=2),
        )

    def test_unexpected_multiple_object_versions_fail_closed(self):
        retention_until = datetime.now(UTC) + timedelta(hours=1)
        self.put(retention_until)
        self.s3.versions[("bucket", self.key)] = ["version-1", "version-2"]
        with self.assertRaisesRegex(EvidenceStorageError, "birden fazla S3 versiyonu"):
            self.store.delete_after_retention(
                tenant_id="eay-ci",
                object_key=self.key,
                expected_sha256=self.digest,
                retention_until=retention_until,
                now=retention_until + timedelta(seconds=1),
            )
        self.assertIn(("bucket", self.key), self.s3.objects)

    def test_tampered_object_is_not_silently_deleted(self):
        retention_until = datetime.now(UTC) + timedelta(hours=1)
        self.put(retention_until)
        self.s3.objects[("bucket", self.key)] = b"tampered-envelope"
        with self.assertRaises(EvidenceStorageError):
            self.store.delete_after_retention(
                tenant_id="eay-ci",
                object_key=self.key,
                expected_sha256=self.digest,
                retention_until=retention_until,
                now=retention_until + timedelta(seconds=1),
            )
        self.assertIn(("bucket", self.key), self.s3.objects)


if __name__ == "__main__":
    unittest.main()
