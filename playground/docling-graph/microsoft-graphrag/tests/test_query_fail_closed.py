import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import write_json
from query_graph import ask


class QueryFailures(TestCase):
    def test_native_partial_answer_is_not_promoted_after_provider_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            write_json(run / "run.json", {"status": "completed", "source_sha256": "test", "partial_document_scope": False})
            runtime = SimpleNamespace(calls=[], key="private", model="test", close=lambda: None, save=lambda: None)
            async def partial(**kwargs):
                runtime.calls.append({"status": "failed", "request_hash": "failed-map"})
                return "An apparently successful answer [Data: Sources (1)]", {}
            with patch("_query_runtime.configure", return_value=runtime), patch("graphrag.api.basic_search", side_effect=partial), \
                 patch("query_graph.load_config", return_value=SimpleNamespace()), \
                 patch("query_graph.load_tables", return_value={"text_units": []}), \
                 patch("query_graph.resolve_context", return_value={}):
                result = asyncio.run(ask(run, "A question", "basic", output=run / "query"))
            self.assertEqual(result["status"], "failed")
            self.assertIn("partial answers are not promoted", result["error"])

    def test_global_map_mode_enforces_native_points_schema(self):
        from _query_runtime import QueryRuntime
        import test_contracts as fixtures
        with tempfile.TemporaryDirectory() as folder:
            with patch("_providers.connection", return_value=("test", "https://example.invalid/v1", "private")), patch("openai.OpenAI"):
                runtime = QueryRuntime(folder)
            runtime.client.chat.completions.create.return_value = fixtures.ProviderContracts().response(
                content='{"points":[{"description":"Supported point","score":80}]}')
            result = runtime.complete("Map a report", response_format_json_object=True)
            options = runtime.client.chat.completions.create.call_args.kwargs
            self.assertEqual(options["response_format"]["json_schema"]["name"], "GlobalMapResponse")
            self.assertEqual(result.formatted_response.points[0].score, 80)
            runtime.close()
