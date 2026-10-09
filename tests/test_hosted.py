"""Hosted startup and explicit host/origin boundaries."""

import os
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

GUI_AVAILABLE = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx"))
if GUI_AVAILABLE:
    from fastapi.testclient import TestClient
    from pbl_docintel.gui.hosted import create_hosted_app


@unittest.skipUnless(GUI_AVAILABLE, "Install .[gui,test] for hosted boundary tests")
class HostedTests(unittest.TestCase):
    def test_hosted_storage_hosts_and_frontend_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            settings = {"SANTIO_WORKSPACE": str(workspace),
                        "RENDER_EXTERNAL_HOSTNAME": "santio.onrender.com",
                        "SANTIO_ALLOWED_HOSTS": "api.example.com",
                        "SANTIO_ALLOWED_ORIGINS": "https://santio.vercel.app/"}
            with patch.dict(os.environ, settings, clear=True):
                with TestClient(create_hosted_app(), base_url="https://santio.onrender.com") as client:
                    self.assertEqual(client.get("/api/health").json(), {"status": "ok"})
                    self.assertEqual(client.get("/api/papers").json(), [])
                    self.assertTrue((workspace / "data/import-jobs").is_dir())
                    self.assertTrue((workspace / "data/understanding").is_dir())
                    self.assertEqual(os.environ["HF_HOME"], str(workspace / "model-cache/huggingface"))
                    self.assertEqual(client.get("/api/health", headers={"Host": "api.example.com"}).status_code, 200)
                    self.assertEqual(client.get("/api/health", headers={"Host": "attacker.example"}).status_code, 400)
                    accepted = {"Origin": "https://santio.vercel.app", "Sec-Fetch-Site": "cross-site"}
                    response = client.post("/api/imports/missing/cancel", headers=accepted)
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.headers["access-control-allow-origin"], accepted["Origin"])
                    rejected = {"Origin": "https://attacker.example", "Sec-Fetch-Site": "cross-site"}
                    self.assertEqual(client.post("/api/imports/missing/cancel", headers=rejected).status_code, 403)
                    self.assertEqual(client.post("/api/imports/missing/cancel", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
