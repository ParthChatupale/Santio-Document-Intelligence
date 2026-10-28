"""Observable model output without credential disclosure or terminal failures."""
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pbl_docintel.vector_rag.terminal import TerminalTrace
from pbl_docintel.vector_rag.rag import call_answer_model
from pbl_docintel.vector_rag.retrieval import plan_query, rerank_sources


class TerminalTraceTests(unittest.TestCase):
    def test_nested_secrets_and_secret_text_are_redacted_before_json_escaping(self):
        stream = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {}, clear=True):
            path = Path(directory) / '.env'
            path.write_text('NVIDIA_API_KEY=test-nvidia-secret\nPGPASSWORD=some-db-secret\n', encoding='utf-8')
            terminal = TerminalTrace([path], stream=stream)
            terminal('Raw model response', {'api_key':'another-secret', 'data':{'password':'hidden'},
                     'content':'test-nvidia-secret and some-db-secret', 'usage':{'total_tokens':100}})
        output = stream.getvalue()
        self.assertNotIn('test-nvidia-secret', output)
        self.assertNotIn('some-db-secret', output)
        self.assertNotIn('another-secret', output)
        self.assertNotIn('hidden', output)
        self.assertIn('100', output)
        self.assertIn('[REDACTED]', output)
        self.assertIn('Raw model response', output)

    def test_disabled_logging_and_closed_terminal_do_not_fail_a_question(self):
        stream = io.StringIO()
        with patch.dict('os.environ', {'SANTIO_RAG_TRACE':'0'}):
            TerminalTrace(stream=stream)('Raw response', {'content':'private text'})
        self.assertEqual(stream.getvalue(), '')
        stream.close()
        with patch.dict('os.environ', {'SANTIO_RAG_TRACE':'1'}):
            TerminalTrace(stream=stream)('Raw response', {'content':'not writable'})

    def test_ascii_console_escapes_math_without_crashing(self):
        class AsciiStream(io.StringIO):
            encoding = 'ascii'
            def write(self, value):
                value.encode('ascii')
                return super().write(value)
        stream = AsciiStream()
        with patch.dict('os.environ', {'SANTIO_RAG_TRACE':'1'}):
            TerminalTrace(stream=stream)('Source', {'text':'Σ → θ'})
        self.assertIn('\\u03a3', stream.getvalue())

    def test_raw_answer_and_rejection_are_visible_before_repair_and_final_acceptance(self):
        source = {'source_id':'S1','chunk_id':'chunk-1','text':'The original author passage.', 'pages':[1], 'source_refs':['#/texts/0']}
        good = {'status':'answered','claims':[{'text':'A supported claim','evidence':[
                {'source_id':'S1','quote':source['text']}]}], 'missing_information':''}
        bad = {**good, 'claims':[{'text':'Invalid citation','evidence':[
                {'source_id':'S99','quote':source['text']}]}]}
        events = []
        def response(value):
            return SimpleNamespace(id='response-id',usage=None,choices=[SimpleNamespace(
                finish_reason='stop',message=SimpleNamespace(content=json.dumps(value)))])
        with patch('openai.OpenAI') as client, redirect_stderr(io.StringIO()):
            client.return_value.__enter__.return_value.chat.completions.create.side_effect = [response(bad),response(good)]
            answer, _ = call_answer_model([], [source], {'api_key':'secret','base_url':'https://example.invalid','model':'test'},
                                          on_trace=lambda name,data: events.append((name,data)))
        self.assertEqual(answer['status'],'answered')
        names = [name for name,data in events]
        self.assertEqual(names.count('Raw answer model response'),2)
        self.assertLess(names.index('Raw answer model response'), names.index('Answer rejected; repair pending'))
        self.assertEqual(names[-1], 'Answer validation accepted')
        self.assertNotIn('secret',json.dumps(events))
        self.assertIn('S99',next(data for name,data in events if name == 'Raw answer model response')['content'])

    def test_invalid_planner_response_and_reranker_scores_are_observable(self):
        settings = {'api_key':'secret','base_url':'https://example.invalid','model':'test'}
        events = []
        observe = lambda name,data: events.append((name,data))
        with patch('openai.OpenAI') as client:
            client.return_value.__enter__.return_value.chat.completions.create.return_value = SimpleNamespace(
                id='bad-plan',usage=None,choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content='{"wrong":true}'))])
            plan, trace = plan_query('Tell me about the paper',{},settings,on_trace=observe)
        self.assertEqual(plan['intent'],'overview')
        self.assertEqual(trace['content'],'{"wrong":true}')
        self.assertIn('Raw question planner response',[e[0] for e in events])
        response = SimpleNamespace(is_success=True,status_code=200,json=lambda:{'rankings':[{'index':0,'logit':1.5}]})
        with patch('httpx.post',return_value=response), patch.dict('os.environ',{'SANTIO_RERANK_ENABLED':'true'}):
            rerank_sources('question',[{'chunk_id':'chunk','text':'author text'}],settings,on_trace=observe)
        self.assertEqual(events[-1][0],'Raw reranker response')
        self.assertEqual(events[-1][1]['rankings'][0]['logit'],1.5)
        self.assertNotIn('secret',json.dumps(events))


if __name__ == '__main__':
    unittest.main()
