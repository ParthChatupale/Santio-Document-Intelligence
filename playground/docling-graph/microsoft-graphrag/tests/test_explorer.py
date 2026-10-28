"""Explorer HTTP and native graph contracts. No remote model calls."""
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from unittest import TestCase, main
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import write_json
from serve import Explorer, graph_payload, handler
from _providers import Runtime
from index_graph import coverage_audit
import test_contracts as provider_test


class RetryContracts(TestCase):
    def test_atomic_ledger_write_tolerates_windows_reader_lock(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            original = os.replace
            tries = []
            def replace(source, destination):
                tries.append(1)
                if len(tries) < 3:
                    raise PermissionError("reader has file open")
                return original(source, destination)
            with patch("_common.os.replace", side_effect=replace), patch("_common.sleep"):
                write_json(path, {"valid": True})
            self.assertEqual(json.loads(path.read_text()), {"valid": True})
            self.assertEqual(len(tries), 3)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_transient_failure_retries_with_budget_and_keeps_failure_record(self):
        import openai
        import httpx
        with tempfile.TemporaryDirectory() as directory:
            runtime = provider_test.ProviderContracts().runtime(directory, calls=3)
            error = openai.InternalServerError("temporary", response=httpx.Response(500,
                request=httpx.Request("POST", "https://example.invalid")), body={})
            runtime.client.chat.completions.create.side_effect = [error, provider_test.ProviderContracts().response()]
            with patch("_providers.sleep"):
                self.assertEqual(runtime.complete("Hi").content, "Hi")
            self.assertEqual([c["status"] for c in runtime.calls], ["failed", "completed"])
            self.assertEqual(runtime.client.chat.completions.create.call_count, 2)
            runtime.close()

    def test_distinct_requests_can_overlap_and_share_one_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = provider_test.ProviderContracts().runtime(directory, calls=2)
            barrier = threading.Barrier(2)
            def respond(**kwargs):
                barrier.wait(timeout=3)
                return provider_test.ProviderContracts().response()
            runtime.client.chat.completions.create.side_effect = respond
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(runtime.complete, ["one", "two"]))
            self.assertEqual([r.content for r in results], ["Hi", "Hi"])
            self.assertEqual(len(runtime.calls), 2)
            runtime.close()

    def test_close_drains_an_in_flight_request_before_closing_client(self):
        import graphrag_llm.types  # Exclude one-time library imports from the synchronization assertion.
        with tempfile.TemporaryDirectory() as directory:
            runtime = provider_test.ProviderContracts().runtime(directory, calls=1)
            entered, release = threading.Event(), threading.Event()
            def respond(**kwargs):
                entered.set()
                release.wait(timeout=3)
                return provider_test.ProviderContracts().response()
            runtime.client.chat.completions.create.side_effect = respond
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = pool.submit(runtime.complete, "Hi")
                self.assertTrue(entered.wait(timeout=3))
                closing = pool.submit(runtime.close)
                time.sleep(.05)
                self.assertFalse(closing.done())
                runtime.client.close.assert_not_called()
                release.set()
                self.assertEqual(pending.result(timeout=3).content, "Hi")
                closing.result(timeout=3)
            self.assertEqual(runtime.calls[0]["status"], "completed")


