import json,unittest,httpx
from app.modules.recruitment.official_document_m2m import AuthorizedOfficialM2MAdapter,OfficialM2MConfig,OfficialM2MError
class C:
 def __init__(self): self.calls=[]
 def post(self,url,**kw):
  self.calls.append((url,kw))
  if url.endswith('/token'): return httpx.Response(200,json={'access_token':'secret','token_type':'Bearer'},request=httpx.Request('POST',url))
  body={'official_receipt_id':'r1','result':'VERIFIED','subject_match':'MATCH','document_type':'RESIDENCE','evidence_sha256':'a'*64}; return httpx.Response(200,content=json.dumps(body).encode(),headers={'X-Provider-Signature':'verified'},request=httpx.Request('POST',url))
def cfg(): return OfficialM2MConfig(endpoint='https://institutional.example.gov.tr/verify',token_url='https://institutional.example.gov.tr/token',client_id='c',client_secret='s',mtls_cert='/c',mtls_key='/k',allowed_hosts=('institutional.example.gov.tr',),contract_id='v1')
class Tests(unittest.TestCase):
 def test_signed_exact_binding(self):
  a=AuthorizedOfficialM2MAdapter(cfg(),response_verifier=lambda raw,h:h.get('x-provider-signature')=='verified',response_mapper=lambda p:p,client=C()); r=a.verify_document(evidence_sha256='a'*64,document_type='RESIDENCE',barcode='b',subject_reference='ref',correlation_id='c'); self.assertTrue(r['provider_signature_verified'])
 def test_public_portal_rejected(self):
  bad=OfficialM2MConfig(endpoint='https://www.turkiye.gov.tr/belge-dogrulama',token_url='https://www.turkiye.gov.tr/token',client_id='c',client_secret='s',mtls_cert='/c',mtls_key='/k',allowed_hosts=('www.turkiye.gov.tr',),contract_id='v1')
  with self.assertRaises(OfficialM2MError): AuthorizedOfficialM2MAdapter(bad,response_verifier=lambda *_:True,response_mapper=lambda p:p,client=C())
 def test_unsigned_fails(self):
  a=AuthorizedOfficialM2MAdapter(cfg(),response_verifier=lambda *_:False,response_mapper=lambda p:p,client=C())
  with self.assertRaises(OfficialM2MError): a.verify_document(evidence_sha256='a'*64,document_type='RESIDENCE',barcode='b',subject_reference='ref',correlation_id='c')
if __name__=='__main__': unittest.main()
