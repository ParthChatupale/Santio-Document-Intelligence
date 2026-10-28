from pathlib import Path
import sys
import tempfile
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import write_json, read_json, digest
from prepare_context_v3 import prepare


class PreparationV3(TestCase):
    def fixture(self, folder, rows):
        source = folder / 'original.json'
        write_json(source, {'unchanged': True})
        prepared = folder / 'prepared'
        records, sources = [], {}
        for index, (kind, heading, body) in enumerate(rows):
            ident = f'record-{index}'
            ref = f'#/texts/{index}'
            text = f'Paper title: Atlas\nSection: {heading}\n\n{body}'
            records.append({'id': ident, 'content_kind': kind, 'headings': [heading],
                            'docling_refs': [ref], 'text': text})
            sources[ident] = {'record_id': ident, 'item_refs': [ref], 'content': text,
                              'pages': [index + 1], 'locations': {ref: []}}
        write_json(prepared / 'input/documents.json', records)
        write_json(prepared / 'source_map.json', sources)
        write_json(prepared / 'headings.json', [])
        write_json(prepared / 'preparation_report.json', {'source': str(source), 'source_sha256': digest(source)})
        return prepared

    def test_adjacent_definition_fragments_keep_both_pages_and_references(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared = self.fixture(root, [('text', 'Metrics', 'MMD is a distance metric.'),
                                           ('text', 'Metrics', 'It uses Chamfer Distance.')])
            result = prepare(prepared, root / 'new')
            records = read_json(root / 'new/input/documents.json')
            source = read_json(root / 'new/source_map.json')[records[0]['id']]
            self.assertEqual(result['parent_records_accounted'], 2)
            self.assertEqual(len(records), 1)
            self.assertEqual(source['pages'], [1, 2])
            self.assertEqual(source['item_refs'], ['#/texts/0', '#/texts/1'])
            self.assertIn('MMD is a distance metric.\n\nIt uses Chamfer Distance.', source['content'])

    def test_independent_substantial_paragraphs_and_headings_are_not_swallowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = 'A distinct technical statement. ' * 35
            prepared = self.fixture(root, [('text', 'Introduction', body),
                                           ('text', 'Introduction', body), ('text', 'Method', 'Short definition.')])
            prepare(prepared, root / 'new')
            records = read_json(root / 'new/input/documents.json')
            self.assertEqual(len(records), 3)

    def test_ambiguous_header_path_is_marked_without_guessing_or_losing_cell(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = 'Row label: Baseline\nCell [CD ↓ F1 ↑]: 0.3'
            prepared = self.fixture(root, [('table', 'Results', body)])
            prepare(prepared, root / 'new')
            record = read_json(root / 'new/input/documents.json')[0]
            self.assertTrue(record['table_metric_alignment_ambiguous'])
            self.assertIn('TABLE_METRIC_ALIGNMENT: ambiguous', record['text'])
            self.assertIn(body, record['text'])
            self.assertEqual(read_json(prepared / 'input/documents.json')[0]['text'].count('TABLE_METRIC_ALIGNMENT'), 0)

    def test_new_named_definition_does_not_inherit_previous_formula_variables(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared = self.fixture(root, [('text', 'Metrics', 'where velocity measures object motion.'),
                                           ('text', 'Metrics', 'MMD and COV. We use Chamfer Distance.')])
            prepare(prepared, root / 'new')
            self.assertEqual(len(read_json(root / 'new/input/documents.json')), 2)
