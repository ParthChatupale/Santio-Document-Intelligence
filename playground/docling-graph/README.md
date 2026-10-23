# Docling Graph playground

This is a separate experiment around the published `docling-graph` library.
It reads a saved DoclingDocument JSON and generates a research knowledge graph
using the configured NVIDIA endpoint. It does not change or start Santio's app.

The implementation plan is in [PLAN.md](PLAN.md).
The research-based next-stage plan, including audit findings and evaluation
gates, is in [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md). The v2 sandbox implements
the research schema, source checks, contextual measurements, lexical/graph RAG
and separate demonstration workspace. See [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md)
for measured results, failed experiments and remaining gates. The original
application frontend is unchanged.

## Explicit relationships and semantic review

The [relationship fix report](RELATIONSHIP_FIX_REPORT.md) records the live result:
seven model-proposed inter-entity connections survive source and semantic checks
in the instruction-tuning section. Four targeted positive checks pass; three
unsupported proposals are withheld. This is a selected-section experiment, not
exhaustive extraction of the 47-page survey.

The new pipeline is saved section trial → typed relationship extraction → exact
evidence/type checks → separate model review of source entailment → native Docling
Graph conversion → development checks. Both the deterministic checks and the
model review must accept a proposal; model review cannot rescue a failed quote.
Empty relationship groups still require explicit source reviews. Paper-to-entity
links alone no longer pass the sandbox's knowledge-graph relationship gate.

To reopen the saved reviewed result without making model requests:

```powershell
cd C:\Santio
$relationshipTrial = Get-Content .\playground\docling-graph\outputs\latest_relationship_trial.json -Raw | ConvertFrom-Json
.\.venv\Scripts\python.exe .\playground\docling-graph\run_v2.py serve --run $relationshipTrial.run_dir --port 8774
```

Open `http://127.0.0.1:8774/`, then **Relationships**. Each card offers the
supporting quotation and its original PDF page. If this server is already
running, simply open the URL; starting it again on the same port will fail.

For a fresh bounded experiment, provide an existing section trial directory:

```powershell
.\.venv\Scripts\python.exe .\playground\docling-graph\run_relationships.py --run <section-trial-directory> --heading '<exact-heading>' --reference <matching-source-development-reference.json> --max-calls 2
.\.venv\Scripts\python.exe .\playground\docling-graph\review_relationships.py --run <new-relationship-directory> --reference <matching-source-development-reference.json>
```

Replace the angle-bracket arguments with actual values. The first command prints
the output directory for the second. The review makes at most one additional
request, with a 2,500-token output allowance, no retries, and a 90-second timeout.
Its estimated input cap is 10,000 tokens; larger reviews must use a smaller scope.
Schema and source matching are verified before requests. The default references
are survey development fixtures; supply a matching reference for another paper.
Results with unresolved gates exit nonzero and remain saved as partial trials.
The separate `latest_relationship_trial.json` pointer never replaces `latest_v2`
or the original application.

The follow-up [survey failure investigation](SURVEY_FAILURE_INVESTIGATION.md)
reconstructs the exact failed request and records two bounded live tests that
separate whole-document failure from short-section extraction.

## Try manageable sections

The section runner reuses saved Docling JSON, native hierarchical chunks,
Docling Graph's LLM backend, identity-aware merge and graph converter. It makes
separate bounded calls over selected headings, with an explicit API-call budget.
It leaves the original application and the latest v2 demonstration pointer alone.

```powershell
.\.venv\Scripts\python.exe .\playground\docling-graph\run_sections.py --source .\outputs\2307.06435v10.json --heading '3.4.1. Retrieval Augmented LLMs' --batch-tokens 900 --max-output-tokens 4096 --max-calls 3 --concise
```

The paper and heading above are example inputs. Use exact headings from your
selected saved document; repeat `--heading` to select several. Omitting headings
selects non-bibliography content, but the call/time budgets still apply and may
leave part of the document unattempted. No content is silently truncated to fit
an input batch: overlarge native chunks are marked as skipped.

Body batching and full-input caps use an approximate tokenizer. Actual NVIDIA
`prompt_tokens`, `completion_tokens` and `finish_reason` are recorded per call.
Returned usage is authoritative; failed requests may not return usage at all.
All completed content is saved per batch. Empty or failed sections are visible,
not counted as completed extraction. A truncated response is retained for
diagnosis but excluded from the accepted merge.

`retry_section_batch.py --run <output-folder> --batch <number>` retries one
unsuccessful batch within that run's original call budget. It never repeats an
already successful batch. `combine_section_runs.py` combines saved successful
records offline, preserving origins and without making another model request.

The live survey trial did recover entities and limitations with smaller batches.
It also exposed missing semantic links: named entities connected to a paper do
not by themselves establish a useful method-to-method knowledge graph. See
[SECTION_TRIAL_REPORT.md](SECTION_TRIAL_REPORT.md) for results and limitations.

