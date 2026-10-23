# Research sandbox v2: implementation and measured status

Updated 16 October 2026. This is a separate playground in `C:\Santio\playground\docling-graph`.
The original React frontend, app backend, npm scripts and extraction outputs were
not changed. Nothing has been committed or pushed.

## What works now

- Reads an existing full DoclingDocument JSON through the real Docling Graph
  library. No PDF re-extraction is needed. Uses NVIDIA Nemotron 3 Super through
  the project's existing server-side `.env` connection.
- V2 research schema distinguishes methods, datasets, technical concepts,
  metrics, experimental configurations, experiments, findings and measurements.
  It preserves configurations from nested references instead of discarding them
  when the model leaves a root catalog empty.
- Native Docling hierarchical chunking retains heading breadcrumbs, original
  item references and PDF pages. The existing project evidence index supplies
  table cells, row/header/caption context and bounding boxes.
- Source checks resolve quotations and cell assignments. They reject known
  metric-as-concept/type errors and withhold unresolved links from retrieval.
  An entity-name match establishes a mention, not the truth of its description.
- Unambiguous numeric cells become contextual measurements. Ambiguous merged
  cells are withheld. Exact strings are preserved; units/scales remain unknown
  when extraction did not establish them.
- Plain Python retrieval returns source chunks plus bounded graph expansion.
  It uses BM25-style lexical scoring, not embeddings. Source-cited NVIDIA answers
  support explicit abstention on questions absent from the retrieved passages.
- A separate FastAPI workspace offers Understand, Results, Ask the paper,
  Relationships and Coverage & sources, with direct links to original PDF pages.
  Method dependencies in Understand come only from the source-linked graph;
  unresolved candidates remain available in the full graph.
- Versioned raw/normalized records, native/assessed/source-linked graphs,
  evidence, aliases, chunks, coverage, model-call logs and development evaluation
  are saved. Exact-request caching is explicit. Provider/SDK retries are bounded
  in the v2 runner. A root-only extraction fails the success gate.
- The actual extraction contract is recorded from the native trace, so a dense
  attempt that falls back to direct cannot be reported as a successful dense run.

## First-paper results

Current demonstration run:

`outputs/2610.10539v1-v2-direct-20261016T065635720877Z`

Input: saved full 30-page Tetris3D Docling JSON, SHA-256
`c7cca5c7618d084c22ec026bd53ac0848e19346af4109a4209c2f77b7ef7e58a`.
The input remains unchanged. No paper names, numeric values or source positions
are hardcoded in the extraction/normalization logic; named expectations occur
only in development fixtures and evaluation.

| Output | Measured result |
|---|---:|
| Native library graph before our table adapter | 81 nodes, 115 edges |
| Assessed graph after normalization and table adapter | 333 nodes, 906 edges |
| Source-linked candidate graph | 319 nodes, 863 edges |
| Methods / datasets / concepts / metrics | 15 / 4 / 3 / 14 |
| Configurations / experiments / findings | 27 / 5 / 12 |
| Findings classified as limitations | 3 |
| Measurements with exact source-cell context | 252 |
| Heading-aware retrieval chunks | 141 |
| Frozen development reference checks represented and source-linked | 24 / 24 |
| Expected evidence retrieved, six development questions, chunks only | 6 / 6 |
| Expected evidence retrieved, same questions, chunks + graph | 6 / 6 |

These are representation/source-retrieval checks, not independent factual
accuracy or exhaustive recall. The graph does not suddenly have 333 distinct
scientific concepts: 252 nodes are measurements. The graph mode did not improve
the six-question evidence hit rate over lexical retrieval. That result must not
be sold as demonstrated RAG superiority.

Values come from Tables 1, 3, 4 and 5. Table 2 remains unresolved because its
Docling cells merge multiple values/headers. The text-only model did not visually
interpret diagrams. Fourteen formula regions contain no extracted formula text.
No formula content, merged numeric splits or unknown multipliers are invented.

Example checked against real source cells: Table 3 reports PD `0.0192` for
Full model (Ours) and `0.4980` for w/o Interaction Cond., PDF page 9.
The final live NVIDIA answer returned those values with a resolvable citation.
It also retained the paper's physical-guarantee/error-propagation caveats and
declined an unreported software-warranty question. `workspace_smoke.json` retains
these three development smoke cases and their source references. These checks
are not an independent answer-quality benchmark.

The direct run took about 19.2 minutes inside extraction, with four logged
client calls: three completed and one failed. Reported completed-call token
usage totals 68,569. Earlier SDK/provider retries caused a long timeout; the
current runner disables SDK retries and defaults provider retries to zero.
The optional gleaning failure is retained in the logs. The graph remains
`complete_with_unresolved`, not an exhaustive successful extraction.

## Staged/dense experiment: failure and recovery

Original attempt:

`outputs/2610.10539v1-v2-dense-20261016T070222471020Z`

It took about 45.5 minutes and logged 121 client entries: 117 completed,
two failed and two cache hits, with 1,125,868 reported completed-call tokens.
One timed-out discovery batch and many fill jobs made this expensive.
This is a logged client-call count; SDK internal retries in that old run were
not separately counted as network requests.

