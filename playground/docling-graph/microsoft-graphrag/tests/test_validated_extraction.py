import json
from pathlib import Path
import sys
import tempfile
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _contracts import GraphRecords, serialize, source_text, EXTRACTION_PROMPT, project
from prepare_context import prepare_context
from _common import HERE, read_json
import test_contracts as fixtures


class ValidatedExtraction(TestCase):
    source = "Atlas is trained on Corpus and evaluated on Bench."

    def test_native_two_pass_extractor_preserves_first_gleaned_record(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from graphrag.index.operations.extract_graph.graph_extractor import GraphExtractor
        first = self.records()
        second = self.records()
        second.entities[1].name = 'Bench'
        second.relationships[0].target = 'Bench'
        second.relationships[0].kind = 'EVALUATED_ON'
        second.relationships[0].evidence = self.source
        model = SimpleNamespace(completion_async=AsyncMock(side_effect=[
            SimpleNamespace(content=serialize(first, self.source)[0]),
            SimpleNamespace(content=serialize(second, self.source)[0])]))
        extractor = GraphExtractor(model, EXTRACTION_PROMPT, 1)
        entities, relations = asyncio.run(extractor(self.source, ['Method', 'Dataset'], 'source'))
        self.assertEqual(len(entities), 4)
        self.assertEqual(set(entities['title']), {'ATLAS', 'CORPUS', 'BENCH'})
        self.assertEqual(len(relations), 2)
        self.assertEqual(set(relations['target']), {'CORPUS', 'BENCH'})

    def records(self):
        return GraphRecords.model_validate({"entities": [
            {"name": "Atlas", "type": "Method", "description": "A model"},
            {"name": "Corpus", "type": "Dataset", "description": "Training data"}],
            "relationships": [{"source": "Atlas", "target": "Corpus", "kind": "TRAINED_ON",
                               "description": "Atlas trains on Corpus", "evidence": "Atlas is trained on Corpus"}]})

    def test_native_parser_consumes_all_records_and_weights(self):
        text, audit = serialize(self.records(), self.source)
        self.assertEqual(audit["entities"], 2)
        self.assertEqual(audit["relationships"], 1)
        self.assertTrue(audit["all_records_consumed"])
        self.assertIn('<|>1)\n##\n<|COMPLETE|>', text)

    def test_invented_quotation_is_rejected(self):
        r = self.records(); r.relationships[0].evidence = "Atlas is evaluated on Corpus"
        with self.assertRaisesRegex(ValueError, "quotation"):
            serialize(r, self.source)

    def test_bad_role_and_undeclared_endpoint_are_rejected(self):
        r = self.records(); r.entities[1].type = "Method"
        with self.assertRaisesRegex(ValueError, "Method to Dataset"):
            serialize(r, self.source)
        r = self.records(); r.relationships[0].target = "Other"
        with self.assertRaisesRegex(ValueError, "endpoint"):
            serialize(r, self.source)

    def test_missing_entities_cannot_be_smuggled_into_tuple_fields(self):
        r = self.records(); r.entities[0].description += ' ## ("entity"<|>Bad)'
        with self.assertRaisesRegex(ValueError, "delimiter"):
            serialize(r, self.source)

    def test_duplicate_names_and_invented_names_rejected(self):
        r = self.records(); r.entities.append(r.entities[0])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            serialize(r, self.source)
        r = self.records(); r.entities[0].name = "Invented"
        with self.assertRaisesRegex(ValueError, "absent"):
            serialize(r, self.source)

    def test_empty_output_is_valid_format_not_semantic_completeness(self):
        _, audit = serialize(GraphRecords(entities=[], relationships=[]), self.source)
        self.assertTrue(audit["all_records_consumed"])
        self.assertFalse(audit["semantic_entailment_verified"])

    def test_invalid_candidates_are_withheld_with_complete_accounting(self):
        r = self.records(); bad = r.relationships[0].model_copy(deep=True)
        bad.evidence = "Invented claim"; r.relationships.append(bad)
        text, audit = project(r, self.source)
        self.assertEqual(audit["relationships"], 1)
        self.assertEqual(len(audit["withheld_records"]), 1)
        self.assertTrue(audit["all_generated_records_accounted"])

    def test_initialization_ownership_and_metric_components_rejected(self):
        r = self.records(); r.entities[1].type = "Method"
        r.relationships[0].kind = "INITIALIZED_FROM"
        with self.assertRaisesRegex(ValueError, "source of weights"):
            serialize(r, self.source)
        r = self.records(); r.entities[1].type = "Metric";r.relationships[0].kind = "HAS_COMPONENT"
        with self.assertRaisesRegex(ValueError, "reported metric"):
            serialize(r, self.source)

    def test_explicit_component_initialization_is_not_rejected_for_concept_type(self):
        source = 'We initialize the weights of Backbone from Pixal3D.'
        records = GraphRecords.model_validate({'entities': [
            {'name': 'Backbone', 'type': 'Concept', 'description': 'A backbone component'},
            {'name': 'Pixal3D', 'type': 'Method', 'description': 'Pretrained source model'}],
            'relationships': [{'source': 'Backbone', 'target': 'Pixal3D', 'kind': 'INITIALIZED_FROM',
                               'description': 'Weights initialized from Pixal3D', 'evidence': source}]})
        _, audit = serialize(records, source)
        self.assertEqual(audit['relationships'], 1)

    def test_provider_preserves_raw_json_and_returns_canonical_tuples(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = fixtures.ProviderContracts().runtime(folder)
            runtime.client.chat.completions.create.return_value = fixtures.ProviderContracts().response(
                content=self.records().model_dump_json())
            prompt = EXTRACTION_PROMPT.format(entity_types="Method,Dataset", input_text=self.source)
            answer = runtime.complete(prompt)
            self.assertIn('("relationship"', answer.content)
            self.assertEqual(source_text([{"content": prompt}]), self.source)
            raw = next((Path(folder) / "response_cache").glob("*.json"))
            self.assertTrue(json.loads(raw.read_text())["choices"][0]["message"]["content"].startswith('{'))
            runtime.close()

    def test_upstream_schema_error_falls_back_without_cache_alias_or_validation_bypass(self):
        import httpx
        import openai
        from unittest.mock import patch
        from _providers import unresolved_failures
        with tempfile.TemporaryDirectory() as folder:
            runtime = fixtures.ProviderContracts().runtime(folder, calls=3)
            error = openai.InternalServerError('Failed to generate completions', response=httpx.Response(500,
                request=httpx.Request('POST', 'https://example.invalid')), body={})
            runtime.client.chat.completions.create.side_effect = [error, fixtures.ProviderContracts().response(
                content=self.records().model_dump_json())]
            prompt = EXTRACTION_PROMPT.format(entity_types='Method,Dataset', input_text=self.source)
            with patch('_providers.sleep'):
                result = runtime.complete(prompt)
            self.assertIn('TRAINED_ON', result.content)
            sent = runtime.client.chat.completions.create.call_args_list
            self.assertEqual(sent[0].kwargs['response_format']['type'], 'json_schema')
            self.assertEqual(sent[1].kwargs['response_format']['type'], 'json_object')
            fallback_prompt = sent[1].kwargs['messages'][0]
            self.assertEqual(fallback_prompt['role'], 'system')
            self.assertIn('"description"', fallback_prompt['content'])
            self.assertIn('"required"', fallback_prompt['content'])
            from _contracts import native_messages
            self.assertEqual(native_messages(sent[1].kwargs['messages']), sent[0].kwargs['messages'])
            self.assertNotEqual(runtime.calls[0]['request_hash'], runtime.calls[1]['request_hash'])
            self.assertEqual(runtime.calls[0]['logical_request_hash'], runtime.calls[1]['logical_request_hash'])
            self.assertEqual(unresolved_failures(runtime.calls), [])
            self.assertEqual(len(list((Path(folder)/'requests').glob('*.json'))), 2)
            self.assertEqual(len(list((Path(folder)/'response_cache').glob('*.json'))), 1)
            runtime.complete(prompt)
            self.assertEqual(runtime.client.chat.completions.create.call_count, 2)
            runtime.close()

    def test_json_transport_fallback_still_rejects_invalid_schema(self):
        import httpx
        import openai
        from unittest.mock import patch
        from _providers import unresolved_failures
        with tempfile.TemporaryDirectory() as folder:
            runtime = fixtures.ProviderContracts().runtime(folder, calls=3)
            error = openai.InternalServerError('decoder', response=httpx.Response(500,
                request=httpx.Request('POST', 'https://example.invalid')), body={})
            runtime.client.chat.completions.create.side_effect = [error, fixtures.ProviderContracts().response(
                content='{"entities":[]}')]
            prompt = EXTRACTION_PROMPT.format(entity_types='Method', input_text=self.source)
            with patch('_providers.sleep'), self.assertRaises(RuntimeError):
                runtime.complete(prompt)
            self.assertTrue(unresolved_failures(runtime.calls))
            self.assertEqual(list((Path(folder)/'response_cache').glob('*.json')), [])
            runtime.close()

    def test_repeated_upstream_errors_use_disclosed_model_failover_and_exact_cache(self):
        import httpx
        import openai
        from unittest.mock import patch
        from _providers import unresolved_failures
        with tempfile.TemporaryDirectory() as folder:
            runtime = fixtures.ProviderContracts().runtime(folder, calls=4)
            runtime.fallback_model = 'nvidia/fallback-test'
            error = openai.InternalServerError('upstream', response=httpx.Response(500,
                request=httpx.Request('POST', 'https://example.invalid')), body={})
            runtime.client.chat.completions.create.side_effect = [error, error,
                fixtures.ProviderContracts().response(content=self.records().model_dump_json())]
            prompt = EXTRACTION_PROMPT.format(entity_types='Method,Dataset', input_text=self.source)
            with patch('_providers.sleep'):
                runtime.complete(prompt)
            sent = runtime.client.chat.completions.create.call_args_list
            self.assertEqual(sent[0].kwargs['model'], runtime.model)
            self.assertEqual(sent[2].kwargs['model'], runtime.fallback_model)
            self.assertEqual(sent[2].kwargs['response_format']['type'], 'json_schema')
            self.assertEqual(runtime.calls[-1]['model'], runtime.fallback_model)
            self.assertEqual(unresolved_failures(runtime.calls), [])
            runtime.complete(prompt)
            self.assertEqual(runtime.client.chat.completions.create.call_count, 3)
            self.assertEqual(runtime.calls[-1]['status'], 'cache_hit')
            self.assertEqual(runtime.calls[-1]['model'], runtime.fallback_model)
            runtime.close()

    def test_plain_summary_failover_does_not_require_json(self):
        import httpx
        import openai
        from unittest.mock import patch
        from _providers import unresolved_failures
        with tempfile.TemporaryDirectory() as folder:
            runtime = fixtures.ProviderContracts().runtime(folder, calls=4)
            runtime.fallback_model = 'nvidia/fallback-test'
            error = openai.InternalServerError('upstream', response=httpx.Response(500,
                request=httpx.Request('POST', 'https://example.invalid')), body={})
            runtime.client.chat.completions.create.side_effect = [error, error,
                fixtures.ProviderContracts().response(content='A supported merged description.')]
            with patch('_providers.sleep'):
                result = runtime.complete('Summarize the supplied descriptions.')
            self.assertEqual(result.content, 'A supported merged description.')
            self.assertEqual(runtime.client.chat.completions.create.call_args.kwargs['model'], runtime.fallback_model)
            self.assertNotIn('response_format', runtime.client.chat.completions.create.call_args.kwargs)
            self.assertEqual(unresolved_failures(runtime.calls), [])
            runtime.complete('Summarize the supplied descriptions.')
            self.assertEqual(runtime.client.chat.completions.create.call_count, 3)
            runtime.close()

    def test_report_larger_budget_reuses_complete_legacy_request_without_alias(self):
        from pydantic import BaseModel
        class CommunityReportResponse(BaseModel):
            summary: str
        with tempfile.TemporaryDirectory() as folder:
            runtime = fixtures.ProviderContracts().runtime(folder, calls=3)
            runtime.client.chat.completions.create.return_value = fixtures.ProviderContracts().response(
                content='{"summary":"Complete short report"}')
            runtime.complete('Report input', response_format=CommunityReportResponse, max_tokens=4096)
            old_hash = runtime.calls[-1]['request_hash']
            runtime.complete('Report input', response_format=CommunityReportResponse)
            self.assertEqual(runtime.client.chat.completions.create.call_count, 1)
            self.assertEqual(runtime.calls[-1]['request_hash'], old_hash)
            self.assertEqual(runtime.calls[-1]['status'], 'cache_hit')
            runtime.close()

    def test_report_truncation_is_retained_and_recovered_with_validated_failover(self):
        from pydantic import BaseModel
        from _providers import unresolved_failures
        class CommunityReportResponse(BaseModel):
            summary: str
        with tempfile.TemporaryDirectory() as folder:
            runtime = fixtures.ProviderContracts().runtime(folder, calls=3)
            runtime.fallback_model = 'nvidia/fallback-test'
            runtime.client.chat.completions.create.side_effect = [
                fixtures.ProviderContracts().response(finish='length', content='{"summary":"unfinished'),
                fixtures.ProviderContracts().response(content='{"summary":"Complete report"}')]
            result = runtime.complete('Report input', response_format=CommunityReportResponse)
            self.assertEqual(result.formatted_response.summary, 'Complete report')
            self.assertEqual(runtime.client.chat.completions.create.call_args_list[0].kwargs['max_tokens'], 8192)
            self.assertEqual(runtime.calls[-1]['model'], runtime.fallback_model)
            self.assertEqual(unresolved_failures(runtime.calls), [])
            failed_raw = Path(folder)/'provider_responses'/(runtime.calls[0]['request_hash']+'.json')
            self.assertEqual(json.loads(failed_raw.read_text())['choices'][0]['finish_reason'], 'length')
            self.assertEqual(len(list((Path(folder)/'response_cache').glob('*.json'))), 1)
            runtime.close()

    def test_additional_pass_feedback_is_scoped_to_its_source(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = fixtures.ProviderContracts().runtime(folder, calls=3)
            fake = fixtures.ProviderContracts()
            invalid = {"entities": [{"name": "Invented", "type": "Method", "description": "Not in source"}], "relationships": []}
            runtime.client.chat.completions.create.side_effect = [fake.response(content=json.dumps(invalid)),
                fake.response(content='{"entities":[],"relationships":[]}'), fake.response(content='{"entities":[],"relationships":[]}')]
            prompt = EXTRACTION_PROMPT.format(entity_types="Method", input_text=self.source)
            first = runtime.complete(prompt)
            runtime.complete(EXTRACTION_PROMPT.format(entity_types="Method", input_text="An unrelated document."))
            runtime.complete([{"role": "user", "content": prompt}, {"role": "assistant", "content": first.content},
                              {"role": "user", "content": "Find additional records."}])
            sent = runtime.client.chat.completions.create.call_args.kwargs["messages"][-1]["content"]
            self.assertIn('Invented', sent)
            self.assertIn('Validation withheld', sent)
            # The native assistant content was a tuple stream, but the model's
            # continued conversation must retain its own JSON-format response.
            model_history = runtime.client.chat.completions.create.call_args.kwargs['messages'][1]['content']
            self.assertEqual(json.loads(model_history), invalid)
            self.assertNotIn('<|COMPLETE|>', model_history)
            runtime.close()

    def test_real_context_records_keep_table_headers_and_no_hashes(self):
        import tiktoken
        tokenizer = tiktoken.get_encoding("cl100k_base")
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "prepared"
            result = prepare_context(HERE / "runs/tetris-prepared-final", target)
            records = read_json(target / "input/documents.json")
            self.assertTrue(result["table_cell_content_preserved"])
            self.assertTrue(all(len(tokenizer.encode(r["text"])) < 1024 for r in records))
            self.assertTrue(all('Paper title: TETRIS3D' in r["text"] for r in records))
            self.assertTrue(all('source_record_id:' not in r["text"] and 'c7cca5c7618d084c' not in r["text"] for r in records))
            worlds = [r for r in records if r["content_kind"] == "table" and 'Row label: WorldSculpt' in r["text"]]
            self.assertTrue(worlds)
            self.assertTrue(all('Cell [Method' in r["text"] and 'Table ' in r["text"] for r in worlds))
            figures = [r for r in records if r["content_kind"] == "picture"]
            self.assertTrue(any(r.get('figure_labels_for_inspection') for r in figures))
            self.assertTrue(all('Text extracted inside this figure' not in r['text'] for r in figures))
            diagram = next(r for r in figures if 'DINOv3' in r.get('figure_labels_for_inspection', ''))
            self.assertNotIn('DINOv3', diagram['text'])
            self.assertIn('Figure 3:', diagram['text'])