## Run the v2 workspace

From PowerShell in `C:\Santio`:

```powershell
.\playground\docling-graph\run-v2.ps1
```

Open **http://127.0.0.1:8772/**. This serves the latest substantive saved v2 run;
it does not extract another PDF or make a model request at startup. Stop with
Ctrl+C. If port 8772 is already occupied by this workspace, use the running
workspace or select `-Port 8773` instead of starting a second copy on the same port.

Understand shows model-extracted methods, datasets, findings and limitations.
Results shows exact source-cell values with row, metric and experiment context.
Ask the paper retrieves passages locally; pressing Ask uses the NVIDIA connection
already in `.env`. Relationships shows source-linked graph candidates with search
and focus. Coverage & sources exposes unresolved source/table issues.

The graph includes individual measurements, so its node count is not a measure of
conceptual richness. Source linkage is not independent semantic verification.

To extract a different **full saved DoclingDocument JSON**:

```powershell
.\playground\docling-graph\run-v2.ps1 -Action run -Source .\outputs\2610.10539v1.json -PromptJson -SkipGleaning
```

This calls NVIDIA and writes a new versioned output folder. The filename above
is an example input, not hardcoded extraction logic. Prompt JSON bypasses provider
schema enforcement, but local Pydantic validation still runs. Skipping gleaning
bounds the optional follow-up work. These settings do not guarantee coverage;
in particular, the tested survey paper returned an insufficient extraction.
`dense` is experimental: a long staged attempt required offline schema repair;
it is not a validated improvement over direct mode.

```powershell
.\playground\docling-graph\run-v2.ps1 -Action query -Question 'What limitations does the paper report?' -Answer
.\playground\docling-graph\run-v2.ps1 -Action evaluate
```

For Python/RAG use, `retrieval_v2.ResearchWorkspace(run_directory).retrieve(question)`
returns plain source passages, page/item references, headings and graph candidates.
`.ask(question)` adds a source-cited model answer. Import this sandbox module by
adding its directory to the Python import path. It is not installed into the main
application. Retrieval uses BM25-style lexical scoring plus graph expansion;
no embedding model or vector database is claimed.

V2 additionally saves `normalized_records.json`, `measurements.json`,
`usable_graph.json`, `evidence.json`, `source_index.json`, `chunks.json`,
`source_quality.json`, `aliases.json`, `quality_report.json`, `understanding.json`
and `evaluation.json`. Original library artifacts and raw records are retained.
An identity-only/root-only response fails the success gate and cannot become
the latest successful graph.

The original v1 commands and outputs are documented below and remain available.

## Setup

From PowerShell in `C:\Santio`:

```powershell
.\playground\docling-graph\setup.ps1
```

The default reuses the project's existing `.venv` if Docling Graph 1.9.1 and
LiteLLM are already installed. Setup then performs no installation. The sandbox
isolates scripts and outputs; dependencies are shared in this default mode.
The application source and dependency files are not modified.

For a separate dependency environment, use `setup.ps1 -Isolated` and add
`-Isolated` to `run.ps1` (Python 3.12 and CPU runtime). This downloads its own
dependencies. `requirements.txt` pins the main libraries for that optional
installation; `tested-versions.json` records the package versions used in testing.
No repository clone or PDF conversion is required.

The existing project `.env` supplies `NVIDIA_API_KEY` and optionally
`PBL_MODEL_NAME`. A sandbox-local `.env` can override these. Process environment
variables take precedence. Optional `NVIDIA_MODEL` and `NVIDIA_BASE_URL` select
a different NVIDIA deployment. Keys are read into the running process and are
not copied to manifests or committed files.

## Inspect the input without calling a model

```powershell
.\playground\docling-graph\run.ps1 -Action inspect -Source .\outputs\2610.10539v1.json
```

Choose the full DoclingDocument JSON, not its `.summary.json` or `.layout.json`.
Any saved document can be selected using `-Source`; the paper above is an example.
Inspection shows page count, content counts, and heading levels. It does not
prove the detected heading levels or extracted table structure are correct.

## Generate a knowledge graph

```powershell
.\playground\docling-graph\run.ps1 -Action run -Source .\outputs\2610.10539v1.json
```

This sends document content to the configured NVIDIA service. The terminal
shows Docling Graph's progress and the final output location. Extraction may
make several model calls; endpoint access, quotas, and response time apply.

Docling Graph handles document loading, structure-aware chunking, model prompts
and calls, record validation, graph conversion, provenance, and its native HTML
viewer. Our `research_schema.py` defines the extraction target and relationship
labels. It is a template, not another extractor.

