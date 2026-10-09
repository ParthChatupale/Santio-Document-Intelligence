"""Job persistence and HTTP boundaries with explicitly injected model fixtures."""

import json
import time
import unittest

import test_gui as gui
from test_understanding import FixtureModel, statement

if gui.GUI_AVAILABLE:
    from pbl_docintel.gui.intelligence import Intelligence


class ConnectedFixture(FixtureModel):
    def public(self):
        return {"provider": "test-fixture", "url": "http://localhost", "model": self.name,
                "configured": True, "key_present": False, "remote": False}


@unittest.skipUnless(gui.GUI_AVAILABLE, "Install .[gui,test] for GUI boundary tests")
class UnderstandingHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture = gui.WorkspaceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.client = self.fixture.client
        self.service = self.client.app.state.intelligence
        self.addCleanup(self.service.close)
        self.endpoint = "/api/papers/fixture:v1/understanding"

    def wait_job(self, job_id):
        for _ in range(100):
            job = next(j for j in self.client.get(self.endpoint).json()["jobs"] if j["job_id"] == job_id)
            if job["status"] not in {"queued", "processing"}:
                return job
            time.sleep(.01)
        self.fail("Fixture job did not finish")

    def test_unconfigured_model_does_not_create_fake_analysis(self):
        self.assertIsNone(self.client.get(self.endpoint).json()["report"])
        self.assertEqual(self.client.post(self.endpoint).status_code, 409)

    def test_model_key_never_round_trips_and_cross_origin_writes_fail(self):
        body = {"provider": "nvidia", "url": "https://integrate.api.nvidia.com/v1", "model": "fixture", "key": "secret-fixture"}
        result = self.client.post("/api/model", json=body)
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("secret-fixture", result.text)
        self.assertNotIn("secret-fixture", self.client.get("/api/model").text)
        self.assertNotIn("secret-fixture", self.client.get(self.endpoint).text)
        self.assertEqual(self.client.post("/api/model", json=body, headers={"Origin": "https://foreign.example"}).status_code, 403)
        changed = {**body, "provider": "compatible", "url": "https://other.example/v1", "keep_key": True, "key": ""}
        self.assertEqual(self.client.post("/api/model", json=changed).status_code, 400)

    def test_analysis_is_generated_persisted_and_exported_with_identity(self):
        self.service.model = ConnectedFixture([{"statements": [statement()], "relationships": []}])
        response = self.client.post(self.endpoint)
        self.assertEqual(response.status_code, 202)
        job = self.wait_job(response.json()["job_id"])
        self.assertEqual(job["status"], "completed")
        report = self.client.get(self.endpoint).json()["report"]
        self.assertEqual(report["model"], "explicit-test-fixture")
        self.assertEqual(self.client.get(self.endpoint + "/export").json(), report)
        restored = Intelligence(self.client.app.state.workspace)
        self.addCleanup(restored.close)
        self.assertEqual(restored.state("fixture:v1")["report"], report)

    def test_question_job_keeps_evidence_trace_and_rejects_whitespace(self):
        self.service.model = ConnectedFixture([{"status": "answered", "statements": [statement()], "search_queries": [], "missing_information": []}])
        endpoint = "/api/papers/fixture:v1/questions"
        self.assertEqual(self.client.post(endpoint, json={"question": "   "}).status_code, 422)
        self.assertEqual(self.client.post(endpoint, json={"question": "Datasets"}, headers={"Origin":"https://foreign.example"}).status_code, 403)
        response = self.client.post(endpoint, json={"question": "Datasets"})
        job = self.wait_job(response.json()["job_id"])
        self.assertEqual(job["result"]["status"], "answered")
        self.assertTrue(job["result"]["trace"])

    def test_invalid_model_output_fails_without_overwriting_previous_report(self):
        self.service.model = ConnectedFixture([{"statements": [statement()], "relationships": []}])
        self.wait_job(self.client.post(self.endpoint).json()["job_id"])
        previous = self.client.get(self.endpoint).json()["report"]
        self.service.model = ConnectedFixture([{"bad": "sensitive-fixture-response"}])
        job = self.wait_job(self.client.post(self.endpoint).json()["job_id"])
        self.assertEqual(job["status"], "failed")
        self.assertNotIn("sensitive-fixture-response", job["error"])
        self.assertEqual(self.client.get(self.endpoint).json()["report"], previous)

    def test_text_export_comes_from_the_document_and_full_markdown_is_available(self):
        response = self.client.get("/api/papers/fixture:v1/exports/text")
        self.assertIn("Datasets A and B", response.text)
        self.fixture.docling.with_suffix(".md").write_text("# Actual saved conversion\n", encoding="utf-8")
        response = self.client.get("/api/papers/fixture:v1/exports/fulltext")
        self.assertEqual(response.content, self.fixture.docling.with_suffix(".md").read_bytes())


if __name__ == "__main__":
    unittest.main()
