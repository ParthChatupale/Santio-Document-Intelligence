from pathlib import Path
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch

import httpx
import openai

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_contracts as fixtures
from _providers import BudgetExceeded


class GraphRateLimit(TestCase):
    def error(self, retry_after=None):
        headers = {'retry-after': retry_after} if retry_after else {}
        return openai.RateLimitError('Rate limited', response=httpx.Response(429,
            request=httpx.Request('POST', 'https://example.invalid'), headers=headers), body={})

    def test_honors_server_wait_then_returns_real_response(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = fixtures.ProviderContracts().runtime(folder, calls=5)
            runtime.client.chat.completions.create.side_effect = [self.error('20'), fixtures.ProviderContracts().response()]
            with patch('_providers.sleep') as wait:
                self.assertEqual(runtime.complete('test').content, 'Hi')
            wait.assert_called_once_with(20)
            self.assertEqual(runtime.calls[0]['retry_wait_seconds'], 20)
            runtime.close()

    def test_rate_retries_are_bounded_and_do_not_failover_account_rate_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = fixtures.ProviderContracts().runtime(folder, calls=6)
            runtime.client.chat.completions.create.side_effect = self.error()
            with patch('_providers.sleep') as wait, self.assertRaises(RuntimeError):
                runtime.complete('test')
            self.assertEqual([c.args[0] for c in wait.call_args_list], [15, 30, 60])
            self.assertEqual(runtime.client.chat.completions.create.call_count, 4)
            self.assertEqual({c['model'] for c in runtime.calls}, {runtime.model})
            runtime.close()

    def test_excessive_server_wait_stops_without_retrying_early(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = fixtures.ProviderContracts().runtime(folder, calls=5)
            runtime.client.chat.completions.create.side_effect = self.error('120')
            with patch('_providers.sleep') as wait, self.assertRaises(BudgetExceeded):
                runtime.complete('test')
            wait.assert_not_called()
            self.assertEqual(runtime.client.chat.completions.create.call_count, 1)
            runtime.close()

    def test_provider_slots_are_reserved_with_global_spacing(self):
        with tempfile.TemporaryDirectory() as folder, patch('_providers.monotonic', return_value=100):
            runtime = fixtures.ProviderContracts().runtime(folder, calls=5)
            runtime.min_request_interval = 3
            runtime.client.chat.completions.create.return_value = fixtures.ProviderContracts().response()
            with patch('_providers.sleep') as wait:
                for question in ['one', 'two', 'three']:
                    runtime.complete(question)
            self.assertEqual([c.args[0] for c in wait.call_args_list], [3, 6])
            runtime.close()