The tested default is `direct` with heading-preserving Markdown serialization.
The model reads the whole document; library chunking builds the provenance
index. This is not a model run over individual chunks. It produced more specific
experiment/metric records in the initial smoke test than the initial dense
DocLang run, but the template also changed: this was not a controlled benchmark.

`auto` lets the library choose direct or dense based on its input/output budgets.
`dense` discovers entities then fills them over structure-aware chunks. To
explicitly exercise dense extraction:

```powershell
.\playground\docling-graph\run.ps1 -Action run -Source .\outputs\2610.10539v1.json -Contract dense
```

For advanced settings, use the Python runner:

```powershell
.\.venv\Scripts\python.exe .\playground\docling-graph\sandbox.py run --help
```

In particular, `--prompt-json` disables API JSON-schema enforcement if the
selected endpoint does not support it; Pydantic validation still applies.
The dense contract uses the library's prompt-based JSON extraction regardless
of this flag; API JSON-schema enforcement applies to the direct path.
The default model is Nemotron 3 Super unless overridden by your configuration.
The OpenAI provider name selects its compatible request format; the requests
go to the configured NVIDIA base URL.

The thin NVIDIA client adapter adds request timing and token usage and sets
Nemotron's documented `enable_thinking` flag. Reasoning is off by default to
avoid spending the extraction budget on hidden reasoning; `--thinking` enables
it for a separate experiment. This setting is not an accuracy guarantee.
Docling Graph still builds prompts, parses and validates records, and builds
the graph. The adapter does not implement extraction.
See [NVIDIA's reasoning configuration](https://docs.nvidia.com/nim/large-language-models/2.0.4/turbo/get-started-nemotron-3-super-120b-a12b.html).

## Open the graph

```powershell
.\playground\docling-graph\run.ps1 -Action view
```

This opens the latest successful run's native Docling Graph viewer in your
browser. Its JavaScript dependencies are embedded in the generated HTML. You may also
open the printed `graph.html` path directly. The graph viewer is an experimental
library view, not an integration into Santio's React frontend.

Use **Find an entity** to select a method, experiment, or metric. Selecting it
focuses its immediate relationships and opens its properties and evidence.
Click other nodes/edges to inspect them; **Reset View** returns to the whole graph.

## Outputs

Each run gets its own directory under this sandbox's ignored `outputs/` folder:

- `run.json`: input hash, versions, non-secret settings, status, duration, counts,
  and the viewer location. Failed runs remain marked as failed.
- `extracted_records.json`: model-extracted, schema-validated research records.
- `graph.json`: nodes and typed relationships from Docling Graph.
- `graph.html`: the complete upstream viewer, assembled with vendored assets.
- `provenance.json`: the library's source ledger, when available.
- `schema.json`: the exact extraction schema used for this run.
- `model_calls.json`: per-request timing, status, and token usage; no prompts or credentials.
- `artifacts/**/docling_graph/`: library CSV/JSON exports, provenance, report,
  and interactive `graph.html`.

The published wheel omitted its full viewer assets during testing. The sandbox
therefore vendors the official v1.9.1 template and JavaScript under `vendor/`,
with source URLs, checksums, and the upstream license. `viewer.py` assembles those
assets with the exported graph; it does not change the extracted graph. This
keeps the richer viewer available without editing the installed package or
depending on a CDN. The library's original fallback viewer is retained under
`artifacts/` for completeness.
The sandbox's display layer adds entity names, relationship labels/arrows, and
escaping for source-derived detail text; the vendored originals remain intact.

The schema includes methods and their concepts, experiments and their explicitly
associated methods/training datasets/evaluation datasets, findings, metrics,
and short supporting quotations. Unknown details should remain absent.

## Initial smoke-test result

The full saved 30-page Tetris3D document produced 93 nodes and 210 edges with
the revised template and direct/Markdown settings (about 234 seconds inside
the library pipeline). It captured five distinct experiments and named metrics.
This is an integration result, not an accuracy measurement: dataset edges and
limitations were omitted in that run, and most node provenance fell back to
document scope. The earlier dense/DocLang run produced 23 nodes and 27 edges,
mostly from the abstract/introduction. Both runs remain available separately.

## What a successful run means

It verifies that the real model-backed library pipeline produced a connected
graph and usable artifacts from a saved document. It does **not** establish
factual accuracy or exhaustive coverage. An identifier's source match does not
prove every connected edge, and an extracted quotation still needs checking.

Figures and formulas may be represented in the input, but detected regions are
not automatically interpreted. Numerical table assignments must be supported;
the template explicitly asks the model not to guess how merged cells split.

V1 does not implement RAG retrieval or scoring. V2 adds lexical/graph retrieval
and a small source-backed development regression reference. Cross-paper entity
resolution, hierarchy/no-hierarchy comparison and independent ground-truth
scoring remain unimplemented.
