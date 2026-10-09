import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

GUI_AVAILABLE = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx"))
if GUI_AVAILABLE:
    from fastapi.testclient import TestClient
    from pbl_docintel.gui.server import Workspace, create_app
    from pbl_docintel.gui.imports import Imports


@unittest.skipUnless(GUI_AVAILABLE, "Install .[gui,test]")
class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_empty_workspace_can_accept_upload_without_manual_manifest(self):
        with patch.object(Imports, "run"), patch("pbl_docintel.gui.server.importlib.util.find_spec", return_value=object()):
            with TestClient(create_app(self.root)) as client:
                self.assertEqual(client.get("/api/papers").json(), [])
                response = client.post("/api/imports?filename=..%2Fpaper.pdf&title=My%20paper", content=b"%PDF-1.4\nfixture")
                self.assertEqual(response.status_code, 202)
                job = response.json()
                self.assertEqual(job["filename"], "paper.pdf")
                self.assertEqual(job["title"], "My paper")
                self.assertEqual(job["status"], "queued")
                self.assertTrue((self.root / f"data/uploads/{job['job_id']}/source.pdf").is_file())
                self.assertEqual(client.get("/api/imports").json()[0]["job_id"], job["job_id"])
                self.assertEqual(client.post(f"/api/imports/{job['job_id']}/cancel").json()["status"], "cancelled")
                self.assertEqual(client.get("/api/papers").json(), [])
        with TestClient(create_app(self.root)) as client:
            self.assertEqual(client.get("/api/imports").json()[0]["status"], "cancelled")

    def test_invalid_oversized_and_cross_origin_uploads_are_rejected(self):
        with patch("pbl_docintel.gui.server.importlib.util.find_spec", return_value=object()):
            with TestClient(create_app(self.root)) as client:
                self.assertEqual(client.post("/api/imports?filename=x.pdf", content=b"not a pdf").status_code, 400)
                self.assertEqual(client.post("/api/imports?filename=x.exe", content=b"%PDF-").status_code, 400)
                with patch("pbl_docintel.gui.server.MAX_UPLOAD_BYTES", 8):
                    self.assertEqual(client.post("/api/imports?filename=x.pdf", content=b"%PDF-" + b"x"*10).status_code, 413)
                self.assertEqual(client.post("/api/imports?filename=x.pdf", content=b"%PDF-", headers={"Origin":"https://foreign.example"}).status_code, 403)
                self.assertEqual(client.post("/api/imports?filename=x.pdf", content=b"%PDF-", headers={"Sec-Fetch-Site":"cross-site"}).status_code, 403)
                self.assertEqual(client.get("/api/imports").json(), [])
        self.assertEqual(list((self.root / "data/uploads").glob("*")), [])

    def test_missing_docling_is_an_actionable_error(self):
        with patch("pbl_docintel.gui.server.importlib.util.find_spec", return_value=None):
            with TestClient(create_app(self.root)) as client:
                response = client.post("/api/imports?filename=x.pdf", content=b"%PDF-")
                self.assertEqual(response.status_code, 503)
                self.assertIn("Docling extra", response.json()["detail"])

    def test_interrupted_jobs_are_preserved_as_failed_after_restart(self):
        directory = self.root / "data/import-jobs"
        directory.mkdir(parents=True)
        (directory / "job.json").write_text(json.dumps({"job_id":"job","status":"processing","stage":"Converting","created_at":"2026-10-08"}))
        with TestClient(create_app(self.root)) as client:
            job = client.get("/api/imports").json()[0]
            self.assertEqual(job["status"], "failed")
            self.assertIn("stopped", job["error"])

    def test_uploaded_registration_survives_restart_without_changing_corpus(self):
        data = self.root / "data"
        data.mkdir()
        manifest = data / "corpus.json"
        manifest.write_text('{"papers": []}')
        for filename in ("source.pdf", "document.json", "index.json"):
            (self.root / filename).write_text("fixture")
        paper = {"paper_id":"upload:test","title":"User title","source_pdf":"source.pdf","docling_json":"document.json","evidence_index":"index.json"}
        workspace = Workspace(self.root)
        workspace.register(paper)
        self.assertEqual(json.loads(manifest.read_text()), {"papers":[]})
        self.assertEqual(Workspace(self.root).list_papers()[0]["title"], "User title")
        with self.assertRaisesRegex(ValueError, "already registered"):
            workspace.register(paper)

    def test_converter_failure_is_persisted_and_never_registered(self):
        workspace = Workspace(self.root)
        manager = Imports(workspace)
        directory = self.root / "data/uploads/failure"
        directory.mkdir(parents=True)
        (directory / "source.pdf").write_bytes(b"%PDF-")
        process = MagicMock()
        process.stdout = iter(["SANTIO_STAGE:Converting PDF with Docling\n", "Invalid PDF\n"])
        # Match the stream lifecycle as well as the process exit.
        class Lines:
            def __iter__(self):
                return iter(["SANTIO_STAGE:Converting PDF with Docling\n", "Invalid PDF\n"])
            def close(self):
                pass
        process.stdout = Lines()
        process.wait.return_value = 1
        process.poll.return_value = 1
        with patch("pbl_docintel.gui.imports.subprocess.Popen", return_value=process):
            manager.create("failure", "broken.pdf", "Broken upload", False)
            manager.futures["failure"].result(timeout=5)
        self.assertEqual(manager.list()[0]["status"], "failed")
        self.assertIn("Invalid PDF", manager.list()[0]["error"])
        self.assertEqual(workspace.list_papers(), [])
        manager.close()
        restarted = Imports(Workspace(self.root))
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.list()[0]["status"], "failed")
