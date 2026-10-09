"""Understanding contracts and source attribution, using explicit model fixtures.

These tests do not establish model accuracy or call an external provider.
"""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_intelligence import make_document
from pbl_docintel.evidence import build_index_from_bytes
from pbl_docintel.models import HTTPJSONModel
from pbl_docintel.understanding import (
    Statement, UnderstandingDraft, allowed_ids, analyze, answer, batches,
    checked, retrieve, source_entries, validate_citations,
)


def statement(eid="#/texts/0", quote="Datasets A and B", text="The paper discusses datasets A and B."):
    return {"category": "finding", "text": text, "basis": "reported",
            "citations": [{"evidence_id": eid, "quote": quote}]}


class FixtureModel:
    name = "explicit-test-fixture"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, system, payload, schema):
        self.calls.append(payload)
        return copy.deepcopy(self.responses.pop(0))


class UnderstandingTests(unittest.TestCase):
    def setUp(self):
        self.index = build_index_from_bytes(json.dumps(make_document()).encode())

    def test_unknown_evidence_and_invented_quotes_are_rejected(self):
        entries = source_entries(self.index)
        audit = []
        valid = checked(UnderstandingDraft.model_validate({"statements": [statement(), statement(quote="invented"), statement(eid="#/texts/999")], "relationships": []}),
                        self.index, allowed_ids(entries), audit)
        self.assertEqual(len(valid.statements), 1)
        self.assertEqual(len(audit), 2)

    def test_quote_must_be_in_context_actually_given_to_model(self):
        item = Statement.model_validate(statement(quote="Datasets A and B"))
        errors = validate_citations(item, self.index, {"#/texts/0": ["Datasets A"]})
        self.assertIn("quote_not_in_supplied_context:#/texts/0", errors)

    def test_reading_batches_do_not_omit_long_passages(self):
        entries = source_entries(self.index)
        entry = {**entries[0], "text": "x" * 25001}
        groups = batches([entry], limit=7000)
        self.assertEqual("".join(e["text"] for group in groups for e in group), entry["text"])
        self.assertGreater(len(groups), 1)

    def test_table_retrieval_keeps_method_and_column_context(self):
        hits = retrieve(source_entries(self.index), "Ours Score")
        value = next(h for h in hits if h["evidence_id"] == "#/tables/0::cell:8")
        self.assertEqual(value["context"]["row_headers"][0]["text"], "Ours")
        self.assertEqual(value["context"]["column_headers"][-1]["text"], "Score ↑")

    def test_analysis_reports_coverage_and_preserves_inference_basis(self):
        claim = statement()
        claim["basis"] = "inference"
        model = FixtureModel([{"statements": [claim], "relationships": []}])
        report = analyze(self.index, model)
        self.assertEqual(report["model"], "explicit-test-fixture")
        self.assertEqual(report["statements"][0]["basis"], "inference")
        self.assertEqual(report["coverage"]["entries_read"], len(source_entries(self.index)))
        self.assertFalse(report["coverage"]["pictures_interpreted"])

    def test_analysis_does_not_save_a_fabricated_summary(self):
        model = FixtureModel([{"statements": [statement(quote="invented")], "relationships": []}])
        with self.assertRaisesRegex(ValueError, "no source-linked"):
            analyze(self.index, model)

    def test_synthesis_cannot_substitute_unseen_quotes(self):
        candidates = {"statements": [statement(quote="Datasets A"), statement(quote="and B")], "relationships": []}
        final = {"statements": [statement(quote="Datasets A and B")], "relationships": []}
        with self.assertRaisesRegex(ValueError, "no source-linked"):
            analyze(self.index, FixtureModel([candidates, final]))

    def test_answer_rejects_bad_citations(self):
        model = FixtureModel([{"status": "answered", "statements": [statement(quote="imagined quote")], "missing_information": [], "search_queries": []}])
        result = answer(self.index, model, "Datasets")
        self.assertEqual(result["status"], "not_found")
        self.assertFalse(result["statements"])
        self.assertTrue(result["rejected_candidates"])

    def test_agent_requests_additional_evidence_and_records_tools(self):
        first = {"status": "partial", "statements": [], "missing_information": [], "search_queries": ["Datasets"]}
        final = {"status": "answered", "statements": [statement()], "missing_information": [], "search_queries": []}
        model = FixtureModel([first, final])
        result = answer(self.index, model, "Score")
        self.assertEqual(result["status"], "answered")
        self.assertEqual([s["query"] for s in result["trace"]], ["Score", "Datasets"])
        self.assertEqual(len(model.calls), 2)

    def test_agent_stops_after_three_rounds(self):
        response = {"status": "partial", "statements": [], "missing_information": ["Context is missing"], "search_queries": ["Datasets"]}
        model = FixtureModel([response, response, response])
        result = answer(self.index, model, "Datasets")
        self.assertEqual(len(model.calls), 3)
        self.assertEqual(result["status"], "not_found")

    def test_missing_retrieval_returns_abstention_without_model_call(self):
        model = FixtureModel([])
        result = answer(self.index, model, "unfindablewordxyz")
        self.assertEqual(result["status"], "not_found")
        self.assertFalse(model.calls)


class ModelTests(unittest.TestCase):
    def test_nvidia_key_is_not_exposed_and_destination_is_fixed(self):
        model = HTTPJSONModel("nvidia", "https://integrate.api.nvidia.com/v1", "fixture", "secret-test-value")
        self.assertNotIn("secret-test-value", json.dumps(model.public()))
        self.assertTrue(model.public()["configured"])
        with self.assertRaises(ValueError):
            HTTPJSONModel("nvidia", "https://other.example/v1", "fixture", "secret")

    def test_remote_http_and_credential_urls_are_rejected(self):
        for url in ("http://remote.example/v1", "https://user:pass@remote.example/v1"):
            with self.assertRaises(ValueError):
                HTTPJSONModel("compatible", url, "fixture")

    def test_nvidia_requires_a_key_to_be_ready(self):
        self.assertFalse(HTTPJSONModel("nvidia", "https://integrate.api.nvidia.com/v1", "fixture").public()["configured"])

    def test_http_adapter_uses_bearer_auth_and_bounded_response(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size): return b'{"choices":[{"message":{"content":"{\\"ok\\":true}"}}]}'
        model = HTTPJSONModel("nvidia", "https://integrate.api.nvidia.com/v1", "fixture", "test-key")
        with patch("pbl_docintel.models.urlopen", return_value=Response()) as opened:
            self.assertEqual(model.generate("JSON please", {}, {}), {"ok": True})
            request = opened.call_args.args[0]
            self.assertEqual(request.full_url, "https://integrate.api.nvidia.com/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer test-key")
            self.assertEqual(json.loads(request.data)["max_tokens"], 4096)


if __name__ == "__main__":
    unittest.main()