class ExplorerContracts(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        write_json(self.root / "run.json", {"status": "partial_or_failed", "partial_document_scope": False})
        write_json(self.root / "source_map.json", {"source-a": {"pages": [2], "item_refs": ["#/texts/3"]}})
        write_json(self.root / "input/documents.json", [{"id": "source-a", "text": "Original text"}])
        self.pdf = self.root / "paper.pdf"
        self.pdf.write_bytes(b"%PDF-1.7 test data")
        self.explorer = Explorer(self.root, self.pdf)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.explorer))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.explorer.pool.shutdown()
        self.temp.cleanup()

    def request(self, route, data=None, headers=None):
        request = urllib.request.Request(self.base + route, data=data, headers=headers or {})
        return urllib.request.urlopen(request)

    def test_partial_index_is_visible_but_cannot_be_queried(self):
        with self.request("/api/status") as response:
            status = json.load(response)
        self.assertFalse(status["can_ask"])
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.request("/api/questions", b'{"question":"test","mode":"local"}',
                {"X-Graph-Session": self.explorer.token, "Content-Type": "application/json"})
        self.assertEqual(exc.exception.code, 400)

    def test_graph_room_serves_local_module_and_complete_accessible_controls(self):
        with self.request('/') as response:
            html=response.read().decode('utf-8')
        self.assertIn('type="module"',html)
        for ident in ['search','type','community','overview','source-dialog','ask-form','fullscreen','toggle-room','toggle-explore']:
            self.assertIn(f'id="{ident}"',html)
        with self.request('/graph-geometry.js') as response:
            self.assertIn('javascript',response.headers['Content-Type'])
            self.assertIn('assertionDirections',response.read().decode('utf-8'))

    def test_native_completion_still_requires_processing_coverage(self):
        write_json(self.root / "run.json", {"status": "completed", "partial_document_scope": False})
        self.assertFalse(self.explorer.status()["can_ask"])
        write_json(self.root / "coverage.json", {"processing_complete": True})
        self.assertTrue(self.explorer.status()["can_ask"])

    def test_cached_validated_initial_requests_count_during_processing(self):
        from _contracts import EXTRACTION_PROMPT
        write_json(self.root / 'model_calls.json', {'completion_calls': [{'status':'cache_hit','request_hash':'q'}]})
        write_json(self.root / 'validated_extractions/q.json', {'all_records_consumed': True})
        write_json(self.root / 'requests/q.json', {'messages': [{'role':'user','content':
            EXTRACTION_PROMPT.format(entity_types='Method', input_text='Original text')}]})
        status = self.explorer.status()
        self.assertEqual(status['records_with_successful_requests'], 1)
        self.assertFalse(status['can_ask'])

    def test_saved_answers_are_scoped_to_this_run(self):
        ident = "20261022T123456123456Z"
        write_json(self.root / "queries" / ("web-" + ident) / "answer.json",
                   {"status": "answered", "question": "A question", "mode": "local", "answer": "An answer"})
        self.assertEqual(self.explorer.saved_job(ident)["question"], "A question")
        self.assertIsNone(self.explorer.saved_job("../../other-run"))
        self.assertIsNone(self.explorer.saved_job("20261022T111111111111Z"))

    def test_cross_origin_question_and_arbitrary_files_are_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.request("/api/questions", b'{}', {"Origin": "https://example.invalid",
                "X-Graph-Session": self.explorer.token})
        self.assertEqual(exc.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.request("/../../.env")
        self.assertEqual(exc.exception.code, 404)

    def test_pdf_ranges_and_source_lookup(self):
        with self.request("/pdf", headers={"Range": "bytes=0-3"}) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), b"%PDF")
        with self.request("/api/source?id=source-a") as response:
            self.assertEqual(json.load(response)["text"], "Original text")

    def test_original_pdf_page_preview_and_bounds(self):
        from _common import ROOT
        self.explorer.pdf = ROOT / "2610.10539v1.pdf"
        with self.request("/api/page?number=2") as response:
            self.assertEqual(response.headers["Content-Type"], "image/png")
            self.assertEqual(response.read()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertIn(2, self.explorer.page_cache)
        for number in [0, 31]:
            with self.assertRaises(urllib.error.HTTPError) as exc:
                self.request(f"/api/page?number={number}")
            self.assertEqual(exc.exception.code, 400)

    def test_native_entities_and_edges_remain_traceable(self):
        tables = {"text_units": [{"id": "u", "text": "source_record_id: source-a\nOriginal text"}],
                  "entities": [{"id": "a", "title": "METHOD A", "type": "METHOD", "description": "A", "text_unit_ids": ["u"]},
                               {"id": "b", "title": "DATA B", "type": "DATASET", "description": "B", "text_unit_ids": ["u"]}],
                  "relationships": [{"id": "edge", "source": "METHOD A", "target": "DATA B", "description": "Uses B", "text_unit_ids": ["u"], "weight": 8}],
                  "communities": [{"id": "c", "community": 0, "level": 0, "entity_ids": ["a", "b"], "text_unit_ids": ["u"]}]}
        with patch("serve.load_tables", return_value=tables):
            graph = graph_payload(self.root)
        self.assertEqual(graph["edges"][0]["source"], "a")
        self.assertEqual(graph["edges"][0]["target"], "b")
        self.assertEqual(graph["edges"][0]["pages"], [2])
        self.assertEqual(graph["nodes"][0]["community"], 0)

    def test_directed_quotations_are_separate_from_native_merged_edge(self):
        from _contracts import EXTRACTION_PROMPT
        write_json(self.root / 'requests/request.json', {'messages': [{'role': 'user', 'content':
            EXTRACTION_PROMPT.format(entity_types='Method,Dataset', input_text='Original text')}]})
        claim = {'source': 'Method A', 'target': 'Data B', 'kind': 'TRAINED_ON',
                 'description': 'Training', 'evidence': 'Original text'}
        write_json(self.root / 'validated_extractions/request.json', {'relationship_evidence': [claim]})
        # Native undirected edges can have an alphabetical endpoint order.
        tables = {'entities': [{'id': 'a', 'title': 'METHOD A'}, {'id': 'b', 'title': 'DATA B'}],
                  'relationships': [{'id': 'e', 'source': 'DATA B', 'target': 'METHOD A'}]}
        with patch('serve.load_tables', return_value=tables):
            graph = graph_payload(self.root)
        assertion = graph['edges'][0]['assertion_evidence'][0]
        self.assertEqual(assertion['source'], 'Method A')
        self.assertEqual(assertion['target'], 'Data B')
        self.assertEqual(assertion['source_record_id'], 'source-a')
        self.assertEqual(assertion['evidence'], 'Original text')

    def test_coverage_checks_each_split_chunk_not_only_its_parent_record(self):
        tables = {"documents": [{"id": "doc", "raw_data": {"source_record_id": "source-a"}}],
                  "text_units": [{"id": "u1", "text": "source_record_id: source-a\nPart one   "},
                                 {"id": "u2", "text": "source_record_id: source-a\nPart two"}]}
        prompt = "Extract {entity_types}: {input_text}"
        (self.root / "prompts").mkdir()
        (self.root / "prompts/extract_graph.txt").write_text(prompt, encoding="utf-8")
        calls = []
        for i, unit in enumerate(tables["text_units"]):
            write_json(self.root / "requests" / (str(i) + ".json"), {"messages": [
                {"role": "user", "content": prompt.format(entity_types="Method", input_text=unit["text"].strip())}]})
            calls.append({"status": "completed", "request_hash": str(i)})
        config = SimpleNamespace(extract_graph=SimpleNamespace(entity_types=["Method"]))
        with patch("_sources.load_tables", return_value=tables), patch("index_graph.load_config", return_value=config):
            self.assertFalse(coverage_audit(self.root, calls[:1])["processing_complete"])
            self.assertTrue(coverage_audit(self.root, calls)["processing_complete"])
            historical = [{"status": "failed", "request_hash": "obsolete-summary"}, *calls]
            self.assertFalse(coverage_audit(self.root, historical)["processing_complete"])
            self.assertTrue(coverage_audit(self.root, historical, attempt_start=1)["processing_complete"])
            # Transport-only schema instructions must not break source coverage;
            # arbitrary extra system instructions must not be silently ignored.
            from _contracts import SCHEMA_TRANSPORT_MARKER
            path = self.root / 'requests/0.json'
            payload = json.loads(path.read_text())
            payload['messages'].insert(0, {'role': 'system', 'content': SCHEMA_TRANSPORT_MARKER+'Schema'})
            write_json(path, payload)
            self.assertTrue(coverage_audit(self.root, calls)['processing_complete'])
            payload['messages'][0]['content'] = 'Unrecognized changed instructions'
            write_json(path, payload)
            self.assertFalse(coverage_audit(self.root, calls)['processing_complete'])


if __name__ == "__main__":
    main()
