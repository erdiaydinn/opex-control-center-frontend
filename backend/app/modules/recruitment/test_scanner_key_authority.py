import unittest
from app.modules.recruitment.scanner_key_authority import AwsKmsHmacKeyAuthority,ScannerKeyAuthorityError
class K:
 def generate_mac(self,**kw): return {'Mac':b'mac:'+kw['Message']}
 def verify_mac(self,**kw): return {'MacValid':kw['Mac']==b'mac:'+kw['Message']}
class Tests(unittest.TestCase):
 def setUp(self): self.a=AwsKmsHmacKeyAuthority(active_key_id='2026-08',verify_keys={'2026-07':'arn:old','2026-08':'arn:active'},kms_client=K())
 def test_rotation(self):
  sig=self.a.sign('2026-08',b'x'); self.assertTrue(self.a.verify('2026-08',b'x',sig)); self.assertTrue(self.a.verify('2026-07',b'x',sig))
 def test_unknown_and_retired_fail(self):
  self.assertFalse(self.a.verify('unknown',b'x',b'y'))
  with self.assertRaises(ScannerKeyAuthorityError): self.a.sign('2026-07',b'x')
if __name__=='__main__': unittest.main()
