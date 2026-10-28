"""Upload handoff, retained extraction, and server-owned question identity."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import test_gui as gui_fixtures
GUI_AVAILABLE = all(importlib.util.find_spec(name) for name in ('fastapi','httpx'))
if GUI_AVAILABLE:
    from fastapi.testclient import TestClient
    from pbl_docintel.gui.server import Workspace, create_app
    from pbl_docintel.gui.imports import Imports
    from pbl_docintel.gui.rag_worker import run_question


@unittest.skipUnless(GUI_AVAILABLE, 'Install .[gui,test]')
class UploadHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_bytes_must_be_confirmed_before_processing_and_restart_keeps_job(self):
        content = b'%PDF-1.4\nfixture'
        with patch.object(Imports, 'run') as worker, TestClient(create_app(self.root)) as client:
            response = client.post('/api/imports/start', json={'filename':'paper.pdf','size':len(content)})
            self.assertEqual(response.status_code, 202)
            location = response.headers['location']
            self.assertEqual(response.headers['retry-after'], '2')
            self.assertEqual(response.json()['status'], 'uploading')
            worker.assert_not_called()
            self.assertEqual(client.post(location + '/retry').status_code, 409)
            sent = client.put(location + '/file', content=content)
            self.assertEqual(sent.status_code, 202)
            self.assertEqual(sent.json()['completed_stages'], ['upload'])
            self.assertEqual(client.put(location + '/file', content=content).status_code, 409)
            self.assertEqual(client.post(location + '/cancel').json()['status'], 'cancelled')
        with TestClient(create_app(self.root)) as client:
            self.assertEqual(client.get(location).json()['status'], 'cancelled')

    def test_partial_upload_is_failed_not_registered_or_retriable(self):
        with patch.object(Imports,'run') as worker, TestClient(create_app(self.root)) as client:
            location = client.post('/api/imports/start',json={'filename':'paper.pdf','size':100}).headers['location']
            self.assertEqual(client.put(location+'/file',content=b'%PDF-').status_code,400)
            self.assertEqual(client.get(location).json()['status'],'failed')
            self.assertEqual(client.post(location+'/retry').status_code,409)
            self.assertEqual(client.get('/api/papers').json(),[])
            worker.assert_not_called()

    def test_duplicate_transfer_keeps_first_stream_and_cancel_prevents_upload(self):
        with TestClient(create_app(self.root)) as client:
            response = client.post('/api/imports/start',json={'filename':'paper.pdf','size':5})
            location = response.headers['location']
            part = self.root / 'data/uploads' / response.json()['job_id'] / 'source.pdf.part'
            part.write_bytes(b'first transfer')
            self.assertEqual(client.put(location+'/file',content=b'%PDF-').status_code,409)
            self.assertEqual(part.read_bytes(),b'first transfer')
            client.post(location+'/cancel')
            self.assertEqual(client.put(location+'/file',content=b'%PDF-').status_code,409)

    def test_upload_schema_and_foreign_origin(self):
        with TestClient(create_app(self.root)) as client:
            self.assertEqual(client.post('/api/imports/start',json={'filename':'x.pdf','size':0}).status_code,422)
            self.assertEqual(client.post('/api/imports/start',json={'filename':'x.exe','size':5}).status_code,400)
            self.assertEqual(client.post('/api/imports/start',json={'filename':'x.pdf','size':5},headers={'Origin':'https://foreign.example'}).status_code,403)

    def test_retry_recovers_export_saved_before_event_and_worker_uses_utf8(self):
        workspace = Workspace(self.root)
        manager = Imports(workspace)
        self.addCleanup(manager.close)
        manager.start_upload('recover','paper.pdf','Paper',False,5)
        pdf = self.root / 'data/uploads/recover/source.pdf'
        pdf.write_bytes(b'%PDF-')
        previous = self.root / 'data/preparations/recover/attempt-1-output/converted'
        previous.mkdir(parents=True)
        (previous/'document.json').write_text('{}')
        (previous/'conversion_report.json').write_text(json.dumps({'status':'success','source':str(pdf),'pages':1}))
        (previous.parent.parent/'attempt-1.json').write_text(json.dumps({'output':'data/preparations/recover/attempt-1-output'}))
        manager.update('recover',status='queued',attempt=1)
        process = MagicMock()
        process.stdout = __import__('io').StringIO('')
        process.poll.return_value = process.wait.return_value = 1
        with patch('pbl_docintel.gui.imports.subprocess.Popen',return_value=process) as popen:
            manager.run('recover')
        spec = json.loads((previous.parent.parent/'attempt-2.json').read_text())
        self.assertEqual(spec['document'],str((previous/'document.json').relative_to(self.root)))
        self.assertEqual(popen.call_args.args[0][1:4],['-X','utf8','-u'])


@unittest.skipUnless(GUI_AVAILABLE, 'Install .[gui,test]')
class PaperQuestionTests(unittest.TestCase):
    setUp = gui_fixtures.WorkspaceTests.setUp
    save_manifest = gui_fixtures.WorkspaceTests.save_manifest

    def test_waiting_worker_remains_active_and_cancel_terminates_it(self):
        import subprocess
        import sys
        from threading import Event, Thread
        from datetime import datetime, timezone, timedelta
        workspace=self.client.app.state.workspace
        workspace.set_rag_status('fixture:v1',status='ready',index_id='server-selected',
            document_sha256=hashlib.sha256(self.docling.read_bytes()).hexdigest(),
            source_sha256=hashlib.sha256(self.pdf.read_bytes()).hexdigest())
        manager=self.client.app.state.questions
        with patch.object(manager,'run'):
            job=manager.create('fixture:v1','Explain this paper')
        qid=job['question_id']
        waiting=Event()
        original_update=manager.update
        def update(*args,**fields):
            value=original_update(*args,**fields)
            if fields.get('retry'):waiting.set()
            return value
        retry={'stage':'answer generation','reason':'rate_limit','retry_number':1,'maximum_retries':2,
               'retry_at':(datetime.now(timezone.utc)+timedelta(seconds=30)).isoformat()}
        event='SANTIO_EVENT:'+json.dumps({'stage':'Waiting to retry','retry':retry})
        child_code='import time; print('+repr(event)+',flush=True); time.sleep(30)'
        popen=subprocess.Popen
        def spawn(*args,**kwargs):
            if 'pbl_docintel.gui.rag_worker' in args[0]:
                return popen([sys.executable,'-u','-c',child_code],**kwargs)
            return popen(*args,**kwargs)
        thread=Thread(target=manager.run,args=(qid,))
        with patch('pbl_docintel.gui.questions.subprocess.Popen',side_effect=spawn), \
             patch.object(manager,'update',side_effect=update), patch.dict('os.environ',{'SANTIO_RAG_TRACE':'0'}):
            thread.start()
            try:
                self.assertTrue(waiting.wait(5),'Worker did not report waiting')
                current=self.client.get('/api/questions/'+qid).json()
                self.assertEqual(current['status'],'processing')
                self.assertEqual(current['retry'],retry)
                process=manager.processes[qid]
                # Use the real process terminator; no model or database request.
                cancelled=self.client.post('/api/questions/'+qid+'/cancel').json()
                self.assertEqual(cancelled['status'],'cancelled')
                self.assertIsNone(cancelled['retry'])
                thread.join(5)
                self.assertFalse(thread.is_alive())
                self.assertIsNotNone(process.poll())
                self.assertNotIn(qid,manager.processes)
            finally:
                manager.cancel(qid)
                thread.join(5)

    def test_question_worker_publishes_retry_deadline_and_clears_it_when_resuming(self):
        spec={'pdf':'sample.pdf','document':'document.json','index_id':'selected','trace':'question.trace.json',
              'source_sha256':hashlib.sha256(self.pdf.read_bytes()).hexdigest(),
              'document_sha256':hashlib.sha256(self.docling.read_bytes()).hexdigest(),'question':'Explain'}
        retry={'stage':'answer generation','reason':'rate_limit','retry_number':1,'maximum_retries':2,
               'retry_at':'2026-10-23T12:00:00+00:00'}
        def answer(*args,**kwargs):
            kwargs['on_trace']('Provider retry waiting',retry)
            kwargs['on_trace']('Provider retry resumed',{'stage':'answer generation'})
            return {'answer':{'status':'answered'}}
        with patch('pbl_docintel.vector_rag.vector_index.connect_database') as connect, \
             patch('pbl_docintel.vector_rag.rag.answer_question',side_effect=answer), \
             patch('pbl_docintel.gui.rag_worker.emit') as emit, patch.dict('os.environ',{'SANTIO_RAG_TRACE':'0'}):
            connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value=(
                {'identity':{'source_sha256':spec['document_sha256']}},)
            run_question(self.root,spec)
        published=[c.kwargs for c in emit.call_args_list if 'retry' in c.kwargs]
        self.assertEqual(published,[{'stage':'Waiting to retry','retry':retry},
                                    {'stage':'Retrying answer generation','retry':None}])

    def test_worker_model_output_is_teed_to_backend_terminal_and_retained_log(self):
        import io
        from contextlib import redirect_stderr
        workspace = self.client.app.state.workspace
        workspace.set_rag_status('fixture:v1',status='ready',index_id='server-selected',
            document_sha256=hashlib.sha256(self.docling.read_bytes()).hexdigest(),
            source_sha256=hashlib.sha256(self.pdf.read_bytes()).hexdigest())
        manager = self.client.app.state.questions
        with patch.object(manager,'run'):
            job = manager.create('fixture:v1','Explain this paper')
        qid = job['question_id']
        report = {'answer':{'status':'answered','claims':[]}, 'retrieval':{}, 'sources':[], 'total_seconds':1}
        (self.root/f'data/question-jobs/{qid}.trace.json').write_text(json.dumps(report),encoding='utf-8')
        process = MagicMock()
        process.stdout = io.StringIO('SANTIO_EVENT:{"stage":"Writing answer"}\n'
                                    '=== RAG / Raw answer model response ===\n'
                                    '{"content":"model said hello", "secret":"test-nv-key"}\n')
        process.wait.return_value = process.poll.return_value = 0
        output = io.StringIO()
        with patch('pbl_docintel.gui.questions.subprocess.Popen',return_value=process), \
             patch.dict('os.environ',{'SANTIO_RAG_TRACE':'1','NVIDIA_API_KEY':'test-nv-key'}), redirect_stderr(output):
            manager.run(qid)
        self.assertEqual(manager.get(qid)['status'],'completed')
        self.assertIn(f'[RAG {qid[:8]}] Writing answer',output.getvalue())
        self.assertIn('Raw answer model response',output.getvalue())
        self.assertIn('model said hello',output.getvalue())
        saved=(self.root/f'data/question-jobs/{qid}.log').read_text(encoding='utf-8')
        self.assertIn('model said hello',saved)
        self.assertNotIn('test-nv-key',output.getvalue()+saved)

    def test_preparation_deduplicates_and_no_arbitrary_index_is_accepted(self):
        with patch.object(Imports,'run'):
            a = self.client.post('/api/papers/fixture:v1/prepare')
            b = self.client.post('/api/papers/fixture:v1/prepare')
            self.assertEqual(a.status_code,202)
            self.assertEqual(a.json()['job_id'],b.json()['job_id'])
            self.client.post('/api/imports/'+a.json()['job_id']+'/cancel')
        endpoint = '/api/papers/fixture:v1/questions'
        self.assertEqual(self.client.post(endpoint,json={'question':'What is it?'}).status_code,409)
        self.assertEqual(self.client.post(endpoint,json={'question':'What is it?','index_id':'other'}).status_code,422)
        self.assertEqual(self.client.post(endpoint,json={'question':' '}).status_code,422)
        self.assertEqual(self.client.get('/api/questions/missing').status_code,404)

    def test_questions_bind_saved_paper_and_restart_preserves_history(self):
        workspace = self.client.app.state.workspace
        workspace.set_rag_status('fixture:v1',status='ready',index_id='server-selected',
            document_sha256=hashlib.sha256(self.docling.read_bytes()).hexdigest(),
            source_sha256=hashlib.sha256(self.pdf.read_bytes()).hexdigest())
        manager = self.client.app.state.questions
        with patch.object(manager,'run'):
            response = self.client.post('/api/papers/fixture:v1/questions',json={'question':'Explain this paper.'})
            self.assertEqual(response.status_code,202)
            qid = response.json()['question_id']
            spec = json.loads((self.root / f'data/question-jobs/{qid}.input.json').read_text())
            self.assertEqual(spec['index_id'],'server-selected')
            self.assertEqual(spec['document'],'document.json')
            self.assertEqual(self.client.get('/api/papers/fixture:v1/questions').json()[0]['question_id'],qid)
            manager.cancel(qid)
        from concurrent.futures import ThreadPoolExecutor
        from pbl_docintel.gui.questions import Questions
        with ThreadPoolExecutor(1) as executor:
            restored = Questions(Workspace(self.root),executor)
            self.assertEqual(restored.get(qid)['status'],'cancelled')

    def test_wrong_index_or_changed_pdf_never_reaches_answer_model(self):
        spec = {'pdf':'sample.pdf','document':'document.json','index_id':'foreign-index',
                'source_sha256':hashlib.sha256(self.pdf.read_bytes()).hexdigest(),
                'document_sha256':hashlib.sha256(self.docling.read_bytes()).hexdigest()}
        with patch('pbl_docintel.vector_rag.rag.answer_question') as answer, patch('pbl_docintel.vector_rag.vector_index.connect_database') as connect:
            connection = connect.return_value.__enter__.return_value
            connection.execute.return_value.fetchone.return_value = ({'identity':{'source_sha256':'other'}},)
            with self.assertRaisesRegex(ValueError,'does not match'):
                run_question(self.root,spec)
            self.pdf.write_bytes(b'%PDF-changed')
            with self.assertRaisesRegex(ValueError,'PDF changed'):
                run_question(self.root,spec)
            answer.assert_not_called()

    def test_fresh_questions_have_no_hidden_history_and_followups_are_scoped(self):
        workspace=self.client.app.state.workspace
        workspace.set_rag_status('fixture:v1',status='ready',index_id='server-selected',
            document_sha256=hashlib.sha256(self.docling.read_bytes()).hexdigest(),
            source_sha256=hashlib.sha256(self.pdf.read_bytes()).hexdigest())
        manager=self.client.app.state.questions
        endpoint='/api/papers/fixture:v1/questions'
        with patch.object(manager,'run'):
            first=self.client.post(endpoint,json={'question':'Explain this paper'}).json()
            manager.update(first['question_id'],status='completed',result={'answer':{'claims':[{'text':'A sourced answer'}]}})
            fresh=self.client.post(endpoint,json={'question':'A fresh request'}).json()
            spec=json.loads((self.root/f"data/question-jobs/{fresh['question_id']}.input.json").read_text())
            self.assertEqual(spec['history'],[])
            follow=self.client.post(endpoint,json={'question':'Explain that further','context_question_id':first['question_id']}).json()
            spec=json.loads((self.root/f"data/question-jobs/{follow['question_id']}.input.json").read_text())
            self.assertEqual(spec['history'],[{'question':'Explain this paper','answer':'A sourced answer'}])
            self.assertEqual(self.client.post(endpoint,json={'question':'q','context_question_id':fresh['question_id']}).status_code,409)
            manager.jobs[first['question_id']]['paper_id']='other-paper'
            self.assertEqual(self.client.post(endpoint,json={'question':'q','context_question_id':first['question_id']}).status_code,409)
            manager.cancel(fresh['question_id']);manager.cancel(follow['question_id'])

    def test_extraction_survives_index_failure_and_retry_reuses_it(self):
        manager = self.client.app.state.imports
        with patch.object(manager,'run'):
            job = manager.prepare('fixture:v1')
        manager._extracted(job['job_id'],{'document':'document.json','evidence_index':'evidence.json','conversion_status':'success','pages':1})
        manager.update(job['job_id'],status='failed',error='Database unavailable',chunks_file='saved/chunks.jsonl')
        self.assertEqual(self.client.get('/api/papers/fixture:v1').status_code,200)
        self.assertEqual(Workspace(self.root).papers['fixture:v1']['docling_json'],'document.json')
        with patch.object(manager,'run'):
            retried = manager.retry(job['job_id'])
        self.assertEqual(retried['paper_id'],'fixture:v1')
        self.assertEqual(retried['chunks_file'],'saved/chunks.jsonl')
        manager.cancel(job['job_id'])

    def test_search_export_is_the_actual_indexed_input(self):
        chunks = self.root / 'chunks.jsonl'
        chunks.write_text('{"contextualized_text":"actual indexed passage"}\n')
        workspace = self.client.app.state.workspace
        workspace.set_rag_status('fixture:v1',status='ready',chunks_file='chunks.jsonl',
            document_sha256=hashlib.sha256(self.docling.read_bytes()).hexdigest())
        self.assertIn('search_chunks',self.client.get('/api/papers/fixture:v1').json()['exports'])
        response = self.client.get('/api/papers/fixture:v1/exports/search_chunks')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content,chunks.read_bytes())


if __name__ == '__main__':
    unittest.main()
