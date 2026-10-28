import copy
from pathlib import Path
import sys
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _contracts import GraphRecords, project
from audit_isolates import replay_with_prior_declarations, verify_viewer


class IsolationAudit(TestCase):
    source = 'Atlas is trained on Corpus and evaluated on Bench.'

    def records(self, entities, relationships=()):
        return GraphRecords.model_validate({'entities': [
            {'name': name, 'type': kind, 'description': name} for name, kind in entities],
            'relationships': list(relationships)})

    def relation(self, evidence=None, target='Corpus'):
        return {'source': 'Atlas', 'target': target, 'kind': 'TRAINED_ON',
                'description': 'Atlas training', 'evidence': evidence or self.source}

    def test_prior_declaration_experiment_reproduces_scope_loss_without_mutating_records(self):
        prior = self.records([('Atlas', 'Method'), ('Corpus', 'Dataset')])
        current = self.records([], [self.relation()])
        original = copy.deepcopy((prior.model_dump(), current.model_dump()))
        self.assertEqual(project(current, self.source)[1]['relationships'], 0)
        passed, conflicts = replay_with_prior_declarations(current, prior, self.source)
        self.assertEqual(len(passed), 1)
        self.assertEqual(conflicts, [])
        self.assertEqual((prior.model_dump(), current.model_dump()), original)

    def test_prior_rejected_or_non_source_entities_cannot_authorize_relationship(self):
        prior = self.records([('Atlas', 'Method'), ('Invented', 'Dataset')])
        current = self.records([], [self.relation(target='Invented')])
        self.assertEqual(replay_with_prior_declarations(current, prior, self.source)[0], [])

    def test_type_conflict_cannot_authorize_recovery(self):
        prior = self.records([('Atlas', 'Concept'), ('Corpus', 'Dataset')])
        current = self.records([('Atlas', 'Method')], [self.relation()])
        passed, conflicts = replay_with_prior_declarations(current, prior, self.source)
        self.assertEqual(passed, [])
        self.assertEqual(conflicts, ['atlas'])

    def test_scope_experiment_preserves_quotation_and_role_constraints(self):
        prior = self.records([('Atlas', 'Method'), ('Corpus', 'Dataset'), ('Bench', 'Concept')])
        current = self.records([], [self.relation(evidence='A fabricated quotation'),
                                    self.relation(target='Bench')])
        self.assertEqual(replay_with_prior_declarations(current, prior, self.source)[0], [])

    def test_no_relationship_is_created_for_an_isolated_mention(self):
        prior = self.records([('Atlas', 'Method'), ('Corpus', 'Dataset')])
        current = self.records([])
        self.assertEqual(replay_with_prior_declarations(current, prior, self.source)[0], [])

    def test_viewer_check_detects_missing_edges_and_swapped_mapping(self):
        entities = [{'id': 'a', 'title': 'Atlas'}, {'id': 'b', 'title': 'Corpus'}]
        edges = [{'id': 'e', 'source': 'Atlas', 'target': 'Corpus'}]
        payload = {'nodes': [{'id': 'a', 'label': 'Atlas'}, {'id': 'b', 'label': 'Corpus'}],
                   'edges': [{'id': 'e', 'source': 'a', 'target': 'b'}]}
        self.assertEqual(verify_viewer(entities, edges, payload)['wrong_endpoint_mappings'], [])
        payload['edges'][0]['source'] = 'b'
        self.assertEqual(verify_viewer(entities, edges, payload)['wrong_endpoint_mappings'], ['e'])
        payload['edges'] = []
        self.assertEqual(verify_viewer(entities, edges, payload)['missing_edge_ids'], ['e'])

    def test_quote_matching_alone_does_not_establish_ownership(self):
        # Regression proof of a LIMITATION of the existing contract. The audit
        # must not label every mechanically recovered record a true fact.
        source = ('Paper title: Atlas. Section: DATASET GENERATOR DETAILS. '
                  'We use boxes to create training scenes.')
        prior = self.records([('Atlas', 'Method'), ('boxes', 'Concept')])
        relation = {'source': 'Atlas', 'target': 'boxes', 'kind': 'USES',
                    'description': 'Atlas inference uses boxes',
                    'evidence': 'We use boxes to create training scenes.'}
        passed, _ = replay_with_prior_declarations(self.records([], [relation]), prior, source)
        self.assertEqual(len(passed), 1)
        # This test intentionally demonstrates why candidates are NOT promoted.

    def test_reproduces_overbroad_metric_dependency_rejection(self):
        source = 'MMD uses Chamfer Distance as the underlying distance measure.'
        records = self.records([('MMD', 'Metric'), ('Chamfer Distance', 'Metric')], [
            {'source': 'MMD', 'target': 'Chamfer Distance', 'kind': 'USES',
             'description': source, 'evidence': source}])
        _, audit = project(records, source)
        self.assertEqual(audit['relationships'], 0)
        self.assertEqual(audit['withheld_records'][0]['reason'],
                         'A reported metric is not a method component or tool')

    def test_reproduces_last_from_clause_false_rejection(self):
        source = ('We initialize branch projections from pretrained cross-attention, '
                  'and key/value projections from self-attention.')
        records = self.records([('branch projections', 'Concept'),
                                ('pretrained cross-attention', 'Method')], [
            {'source': 'branch projections', 'target': 'pretrained cross-attention',
             'kind': 'INITIALIZED_FROM', 'description': 'Branch weights source', 'evidence': source}])
        _, audit = project(records, source)
        self.assertEqual(audit['relationships'], 0)
        self.assertEqual(audit['withheld_records'][0]['reason'],
                         'Initialization target is not the stated source of weights')
