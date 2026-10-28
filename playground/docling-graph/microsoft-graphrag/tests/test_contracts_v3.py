import json
from pathlib import Path
import sys
import tempfile
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _contracts_v3 import EntityRecord, GraphRecords, EXTRACTION_PROMPT, project, prior_entities
import test_contracts as fixtures


def entity(name, kind='Concept'):
    return EntityRecord(name=name, type=kind, description=name)


def relation(a, b, kind, quote, scope='method'):
    return {'source': a, 'target': b, 'kind': kind, 'scope': scope,
            'description': f'{a} {kind} {b}', 'evidence': quote}


class ScientificV3(TestCase):
    def check(self, source, entities, relations, previous=()):
        return project(GraphRecords(entities=entities, relationships=relations), source, previous)[1]

    def test_citations_and_abbreviated_table_references_are_not_nodes(self):
        a = self.check('Huang et al., 2025 and Tab. 1 and KAIST AI',
                       [entity('Huang et al., 2025', 'Organization'), entity('Tab. 1', 'Configuration'),
                        entity('KAIST AI', 'Organization')], [])
        self.assertEqual(a['entities'], 1)
        self.assertEqual(len(a['withheld_records']), 2)

    def test_additional_pass_inherits_only_needed_accepted_source_entities(self):
        source = 'Atlas is trained on Corpus. Bench is another dataset.'
        initial, _ = project(GraphRecords(entities=[entity('Atlas', 'Method'), entity('Corpus', 'Dataset'),
                                                   entity('Bench', 'Dataset')], relationships=[]), source)
        messages = [{'role': 'user', 'content': EXTRACTION_PROMPT.format(entity_types='Method,Dataset', input_text=source)},
                    {'role': 'assistant', 'content': initial}]
        previous = prior_entities(messages, source)
        a = self.check(source, [], [relation('Atlas', 'Corpus', 'TRAINED_ON', 'Atlas is trained on Corpus.')], previous)
        self.assertEqual(a['relationships'], 1)
        self.assertEqual(len(a['inherited_entities']), 2)
        self.assertTrue(a['all_generated_records_accounted'])
        self.assertEqual(prior_entities(messages, 'A different source'), [])

    def test_inheritance_cannot_bypass_entity_or_conflicting_type_validation(self):
        a = self.check('Atlas uses Corpus.', [entity('Atlas', 'Concept')],
                       [relation('Atlas', 'Corpus', 'USES', 'Atlas uses Corpus.')],
                       [entity('Atlas', 'Method'), entity('Corpus')])
        self.assertEqual(a['relationships'], 0)
        self.assertIn('Conflicting', a['withheld_records'][0]['reason'])
        a = self.check('Atlas uses Corpus.', [], [relation('Atlas', 'Invented', 'USES', 'Atlas uses Corpus.')],
                       [entity('Atlas', 'Method'), entity('Invented')])
        self.assertEqual(a['relationships'], 0)

    def test_metric_can_use_metric_but_cannot_be_model_component(self):
        source = 'MMD uses Chamfer Distance. Atlas reports MMD.'
        es = [entity('MMD', 'Metric'), entity('Chamfer Distance', 'Metric'), entity('Atlas', 'Method')]
        a = self.check(source, es, [relation('MMD', 'Chamfer Distance', 'USES', 'MMD uses Chamfer Distance.', 'definition'),
                                   relation('Atlas', 'MMD', 'HAS_COMPONENT', 'Atlas reports MMD.')])
        self.assertEqual(a['relationships'], 1)
        self.assertEqual(len(a['withheld_records']), 1)

    def test_metric_does_not_inherit_variables_from_unrelated_previous_formula(self):
        source = 'Energy uses velocity.\n\nMMD uses Chamfer Distance.'
        a = self.check(source, [entity('MMD', 'Metric'), entity('velocity'), entity('Chamfer Distance', 'Metric')],
                       [relation('MMD', 'velocity', 'DERIVED_FROM', 'velocity', 'definition'),
                        relation('MMD', 'Chamfer Distance', 'USES', 'MMD uses Chamfer Distance.', 'definition')])
        self.assertEqual(a['relationships'], 1)
        self.assertIn('unrelated source paragraphs', a['withheld_records'][0]['reason'])

    def test_parallel_initialization_clauses_accept_first_source_not_sibling(self):
        source = 'Branch projections are initialized from Cross, and keys from Self.'
        es = [entity('Branch projections'), entity('Cross', 'Method'), entity('Self', 'Method')]
        a = self.check(source, es, [relation('Branch projections', 'Cross', 'INITIALIZED_FROM', source)])
        self.assertEqual(a['relationships'], 1)
        wrong = 'Branch projections and Cross are initialized from Self.'
        a = self.check(wrong, es, [relation('Branch projections', 'Cross', 'INITIALIZED_FROM', wrong)])
        self.assertEqual(a['relationships'], 0)

    def test_table_row_ownership_and_ambiguous_headers_are_enforced(self):
        source = 'Paper title: Atlas\nRow label: Baseline†\nCell [MMD]: 1.2'
        es = [entity('Atlas', 'Method'), entity('Baseline', 'Method'), entity('MMD', 'Metric')]
        a = self.check(source, es, [relation('Atlas', 'MMD', 'REPORTS', 'Cell [MMD]: 1.2', 'evaluation'),
                                   relation('Baseline', 'MMD', 'REPORTS', 'Cell [MMD]: 1.2', 'evaluation')])
        self.assertEqual(a['relationships'], 1)
        self.assertIn('row owner', a['withheld_records'][0]['reason'])
        a = self.check(source + '\nTABLE_METRIC_ALIGNMENT: ambiguous', es,
                       [relation('Baseline', 'MMD', 'REPORTS', 'Cell [MMD]: 1.2', 'evaluation')])
        self.assertEqual(a['relationships'], 0)

    def test_dataset_generator_is_distinct_from_root_method(self):
        source = 'Paper title: Atlas: A model\nSection: DATASET GENERATOR DETAILS\nCorpus uses boxes.'
        es = [entity('Atlas', 'Method'), entity('Corpus', 'Dataset'), entity('boxes')]
        a = self.check(source, es, [relation('Atlas', 'boxes', 'USES', 'Corpus uses boxes.', 'dataset_construction'),
                                   relation('Corpus', 'boxes', 'CONSTRUCTED_FROM', 'Corpus uses boxes.', 'dataset_construction')])
        self.assertEqual(a['relationships'], 1)
        self.assertIn('root inference method', a['withheld_records'][0]['reason'])

    def test_source_quotes_are_not_silently_rewritten(self):
        a = self.check('Atlas usesCorpus.', [entity('Atlas', 'Method'), entity('Corpus')],
                       [relation('Atlas', 'Corpus', 'USES', 'Atlas uses Corpus.')])
        self.assertEqual(a['relationships'], 0)

    def test_natural_application_relation_does_not_masquerade_as_evaluation(self):
        source = 'Scene reconstruction supports applications such as VR/AR.'
        es = [entity('Scene reconstruction'), entity('VR/AR')]
        a = self.check(source, es, [relation('Scene reconstruction', 'VR/AR', 'APPLICABLE_TO', source, 'application'),
                                   relation('Scene reconstruction', 'VR/AR', 'EVALUATED_ON', source, 'application')])
        self.assertEqual(a['relationships'], 1)

    def test_provider_resume_restores_json_history_and_scoped_endpoint_declarations(self):
        source = 'Atlas uses Corpus.'
        raw = GraphRecords(entities=[entity('Atlas', 'Method'), entity('Corpus'), entity('Invented')], relationships=[])
        continuation = GraphRecords(entities=[], relationships=[relation('Atlas', 'Corpus', 'USES', source)])
        prompt = EXTRACTION_PROMPT.format(entity_types='Method,Concept', input_text=source)
        with tempfile.TemporaryDirectory() as folder:
            runtime = fixtures.ProviderContracts().runtime(folder, calls=3)
            runtime.client.chat.completions.create.return_value = fixtures.ProviderContracts().response(content=raw.model_dump_json())
            initial = runtime.complete(prompt).content
            runtime.close()
            runtime = fixtures.ProviderContracts().runtime(folder, calls=3)
            runtime.client.chat.completions.create.return_value = fixtures.ProviderContracts().response(content=continuation.model_dump_json())
            response = runtime.complete([{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': initial},
                                         {'role': 'user', 'content': 'Find additional records.'}])
            self.assertIn('USES [method]', response.content)
            sent = runtime.client.chat.completions.create.call_args.kwargs['messages']
            self.assertEqual(json.loads(sent[1]['content']), raw.model_dump())
            self.assertIn('Validation withheld', sent[-1]['content'])
            self.assertIn('Invented', sent[-1]['content'])
            runtime.close()
