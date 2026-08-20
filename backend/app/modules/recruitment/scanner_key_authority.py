"""AWS KMS-backed HMAC key authority for candidate malware scanner receipts.

Only the active ``kid`` may sign. A bounded verification set may contain prior
KMS HMAC keys during rotation. Raw HMAC key material never enters the process.
"""
from __future__ import annotations

import json
import os
from typing import Any


class ScannerKeyAuthorityError(RuntimeError):
    pass


class AwsKmsHmacKeyAuthority:
    def __init__(
        self,
        *,
        active_key_id: str,
        verify_keys: dict[str, str],
        kms_client: Any = None,
    ) -> None:
        active = str(active_key_id or "").strip()
        normalized = {
            str(kid).strip(): str(kms_key_id).strip()
            for kid, kms_key_id in verify_keys.items()
            if str(kid).strip() and str(kms_key_id).strip()
        }
        if not active or active not in normalized:
            raise ScannerKeyAuthorityError(
                "Aktif scanner KMS key_id doğrulama kümesinde bulunmalıdır."
            )
        if len(normalized) > 4:
            raise ScannerKeyAuthorityError(
                "Scanner KMS rotation doğrulama penceresi en fazla 4 anahtar olabilir."
            )
        if len(set(normalized.values())) != len(normalized):
            raise ScannerKeyAuthorityError(
                "Farklı scanner kid değerleri aynı KMS anahtarına bağlanamaz."
            )
        if kms_client is None:
            import boto3

            kms_client = boto3.client("kms")
        self.active_key_id = active
        self.verify_keys = normalized
        self.kms = kms_client

    @classmethod
    def from_environment(cls) -> "AwsKmsHmacKeyAuthority":
        try:
            mapping = json.loads(os.getenv("RECRUITMENT_SCANNER_KMS_VERIFY_KEYS", "{}"))
        except json.JSONDecodeError as error:
            raise ScannerKeyAuthorityError(
                "Scanner KMS doğrulama anahtar haritası geçersiz."
            ) from error
        if not isinstance(mapping, dict):
            raise ScannerKeyAuthorityError(
                "Scanner KMS doğrulama anahtar haritası nesne olmalıdır."
            )
        return cls(
            active_key_id=os.getenv("RECRUITMENT_SCANNER_ACTIVE_KID", ""),
            verify_keys=mapping,
        )

    def sign(self, key_id: str, message: bytes) -> bytes:
        kid = str(key_id or "").strip()
        if kid != self.active_key_id:
            raise ScannerKeyAuthorityError(
                "Yalnız aktif scanner anahtarı imza üretebilir."
            )
        if not message:
            raise ScannerKeyAuthorityError("Boş scanner receipt imzalanamaz.")
        response = self.kms.generate_mac(
            KeyId=self.verify_keys[kid],
            Message=message,
            MacAlgorithm="HMAC_SHA_256",
        )
        return bytes(response["Mac"])

    def verify(self, key_id: str, message: bytes, signature: bytes) -> bool:
        key_arn = self.verify_keys.get(str(key_id or "").strip())
        if not key_arn or not message or not signature:
            return False
        try:
            response = self.kms.verify_mac(
                KeyId=key_arn,
                Message=message,
                Mac=signature,
                MacAlgorithm="HMAC_SHA_256",
            )
            return bool(response.get("MacValid"))
        except Exception:
            return False
