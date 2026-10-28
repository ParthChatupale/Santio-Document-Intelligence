"""Transport retries preserve evidence, honor provider delays, and stay bounded."""
from datetime import datetime, timezone
from email.utils import format_datetime
from types import SimpleNamespace
import json
import unittest
from unittest.mock import Mock, patch

import httpx
from openai import APIStatusError

from pbl_docintel.vector_rag.provider_retry import ProviderRetries, retry_after_seconds
from pbl_docintel.vector_rag.rag import call_answer_model
from pbl_docintel.vector_rag.retrieval import plan_query, rerank_sources


def failure(status=429, headers=None):
    response = httpx.Response(status, headers=headers, request=httpx.Request('POST', 'https://example.invalid'))
    return APIStatusError('private provider details', response=response, body=None)


def response(value):
    return SimpleNamespace(id='test', usage=None, choices=[SimpleNamespace(finish_reason='stop',
        message=SimpleNamespace(content=json.dumps(value)))])


SOURCE = {'source_id':'S1','chunk_id':'same-chunk','pages':[1], 'source_refs':['#/texts/1'],
          'text':'The method reduces the number of trainable parameters.'}
ANSWER = {'status':'answered','claims':[{'text':'Fewer parameters are trained.',
          'evidence':[{'source_id':'S1','quote':SOURCE['text']}]}], 'missing_information':''}
SETTINGS = {'api_key':'secret', 'base_url':'https://example.invalid', 'model':'test'}


