"""Authorized official-document M2M transport.

This module deliberately has no browser automation and rejects the public
``turkiye.gov.tr`` human UI as an integration endpoint. Production activation
requires an explicitly assigned HTTPS host, OAuth2 client credentials, mTLS,
and a configured provider response-signature profile.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import httpx


class OfficialM2MError(RuntimeError):
    pass


ResponseVerifier = Callable[[bytes, Mapping[str, str]], bool]
ResponseMapper = Callable[[dict[str, Any]], dict[str, Any]]
_INTERNAL_RESULTS = {"VERIFIED", "FAILED", "INCONCLUSIVE"}
_INTERNAL_SUBJECT_MATCH = {"MATCH", "MISMATCH", "NOT_CHECKED"}
_OFFICIAL_DOCUMENT_TYPES = {
    "CRIMINAL_RECORD",
    "RESIDENCE",
    "SGK_SERVICE",
    "MILITARY_STATUS",
    "EDUCATION",
    "CIVIL_REGISTRY",
}
_PUBLIC_HUMAN_PORTAL_HOSTS = {"turkiye.gov.tr", "www.turkiye.gov.tr"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_TOKEN_RESPONSE_BYTES = 64 * 1024
_MAX_OFFICIAL_RESPONSE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class OfficialM2MConfig:
    endpoint: str
    token_url: str
    client_id: str
    client_secret: str
    mtls_cert: str
    mtls_key: str
    allowed_hosts: tuple[str, ...]
    contract_id: str
    timeout_seconds: float = 15.0

    @classmethod
    def from_environment(cls) -> "OfficialM2MConfig":
        hosts = tuple(
            host.strip().lower()
            for host in os.getenv("RECRUITMENT_OFFICIAL_M2M_ALLOWED_HOSTS", "").split(",")
            if host.strip()
        )
        try:
            timeout = float(os.getenv("RECRUITMENT_OFFICIAL_M2M_TIMEOUT_SECONDS", "15"))
        except ValueError as error:
            raise OfficialM2MError("Yetkili M2M timeout yapılandırması geçersiz.") from error
        return cls(
            endpoint=os.getenv("RECRUITMENT_OFFICIAL_M2M_ENDPOINT", ""),
            token_url=os.getenv("RECRUITMENT_OFFICIAL_M2M_TOKEN_URL", ""),
            client_id=os.getenv("RECRUITMENT_OFFICIAL_M2M_CLIENT_ID", ""),
            client_secret=os.getenv("RECRUITMENT_OFFICIAL_M2M_CLIENT_SECRET", ""),
            mtls_cert=os.getenv("RECRUITMENT_OFFICIAL_M2M_MTLS_CERT", ""),
            mtls_key=os.getenv("RECRUITMENT_OFFICIAL_M2M_MTLS_KEY", ""),
            allowed_hosts=hosts,
            contract_id=os.getenv("RECRUITMENT_OFFICIAL_M2M_CONTRACT_ID", ""),
            timeout_seconds=timeout,
        )

    def validate(self) -> None:
        if not all(
            (
                self.endpoint,
                self.token_url,
                self.client_id,
                self.client_secret,
                self.mtls_cert,
                self.mtls_key,
                self.contract_id,
            )
        ):
            raise OfficialM2MError(
                "Yetkili e-Devlet M2M sözleşme/credential yapılandırması eksik."
            )
        if not 1 <= self.timeout_seconds <= 60:
            raise OfficialM2MError("Yetkili M2M timeout 1-60 saniye aralığında olmalıdır.")
        allowed = {host.strip().lower() for host in self.allowed_hosts if host.strip()}
        if not allowed:
            raise OfficialM2MError("Yetkili M2M host allow-list zorunludur.")
        if allowed.intersection(_PUBLIC_HUMAN_PORTAL_HOSTS):
            raise OfficialM2MError(
                "Kamuya açık e-Devlet insan arayüzü M2M allow-list içinde olamaz."
            )
        for value in (self.endpoint, self.token_url):
            parsed = urlparse(value)
            host = (parsed.hostname or "").lower()
            if (
                parsed.scheme != "https"
                or host not in allowed
                or parsed.username is not None
                or parsed.password is not None
                or parsed.fragment
            ):
                raise OfficialM2MError(
                    "M2M endpoint yalnız allow-list içindeki sade HTTPS hostta olabilir."
                )
            if host in _PUBLIC_HUMAN_PORTAL_HOSTS:
                raise OfficialM2MError(
                    "Kamuya açık e-Devlet insan arayüzü M2M endpoint olarak kullanılamaz."
                )


def _decode_signature(value: str) -> bytes:
    raw = str(value or "").strip()
    if not raw or len(raw) > 8192:
        raise OfficialM2MError("Yetkili M2M sağlayıcı imzası eksik veya geçersiz.")
    try:
        return base64.b64decode(raw, validate=True)
    except ValueError:
        try:
            return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        except Exception as error:
            raise OfficialM2MError("Yetkili M2M sağlayıcı imzası kodlaması geçersiz.") from error


def _json_content_type(headers: Mapping[str, str]) -> bool:
    value = str(headers.get("content-type") or headers.get("Content-Type") or "")
    media_type = value.split(";", 1)[0].strip().lower()
    return media_type == "application/json" or media_type.endswith("+json")


def _decode_json_object(raw: bytes, *, label: str, maximum_bytes: int) -> dict[str, Any]:
    if not raw or len(raw) > maximum_bytes:
        raise OfficialM2MError(f"{label} yanıt boyutu sözleşme sınırını aşıyor.")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise OfficialM2MError(f"{label} yanıtında duplicate JSON anahtarı var.")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except OfficialM2MError:
        raise
    except Exception as error:
        raise OfficialM2MError(f"{label} yanıtı geçerli UTF-8 JSON değil.") from error
    if not isinstance(value, dict):
        raise OfficialM2MError(f"{label} yanıtının kökü JSON object olmalıdır.")
    return value


def _safe_text(value: str, *, label: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum:
        raise OfficialM2MError(f"Yetkili M2M {label} geçersiz.")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise OfficialM2MError(f"Yetkili M2M {label} kontrol karakteri içeremez.")
    return normalized


def build_detached_signature_verifier_from_environment() -> ResponseVerifier:
    """Build a contract-selected detached signature verifier over exact response bytes.

    Supported profiles are intentionally explicit. If an institutional contract
    uses a different signature container (for example JWS/CMS), activation stays
    fail-closed until that profile is implemented and reviewed.
    """
    profile = os.getenv("RECRUITMENT_OFFICIAL_M2M_SIGNATURE_PROFILE", "").strip().upper()
    public_key_file = os.getenv("RECRUITMENT_OFFICIAL_M2M_PROVIDER_PUBLIC_KEY_FILE", "").strip()
    header = os.getenv(
        "RECRUITMENT_OFFICIAL_M2M_SIGNATURE_HEADER", "X-Provider-Signature"
    ).strip().lower()
    if profile not in {"RSA_PSS_SHA256", "RSA_PKCS1V15_SHA256", "ECDSA_SHA256"}:
        raise OfficialM2MError(
            "Yetkili M2M response-signature profili yapılandırılmadı veya desteklenmiyor."
        )
    if not public_key_file or not header:
        raise OfficialM2MError("Yetkili M2M sağlayıcı public-key/signature-header eksik.")
    path = Path(public_key_file)
    if not path.is_file():
        raise OfficialM2MError("Yetkili M2M sağlayıcı public key dosyası bulunamadı.")

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

        public_key = serialization.load_pem_public_key(path.read_bytes())
    except Exception as error:
        raise OfficialM2MError("Yetkili M2M sağlayıcı public key okunamadı.") from error

    if profile.startswith("RSA_") and not isinstance(public_key, rsa.RSAPublicKey):
        raise OfficialM2MError("M2M signature profili ile provider public key türü eşleşmiyor.")
    if profile == "ECDSA_SHA256" and not isinstance(public_key, ec.EllipticCurvePublicKey):
        raise OfficialM2MError("M2M signature profili ile provider public key türü eşleşmiyor.")

    def verify(raw: bytes, headers: Mapping[str, str]) -> bool:
        try:
            signature = _decode_signature(headers.get(header, ""))
            if profile == "RSA_PSS_SHA256":
                public_key.verify(
                    signature,
                    raw,
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.DIGEST_LENGTH,
                    ),
                    hashes.SHA256(),
                )
            elif profile == "RSA_PKCS1V15_SHA256":
                public_key.verify(signature, raw, padding.PKCS1v15(), hashes.SHA256())
            else:
                public_key.verify(signature, raw, ec.ECDSA(hashes.SHA256()))
            return True
        except Exception:
            return False

    return verify


def canonical_response_mapper(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept only the reviewed EAY canonical provider gateway response shape."""
    profile = os.getenv("RECRUITMENT_OFFICIAL_M2M_RESPONSE_PROFILE", "").strip().upper()
    if profile != "EAY_CANONICAL_V1":
        raise OfficialM2MError(
            "Yetkili M2M response mapping profili yapılandırılmadı."
        )
    return dict(payload)


