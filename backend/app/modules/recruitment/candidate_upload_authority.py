"""PostgreSQL one-time candidate upload authority with production KMS/S3 evidence storage."""
from __future__ import annotations
from datetime import UTC,datetime,timedelta
from hashlib import sha256
import json,os
from pathlib import Path
import secrets
from uuid import uuid4
from app.modules.workforce import persistence
from .candidate_evidence_storage import EvidenceStorageError,S3KmsEnvelopeEvidenceStore

class CandidateUploadAuthorityError(ValueError): pass
def _invalid(): return CandidateUploadAuthorityError("Aday yükleme yetkisi geçersiz veya süresi dolmuş.")
def _token_digest(raw_token:str)->bytes:
    token=str(raw_token or "").strip()
    if not 32<=len(token)<=256: raise _invalid()
    return sha256(token.encode()).digest()

def issue(request_id:str,candidate_id:str,document_type:str,expires_in_minutes:int,actor:str)->dict:
    if not persistence.ENABLED: raise CandidateUploadAuthorityError("PostgreSQL aday yükleme otoritesi yapılandırılmadı.")
    raw_token=secrets.token_urlsafe(32); digest=_token_digest(raw_token); capability_id=uuid4(); staging_key=f"quarantine/{persistence.tenant_id()}/{capability_id}"; now=datetime.now(UTC); expires_at=now+timedelta(minutes=expires_in_minutes)
    with persistence.connection() as database,database.cursor() as cursor:
        persistence._set_tenant(cursor); tenant_id=persistence.tenant_id(); cursor.execute("SELECT payload,revision FROM recruitment_requests WHERE tenant_id=%s AND id=%s FOR UPDATE",(tenant_id,request_id)); row=cursor.fetchone()
        if row is None: raise CandidateUploadAuthorityError("Aday bulunamadı veya belge kabul eden aşamada değil.")
        record,revision=row; candidate=next((i for i in record.get("candidates",[]) if i.get("id")==candidate_id),None)
        if candidate is None or candidate.get("status") not in {"EVIDENCE_PENDING","REVIEW_PENDING"}: raise CandidateUploadAuthorityError("Aday bulunamadı veya belge kabul eden aşamada değil.")
        cursor.execute("SELECT * FROM recruitment.issue_candidate_upload_capability(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(tenant_id,capability_id,request_id,candidate_id,digest,document_type,staging_key,10*1024*1024,expires_at,actor))
        if cursor.fetchone() is None: raise CandidateUploadAuthorityError("Aday yükleme yetkisi oluşturulamadı.")
        record.setdefault("history",[]).append({"at":now.isoformat(),"action":"CANDIDATE_UPLOAD_CAPABILITY_ISSUED","actor":actor,"candidate_id":candidate_id,"capability_id":str(capability_id),"document_type":document_type}); next_revision=int(revision)+1; record["revision"]=next_revision
        cursor.execute("UPDATE recruitment_requests SET revision=%s,payload=%s::jsonb WHERE tenant_id=%s AND id=%s AND revision=%s",(next_revision,json.dumps(record,ensure_ascii=False,default=str),tenant_id,request_id,revision))
        if cursor.rowcount!=1: raise CandidateUploadAuthorityError("İşe alım kaydı eşzamanlı olarak değiştirildi.")
        persistence._build_audit_record(cursor,"RECRUITMENT_CANDIDATE_UPLOAD_CAPABILITY_ISSUED",actor,{"record_id":request_id,"candidate_id":candidate_id,"capability_id":str(capability_id),"document_type":document_type}); database.commit()
    return {"capability":raw_token,"expires_at":expires_at.isoformat(),"document_type":document_type,"max_uploads":1}

def _persist_aggregate(cursor,*,tenant_id,request_id,candidate_id,capability_id,evidence_id,filename,content_type,content,bound_type,object_key,now,retention_until,storage_manifest):
    evidence_digest=sha256(content).digest(); cursor.execute("SELECT payload,revision FROM recruitment_requests WHERE tenant_id=%s AND id=%s FOR UPDATE",(tenant_id,request_id)); row=cursor.fetchone()
    if row is None: raise _invalid()
    record,revision=row; candidate=next((i for i in record.get("candidates",[]) if i.get("id")==candidate_id),None)
    if candidate is None or candidate.get("status") not in {"EVIDENCE_PENDING","REVIEW_PENDING"}: raise _invalid()
    evidence={"id":str(evidence_id),"original_name":Path(filename).name[:240],"content_type":content_type,"size":len(content),"sha256":evidence_digest.hex(),"stored_name":object_key,"uploaded_at":now.isoformat(),"uploaded_by":f"candidate-capability:{capability_id}","retention_until":retention_until.isoformat(),"document_type":bound_type,"requires_official_verification":bound_type!="OTHER","verification_state":"BARCODE_EXTRACTION_PENDING" if bound_type!="OTHER" else "NOT_REQUIRED","official_verification":None,"content_safety_state":"STATIC_FORMAT_ACCEPTED_AV_PENDING","content_safety_truth_boundary":"NOT_MALWARE_CLEARED",**storage_manifest}
    candidate.setdefault("evidence",[]).append(evidence); candidate["status"]="REVIEW_PENDING"; record.setdefault("history",[]).append({"at":now.isoformat(),"action":"CANDIDATE_EVIDENCE_UPLOADED","actor":evidence["uploaded_by"],"candidate_id":candidate_id,"sha256":evidence_digest.hex(),"capability_id":str(capability_id)}); next_revision=int(revision)+1; record["revision"]=next_revision
    cursor.execute("UPDATE recruitment_requests SET status=%s,revision=%s,payload=%s::jsonb WHERE tenant_id=%s AND id=%s AND revision=%s",(record["status"],next_revision,json.dumps(record,ensure_ascii=False,default=str),tenant_id,request_id,revision))
    if cursor.rowcount!=1: raise CandidateUploadAuthorityError("İşe alım kaydı eşzamanlı olarak değiştirildi.")
    persistence._build_audit_record(cursor,"RECRUITMENT_CANDIDATE_EVIDENCE_UPLOADED",evidence["uploaded_by"],{"record_id":request_id,"candidate_id":candidate_id,"capability_id":str(capability_id),"evidence_id":str(evidence_id),"sha256":evidence_digest.hex(),"size":len(content),"storage_backend":storage_manifest.get("storage_backend")}); return evidence

def _finalize_encrypted(raw_token,document_type,filename,content_type,content,*,retention_days):
    if (persistence.schema_version() or 0)<40: raise CandidateUploadAuthorityError("Şifreli aday kanıt otoritesi V40 migration olmadan açılamaz.")
    token_digest=_token_digest(raw_token); evidence_digest=sha256(content).digest(); evidence_id=uuid4(); now=datetime.now(UTC); retention_until=now+timedelta(days=retention_days); store=S3KmsEnvelopeEvidenceStore.from_environment()
    with persistence.connection() as database,database.cursor() as cursor:
        persistence._set_tenant(cursor); tenant_id=persistence.tenant_id(); cursor.execute("SELECT * FROM recruitment.prepare_candidate_evidence_upload(%s,%s,%s,%s,%s)",(tenant_id,token_digest,document_type,len(content),evidence_digest)); prepared=cursor.fetchone()
        if prepared is None: raise _invalid()
        capability_id,request_id,candidate_id,bound_type,object_key=prepared
        try: manifest=store.put(tenant_id=tenant_id,object_key=str(object_key),plaintext=content,expected_sha256=evidence_digest.hex(),retention_until=retention_until)
        except EvidenceStorageError as error: database.rollback(); raise CandidateUploadAuthorityError(str(error)) from error
        cursor.execute("SELECT * FROM recruitment.finalize_candidate_evidence_upload_v2(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(tenant_id,token_digest,document_type,evidence_id,Path(filename).name[:240],content_type,len(content),evidence_digest,retention_until,manifest["storage_bucket"],manifest["encryption_scheme"],manifest["kms_key_id"],manifest["envelope_version"])); finalized=cursor.fetchone()
        if finalized is None: raise _invalid()
        reid,rcid,rrid,r_candidate,rtype,rkey=finalized
        if reid!=evidence_id or rcid!=capability_id or rrid!=request_id or r_candidate!=candidate_id or rtype!=bound_type or str(rkey)!=str(object_key): raise CandidateUploadAuthorityError("Aday kanıt otoritesi bütünlük kontrolünü geçemedi.")
        evidence=_persist_aggregate(cursor,tenant_id=tenant_id,request_id=request_id,candidate_id=candidate_id,capability_id=capability_id,evidence_id=evidence_id,filename=filename,content_type=content_type,content=content,bound_type=bound_type,object_key=str(object_key),now=now,retention_until=retention_until,storage_manifest=manifest); database.commit(); return evidence

def _finalize_local_development(raw_token,document_type,filename,content_type,content,evidence_dir,*,retention_days):
    if os.getenv("DOCKOS_ENV","development").strip().lower()=="production": raise CandidateUploadAuthorityError("Production aday kanıtı plaintext dosya sistemine yazılamaz.")
    digest=_token_digest(raw_token); evidence_digest=sha256(content).digest(); evidence_id=uuid4(); now=datetime.now(UTC); retention_until=now+timedelta(days=retention_days)
    with persistence.connection() as database,database.cursor() as cursor:
        persistence._set_tenant(cursor); tenant_id=persistence.tenant_id(); cursor.execute("SELECT * FROM recruitment.finalize_candidate_evidence_upload(%s,%s,%s,%s,%s,%s,%s,%s,%s)",(tenant_id,digest,document_type,evidence_id,Path(filename).name[:240],content_type,len(content),evidence_digest,retention_until)); authority=cursor.fetchone()
        if authority is None: raise _invalid()
        _,capability_id,request_id,candidate_id,bound_type,object_key=authority; relative=Path(str(object_key))
        if relative.is_absolute() or ".." in relative.parts or relative.parts[:2]!=("quarantine",tenant_id) or len(relative.parts)!=3: raise CandidateUploadAuthorityError("Aday kanıt nesne otoritesi geçersiz.")
        evidence_dir.mkdir(parents=True,exist_ok=True); path=evidence_dir/relative; path.parent.mkdir(parents=True,exist_ok=True); created=not path.exists(); path.write_bytes(content)
        try: evidence=_persist_aggregate(cursor,tenant_id=tenant_id,request_id=request_id,candidate_id=candidate_id,capability_id=capability_id,evidence_id=evidence_id,filename=filename,content_type=content_type,content=content,bound_type=bound_type,object_key=str(relative),now=now,retention_until=retention_until,storage_manifest={"storage_backend":"LEGACY_LOCAL"}); database.commit(); return evidence
        except Exception:
            if created: path.unlink(missing_ok=True)
            raise

def finalize(raw_token,document_type,filename,content_type,content,evidence_dir,*,retention_days):
    if not persistence.ENABLED: raise CandidateUploadAuthorityError("PostgreSQL aday yükleme otoritesi yapılandırılmadı.")
    mode=os.getenv("RECRUITMENT_EVIDENCE_STORAGE_MODE","disabled").strip().lower(); environment=os.getenv("DOCKOS_ENV","development").strip().lower()
    if mode=="s3-kms-envelope": return _finalize_encrypted(raw_token,document_type,filename,content_type,content,retention_days=retention_days)
    if environment=="production": raise CandidateUploadAuthorityError("Production aday kanıtı KMS/envelope şifreli nesne depolama olmadan kabul edilemez.")
    return _finalize_local_development(raw_token,document_type,filename,content_type,content,evidence_dir,retention_days=retention_days)
