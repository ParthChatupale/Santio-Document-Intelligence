"""Checks that attribution failures cannot masquerade as clean results."""

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic import ValidationError
from pbl_docintel.evidence import build_index, cell_id
from pbl_docintel.schema import ResultCollection
from pbl_docintel.validation import check_collection

ROOT = Path(__file__).resolve().parents[1]
BOX = {"l": 1.0, "t": 2.0, "r": 3.0, "b": 4.0, "coord_origin": "TOPLEFT"}


def make_document():
    def cell(text, row, col, **flags):
        return {"text": text, "start_row_offset_idx": row, "end_row_offset_idx": row + 1,
                "start_col_offset_idx": col, "end_col_offset_idx": col + 1,
                "bbox": BOX, **flags}
    prov = [{"page_no": 1, "bbox": BOX, "charspan": [0, 0]}]
    return {"schema_name": "DoclingDocument", "version": "1.0", "name": "sample",
            "origin": {"filename": "sample.pdf"},
            "pages": {str(n): {"page_no": n, "size": {"width": 612.0, "height": 792.0}} for n in [1, 2]},
            "texts": [{"self_ref": "#/texts/0", "label": "caption", "text": "Datasets A and B", "prov": prov},
                      {"self_ref": "#/texts/1", "label": "formula", "text": "", "prov": prov}],
            "tables": [{"self_ref": "#/tables/0", "label": "table", "prov": prov,
                        "captions": [{"$ref": "#/texts/0"}], "data": {"num_rows": 4, "num_cols": 3,
                        "table_cells": [cell("A", 0, 1, column_header=True),
                                        cell("B", 0, 2, column_header=True),
                                        cell("Score ↑", 1, 1, column_header=True),
                                        cell("Score ↑", 1, 2, column_header=True),
                                        cell("Baseline", 2, 0, row_header=True),
                                        cell("0.5", 2, 1), cell("0.5", 2, 2),
                                        cell("Ours", 3, 0, row_header=True),
                                        cell("0.5", 3, 1), cell("0.7 0.8", 3, 2)]}}], "pictures": []}


def sample_collection(index):
    eid = lambda n: {"evidence_id": cell_id("#/tables/0", n)}
    return {"document_id": index.document.document_id,
            "run": {"extractor": "test_annotation", "created_at": "2026-10-08T00:00:00Z"},
            "records": [{"result_id": "ours-a", "document_id": index.document.document_id,
                         "method": {"reported": "Ours"},
                         "benchmark": {"dataset": {"reported": "A"}, "evidence": [eid(0)]},
                         "metric": {"name": {"reported": "Score"}, "direction": "higher"},
                         "value": {"raw": "0.5", "numeric": 0.5}, "value_evidence": eid(8),
                         "method_evidence": eid(7), "metric_evidence": [eid(2)]}]}


class AttributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "document.json"
        self.document = make_document()
        self.save_document()
        self.index = build_index(self.path)
        self.collection = sample_collection(self.index)

    def save_document(self):
        self.path.write_text(json.dumps(self.document), encoding="utf-8")

    def check(self):
        return check_collection(ResultCollection.model_validate_json(json.dumps(self.collection)), self.index)[0]

    def test_supported_record_does_not_become_human_reviewed(self):
        model = ResultCollection.model_validate_json(json.dumps(self.collection))
        self.assertEqual(check_collection(model, self.index)[0]["outcome"], "evidence_checks_passed")
        self.assertEqual(model.records[0].review.status, "unreviewed")

    def test_same_number_wrong_method_row_is_rejected(self):
        self.collection["records"][0]["method"] = {"reported": "Baseline"}
        self.collection["records"][0]["method_evidence"] = {"evidence_id": cell_id("#/tables/0", 4)}
        self.assertIn("method_not_in_value_row", self.check()["errors"])

    def test_identical_header_in_other_column_is_rejected(self):
        self.collection["records"][0]["metric_evidence"] = [{"evidence_id": cell_id("#/tables/0", 3)}]
        self.assertIn("metric_not_in_value_column", self.check()["errors"])

    def test_caption_with_both_datasets_cannot_bind_wrong_dataset(self):
        self.collection["records"][0]["benchmark"] = {"dataset": {"reported": "B"},
                                                     "evidence": [{"evidence_id": "#/texts/0"}]}
        self.assertIn("dataset_not_in_value_column", self.check()["errors"])

    def test_numeric_mismatch_is_rejected(self):
        self.collection["records"][0]["value"]["numeric"] = 0.6
        self.assertIn("numeric_value_mismatch", self.check()["errors"])

    def test_missing_header_flags_require_review_without_inventing_structure(self):
        self.document["tables"][0]["data"]["table_cells"][7]["row_header"] = False
        self.save_document()
        self.index = build_index(self.path)
        self.collection = sample_collection(self.index)
        self.collection["records"][0]["metric_evidence"] = [{"evidence_id": "#/tables/0"}]
        check = self.check()
        self.assertEqual(check["outcome"], "needs_review")
        self.assertIn("method_row_label_inferred", check["warnings"])
        self.assertIn("metric_requires_table_layout_review", check["warnings"])

    def test_wrong_direction_is_rejected(self):
        self.collection["records"][0]["metric"]["direction"] = "lower"
        self.assertIn("metric_direction_mismatch", self.check()["errors"])

    def test_multi_value_cell_is_preserved_and_flagged(self):
        record = self.collection["records"][0]
        record["value_evidence"] = {"evidence_id": cell_id("#/tables/0", 9)}
        record["value"] = {"raw": "0.7 0.8", "numeric": 0.7}
        record["metric_evidence"] = [{"evidence_id": cell_id("#/tables/0", 3)}]
        record["benchmark"] = {"dataset": {"reported": "B"},
                               "evidence": [{"evidence_id": cell_id("#/tables/0", 1)}]}
        check = self.check()
        self.assertEqual(check["outcome"], "needs_review")
        self.assertIn("multiple_numeric_values", check["warnings"])
        self.assertEqual(self.index.units[cell_id("#/tables/0", 9)].text, "0.7 0.8")

    def test_missing_ref_and_invented_quote_are_rejected(self):
        self.collection["records"][0]["value_evidence"]["quote"] = "invented value"
        self.assertTrue(any(e.startswith("quote_not_found") for e in self.check()["errors"]))
        self.collection["records"][0]["value_evidence"] = {"evidence_id": "#/texts/999"}
        self.assertTrue(any(e.startswith("unknown_evidence") for e in self.check()["errors"]))

    def test_reconversion_invalidates_old_references(self):
        self.document["version"] = "1.1"
        self.save_document()
        other_index = build_index(self.path)
        with self.assertRaisesRegex(ValueError, "different Docling conversion"):
            check_collection(ResultCollection.model_validate_json(json.dumps(self.collection)), other_index)

    def test_multipage_table_does_not_invent_cell_page(self):
        self.document["tables"][0]["prov"].append({"page_no": 2, "bbox": BOX, "charspan": [0, 0]})
        self.save_document()
        unit = build_index(self.path).units[cell_id("#/tables/0", 8)]
        self.assertEqual({loc.page_no for loc in unit.locations}, {1, 2})
        self.assertTrue(all(loc.granularity == "table" for loc in unit.locations))
        self.assertIn("cell_location_not_resolved", unit.issues)

    def test_empty_equation_and_coordinate_origin_are_preserved(self):
        unit = self.index.units["#/texts/1"]
        self.assertEqual(unit.text, "")
        self.assertIn("empty_extracted_text", unit.issues)
        self.assertEqual(self.index.units[cell_id("#/tables/0", 8)].locations[0].bbox.coord_origin, "TOPLEFT")

    def test_unknown_fields_and_nonfinite_values_fail_schema(self):
        for update in ({"hallucinated": True}, {"numeric": float("inf")}):
            data = copy.deepcopy(self.collection)
            data["records"][0]["value"].update(update)
            with self.assertRaises(ValidationError):
                ResultCollection.model_validate_json(json.dumps(data))

    def test_duplicate_results_and_unsupported_human_approval_fail(self):
        self.collection["records"].append(copy.deepcopy(self.collection["records"][0]))
        with self.assertRaises(ValidationError):
            ResultCollection.model_validate_json(json.dumps(self.collection))
        self.collection["records"].pop()
        self.collection["records"][0]["review"] = {"status": "human_reviewed"}
        with self.assertRaises(ValidationError):
            ResultCollection.model_validate_json(json.dumps(self.collection))

    def test_invalid_cell_and_page_are_rejected(self):
        self.document["tables"][0]["data"]["table_cells"][8]["end_col_offset_idx"] = 4
        self.save_document()
        with self.assertRaisesRegex(ValueError, "Out-of-bounds cell"):
            build_index(self.path)
        self.document = make_document()
        self.document["tables"][0]["prov"][0]["page_no"] = 999
        self.save_document()
        with self.assertRaisesRegex(ValueError, "Invalid page provenance"):
            build_index(self.path)

    def test_cli_never_overwrites_input(self):
        protected = Path(self.temp.name) / "evidence.index.json"
        protected.write_bytes(self.path.read_bytes())
        before = hashlib.sha256(protected.read_bytes()).hexdigest()
        result = subprocess.run([sys.executable, str(ROOT / "src/build_evidence.py"),
                                 str(protected), "--output-dir", self.temp.name], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("overwrite an input", result.stderr)
        self.assertEqual(hashlib.sha256(protected.read_bytes()).hexdigest(), before)

    def test_cli_exports_then_refuses_stale_results_on_index_only_run(self):
        annotation = Path(self.temp.name) / "annotation.json"
        annotation.write_text(json.dumps(self.collection), encoding="utf-8")
        output = Path(self.temp.name) / "output"
        base = [sys.executable, str(ROOT / "src/build_evidence.py"),
                str(self.path), "--output-dir", str(output)]
        completed = subprocess.run([*base, "--results", str(annotation)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for name in ("results.csv", "results.md", "evidence.index.json", "result.schema.json"):
            self.assertTrue((output / name).is_file())
        repeated = subprocess.run(base, capture_output=True, text=True)
        self.assertNotEqual(repeated.returncode, 0)
        self.assertIn("contains result exports", repeated.stderr)

    def test_cli_invalid_evidence_returns_nonzero_with_findings(self):
        self.collection["records"][0]["value"]["numeric"] = 99.0
        annotation = Path(self.temp.name) / "bad-annotation.json"
        annotation.write_text(json.dumps(self.collection), encoding="utf-8")
        output = Path(self.temp.name) / "invalid-output"
        completed = subprocess.run([sys.executable, str(ROOT / "src/build_evidence.py"),
                                    str(self.path), "--results", str(annotation),
                                    "--output-dir", str(output)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        checks = json.loads((output / "checks.json").read_text(encoding="utf-8"))
        self.assertIn("numeric_value_mismatch", checks["checks"][0]["errors"])


if __name__ == "__main__":
    unittest.main()