The staged assembly failed validation because our MethodConfiguration required
the full method on identity-only references. That requirement was our schema
bug. The library then fell back to direct extraction. Its resulting graph must
not be used as evidence that dense extraction succeeded or improved coverage.

Schema `research-v2.0.1` makes that nonidentity field optional. Canonical records
can retain full details; references can contain only name and experiment name.
A regression test exercises validation and the real graph converter with those
identity-only references. No installed library files were edited.

`recover_dense_v2.py` validates the preserved assembly offline, into a separate
derived run, without calling NVIDIA or replacing the failed attempt. That run
produced 120 nodes, 176 edges, no table measurements, and represented 13/24
development checks. Its metadata identifies the origin, source assembly hash,
schema repair and zero new API calls. This is useful diagnostic evidence, not
a clean controlled comparison. Direct remains the demonstration default.

## Second-paper test: generalization gate failed

Input: the user's 47-page survey, `2307.06435v10.json`.
Run: `outputs/2307.06435v10-v2-direct-20261016T074713768464Z`.

With prompt JSON, optional gleaning disabled, a 60-second provider timeout and
SDK retries disabled, one real call returned only the paper root: one node,
zero edges. Extraction took approximately 59 seconds and reported 97,100 tokens.
The run is now explicitly `insufficient_extraction` and cannot replace the
latest substantive graph. Its artifacts are retained for diagnosis. There is
no matching reference for this paper, so no accuracy score is inferred.

The current original-research schema/full-document request did not generalize
to this survey. Another full-paper run would not fix that by itself. A bounded,
section-scoped strategy and a schema suitable for surveys need their own test.
The remaining 48-page paper has not undergone a new v2 model extraction.

Follow-up: [SURVEY_FAILURE_INVESTIGATION.md](SURVEY_FAILURE_INVESTIGATION.md)
verified the exact request fingerprint and tested two short excerpts. Even the
unchanged schema/native prompt extracted methods and concepts at small scope.
This makes single-pass document scope a stronger suspect than a blanket schema
incompatibility, while classification issues still require work. The full-survey
extraction gate remains failed.

## Validation and reproducible commands

From PowerShell in `C:\Santio`:

```powershell
.\playground\docling-graph\run-v2.ps1
```

Open `http://127.0.0.1:8772/`. The command serves the latest substantive saved
run; startup does not submit another extraction or answer request. If this
server is already running, open that URL or choose `-Port 8773` for another copy.
Logs appear in the same terminal; Ctrl+C stops it. The original app's npm
commands are unchanged.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s .\playground\docling-graph\tests -v
.\.venv\Scripts\python.exe .\playground\docling-graph\validate_workspace_v2.py
# Explicitly make three live NVIDIA answer requests:
.\.venv\Scripts\python.exe .\playground\docling-graph\validate_workspace_v2.py --live
```

The regression suite checks real source cells, merged-cell abstention, missing
or ambiguous mappings, hierarchy, wrong quotations/references, invalid entity
types, contextual IDs, shared native entities, reference-only records, dense
fallback reporting, citation checking, empty-output failure and HTTP contracts.
The HTTP tests mock model calls and check error redaction. Browser checks verified
filtered result cards, graph search/focus and a live cited answer. The saved
workspace preview shows the actual tested application.

Final verification: **25 tests passed**, five HTTP smoke routes passed and all
three live NVIDIA answer cases passed. A scan of 300 sandbox text artifacts
found no occurrence of the current API key. The source JSON checksum is unchanged.
Git reports no tracked or untracked changes in the original frontend, GUI backend,
root npm manifests or root scripts. `tests_last_run.json`, `workspace_smoke.json`
and `integrity_check.json` retain these checks beside the demonstration outputs.

## Remaining work and integration decision

The sandbox implementation is usable for testing, but the full product plan is
not complete. Main-app integration remains pending because its preceding quality
gates have not all passed.

1. Fix survey/long-document coverage with a bounded section-scoped experiment;
   compare on a separate source-backed reference before claiming generalization.
2. Repeat a truly controlled mode comparison after freezing the repaired
   schema, with an explicit overall call/time budget. Dense is currently
   slower and incomplete in the available evidence.
3. Expand semantic/answer evaluation beyond the small development reference.
   Current exact-source checks are not entailment verification. An optional
   bounded model review has not been implemented.
4. Improve retrieval only where a larger held-out question set shows a gap.
   Embeddings/vector retrieval have not been implemented; lexical/graph output
   is already available to other Python systems as plain evidence bundles.
5. Integrate the validated pipeline into the original app only after those
   gates pass. Cross-paper resolution, visual diagram/formula interpretation,
   merged-table recovery and production deployment remain later work.

## Research choices used

The richer research schema follows the separation of entities and references
shown by [Docling Graph's official research example](https://github.com/docling-project/docling-graph/blob/main/docs/examples/templates/rheology_research.py)
and [reference-field documentation](https://docling-project.github.io/docling-graph/fundamentals/schema-definition/relationships/).
The staged experiment uses its [native dense extraction](https://docling-project.github.io/docling-graph/fundamentals/extraction-process/dense-extraction/).
Keeping source chunks alongside graph records follows the source-traceability
pattern in [Microsoft GraphRAG outputs](https://microsoft.github.io/graphrag/index/outputs/).
These sources guide the design; they do not establish our implementation's accuracy.
