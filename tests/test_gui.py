"""Source identity, provenance precision, and the read-only local HTTP boundary."""

import copy
import csv
import hashlib
import importlib.util
import json
import io
from pathlib import Path
import tempfile
import unittest

from test_intelligence import make_document, sample_collection
from pbl_docintel.evidence import build_index
from pbl_docintel.schema import Location

GUI_AVAILABLE = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx"))
if GUI_AVAILABLE:
    from fastapi.testclient import TestClient
    from pbl_docintel.gui.server import Workspace, create_app, display_rect


@unittest.skipUnless(GUI_AVAILABLE, "Install .[gui,test] for GUI boundary tests")
class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        self.pdf = self.root / "sample.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\nfixture for transport and fingerprint checks\n")
        self.docling = self.root / "document.json"
        self.docling.write_text(json.dumps(make_document()), encoding="utf-8")
        index = build_index(self.docling, self.pdf)
        self.index_path = self.root / "evidence.json"
        self.index_path.write_text(index.model_dump_json(), encoding="utf-8")
        collection = sample_collection(index)
        merged = copy.deepcopy(collection["records"][0])
        merged.update(result_id="merged", value={"raw": "0.7 0.8", "numeric": None},
                      value_evidence={"evidence_id": "#/tables/0::cell:9"},
                      metric_evidence=[{"evidence_id": "#/tables/0::cell:3"}])
        merged["benchmark"] = {"dataset": {"reported": "B"}, "evidence": [{"evidence_id": "#/tables/0::cell:1"}]}
        collection["records"].append(merged)
        (self.root / "annotations.json").write_text(json.dumps(collection), encoding="utf-8")
        self.manifest = {"papers": [{"paper_id": "fixture:v1", "title": "Fixture",
                        "role": "experiment_comparison_seed", "source_pdf": "sample.pdf",
                        "source_sha256": hashlib.sha256(self.pdf.read_bytes()).hexdigest(),
                        "docling_json": "document.json", "evidence_index": "evidence.json",
                        "annotations": "annotations.json"}]}
        self.save_manifest()
        self.client = TestClient(create_app(self.root))
        self.addCleanup(self.client.close)

    def save_manifest(self):
        (self.root / "data/corpus.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def get_document(self):
        return self.client.get("/api/papers/fixture:v1")

    def test_real_checks_preserve_ambiguity_and_review_status(self):
        response = self.get_document()
        self.assertEqual(response.status_code, 200)
        document = response.json()
        self.assertEqual(document["checks"][0]["outcome"], "evidence_checks_passed")
        self.assertEqual(document["records"][0]["review"]["status"], "unreviewed")
        self.assertEqual(document["records"][1]["value"], {"raw": "0.7 0.8", "numeric": None, "uncertainty": None})
        self.assertIn("multiple_numeric_values", document["checks"][1]["warnings"])
        self.assertIn("empty_extracted_text", document["units"]["#/texts/1"]["issues"])

    def test_source_changes_are_rejected_even_after_cache_warmup(self):
        self.assertEqual(self.get_document().status_code, 200)
        self.pdf.write_bytes(self.pdf.read_bytes() + b"changed")
        response = self.get_document()
        self.assertEqual(response.status_code, 409)
        self.assertIn("fingerprint", response.json()["detail"])
        self.assertEqual(self.client.get("/api/papers/fixture:v1/pdf").status_code, 409)

    def test_changed_conversion_cannot_reuse_saved_evidence(self):
        self.docling.write_bytes(self.docling.read_bytes() + b"\n")
        response = self.get_document()
        self.assertEqual(response.status_code, 409)
        self.assertIn("Docling export", response.json()["detail"])

    def test_result_conversion_mismatch_is_rejected(self):
        path = self.root / "annotations.json"
        data = json.loads(path.read_text())
        data["document_id"] = "0" * 64
        for record in data["records"]:
            record["document_id"] = data["document_id"]
        path.write_text(json.dumps(data))
        self.assertEqual(self.get_document().status_code, 409)

    def test_missing_source_is_a_visible_loading_error(self):
        self.pdf.unlink()
        self.assertEqual(self.get_document().status_code, 409)

    def test_pdf_byte_ranges_and_module_mime_types(self):
        response = self.client.get("/api/papers/fixture:v1/pdf", headers={"Range": "bytes=0-7"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, self.pdf.read_bytes()[:8])
        module = self.client.get("/static/vendor/pdf.mjs")
        self.assertEqual(module.status_code, 200)
        self.assertIn("javascript", module.headers["content-type"])
        self.assertEqual(module.headers["x-content-type-options"], "nosniff")

    def test_exports_preserve_evidence_and_do_not_write_to_workspace(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for kind in ("evidence", "results", "csv", "markdown", "checks", "rag", "docling"):
            response = self.client.get(f"/api/papers/fixture:v1/exports/{kind}")
            self.assertEqual(response.status_code, 200, kind)
            self.assertIn("attachment", response.headers["content-disposition"])
        evidence = self.client.get("/api/papers/fixture:v1/exports/evidence").json()
        self.assertNotIn("display_rect", evidence["units"]["#/texts/0"]["locations"][0])
        chunks = self.client.get("/api/papers/fixture:v1/exports/rag").text.splitlines()
        self.assertTrue(all(json.loads(line)["metadata"]["document_id"] == evidence["document"]["document_id"] for line in chunks))
        csv_text = self.client.get("/api/papers/fixture:v1/exports/csv").content.decode("utf-8-sig")
        row = next(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(row["source_sha256"], evidence["document"]["source_sha256"])
        self.assertEqual(row["document_id"], evidence["document"]["document_id"])
        self.assertEqual(row["review_status"], "unreviewed")
        self.assertEqual(json.loads(row["conditions_json"]), [])
        after = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_reference_pdf_does_not_gain_fabricated_evidence(self):
        paper = self.manifest["papers"][0]
        for key in ("docling_json", "evidence_index", "annotations"):
            paper.pop(key)
        self.save_manifest()
        with TestClient(create_app(self.root)) as client:
            data = client.get("/api/papers/fixture:v1").json()
            self.assertIsNone(data["document"])
            self.assertEqual(data["records"], [])
            self.assertEqual(data["units"], {})
            self.assertEqual(client.get("/api/papers/fixture:v1/exports/results").status_code, 404)

    def test_workspace_paths_cannot_escape_manifest_root(self):
        self.manifest["papers"][0]["source_pdf"] = "../outside.pdf"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "inside the workspace"):
            Workspace(self.root)

    def test_service_rejects_mutations_unknown_files_and_foreign_hosts(self):
        self.assertEqual(self.client.post("/api/papers/fixture:v1", json={}).status_code, 405)
        self.assertEqual(self.client.get("/api/papers/unknown/pdf").status_code, 404)
        self.assertEqual(self.client.get("/api/papers/fixture:v1/exports/arbitrary").status_code, 404)
        self.assertEqual(self.client.get("/api/papers", headers={"Host": "attacker.example"}).status_code, 400)


@unittest.skipUnless(GUI_AVAILABLE, "Install .[gui,test] for GUI boundary tests")
class CoordinateTests(unittest.TestCase):
    def test_both_origins_project_to_the_same_visible_region(self):
        pages = {"1": {"width": 200.0, "height": 100.0}}
        top = Location(page_no=1, bbox={"l":20.0,"t":10.0,"r":60.0,"b":30.0,"coord_origin":"TOPLEFT"})
        bottom = Location(page_no=1, bbox={"l":20.0,"t":90.0,"r":60.0,"b":70.0,"coord_origin":"BOTTOMLEFT"})
        self.assertEqual(display_rect(top, pages), {"left":.1,"top":.1,"right":.3,"bottom":.3})
        self.assertEqual(display_rect(bottom, pages), display_rect(top, pages))

    def test_missing_invalid_and_coarse_locations_do_not_gain_precision(self):
        pages = {"1": {"width": 200.0, "height": 100.0}}
        self.assertIsNone(display_rect(Location(page_no=1), pages))
        invalid = Location(page_no=1, bbox={"l":20.0,"t":10.0,"r":260.0,"b":30.0,"coord_origin":"TOPLEFT"})
        self.assertIsNone(display_rect(invalid, pages))
        coarse = Location(page_no=1,granularity="table",bbox={"l":20.0,"t":10.0,"r":60.0,"b":30.0,"coord_origin":"TOPLEFT"})
        display_rect(coarse, pages)
        self.assertEqual(coarse.granularity, "table")


if __name__ == "__main__":
    unittest.main()
