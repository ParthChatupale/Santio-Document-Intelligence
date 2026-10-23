"""Run with the MAIN environment, which already has Docling. No inference."""
from pathlib import Path
import sys
import tempfile
from unittest import TestCase, main

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import ROOT, digest, read_json
from prepare_input import prepare


class PreparationContracts(TestCase):
    def test_real_document_preserves_tables_captions_and_picture_children(self):
        source = ROOT / "outputs/2610.10539v1.json"
        before = digest(source)
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "prepared"
            report = prepare(source, output)
            records = read_json(output / "input/documents.json")
            source_map = read_json(output / "source_map.json")
            self.assertEqual(report["accounted_items"], report["source_items"])
            self.assertFalse(report["resolution_errors"])
            self.assertFalse(report["unresolved_refs"])
            table = next(r for r in records if "#/tables/2" in r["docling_refs"])
            self.assertIn("0.0192", table["text"])
            self.assertIn("0.4980", table["text"])
            picture = next(r for r in records if "#/pictures/0" in r["docling_refs"])
            self.assertIn("#/texts/5", picture["docling_refs"])
            self.assertTrue(picture["figure_text_refs"])
            self.assertFalse(any(r["docling_refs"] == ["#/texts/5"] for r in records))
            self.assertTrue(all(r["id"] in source_map for r in records))
            self.assertTrue(all(not r["ai_description_included"] for r in records))
            self.assertEqual(digest(source), before)
            with self.assertRaisesRegex(ValueError, "already exists"):
                prepare(source, output)


if __name__ == "__main__":
    main()
