"""Run with the GraphRAG environment. Tests do not make provider requests."""
import json
from pathlib import Path
import sys
import tempfile
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import select_records, supervise, write_json
from _sources import check_citations, source_ledger
from _providers import Runtime, BudgetExceeded, unresolved_failures


class SourceContracts(TestCase):
    def test_process_watchdog_stops_blocking_work(self):
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "blocking.py"
            script.write_text("import time\ntime.sleep(10)\n")
            self.assertEqual(supervise(script, [], 0.2), 124)

    def test_split_native_text_units_keep_their_original_source(self):
        with tempfile.TemporaryDirectory() as d:
            write_json(Path(d) / "source_map.json", {"block-a": {"item_refs": ["#/texts/2"], "pages": [3]}})
            tables = {"text_units": [{"id": "chunk-a", "text": "source_record_id: block-a\nfirst half"},
                                     {"id": "chunk-b", "text": "source_record_id: block-a\nsecond half"}],
                      "entities": [{"id": "entity-a", "text_unit_ids": ["chunk-a", "chunk-b"]}],
                      "relationships": [{"id": "edge-a", "text_unit_ids": ["chunk-b"]}],
                      "communities": [{"id": "community-a", "community": 0, "text_unit_ids": ["chunk-a", "chunk-b"]}],
                      "community_reports": [{"id": "report-a", "community": 0}]}
            _, ledger = source_ledger(d, tables)
            for key in [("text_units", "chunk-b"), ("relationships", "edge-a"), ("community_reports", "report-a")]:
                self.assertEqual(ledger[key], {"block-a"})

    def test_missing_source_is_not_treated_as_verified(self):
        result = check_citations("Claim [Data: Sources (10)]", {"sources": []})
        self.assertFalse(result["all_cited_records_resolved"])

    def test_source_identifier_prefix_is_not_an_evidence_match(self):
        with tempfile.TemporaryDirectory() as d:
            write_json(Path(d) / "source_map.json", {"block-a": {}, "block-a0": {}})
            _, ledger = source_ledger(d, {"text_units": [{"id": "chunk", "text": "source_record_id: block-a0.\nText"}]})
            self.assertEqual(ledger[("text_units", "chunk")], {"block-a0"})

    def test_only_selected_context_can_resolve_a_citation(self):
        context = {"sources": [{"citation_id": "2", "resolved": True, "docling_refs": ["#/texts/2"], "pages": [3]}]}
        self.assertTrue(check_citations("Claim [Data: Sources (2)]", context)["all_cited_records_resolved"])
        self.assertFalse(check_citations("Claim [Data: Sources (2, 9)]", context)["all_cited_records_resolved"])
        self.assertFalse(check_citations("An uncited claim", context)["all_cited_records_resolved"])

    def test_heading_selection_does_not_match_unrelated_substrings(self):
        with tempfile.TemporaryDirectory() as d:
            write_json(Path(d) / "input/documents.json", [{"id": "a", "headings": ["3 Methods"]},
                                                        {"id": "b", "headings": ["4 Methods comparison"]}])
            self.assertEqual(select_records(d, ["3 methods"])[0]["id"], "a")
            with self.assertRaises(ValueError):
                select_records(d, ["Methods"])


class ProviderContracts(TestCase):
    def test_native_workflow_success_does_not_hide_a_provider_failure(self):
        calls = [{"request_hash": "a", "status": "completed"}, {"request_hash": "b", "status": "failed"}]
        self.assertEqual(len(unresolved_failures(calls)), 1)
        calls.append({"request_hash": "b", "status": "completed"})
        self.assertFalse(unresolved_failures(calls))

    def runtime(self, folder, calls=1):
        with patch("_providers.connection", return_value=("test-model", "https://example.invalid/v1", "dummy-secret")), patch("openai.OpenAI"):
            return Runtime(folder, max_calls=calls)

    def response(self, finish="stop", content="Hi"):
        response = MagicMock()
        response.choices[0].finish_reason = finish
        response.choices[0].message.content = content
        response.usage.model_dump.return_value = {"total_tokens": 12}
        response.model_dump.return_value = {"id": "test", "created": 1, "model": "test-model", "object": "chat.completion",
            "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": content}}]}
        return response

    def test_zero_budget_stops_before_network_call(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = self.runtime(d, 0)
            with self.assertRaises(BudgetExceeded):
                runtime.complete("hi")
            runtime.client.chat.completions.create.assert_not_called()
            runtime.close()

    def test_truncated_output_is_not_cached_as_success(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = self.runtime(d)
            runtime.client.chat.completions.create.return_value = self.response("length", "unfinished")
            with self.assertRaisesRegex(RuntimeError, "finish normally"):
                runtime.complete("hi")
            self.assertFalse((Path(d) / "response_cache").exists())
            self.assertEqual(runtime.calls[0]["status"], "failed")
            runtime.close()

    def test_resume_preserves_call_budget_and_redacts_provider_error(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = self.runtime(d)
            runtime.client.chat.completions.create.side_effect = ValueError("dummy-secret rejected")
            with self.assertRaisesRegex(RuntimeError, "REDACTED"):
                runtime.complete("hi")
            runtime.close()
            self.assertNotIn("dummy-secret", (Path(d) / "model_calls.json").read_text())
            resumed = self.runtime(d)
            with self.assertRaises(BudgetExceeded):
                resumed.complete("retry")
            resumed.client.chat.completions.create.assert_not_called()
            resumed.close()

    def test_exact_cached_request_needs_no_second_network_call(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = self.runtime(d)
            runtime.client.chat.completions.create.return_value = self.response()
            self.assertEqual(runtime.complete("hi").content, "Hi")
            self.assertEqual(runtime.complete("hi").content, "Hi")
            self.assertEqual(runtime.client.chat.completions.create.call_count, 1)
            self.assertEqual(runtime.calls[-1]["status"], "cache_hit")
            runtime.close()


if __name__ == "__main__":
    main()
