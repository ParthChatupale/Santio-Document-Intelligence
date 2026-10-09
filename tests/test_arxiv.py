"""Download/cache integrity checks use fake responses, not live network."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pbl_docintel.arxiv import download_arxiv_pdf, normalize_arxiv_id


class Response(io.BytesIO):
    url = "https://arxiv.org/pdf/2501.17887v1"
    headers = {"Content-Type": "application/pdf"}


class ArxivTests(unittest.TestCase):
    def test_identifiers_and_explicit_versions(self):
        for value in ["2501.17887v1", "arxiv:2501.17887v1", "https://arxiv.org/abs/2501.17887v1",
                      "https://arxiv.org/pdf/2501.17887v1.pdf"]:
            self.assertEqual(normalize_arxiv_id(value), "2501.17887v1")
        self.assertEqual(normalize_arxiv_id("hep-th/9901001v2"), "hep-th/9901001v2")

    def test_arbitrary_urls_and_path_traversal_are_rejected(self):
        for value in ["https://example.com/pdf/2501.17887", "../../file", "https://arxiv.org.evil.test/pdf/2501.17887",
                      "https://arxiv.org/pdf/2501.17887?redirect=elsewhere", "2513.00001", "2501.17887v0"]:
            with self.assertRaises(ValueError):
                normalize_arxiv_id(value)

    def test_cache_and_receipt_prevent_repeated_download_and_detect_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("pbl_docintel.arxiv.urlopen", return_value=Response(b"%PDF-test")) as network:
                pdf = download_arxiv_pdf("2501.17887v1", Path(folder))
                self.assertEqual(download_arxiv_pdf("2501.17887v1", Path(folder)), pdf)
                self.assertEqual(network.call_count, 1)
                receipt = json.loads(pdf.with_suffix(".download.json").read_text())
                self.assertTrue(receipt["version_explicit"])
                pdf.write_bytes(b"%PDF-modified")
                with self.assertRaisesRegex(ValueError, "receipt"):
                    download_arxiv_pdf("2501.17887v1", Path(folder))

    def test_html_response_and_excessive_size_do_not_create_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            for content, limit in [(b"<html>blocked</html>", 100), (b"%PDF-too-large", 5)]:
                with patch("pbl_docintel.arxiv.urlopen", return_value=Response(content)), patch("pbl_docintel.arxiv.time.sleep"):
                    with self.assertRaises(ValueError):
                        download_arxiv_pdf("2501.17887v1", Path(folder), max_bytes=limit)
            self.assertFalse(list(Path(folder).glob("*.pdf")))


if __name__ == "__main__":
    unittest.main()
