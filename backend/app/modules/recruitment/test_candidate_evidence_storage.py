from __future__ import annotations
import io,unittest
from datetime import UTC,datetime,timedelta
from hashlib import sha256
from app.modules.recruitment.candidate_evidence_storage import EvidenceStorageError,S3KmsEnvelopeEvidenceStore
class FakeKms:
 def __init__(self): self.key=b'k'*32; self.context=None
 def generate_data_key(self,**kw): self.context=kw['EncryptionContext']; return {'Plaintext':self.key,'CiphertextBlob':b'encrypted-key'}
 def decrypt(self,**kw):
  if kw['EncryptionContext']!=self.context or kw['CiphertextBlob']!=b'encrypted-key': raise ValueError('mismatch')
  return {'Plaintext':self.key}
class FakeS3:
 def __init__(self): self.objects={}
 def put_object(self,**kw):
  k=(kw['Bucket'],kw['Key'])
  if k in self.objects: raise RuntimeError('PreconditionFailed')
  self.objects[k]=bytes(kw['Body'])
 def get_object(self,*,Bucket,Key): return {'Body':io.BytesIO(self.objects[(Bucket,Key)])}
class Tests(unittest.TestCase):
 def setUp(self): self.kms=FakeKms(); self.s3=FakeS3(); self.store=S3KmsEnvelopeEvidenceStore(bucket='bucket',kms_key_id='arn:test',kms_client=self.kms,s3_client=self.s3); self.content=b'%PDF-1.7\nevidence'; self.digest=sha256(self.content).hexdigest(); self.key='quarantine/eay-ci/11111111-1111-1111-1111-111111111111'
 def test_round_trip_ciphertext(self):
  self.store.put(tenant_id='eay-ci',object_key=self.key,plaintext=self.content,expected_sha256=self.digest,retention_until=datetime.now(UTC)+timedelta(days=1)); self.assertNotIn(self.content,self.s3.objects[('bucket',self.key)]); self.assertEqual(self.store.get(tenant_id='eay-ci',object_key=self.key,expected_sha256=self.digest),self.content)
 def test_digest_mismatch_fails(self):
  self.store.put(tenant_id='eay-ci',object_key=self.key,plaintext=self.content,expected_sha256=self.digest,retention_until=datetime.now(UTC)+timedelta(days=1));
  with self.assertRaises(EvidenceStorageError): self.store.get(tenant_id='eay-ci',object_key=self.key,expected_sha256='0'*64)
 def test_cross_tenant_key_rejected(self):
  with self.assertRaises(EvidenceStorageError): self.store.put(tenant_id='other',object_key=self.key,plaintext=self.content,expected_sha256=self.digest,retention_until=datetime.now(UTC)+timedelta(days=1))
if __name__=='__main__': unittest.main()
