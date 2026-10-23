# Overview-routing incident and verification

23 October 2026. User question: `Tell me about the paper ?`, Tetris3D,
index `r2-8a620bb7068679566d082357`.

## Actual incident

Original saved job: `data/question-jobs/6107eed2e2054c4bb93905443ea484d0`.
Its planning request failed with NVIDIA `InternalServerError`. The local fallback
classified the broad request as `fact` and produced no lexical keywords.
Retrieval therefore had zero structural candidates and selected appendix section
lists, ablation rows, metric definitions and training settings. The reranker ran
but had no explicit overview routing. The answer returned `partial`; evidence
recovery only triggers for `insufficient_evidence`, so no recovery was attempted.

The abstract and introductory/concluding chunks were already stored correctly.
This was a question-routing/source-selection failure, not missing PDF extraction
or a database shutdown. It is separate from the earlier hyphen quotation mismatch.
The older same-question job `058a48c2f246445cbd2f4b4919fb60c4` also fell back to
fact after a planner validation error, and its answer failed quote validation.

## Fix

`is_document_overview_request` recognizes broad document requests for degraded
planning, while preserving targeted subquestions as facts. The fallback now
activates existing document-section selection and protection for this request.
Overview answer instructions prioritize problem, approach, contribution and
limitations instead of optimizer settings or table-of-contents lists. No paper
facts, names, values, source positions or expected answers were added to routing.
Partial-answer recovery policy and exact-quotation validation were not relaxed.

## Measured replay

The original planner failure was deliberately replayed; the database, embeddings,
NVIDIA reranking and answer endpoint were real. This tests resilience to the
recorded failure condition, not overall answer accuracy. See `answer.json` for
the explicit verification marker and request trace.

- Intent: `overview`.
- Selected sources: abstract (PDF1), introduction (PDF2), conclusion (PDF9),
  discussion/limitations (PDF22–26) and another introductory passage (PDF2).
- Answer: `answered`, with matching source quotations, covering reconstruction,
  neighboring-object conditioning, ComOb, experiments, generation order,
  architecture and limitations. Matching quotations are not independent semantic
  verification.
- 95 Python tests passed, including broad-request/targeted-question contrasts and
  preserving core sections when the hosted planner fails and ranking prefers an
  appendix passage.

No re-upload, PDF conversion, index rebuild, database write or historical-answer
rewrite was performed. Ask the question again to generate a fresh answer; the
saved earlier partial answer remains unchanged in history.
