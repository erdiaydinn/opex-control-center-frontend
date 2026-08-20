"""Encrypted immutable object storage for candidate evidence.

Production evidence is envelope encrypted with an AWS KMS data key and AES-256-GCM.
The KMS encryption context is also used as AES-GCM AAD, binding ciphertext to the
tenant, opaque object key and exact plaintext digest. No plaintext data key is
persisted.
"""
from __future__ import annotations

import base64
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EvidenceStorageError(RuntimeError):
    pass


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def _object_key(tenant_id: str, object_key: str) -> str:
    key = str(object_key or "").strip()
    expected = f"quarantine/{tenant_id}/"
    if not key.startswith(expected) or ".." in key.split("/") or key.count("/") != 2:
        raise EvidenceStorageError("Aday kanıt nesne anahtarı geçersiz.")
    return key


def _context(tenant_id: str, object_key: str, digest_hex: str) -> dict[str, str]:
    return {"purpose":"eay-recruitment-candidate-evidence-v1","tenant":tenant_id,"object":object_key,"sha256":digest_hex}


def _aad(context: dict[str, str]) -> bytes:
    return json.dumps(context, sort_keys=True, separators=(",", ":")).encode("utf-8")


class S3KmsEnvelopeEvidenceStore:
    def __init__(self, *, bucket: str, kms_key_id: str, kms_client: Any=None, s3_client: Any=None, object_lock_mode: str="GOVERNANCE") -> None:
        if not bucket.strip() or not kms_key_id.strip():
            raise EvidenceStorageError("KMS/S3 evidence storage yapılandırması eksik.")
        mode=object_lock_mode.strip().upper()
        if mode not in {"GOVERNANCE","COMPLIANCE"}:
            raise EvidenceStorageError("S3 Object Lock modu GOVERNANCE veya COMPLIANCE olmalıdır.")
        if kms_client is None or s3_client is None:
            import boto3
            kms_client=kms_client or boto3.client("kms")
            s3_client=s3_client or boto3.client("s3")
        self.bucket=bucket.strip(); self.kms_key_id=kms_key_id.strip(); self.kms=kms_client; self.s3=s3_client; self.object_lock_mode=mode

    @classmethod
    def from_environment(cls) -> "S3KmsEnvelopeEvidenceStore":
        if os.getenv("RECRUITMENT_EVIDENCE_STORAGE_MODE","disabled").strip().lower() != "s3-kms-envelope":
            raise EvidenceStorageError("Production evidence storage s3-kms-envelope olarak etkin değil.")
        return cls(bucket=os.getenv("RECRUITMENT_EVIDENCE_BUCKET",""),kms_key_id=os.getenv("RECRUITMENT_EVIDENCE_KMS_KEY_ID",""),object_lock_mode=os.getenv("RECRUITMENT_EVIDENCE_OBJECT_LOCK_MODE","GOVERNANCE"))

    def put(self, *, tenant_id: str, object_key: str, plaintext: bytes, expected_sha256: str, retention_until: datetime) -> dict[str,str|int]:
        key=_object_key(tenant_id,object_key); digest_hex=sha256(plaintext).hexdigest()
        if digest_hex != expected_sha256.lower(): raise EvidenceStorageError("Aday kanıt özeti depolama sınırında değişti.")
        if retention_until.astimezone(UTC) <= datetime.now(UTC): raise EvidenceStorageError("Aday kanıt saklama süresi geçersiz.")
        context=_context(tenant_id,key,digest_hex)
        generated=self.kms.generate_data_key(KeyId=self.kms_key_id,KeySpec="AES_256",EncryptionContext=context)
        data_key=bytearray(generated["Plaintext"])
        try:
            nonce=os.urandom(12); ciphertext=AESGCM(bytes(data_key)).encrypt(nonce,plaintext,_aad(context))
        finally:
            for index in range(len(data_key)): data_key[index]=0
        envelope={"version":1,"algorithm":"AES-256-GCM","kms_key_id":self.kms_key_id,"encrypted_data_key":_b64(generated["CiphertextBlob"]),"nonce":_b64(nonce),"ciphertext":_b64(ciphertext),"plaintext_sha256":digest_hex}
        body=json.dumps(envelope,sort_keys=True,separators=(",",":")).encode("utf-8")
        try:
            self.s3.put_object(Bucket=self.bucket,Key=key,Body=body,ContentType="application/vnd.eay.encrypted-evidence+json",Metadata={"envelope-version":"1","plaintext-sha256":digest_hex,"kms-key-id-sha256":sha256(self.kms_key_id.encode()).hexdigest()},ServerSideEncryption="aws:kms",SSEKMSKeyId=self.kms_key_id,BucketKeyEnabled=True,ObjectLockMode=self.object_lock_mode,ObjectLockRetainUntilDate=retention_until.astimezone(UTC),IfNoneMatch="*")
        except Exception as error:
            try: existing=self.get(tenant_id=tenant_id,object_key=key,expected_sha256=digest_hex)
            except Exception: raise EvidenceStorageError("Şifreli aday kanıt nesnesi yazılamadı.") from error
            if existing != plaintext: raise EvidenceStorageError("Mevcut aday kanıt nesnesi exact-byte eşleşmiyor.") from error
        return {"storage_backend":"S3_KMS_ENVELOPE","storage_bucket":self.bucket,"object_key":key,"encryption_scheme":"AES-256-GCM+AWS-KMS-DATA-KEY","kms_key_id":self.kms_key_id,"envelope_version":1}

    def get(self, *, tenant_id: str, object_key: str, expected_sha256: str) -> bytes:
        key=_object_key(tenant_id,object_key); context=_context(tenant_id,key,expected_sha256.lower())
        try:
            raw=self.s3.get_object(Bucket=self.bucket,Key=key)["Body"].read(); envelope=json.loads(raw)
            if envelope.get("version")!=1 or envelope.get("algorithm")!="AES-256-GCM" or envelope.get("plaintext_sha256")!=expected_sha256.lower() or envelope.get("kms_key_id")!=self.kms_key_id: raise EvidenceStorageError("Şifreli aday kanıt zarfı bütünlük kontrolünü geçemedi.")
            decrypted=self.kms.decrypt(CiphertextBlob=_unb64(envelope["encrypted_data_key"]),KeyId=self.kms_key_id,EncryptionContext=context); data_key=bytearray(decrypted["Plaintext"])
            try: plaintext=AESGCM(bytes(data_key)).decrypt(_unb64(envelope["nonce"]),_unb64(envelope["ciphertext"]),_aad(context))
            finally:
                for index in range(len(data_key)): data_key[index]=0
        except EvidenceStorageError: raise
        except Exception as error: raise EvidenceStorageError("Şifreli aday kanıt nesnesi çözülemedi.") from error
        if sha256(plaintext).hexdigest()!=expected_sha256.lower(): raise EvidenceStorageError("Çözülen aday kanıt özeti eşleşmiyor.")
        return plaintext
