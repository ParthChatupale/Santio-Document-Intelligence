# Initial Microsoft GraphRAG implementation results

**Superseded for the full-paper experiment:** see [FULL_PAPER_RESULTS.md](FULL_PAPER_RESULTS.md)
for the completed Tetris3D index, interactive graph room, answer tests and source-backed failures.
The initial smoke-test record below is retained as history.

22 October 2026. All five scripts are implemented and a small real pipeline
has passed. **Full-paper quality gates have not passed; website integration
is not ready.** The original app, database, environments and old graph outputs
are unchanged.

## What was implemented

- Microsoft GraphRAG 3.3.0 in a separate Python 3.13.3 environment, with a
  dependency lock and a successful `pip check`.
- Docling-to-JSON input preparation with headings, table/caption associations,
  figure child text, original formulas and provenance mappings.
- Registered NVIDIA and local Granite providers, using Microsoft's public
  extension points. Microsoft still owns extraction, graph construction,
  summarization, communities and the Basic/Local/Global query methods.
- CUDA-backed Granite embeddings: 384 dimensions, pinned revision, CLS pooling,
  L2 normalization, and no silent input truncation. Main cached weights are reused.
- Native Parquet outputs and LanceDB vectors, readable JSON/CSV exports,
  input/settings/prompt snapshots, request/response records and usage accounting.
- Citation/source mapping, request budgets/cache accounting, failed-run gates
  and owned-process watchdogs for blocking library calls.
- Offline graph/reference audit and explicit bounded live question evaluation.
  Matching endpoints/citation IDs is deliberately not scored as semantic truth.

## Input preparation

| Document | Source items accounted for | Source records | Unresolved |
|---|---:|---:|---|
| Tetris3D | 498 / 498 | 147 | None |
| LLM survey | 1,095 / 1,095 | 354 | One picture without usable caption/text |

Inspect `runs/tetris-prepared-final/preview.md` and
`runs/survey-prepared-final/preview.md`, alongside their `preparation_report.json`
and `source_map.json`. Preparation made zero model calls and source hashes are
unchanged. Accounting includes explicitly documented exclusions; bibliography
and page furniture are excluded by default. AI descriptions are excluded.

One Tetris3D table and fourteen survey tables trigger conservative merged-cell/
multiple-number warnings. These are **heuristic ambiguity flags**, not proof that
fourteen tables are wrong. Original cells remain available and values are not
manually split to fill graph records. Figure labels remain attached to figures.

## Successful native smoke test

Run: `runs/survey-small-smoke/`.

Scope: one original paragraph, `#/texts/303`, PDF page 16, about Evol-Instruct,
WizardLM and WizardCoder. Selection uses a general `--item-ref` option; extraction
does not hardcode the expected entities or relationships.

| Output | Measured result |
|---|---:|
| Native documents / text units | 1 / 1 |
| Entities / relationships | 7 / 6 |
| Communities / reports | 2 / 2 |
| NVIDIA indexing requests | 3 |
| Reported indexing tokens | 8,293 |
| Indexing time | About 89 seconds, including local model startup |
| Unresolved provider failures | 0 |
| Dangling edges / unmapped relationship sources | 0 / 0 |

The graph includes WizardLM-LLaMA and WizardCoder-StarCoder dependencies,
Evol-Instruct associations, and the paper-reported WizardLM comparisons with
Vicuna/Alpaca. The coding assistant inspected these six descriptions against the
saved paragraph. This is AI-assisted review, not independent accuracy measurement
or exhaustive recall. The native weights are not calibrated confidence scores.

Four live question checks are retained in the run's `queries/` directory:

| Mode | Check | Observed behavior |
|---|---|---|
| Local | WizardCoder's base model | Answers StarCoder; native citations map to page 16 |
| Global | WizardLM/WizardCoder and their underlying models | Summarizes LLaMA/StarCoder and shared instruction methodology with source mappings |
| Basic | Natural wording: what existing model was adapted to create WizardCoder? | Answers StarCoder with its source |
| Local | Unreported warranty for deploying WizardCoder in Santio | Declines to invent a warranty and says the excerpt does not establish one |

The recorded query times are about 24-30 seconds. Native methods were actually
called; answers were not prewritten. Because there is only one text unit, these
checks establish wiring/source traceability and selected behavior, not retrieval
superiority or long-document accuracy. `quality_verified` remains false.

## Larger pilots and failures

Two four-record instruction-tuning trials remain explicitly partial:

- `runs/survey-pilot-v1/`: a NVIDIA server error omitted the LLaMA-tuned paragraph,
  while Microsoft still returned a nonempty graph. Initial output was 16 entities
  and 12 relationships. Checking the provider ledger exposed the missing work;
  its status was corrected to partial. A bounded retry recovered the paragraph,
  but report-generation server errors and the cumulative 20-request budget left
  only 2 reports for 8 communities in the final 27-node/27-edge snapshot.
- `runs/survey-pilot-v2/`: adding generic Platform/Tool types corrected Hugging
  Face's earlier Dataset classification. Another extraction request failed, and
  later processing exceeded the asynchronous time allowance. Its partial native
  output contains 15 entities and 11 relationships. This exposed the need for
  the separate process watchdog now implemented.

Early Basic/Local diagnostics on the initial v1 snapshot found that Basic
retrieved the training-data passage, while Local missed it in the incomplete
graph. One Local answer also cited an existing WizardLM record for a Vicuna
dependency claim: valid IDs did not establish semantic support. The answers and
contexts remain under that trial's `evaluations/`. They are failure evidence,
not evaluation success for the repaired pipeline. The current runner rejects
partial indexes.

New stage callbacks stop downstream work after a provider failure. Final
promotion also checks unresolved provider errors, even if native workflows
swallow exceptions. The watchdog and failure rules have regression coverage;
a larger clean post-fix run has not yet demonstrated dependable full-section
or full-paper indexing. Upstream server-error causes are not established.
They do not establish an expired key or a model token-window overflow.

## Verification and actual request accounting

- 11 GraphRAG environment contract tests passed: request/cache/retry budgets,
  redaction, truncation rejection, source/citation scope, ID boundaries and
  terminating owned blocking work.
- 1 real-document preparation regression passed: source integrity, real table
  values, caption ownership, figure children and immutable output directories.
- Offline audit of the successful smoke graph found no dangling edges or
  unresolved relationship source mappings. Only two positive reference facts
  are in its selected scope; the remaining section facts are labelled out of
  scope rather than silently treated as successes or misses.

Saved ledgers account for **42 remote requests**, including **8 failed requests**.
There were also **5 exact-request cache hits**. Successful responses reported
**73,029 tokens**; failed requests returned no usage, so this is not the complete
consumption total. See `runs/implementation_accounting.json` for the breakdown.
No monetary price is inferred from free endpoint access.

## Remaining work and next checkpoint

The plan's 60 relationship references, 12 development/48 evaluation questions,
third-paper transfer, full-paper extraction, broad semantic adjudication,
numeric-table answer checks and comparison with the original app remain pending.
The evaluator exposes candidate records/evidence for review; it does not invent
precision/recall or correctness scores from endpoint/word matches.

There is no Microsoft graph browser or website integration in this phase. Native
entities/relationships are inspectable as JSON/CSV. The old viewer is separate.

Next: inspect `prepare_input.py`, its final source preview/ledger, and the
successful native smoke outputs. Then expand bounded extraction with source
coverage/recovery checks and prepare the remaining frozen evaluation data.
This implementation is usable for controlled experiments, not yet a replacement
for the website's existing RAG.
