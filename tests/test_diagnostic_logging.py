import unittest
from app.services.diagnostic_logging import redact

class DiagnosticLoggingTests(unittest.TestCase):
    def test_credentials_and_tokens_are_redacted(self):
        value=redact('camera rtsp://operator:swordfish@host/live password=secret token: abc123')
        self.assertNotIn('swordfish',value);self.assertNotIn('secret',value);self.assertNotIn('abc123',value);self.assertIn('[REDACTED]',value)

if __name__=='__main__':unittest.main()