class AuthorizedOfficialM2MAdapter:
    def __init__(
        self,
        config: OfficialM2MConfig,
        *,
        response_verifier: ResponseVerifier,
        response_mapper: ResponseMapper,
        client: httpx.Client | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.response_verifier = response_verifier
        self.response_mapper = response_mapper
        self.client = client or httpx.Client(
            cert=(config.mtls_cert, config.mtls_key),
            verify=True,
            http2=True,
            timeout=config.timeout_seconds,
            follow_redirects=False,
        )

    @classmethod
    def from_environment(cls) -> "AuthorizedOfficialM2MAdapter":
        return cls(
            OfficialM2MConfig.from_environment(),
            response_verifier=build_detached_signature_verifier_from_environment(),
            response_mapper=canonical_response_mapper,
        )

    def _access_token(self) -> str:
        response = self.client.post(
            self.config.token_url,
            data={"grant_type": "client_credentials"},
            auth=(self.config.client_id, self.config.client_secret),
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        headers = {key.lower(): value for key, value in response.headers.items()}
        if not _json_content_type(headers):
            raise OfficialM2MError("Yetkili M2M OAuth yanıtı JSON content-type taşımıyor.")
        payload = _decode_json_object(
            response.content,
            label="OAuth",
            maximum_bytes=_MAX_TOKEN_RESPONSE_BYTES,
        )
        token = _safe_text(
            str(payload.get("access_token") or ""),
            label="OAuth access_token",
            maximum=16384,
        )
        if str(payload.get("token_type", "")).lower() != "bearer":
            raise OfficialM2MError("Yetkili M2M OAuth token_type desteklenmiyor.")
        return token

    def verify_document(
        self,
        *,
        evidence_sha256: str,
        document_type: str,
        barcode: str,
        subject_reference: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        evidence_digest = str(evidence_sha256 or "").strip().lower()
        if not _SHA256.fullmatch(evidence_digest):
            raise OfficialM2MError("Yetkili M2M evidence SHA-256 geçersiz.")
        normalized_document_type = str(document_type or "").strip().upper()
        if normalized_document_type not in _OFFICIAL_DOCUMENT_TYPES:
            raise OfficialM2MError("Yetkili M2M belge türü desteklenmiyor.")
        correlation = _safe_text(correlation_id, label="correlation_id", maximum=128)
        barcode_value = _safe_text(barcode, label="barkod alanı", maximum=512)
        subject = _safe_text(subject_reference, label="kişi referansı", maximum=512)

        token = self._access_token()
        request_payload = {
            "contract_id": self.config.contract_id,
            "correlation_id": correlation,
            "document": {
                "type": normalized_document_type,
                "barcode": barcode_value,
                "evidence_sha256": evidence_digest,
                "subject_reference": subject,
            },
        }
        response = self.client.post(
            self.config.endpoint,
            json=request_payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "X-Correlation-ID": correlation,
                "X-Integration-Contract-ID": self.config.contract_id,
            },
        )
        response.raise_for_status()
        raw = response.content
        if not raw or len(raw) > _MAX_OFFICIAL_RESPONSE_BYTES:
            raise OfficialM2MError("Yetkili M2M sağlayıcı yanıt boyutu sözleşme sınırını aşıyor.")
        headers = {key.lower(): value for key, value in response.headers.items()}
        if not _json_content_type(headers):
            raise OfficialM2MError("Yetkili M2M sağlayıcı yanıtı JSON content-type taşımıyor.")
        if not self.response_verifier(raw, headers):
            raise OfficialM2MError("Yetkili M2M sağlayıcı yanıt imzası doğrulanmadı.")
        parsed = _decode_json_object(
            raw,
            label="Yetkili M2M sağlayıcı",
            maximum_bytes=_MAX_OFFICIAL_RESPONSE_BYTES,
        )
        try:
            mapped = self.response_mapper(parsed)
        except OfficialM2MError:
            raise
        except Exception as error:
            raise OfficialM2MError("Yetkili M2M yanıt sözleşmesi eşleşmedi.") from error
        if not isinstance(mapped, dict):
            raise OfficialM2MError("Yetkili M2M response mapper JSON object üretmelidir.")

        required = {
            "official_receipt_id",
            "result",
            "subject_match",
            "document_type",
            "evidence_sha256",
        }
        if not required.issubset(mapped):
            raise OfficialM2MError(
                "Yetkili M2M yanıtı zorunlu doğrulama alanlarını içermiyor."
            )
        if (
            mapped["document_type"] != normalized_document_type
            or mapped["evidence_sha256"] != evidence_digest
        ):
            raise OfficialM2MError(
                "Yetkili M2M yanıtı exact evidence/document binding kontrolünü geçemedi."
            )
        if (
            mapped["result"] not in _INTERNAL_RESULTS
            or mapped["subject_match"] not in _INTERNAL_SUBJECT_MATCH
        ):
            raise OfficialM2MError("Yetkili M2M doğrulama sonucu desteklenmiyor.")
        receipt_id = _safe_text(
            str(mapped["official_receipt_id"] or ""),
            label="official receipt kimliği",
            maximum=240,
        )
        issued_at = mapped.get("issued_at")
        if issued_at is not None:
            if not isinstance(issued_at, str) or len(issued_at) > 10:
                raise OfficialM2MError("Yetkili M2M issued_at alanı geçersiz.")
            try:
                date.fromisoformat(issued_at)
            except ValueError as error:
                raise OfficialM2MError("Yetkili M2M issued_at alanı geçersiz.") from error

        return {
            **mapped,
            "official_receipt_id": receipt_id,
            "official_response_sha256": sha256(raw).hexdigest(),
            "provider_signature_verified": True,
            "verification_method": "AUTHORIZED_OFFICIAL_API",
            "truth_boundary": "AUTHORIZED_MACHINE_TO_MACHINE",
        }
