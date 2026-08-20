"""Real PostgreSQL acceptance for recruitment production authorities."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import os
from pathlib import Path
from urllib.parse import quote,urlsplit,urlunsplit
from uuid import uuid4
import psycopg
ADMIN_URL=os.environ['RECRUITMENT_AUTHORITY_ADMIN_URL']; TENANT=os.getenv('WORKFORCE_TENANT_ID','eay-ci')
ROLE_PASSWORDS={'eay_candidate_upload_runtime':'candidate_upload_ci','eay_recruitment_runtime':'recruitment_ci','eay_candidate_scanner_runtime':'candidate_scanner_ci','eay_rls_probe':'rls_probe_ci'}
BACKEND=Path(__file__).resolve().parents[1]; M23=BACKEND/'migrations'/'023_recruitment_candidate_upload_authority.sql'; M24=BACKEND/'migrations'/'024_recruitment_production_authority.sql'
def role_url(role):
 p=urlsplit(ADMIN_URL); host=p.hostname or 'localhost'; host=f'{host}:{p.port}' if p.port else host; return urlunsplit((p.scheme,f'{quote(role)}:{quote(ROLE_PASSWORDS[role])}@{host}',p.path,p.query,p.fragment))
def execute_script(db,path):
 with db.cursor() as c: c.execute(path.read_text(encoding='utf-8'))
 db.commit()
def bootstrap():
 with psycopg.connect(ADMIN_URL,autocommit=False) as db:
  with db.cursor() as c:
   for role,password in ROLE_PASSWORDS.items(): c.execute(f"DO $do$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN CREATE ROLE {role} LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF; END $do$;")
   c.execute("INSERT INTO workforce_tenant_bindings(role_name,tenant_id) VALUES ('eay_candidate_upload_runtime',%s),('eay_recruitment_runtime',%s),('eay_candidate_scanner_runtime',%s),('eay_rls_probe',%s) ON CONFLICT(role_name) DO UPDATE SET tenant_id=EXCLUDED.tenant_id",(TENANT,TENANT,TENANT,TENANT)); c.execute('GRANT CONNECT ON DATABASE workforce_ci TO eay_candidate_upload_runtime,eay_recruitment_runtime,eay_candidate_scanner_runtime,eay_rls_probe')
  db.commit(); execute_script(db,M23); execute_script(db,M24)
  with db.cursor() as c: c.execute('GRANT USAGE ON SCHEMA recruitment TO eay_rls_probe'); c.execute('GRANT SELECT ON recruitment.candidate_upload_capabilities,recruitment.candidate_evidence_objects,recruitment.candidate_evidence_scan_receipts TO eay_rls_probe')
  db.commit()
def seed(tenant,token):
 cap=uuid4(); key=f'quarantine/{tenant}/{cap}'
 with psycopg.connect(ADMIN_URL,autocommit=False) as db,db.cursor() as c: c.execute("INSERT INTO recruitment.candidate_upload_capabilities(tenant_id,capability_id,request_id,candidate_id,token_sha256,document_type,staging_object_key,max_bytes,expires_at,issued_by) VALUES(%s,%s,%s,%s,%s,'RESIDENCE',%s,10485760,now()+interval '15 minutes','ci')",(tenant,cap,f'REQ-{cap}',f'CAND-{cap}',token,key)); db.commit()
 return str(cap)
def role_rls():
 seed('other-tenant',sha256(b'other').digest())
 with psycopg.connect(role_url('eay_candidate_upload_runtime')) as db,db.cursor() as c:
  c.execute('SELECT workforce_current_tenant()'); assert c.fetchone()[0]==TENANT; c.execute("SELECT set_config('app.workforce_tenant','other-tenant',true)"); c.execute('SELECT workforce_current_tenant()'); assert c.fetchone()[0]==TENANT
  try: c.execute('SELECT count(*) FROM recruitment.candidate_upload_capabilities')
  except psycopg.Error: db.rollback()
  else: raise AssertionError('upload role has direct SELECT')
 with psycopg.connect(role_url('eay_rls_probe')) as db,db.cursor() as c:
  c.execute('SELECT count(*) FROM recruitment.candidate_upload_capabilities'); assert c.fetchone()[0]==0; c.execute("SELECT set_config('app.workforce_tenant','other-tenant',true)"); c.execute('SELECT count(*) FROM recruitment.candidate_upload_capabilities'); assert c.fetchone()[0]==0
def finalize_once(token,eid,evidence_sha):
 try:
  with psycopg.connect(role_url('eay_candidate_upload_runtime'),autocommit=False) as db,db.cursor() as c: c.execute("SELECT * FROM recruitment.finalize_candidate_evidence_upload_v2(%s,%s,'RESIDENCE',%s,'residence.pdf','application/pdf',128,%s,now()+interval '365 days','eay-ci-evidence','AES-256-GCM+AWS-KMS-DATA-KEY','arn:aws:kms:eu-central-1:000000000000:key/ci',1)",(TENANT,token,eid,evidence_sha)); ok=c.fetchone() is not None; db.commit(); return ok
 except psycopg.Error: return False
def upload_replay():
 token=sha256(b'single-use').digest(); cap=seed(TENANT,token); digest=sha256(b'%PDF-1.7\nci-evidence').digest(); ids=[str(uuid4()),str(uuid4())]
 with ThreadPoolExecutor(max_workers=2) as p: results=list(p.map(lambda eid:finalize_once(token,eid,digest),ids))
 assert results.count(True)==1,results
 with psycopg.connect(ADMIN_URL) as db,db.cursor() as c: c.execute("SELECT evidence_id,storage_backend,encryption_scheme,envelope_version FROM recruitment.candidate_evidence_objects WHERE tenant_id=%s AND capability_id=%s",(TENANT,cap)); row=c.fetchone(); assert row and row[1:]==('S3_KMS_ENVELOPE','AES-256-GCM+AWS-KMS-DATA-KEY',1); return str(row[0]),digest
def scan_once(eid,digest,receipt):
 try:
  with psycopg.connect(role_url('eay_candidate_scanner_runtime'),autocommit=False) as db,db.cursor() as c: c.execute("SELECT recruitment.record_candidate_evidence_scan_receipt(%s,%s,%s,'ci-scanner','2026-08',%s,%s,'CLEAN','HMAC-SHA256',%s,%s,now())",(TENANT,uuid4(),eid,receipt,digest,sha256(b'payload').digest(),sha256(b'sig').digest())); c.fetchone(); db.commit(); return True
 except psycopg.Error: return False
def scanner_replay(eid,digest):
 receipt=f'receipt-{uuid4()}'
 with ThreadPoolExecutor(max_workers=2) as p: results=list(p.map(lambda _:scan_once(eid,digest,receipt),range(2)))
 assert results.count(True)==1,results
def cross_tenant_rejected():
 with psycopg.connect(role_url('eay_candidate_upload_runtime'),autocommit=False) as db,db.cursor() as c:
  try: c.execute("SELECT * FROM recruitment.prepare_candidate_evidence_upload(%s,%s,'RESIDENCE',128,%s)",('other-tenant',sha256(b'x').digest(),sha256(b'y').digest()))
  except psycopg.Error: db.rollback()
  else: raise AssertionError('cross-tenant prepare succeeded')
def replay_migration():
 with psycopg.connect(ADMIN_URL,autocommit=False) as db: execute_script(db,M24)
 with psycopg.connect(ADMIN_URL) as db,db.cursor() as c: c.execute('SELECT max(version) FROM workforce_schema_migrations'); assert int(c.fetchone()[0])>=40
def main():
 bootstrap(); role_rls(); cross_tenant_rejected(); eid,digest=upload_replay(); scanner_replay(eid,digest); replay_migration(); print('recruitment production authority PostgreSQL acceptance: GREEN')
if __name__=='__main__': main()
