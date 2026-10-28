"""Optional graph routing must not leak another paper's graph or change RAG."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pbl_docintel.gui.server import create_app


class GraphFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'data').mkdir()
        self.pdf = self.root / 'a.pdf'
        self.pdf.write_bytes(b'%PDF-1.4\nPaper A')
        (self.root / 'b.pdf').write_bytes(b'%PDF-1.4\nPaper B')
        papers = [{'paper_id': name, 'title': name, 'source_pdf': name+'.pdf',
                   'status': 'source_only', 'role': 'test'} for name in ['a','b']]
        (self.root / 'data/corpus.json').write_text(json.dumps({'papers': papers}))
        self.run = self.root / 'data/graph-rag/artifacts/a/run-v1'
        self.run.mkdir(parents=True)
        (self.run / 'run.json').write_text(json.dumps({'status':'completed','source_sha256':'docling',
            'native_tables':{'entities':3,'relationships':2}}))
        (self.run / 'coverage.json').write_text(json.dumps({'processing_complete':True}))
        self.registry = self.root / 'data/graph-rag/registry.json'
        self.registry.write_text(json.dumps({'python':sys.executable,'papers':{'a':{
            'run':'data/graph-rag/artifacts/a/run-v1','run_name':'run-v1',
            'docling_sha256':'docling','pdf_sha256':hashlib.sha256(self.pdf.read_bytes()).hexdigest()}}}))

    def test_only_registered_paper_gets_graph_and_no_worker_starts_for_library(self):
        with TestClient(create_app(self.root)) as client:
            self.assertEqual(len(client.get('/api/papers').json()),2)
            self.assertEqual(client.app.state.graphs.workers,{})
            self.assertTrue(client.get('/api/papers/a/graph').json()['available'])
            self.assertEqual(client.get('/api/papers/b/graph').json()['status'],'not_prepared')
            self.assertEqual(client.get('/api/papers/missing/graph').status_code,404)
            self.assertEqual(client.get('/api/papers/b/questions').json(),[])
            self.assertEqual(client.app.state.graphs.workers,{})

    def test_changed_pdf_cannot_use_old_graph(self):
        with TestClient(create_app(self.root)) as client:
            self.assertTrue(client.get('/api/papers/a/graph').json()['available'])
            self.pdf.write_bytes(b'%PDF-1.4\nAnother PDF version')
            result=client.get('/api/papers/a/graph').json()
            self.assertFalse(result['available'])
            self.assertIn('different PDF',result['message'])

    def test_paths_outside_graph_storage_and_incomplete_runs_are_unavailable(self):
        with TestClient(create_app(self.root)) as client:
            (self.run/'coverage.json').write_text('{"processing_complete":false}')
            self.assertFalse(client.get('/api/papers/a/graph').json()['available'])
            registry=json.loads(self.registry.read_text())
            registry['papers']['a']['run']='data/other'
            self.registry.write_text(json.dumps(registry))
            self.assertIn('artifact directory',client.get('/api/papers/a/graph').json()['message'])

    def test_graph_frame_has_self_embedding_only_and_other_routes_keep_policy(self):
        with TestClient(create_app(self.root)) as client:
            graphs=client.app.state.graphs
            with patch.object(graphs,'proxy',return_value=(200,b'<html>graph</html>','text/html')):
                frame=client.get('/api/papers/a/graph/view/')
                self.assertEqual(frame.status_code,200)
                self.assertIn("frame-ancestors 'self'",frame.headers['content-security-policy'])
            regular=client.get('/api/papers')
            self.assertIn("frame-ancestors 'none'",regular.headers['content-security-policy'])

    def test_cross_site_and_oversized_questions_never_reach_worker(self):
        with TestClient(create_app(self.root)) as client:
            with patch.object(client.app.state.graphs,'proxy') as proxy:
                url='/api/papers/a/graph/view/api/questions'
                self.assertEqual(client.post(url,json={'question':'hi'},headers={'Origin':'https://other.example'}).status_code,403)
                self.assertEqual(client.post(url,content=b'x'*32001).status_code,400)
                proxy.assert_not_called()

    def test_unknown_worker_resources_do_not_start_processes(self):
        with TestClient(create_app(self.root)) as client:
            with patch.object(client.app.state.graphs,'_worker') as worker:
                self.assertEqual(client.get('/api/papers/a/graph/view/private.json').status_code,404)
                worker.assert_not_called()


if __name__ == '__main__':
    unittest.main()
