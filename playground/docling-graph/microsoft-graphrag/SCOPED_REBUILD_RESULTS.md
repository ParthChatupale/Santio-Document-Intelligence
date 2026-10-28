# Active scientific extraction V3 sandbox

24 October 2026. Port **8775** now serves the completed
`runs/tetris-full-scoped-v20` index. The extraction repair left the main website unchanged. A subsequent
optional Graph-tab integration now uses app-owned code and a copied artifact;
see `C:/Santio/docs/GRAPH_FEATURE.md`. Existing vector Ask remains separate.

| Measure | Previous v14 | Active v20 |
| --- | ---: | ---: |
| Native entities | 334 | 632 |
| Native merged relationship pairs | 425 | 801 |
| Degree-zero entities | 71 | 86 |

Counts do not establish better accuracy. All native graph records are retained;
no edges were manually invented, removed or reconnected for appearance. Normal
canvas lines are brighter and 1.1 CSS pixels wide, with 2-pixel selection
highlighting, replacing the dark 0.6-pixel default.

## Completed checks

- 157/157 prepared inputs have successful extraction requests; all 108 native
  communities have reports, and local vectors are generated. This checks the
  prepared document view, not every original PDF fact or element.
- All 314 saved extraction responses replay without projection mismatches.
- Native replay of all 157 units exactly matches relationship pairs and weights:
  1,433 accepted relationship occurrences merge into 801 pairs.
- All nine targeted regression gates pass, including source-backed VR/AR
  application, MMD/COV-Chamfer dependencies, cross-attention initialization,
  metadata-node rejection, endpoint mapping and assertion provenance.
- 82 Python tests, 8 JavaScript geometry tests and JS syntax checks pass.
- 33 protected main frontend/backend files match their earlier fingerprints.
- Native Local applications query correctly identifies physical simulation,
  VR/AR and robotic manipulation, without reporting specific VR/AR evaluation.
- Native Basic Table 3 query returns full-model PD **0.0192** and without
  interaction conditioning **0.4980**. Citations resolve to PDF page 9.
- Browser verification confirms the active graph, the VR/AR connection and its
  PDF-page-2 evidence dialog. Live API snapshots and screenshots are saved in
  `runs/tetris-full-scoped-v20/verification/`.

## Remaining semantic limitations

A fixed-seed sample of 24 merged edges has **12 source-supported, 5 partially
supported and 7 unsupported** AI-assisted development judgments. This differs
from the earlier sample and does not establish comparative accuracy. Prepared
table cells were not independently aligned against the PDF in this sample.

Known errors include attributing an agentic baseline's Blender prompt to
Tetris3D, assigning FoundationPose from a generic dagger footnote to the wrong
method, reversing a grid/subset dependency, and confusing an attention ablation's
owner. These records are flagged in the UI; native graph data is preserved.
Community reports and answers can inherit extraction errors. Exact quotations
prove text presence, not semantic entailment. This remains an experimental
addition, not a verified replacement or proven improvement over other RAG.

## Failure recovery

The first v20 attempt exhausted retries on three extraction requests. A secondary
coverage audit then accessed unfinished native tables without final IDs, masking
the original failure as `'id'`. The runner now defers that audit after workflow
failure, preserves the actual cause and writes terminal progress status. A new
regression test reproduces this case.

Resumes recovered extraction and later failed community-report requests through
exact-request caches. No validation was disabled. Final processing has no
unresolved provider requests. Usage and earlier trial lineage remain saved;
active-run fresh-call/token totals exclude seeded historical usage and must not
be reported as total project cost or cold-start processing time.

## Implementation

The source is the same 30-page Tetris3D paper, `C:/Santio/2610.10539v1.pdf`, using
its saved Docling JSON. No new PDF conversion or vision inference was performed.
The original JSON and the baseline `tetris-full-validated-v14` outputs are retained.

- `_contracts_v3.py` adds a versioned scientific schema and prompt. Relations
  explicitly distinguish method, dataset construction, evaluation, related work,
  definitions, applications and quoted prompt instructions.
- Accepted initial-pass entity declarations remain available in the same
  passage's additional pass. Inherited declarations are recorded separately;
  conflicting types, rejected entities and unrelated source records cannot
  silently supply an endpoint.
- Author-year citations and abbreviated table references are rejected as
  scientific entities. Legitimate standalone mentions remain allowed.
- Application, task, metric-dependency, extension and replacement predicates are
  distinct. Metric-to-metric dependencies are allowed; treating a metric as a
  model component is still rejected. Initialization checks inspect all `from`
  clauses rather than just the final clause.
- Reported table measurements must belong to the current row owner. Collapsed
  header paths and merged cells are marked ambiguous; individual metric/value
  assignments from those rows are withheld rather than guessed.
- Dataset-generation details cannot automatically become dependencies of the
  paper's inference method. Descriptions retain scope and conditions.
- `prepare_context_v3.py` joins short adjacent fragments within their hierarchy,
  retains each parent record/reference/page, and separates new named definitions
  after formula continuations. The resulting 157 records account for all 176
  parent records; 21 table records are explicitly marked ambiguous.
- Exact source quotation checks remain enabled. OCR spacing is not silently
  corrected inside evidence quotations. A metric cannot acquire a derivation
  from a variable in an unrelated preceding paragraph.

Microsoft GraphRAG's installed Standard pipeline still owns native parsing,
merging, community detection, reports, embedding storage and query retrieval.
The scientific prompt, preparation and provider bridge are our integrations.
No per-paper edge list or evaluation answers are supplied to graph construction.

## Trial findings and lineage

Earlier trials are retained rather than overwritten:

- v15 exposed rate limiting and showed that combining substantial introduction
  paragraphs could make the model overlook application statements.
- v16 verified source-backed application extraction and an Ours (GT) table row,
  but one continuation exhausted its rate-limit retries.
- v17/v18 identified a restart-history/feedback problem and an unrelated-formula
  dependency induced by joining neighboring metric definitions.
- v19 applies the fixes and revalidates selected raw responses under the final
  contract. Definition-boundary changes produce different actual requests.
- v20 preserves v19's scientific contract and uses two globally paced workers
  to overlap provider waits. It reuses exact raw responses and rebuilds outputs.

`seed_run_cache.py` verifies actual request fingerprints. With `--revalidate`, it
copies only saved raw API requests/responses; it never copies native output
tables, vectors or old canonical projections. There are no fabricated cache
aliases. Requests whose source text, prompt or schema changes cannot hit those
old fingerprints. `cache_origin.json` retains the earlier usage ledgers and
cache lineage; a final run's fresh-call count is not total project usage.

NVIDIA Super VL remains primary with the existing disclosed Lightning failover.
A three-passage Lightning trial missed the application links and failed the
metric quotation check; it was not promoted as a replacement primary. This is
a development check, not a general model-accuracy benchmark.
Each response records its actual model. Indexing uses two globally paced workers, with
bounded provider retries and recorded waits. HTTP 429 waits honor Retry-After
and otherwise use 15/30/60 seconds; rate limits do not trigger model failover.

## Verification artifacts

The completed index passed processing/provenance replay and targeted checks.
See `verification/activation_checks.json`, `verification/rebuild_comparison.json`,
`inspection/validated_record_audit.json`, `evaluations/source-review/semantic_review.json`
and `queries/` under the active run. These checks do not establish exhaustive
semantic accuracy or require zero isolates.

The main Santio website and vector RAG are outside this sandbox repair.
