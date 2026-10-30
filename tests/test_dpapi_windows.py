import os
import unittest

class WindowsDPAPI(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Native DPAPI verification requires Windows')
    def test_native_roundtrip_and_tamper_rejection(self):
        from app.key_store import _crypt
        plain='test-only-ข้อมูลทดสอบ-not-a-real-api-key'.encode('utf-8')
        encrypted=_crypt(plain,True)
        self.assertNotEqual(encrypted,plain)
        self.assertEqual(_crypt(encrypted,False),plain)
        with self.assertRaises(ValueError):_crypt(b'not-a-valid-dpapi-blob',False)
