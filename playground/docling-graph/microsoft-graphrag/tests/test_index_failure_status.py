"""A failed native workflow must remain inspectable without masking its cause."""
import asyncio
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import index_graph
from _common import read_json, write_json


class IndexFailureStatus(TestCase):
    def test_unfinished_native_tables_do_not_enter_final_id_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            write_json(folder / 'run.json', {'status': 'staged', 'input_sha256': 'same',
                       'source': str(folder / 'source.json'), 'source_sha256': 'same'})
            runtime = SimpleNamespace(calls=[], prior_elapsed=0, model='test',
                                      base='https://example.invalid', key='',
                                      close=Mock(), save=Mock())
            failure = SimpleNamespace(workflow='extract_graph', error='Provider request failed: 429')
            with patch('index_graph.digest', return_value='same'), \
                 patch('_providers.configure', return_value=runtime), \
                 patch('index_graph.load_config'), \
                 patch('graphrag.api.build_index', new=AsyncMock(return_value=[failure])), \
                 patch('index_graph.export_tables', return_value={'entities': 2}), \
                 patch('index_graph.coverage_audit', side_effect=KeyError('id')) as audit:
                result = asyncio.run(index_graph.execute(folder))
            audit.assert_not_called()
            self.assertEqual(result['status'], 'partial_or_failed')
            self.assertIn('429', result['workflows_failed'][0]['error'])
            self.assertNotIn('error', result)
            self.assertEqual(read_json(folder / 'progress.json')['state'], 'partial_or_failed')
