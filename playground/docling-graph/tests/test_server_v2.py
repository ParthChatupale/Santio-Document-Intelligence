"""HTTP contracts with a saved run; model responses are mocked here."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))


class WorkspaceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from server_v2 import create_app
        cls.folder=HERE/'outputs/2610.10539v1-v2-direct-20261016T065635720877Z'
        if not cls.folder.exists():raise unittest.SkipTest('Saved integration run unavailable; unit checks still run')
        cls.client=TestClient(create_app(cls.folder))

    def test_overview_and_graph(self):
        r=self.client.get('/api/overview')
        self.assertEqual(r.status_code,200)
        self.assertGreater(r.json()['run']['measurements'],0)
        self.assertTrue(self.client.get('/api/graph').json()['edges'])

    def test_overview_does_not_promote_unresolved_dependencies(self):
        import json
        from tempfile import TemporaryDirectory
        from retrieval_v2 import write_understanding
        from research_schema_v2 import ResearchPaper,Method
        raw=ResearchPaper(title='Fixture',methods=[Method(name='A',components=[Method(name='Unresolved')])])
        with TemporaryDirectory() as directory:
            folder=Path(directory)
            for name,data in [('normalized_records.json',[raw.model_dump()]),('graph.json',{'nodes':[],'edges':[]}),('usable_graph.json',{'nodes':[],'edges':[]})]:
                (folder/name).write_text(json.dumps(data),encoding='utf-8')
            write_understanding(folder)
            result=json.loads((folder/'understanding.json').read_text(encoding='utf-8'))
            self.assertEqual(result['methods'][0]['components'],[])

    def test_unknown_evidence_is_404(self):
        self.assertEqual(self.client.get('/api/evidence',params={'ref':'missing'}).status_code,404)
        self.assertEqual(self.client.get('/api/evidence',params={'ref':'#/texts/411'}).status_code,200)

    def test_invalid_question_does_not_call_model(self):
        with patch('retrieval_v2.ResearchWorkspace.ask') as model:
            self.assertEqual(self.client.post('/api/ask',json={'question':''}).status_code,422)
            model.assert_not_called()
        self.assertEqual(self.client.get('/api/retrieve',params={'question':' '}).status_code,400)

    def test_ask_body_and_provider_error_redaction(self):
        with patch('retrieval_v2.ResearchWorkspace.ask',return_value={'answer':'Example [S1]'}) as model:
            r=self.client.post('/api/ask',json={'question':'A question','use_graph':False})
            self.assertEqual(r.status_code,200)
            model.assert_called_once_with('A question',use_graph=False)
        with patch('retrieval_v2.ResearchWorkspace.ask',side_effect=RuntimeError('failed unit-test-secret')),patch('sandbox.load_connection',return_value=('model','url','unit-test-secret')):
            from fastapi.testclient import TestClient
            from server_v2 import create_app
            # create_app binds its connection loader; patch before constructing it.
            r=TestClient(create_app(self.folder)).post('/api/ask',json={'question':'A question'})
            self.assertEqual(r.status_code,502)
            self.assertNotIn('unit-test-secret',r.text)


if __name__=='__main__':unittest.main()
