import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import model_bundle


class ModelBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/"models").mkdir()
        self.asset=self.root/"models"/"model.bin";self.asset.write_bytes(b"offline model")
        self.digest=hashlib.sha256(self.asset.read_bytes()).hexdigest()

    def manifest(self, *, checksum=None, status="approved"):
        path=self.root/"manifest.json"
        path.write_text(json.dumps({"schema_version":1,"assets":[{"component":"test","required":True,"expected_installed_path":"models/model.bin","sha256":checksum or self.digest,"redistribution_status":status}]}),encoding="utf-8")
        return path

    def test_valid_offline_asset_passes(self):
        with patch.object(model_bundle,"MANIFEST_PATH",self.manifest()):result=model_bundle.verify_bundle(self.root)
        self.assertTrue(result["ok"]);self.assertTrue(result["checks"][0]["checksum_ok"])

    def test_corrupt_asset_fails_before_loading(self):
        with patch.object(model_bundle,"MANIFEST_PATH",self.manifest(checksum="0"*64)):result=model_bundle.verify_bundle(self.root)
        self.assertFalse(result["ok"]);self.assertIn("test: checksum mismatch",result["errors"])

    def test_unapproved_redistribution_blocks_commercial_bundle(self):
        with patch.object(model_bundle,"MANIFEST_PATH",self.manifest(status="not_approved")):result=model_bundle.verify_bundle(self.root,commercial=True)
        self.assertFalse(result["ok"]);self.assertIn("test: redistribution not approved",result["errors"])

    def test_runtime_offline_flags_are_enforced(self):
        with patch.dict(os.environ,{},clear=True):
            model_bundle.enforce_offline_environment()
            self.assertEqual(os.environ["HF_HUB_OFFLINE"],"1");self.assertEqual(os.environ["ULTRALYTICS_OFFLINE"],"true")


if __name__=="__main__":unittest.main()
