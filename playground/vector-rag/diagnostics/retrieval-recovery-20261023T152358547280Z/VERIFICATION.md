# Main RAG retrieval recovery verification

23 October 2026. The implemented feature is one additional evidence-search cycle
on the main hybrid/reranked path after empty usable evidence or a valid
`insufficient_evidence` answer. It is not an authentication retry or model failover.

## Automated checks

93 Python tests passed. See `regression-tests.log`. New tests cover bounded
reformulation, unchanged evidence, a second miss, API/planner/database failures,
preserved per-round source IDs, unknown-citation rejection and answer repair,
retained original results, document/index scope, and the single-pass vector baseline.
No extra dependencies, extraction or embedding writes are needed.

## Live checks and limits

The following are controlled first-search fault injections, not an accuracy
benchmark. Original PDF/Docling sources and database records were not changed.

1. `../retrieval-recovery-20261023T152018456140Z`: actual initial planning succeeded;
   the recovery model returned four queries where three were allowed. The plan
   was rejected. This exposed a robustness issue. The implementation now caps
   otherwise valid extra query strings to three and records the adjustment and
   complete raw response. Invalid fields/types still fail validation.
2. `../retrieval-recovery-20261023T152211669635Z`: initial planning timed out and
   recovery received NVIDIA InternalServerError. The original insufficient
   result was retained; there was no automatic provider retry.
3. This directory: the initial plan was replayed from the first successful real
   API response; the first search was deliberately empty. The recovery planner
   made a real NVIDIA request, and the second search used real PostgreSQL and
   local embeddings. It selected **five new passages**; real reranking was applied.
   The answer model returned a quote absent from its cited passage, then repeated
   it during the existing single repair. Both answers were rejected. Final
   recovery status is `answer_failed`, and the original `insufficient_evidence`
   result is preserved. The live end-to-end accepted-answer assertion did not pass.

Thus the real extra-search path and fail-closed quote checks were exercised,
but a successful accepted end-to-end answer was not established in this smoke
test. Do not present it as an accuracy win. `answer.json` retains the two rounds,
real model outputs, quote-validation failures, timing and recovery plan.

## Use and inspect

- Main GUI question workers use the feature by default. Existing progress and
  warning rendering shows recovery activity; the API exposes `retrieval_info.recovery`.
- Full traces: `data/question-jobs/<question-id>.trace.json`, fields
  `retrieval.recovery`, `retrieval_rounds`, `attempts` and `effective_query_plan`.
- `--no-retrieval-recovery` disables it for CLI comparisons.
- Explicit `--retrieval-mode vector` remains a single-pass baseline. Hybrid and
  reranked are eligible. Partial/successful answers and API errors do not trigger
  recovery; it does not independently detect a confidently incorrect answer.
- Code: `src/pbl_docintel/vector_rag/retrieval.py:recover_query_plan` and
  `src/pbl_docintel/vector_rag/rag.py:answer_question`.
