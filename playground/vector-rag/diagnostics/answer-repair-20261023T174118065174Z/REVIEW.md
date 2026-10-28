# Repeated response-repair failures: source-backed investigation

23 October 2026. Original GUI traces are preserved unchanged:

- `data/question-jobs/3a3c6bc1b2dd4c0597e8ca1191a1e797.trace.json`
- `data/question-jobs/42b3c5bf022a4bf7881a63fa67666b5e.trace.json`

Both asked `Tell me about the paper` for Never Look Back / Ledger. In each run
the actual abstract, introduction, conclusion/limitations and contributions
were selected. Each has **one retrieval round and two answer-model calls**.
The two answer attempts were not two retrievals or two accepted answers.

## Same failure in both logs

1. The first response omitted required `status`. It also contained an S3 quote
   joining nonadjacent sentences with `...`.
2. The previous validator stopped at the schema error, so the single repair
   feedback mentioned only the missing field.
3. The repair added status but repeated the noncontinuous quotation. The whole
   answer was discarded despite four/five other claims having matching quotes.
4. Retrieval recovery did not run because the outcome was a validation error,
   not insufficient evidence. `not_needed` was misleading as a diagnostic label.

The quote rejection itself was correct: the original source has intervening
sentences, and the required evidence contract uses continuous verbatim spans.
Searching for more passages would not fix the model copying an existing passage
incorrectly. This differs from the earlier formatting-only hyphen mismatch.

## Repairs

- Collect schema, state and all parsable citation issues together. Missing root
  status no longer hides a bad quote until the only repair is exhausted.
- Repair feedback asks to fix all paths and split separated quotations into
  distinct evidence entries. One repair remains the hard limit.
- After repair, withhold whole claims with invalid citations and return a clearly
  labeled partial answer when other claims pass. Never silently drop a bad quote
  while retaining the claim it was supposed to support. All raw output remains.
- A still-absent status can be restored from otherwise valid claims and declared
  missing information, under the existing status contract. This is recorded
  result-metadata normalization; it does not alter or generate facts/quotes.
  Explicit or other invalid root fields are not overridden. Quote validation
  remains mandatory after normalization.
- Label retrieval and generation/repair separately, and classify validation/API
  skips explicitly rather than saying retrieval recovery was `not_needed`.
- No quote matching or numeric-value checks were relaxed. Citation matching still
  does not independently establish logical entailment or scientific truth.

## Verification

112 Python tests pass, including combined schema-plus-quote errors, whole-claim
withholding, zero usable claims, unknown citations, numeric changes, missing
metadata restoration, bounded retries and correctly labeled recovery skips.

`saved-log-replay.json` inspects the two actual saved responses. Their second
responses now retain four/five claims as partial answers and withhold one invalid
claim each. These are deterministic replays, not new live answers or precision scores.

`live-repair.json` records one real NVIDIA repair request after replaying the
original failed first response. The new repair fixed all quotations but still
omitted status; the then-current code rejected it, so that live assertion failed.
The final missing-status normalization was added in response to this evidence.

`final-controller-replay.json` replays those same actual raw responses through
the final controller with **no additional API requests**: all seven claims pass
schema/quotation checks after the recorded status restoration. This validates
the final postprocessing on the real repaired output; it is not an independently
reviewed end-to-end accuracy benchmark.

No PDF extraction, reindexing, database write, historical-answer rewrite, model
switch or API-key change was made. A new question run is needed to produce a new
GUI result; historical failed jobs stay intact.
