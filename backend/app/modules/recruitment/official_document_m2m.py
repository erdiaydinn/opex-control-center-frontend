"""Authorized M2M official-document verification transport; no public-portal automation."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from typing import Callable, Mapping, Any
from urllib.parse import urlparse
import httpx

class OfficialM2MError(RuntimeError): pass
ResponseVerifier=Callable[[bytes,Mapping[str,str]],bool]
ResponseMapper=Callable[[dict[str,Any]],dict[str,Any]]

@dataclass(frozen=True)
class OfficialM2MConfig:
    endpoint:str; token_url:str; client_id:str; client_secret:str; mtls_cert:str; mtls_key:str; allowed_hosts:tuple[str,...]; contract_id:str; timeout_seconds:float=15.0
    def validate(self)->None:
        if not all((self.endpoint,self.token_url,self.client_id,self.client_secret,self.mtls_cert,self.mtls_key,self.contract_id)): raise OfficialM2MError("Yetkili e-Devlet M2M sözleşme/credential yapılandırması eksik.")
        allowed={h.strip().lower() for h in self.allowed_hosts if h.strip()}
        if not allowed: raise OfficialM2MError("Yetkili M2M host allow-list zorunludur.")
        for value in (self.endpoint,self.token_url):
            parsed=urlparse(value); host=(parsed.hostname or "").lower()
            if parsed.scheme!="https" or host not in allowed: raise OfficialM2MError("M2M endpoint yalnız allow-list içindeki HTTPS hostta olabilir.")
            if host in {"turkiye.gov.tr","www.turkiye.gov.tr"}: raise OfficialM2MError("Kamuya açık e-Devlet insan arayüzü M2M endpoint olarak kullanılamaz.")

class AuthorizedOfficialM2MAdapter:
    def __init__(self,config:OfficialM2MConfig,*,response_verifier:ResponseVerifier,response_mapper:ResponseMapper,client:httpx.Client|None=None)->None:
        config.validate(); self.config=config; self.response_verifier=response_verifier; self.response_mapper=response_mapper
        self.client=client or httpx.Client(cert=(config.mtls_cert,config.mtls_key),verify=True,http2=True,timeout=config.timeout_seconds)
    def _access_token(self)->str:
        response=self.client.post(self.config.token_url,data={"grant_type":"client_credentials"},auth=(self.config.client_id,self.config.client_secret),headers={"Accept":"application/json"}); response.raise_for_status(); payload=response.json(); token=str(payload.get("access_token") or "")
        if not token: raise OfficialM2MError("Yetkili M2M OAuth access_token alınamadı.")
        if str(payload.get("token_type","Bearer")).lower()!="bearer": raise OfficialM2MError("Yetkili M2M OAuth token_type desteklenmiyor.")
        return token
    def verify_document(self,*,evidence_sha256:str,document_type:str,barcode:str,subject_reference:str,correlation_id:str)->dict[str,Any]:
        token=self._access_token(); request_payload={"contract_id":self.config.contract_id,"correlation_id":correlation_id,"document":{"type":document_type,"barcode":barcode,"evidence_sha256":evidence_sha256,"subject_reference":subject_reference}}
        response=self.client.post(self.config.endpoint,json=request_payload,headers={"Authorization":f"Bearer {token}","Accept":"application/json","X-Correlation-ID":correlation_id,"X-Integration-Contract-ID":self.config.contract_id}); response.raise_for_status(); raw=response.content; headers={k.lower():v for k,v in response.headers.items()}
        if not self.response_verifier(raw,headers): raise OfficialM2MError("Yetkili M2M sağlayıcı yanıt imzası doğrulanmadı.")
        try: mapped=self.response_mapper(response.json())
        except Exception as error: raise OfficialM2MError("Yetkili M2M yanıt sözleşmesi eşleşmedi.") from error
        required={"official_receipt_id","result","subject_match","document_type","evidence_sha256"}
        if not required.issubset(mapped): raise OfficialM2MError("Yetkili M2M yanıtı zorunlu doğrulama alanlarını içermiyor.")
        if mapped["document_type"]!=document_type or mapped["evidence_sha256"]!=evidence_sha256: raise OfficialM2MError("Yetkili M2M yanıtı exact evidence/document binding kontrolünü geçemedi.")
        if mapped["result"] not in {"VERIFIED","NOT_VERIFIED","ERROR"} or mapped["subject_match"] not in {"MATCH","MISMATCH","UNKNOWN"}: raise OfficialM2MError("Yetkili M2M doğrulama sonucu desteklenmiyor.")
        return {**mapped,"official_response_sha256":sha256(raw).hexdigest(),"provider_signature_verified":True,"verification_method":"AUTHORIZED_OFFICIAL_API","truth_boundary":"AUTHORIZED_MACHINE_TO_MACHINE"}
