import { test } from 'node:test';
import assert from 'node:assert/strict';
import { retryMessage } from '../src/questionProgress.ts';

const now = Date.parse('2026-10-23T12:00:00Z');
const retry = {stage:'answer generation',reason:'rate_limit',retry_number:1,maximum_retries:2,retry_at:'2026-10-23T12:00:08Z'};

test('waiting state uses a deadline so countdown survives job polling', () => {
  assert.match(retryMessage(retry,now), /rate-limiting.*in 8 seconds.*retry 1 of 2/);
  assert.match(retryMessage({...retry},now+3000), /in 5 seconds/);
  assert.match(retryMessage(retry,now+9000), /shortly/);
  assert.doesNotMatch(retryMessage(retry,now+9000), /-1/);
});

test('connection failures and malformed deadlines remain understandable', () => {
  assert.match(retryMessage({...retry,reason:'temporary_failure',stage:'question planning'},now), /temporarily unavailable.*question planning/);
  assert.match(retryMessage({...retry,retry_at:'invalid'},now), /shortly/);
});