class ProviderRetryTests(unittest.TestCase):
    def controller(self, **kwargs):
        return ProviderRetries(sleep=Mock(), clock=lambda: 1000, jitter=lambda: 0, **kwargs)

    def test_honors_retry_after_then_returns_and_logs_no_secrets(self):
        retry = self.controller()
        operation = Mock(side_effect=[failure(headers={'Retry-After':'8'}), 'answer'])
        events=[]
        self.assertEqual(retry.run(operation, 'answer generation', on_trace=lambda n,d:events.append((n,d))), 'answer')
        waiting = next(d for n,d in events if n == 'Provider retry waiting')
        self.assertEqual(waiting['wait_seconds'], 8)
        self.assertEqual(waiting['retry_number'], 1)
        self.assertEqual(waiting['retry_at'], '1970-01-01T00:16:48+00:00')
        self.assertEqual(sum(c.args[0] for c in retry.sleep.call_args_list), 8)
        self.assertLessEqual(max(c.args[0] for c in retry.sleep.call_args_list), .5)
        self.assertNotIn('private', json.dumps(retry.summary()))

    def test_retry_after_http_date_and_invalid_values(self):
        date = format_datetime(datetime.fromtimestamp(1012, timezone.utc), usegmt=True)
        self.assertEqual(retry_after_seconds(failure(headers={'Retry-After':date}), 1000), 12)
        for value in ['nan','inf','invalid']:
            self.assertIsNone(retry_after_seconds(failure(headers={'Retry-After':value}), 1000))
        self.assertEqual(retry_after_seconds(failure(headers={'Retry-After':'-2'})), 0)

    def test_temporary_errors_stop_after_two_retries_and_backoff_increases(self):
        for error in [failure(429), failure(503), TimeoutError('private')]:
            with self.subTest(error=type(error).__name__):
                retry = self.controller()
                operation = Mock(side_effect=error)
                with self.assertRaises(type(error)):
                    retry.run(operation,'answer generation')
                self.assertEqual(operation.call_count, 3)
                self.assertEqual([e['wait_seconds'] for e in retry.events if e['event']=='Provider retry waiting'], [4,8])
                self.assertEqual(retry.events[-1]['reason'], 'attempt_limit')

    def test_credentials_missing_model_bad_requests_and_validation_do_not_retry(self):
        for error in [failure(400),failure(401),failure(403),failure(404),ValueError('bad JSON')]:
            with self.subTest(error=str(error)):
                retry = self.controller()
                operation = Mock(side_effect=error)
                with self.assertRaises(type(error)):
                    retry.run(operation, 'answer generation')
                operation.assert_called_once()
                retry.sleep.assert_not_called()

    def test_budget_shared_across_stages_and_never_shortens_provider_delay(self):
        retry = self.controller()
        first=Mock(side_effect=[failure(headers={'Retry-After':'40'}), 'plan'])
        retry.run(first,'question planning')
        second=Mock(side_effect=failure(headers={'Retry-After':'25'}))
        with self.assertRaises(APIStatusError):retry.run(second,'answer generation')
        second.assert_called_once()
        self.assertEqual(retry.waited,40)
        self.assertEqual(retry.events[-1]['remaining_wait_seconds'],20)
        retry=self.controller()
        operation=Mock(side_effect=failure(headers={'Retry-After':'61'}))
        with self.assertRaises(APIStatusError):retry.run(operation,'answer generation')
        operation.assert_called_once()
        retry.sleep.assert_not_called()

    def test_retry_does_not_consume_answer_repair_or_modify_evidence(self):
        bad = {**ANSWER, 'claims':[{'text':'Unsupported', 'evidence':[{'source_id':'S1','quote':'Invented quote'}]}]}
        retry = self.controller()
        with patch('openai.OpenAI') as client:
            create=client.return_value.__enter__.return_value.chat.completions.create
            create.side_effect=[failure(), response(bad), failure(503), response(ANSWER)]
            result, attempts=call_answer_model([{'role':'user','content':'unchanged sources'}], [SOURCE], SETTINGS, provider_retries=retry)
        self.assertEqual(result['status'],'answered')
        self.assertEqual(create.call_count,4)
        self.assertEqual(len(attempts),2)
        requests=[c.kwargs['messages'] for c in create.call_args_list]
        self.assertEqual(requests[0],requests[1])
        self.assertEqual(requests[2],requests[3])
        self.assertEqual(requests[2][0],requests[0][0])
        self.assertEqual(result['claims'][0]['evidence'][0]['chunk_id'],'same-chunk')

    def test_answer_failure_has_actionable_rate_limit_error_without_key_blame(self):
        with patch('openai.OpenAI') as client:
            create=client.return_value.__enter__.return_value.chat.completions.create
            create.side_effect=failure()
            result,attempts=call_answer_model([], [SOURCE], SETTINGS, provider_retries=self.controller())
        self.assertEqual(create.call_count,3)
        self.assertEqual(result['error_kind'],'api_error')
        self.assertIn('rate-limiting',result['error'])
        self.assertNotIn('key',result['error'])
        self.assertEqual(len(attempts),1)

    def test_actual_sdk_429_response_retries_identical_request_and_accepts_citations(self):
        from openai import OpenAI
        requests=[]
        def handler(request):
            requests.append(json.loads(request.content))
            if len(requests)==1:
                return httpx.Response(429,headers={'Retry-After':'2'},json={'error':{'message':'Temporary rate limit'}})
            return httpx.Response(200,json={'id':'retry-success','object':'chat.completion','created':0,'model':'test',
                'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(ANSWER)}}]})
        retry=self.controller()
        def client(**kwargs):return OpenAI(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        with patch('openai.OpenAI',side_effect=client):
            result,attempts=call_answer_model([{'role':'user','content':'Same evidence'}],[SOURCE],SETTINGS,provider_retries=retry)
        self.assertEqual(result['status'],'answered')
        self.assertEqual(len(requests),2)
        self.assertEqual(requests[0],requests[1])
        self.assertEqual(len(attempts),1)
        self.assertEqual(retry.waited,2)

    def test_planner_retries_transport_but_not_malformed_output(self):
        plan={'intent':'fact','search_queries':['cost mechanism'],'keywords':[],'clarification':''}
        with patch('openai.OpenAI') as client:
            create=client.return_value.__enter__.return_value.chat.completions.create
            create.side_effect=[failure(), response(plan)]
            result,trace=plan_query('How?',{},SETTINGS,provider_retries=self.controller())
            self.assertEqual(trace['mode'],'llm')
            self.assertEqual(create.call_count,2)
            create.reset_mock(side_effect=True)
            create.return_value=response({'invalid':'plan'})
            _,trace=plan_query('How?',{},SETTINGS,provider_retries=self.controller())
            self.assertEqual(trace['mode'],'fallback')
            create.assert_called_once()

    def test_reranker_retries_then_keeps_original_order_after_exhaustion(self):
        request=httpx.Request('POST','https://example.invalid')
        limited=httpx.Response(429,request=request,headers={'Retry-After':'0'})
        ok=httpx.Response(200,request=request,json={'rankings':[{'index':0,'logit':1}]})
        with patch('httpx.post',side_effect=[limited,ok]) as post:
            ranked,trace=rerank_sources('question',[SOURCE],SETTINGS,provider_retries=self.controller())
        self.assertEqual(trace['status'],'applied')
        self.assertEqual(post.call_count,2)
        with patch('httpx.post',return_value=limited) as post:
            ranked,trace=rerank_sources('question',[SOURCE],SETTINGS,provider_retries=self.controller())
        self.assertEqual(ranked,[SOURCE])
        self.assertEqual(trace['status'],'unavailable')
        self.assertEqual(trace['http_status'],429)
        self.assertEqual(post.call_count,3)


if __name__ == '__main__':unittest.main()
