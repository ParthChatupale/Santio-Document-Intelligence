# Microsoft GraphRAG sandbox

This experiment uses **Microsoft GraphRAG 3.3.0**, not our old graph extractor.
Its five main scripts prepare Docling input, check providers, build a native
index, query it and record evaluation evidence. See [TEST_PLAN.md](TEST_PLAN.md)
for the larger testing plan and [RESULTS.md](RESULTS.md) for measured progress.
Nothing here starts or changes Santio's website or its PostgreSQL database.

The validated rebuild and its limits are recorded in
[VALIDATED_REBUILD_RESULTS.md](VALIDATED_REBUILD_RESULTS.md). The older
`FULL_PAPER_RESULTS.md` describes the original baseline. Index completion,
record-format validation and source-backed semantic accuracy are separate checks.

## Environments and model roles

- The sandbox `.venv` uses Python **3.13.3**. GraphRAG requires Python below 3.14.
- The main `C:/Santio/.venv` remains the environment for Docling and cached local
  Granite inference. A private worker reuses that environment's PyTorch/CUDA;
  this avoids downloading another large PyTorch build into the new environment.
- Embeddings: pinned `ibm-granite/granite-embedding-small-english-r2`, 384
  dimensions, CLS pooling, L2 normalization, with no silent input truncation.
- Extraction, community summaries and answers: the configured NVIDIA endpoint.
- The native sandbox vector store is **LanceDB on disk**, under each run. WSL
  PostgreSQL does not need to be running for these Microsoft GraphRAG tests.
  The existing application's PostgreSQL indexes are unaffected.

The main and sandbox `.env` files are read at runtime; process environment wins.
An optional sandbox `.env` can override the main NVIDIA settings. No credential
is written into `settings.yaml`, requests, manifests, caches or reports.
`SANTIO_DOCUMENT_PYTHON` can point at the main Python executable if it lives
somewhere other than `C:/Santio/.venv/Scripts/python.exe`.

The installed dependency snapshot is in `requirements-lock.txt`. `requirements.txt`
pins the main direct dependencies. Recreate only this sandbox environment:

```powershell
cd C:\Santio
py -3.13 -m venv C:\Santio\playground\docling-graph\microsoft-graphrag\.venv
& C:\Santio\playground\docling-graph\microsoft-graphrag\.venv\Scripts\python.exe -m pip install -r C:\Santio\playground\docling-graph\microsoft-graphrag\requirements-lock.txt
```

It is already installed in this workspace; recreating it is not required to run
the scripts. The main environment and cached embedding weights are prerequisites.
Use these runners rather than the stock GraphRAG CLI directly: the runners
register the NVIDIA and local Granite providers in-process.

## Five scripts and their actual behavior

| Script | Environment | Role |
|---|---|---|
| `prepare_input.py` | Main | Validate saved Docling JSON; export readable source records and mappings. No model calls. |
| `check_connection.py` | Sandbox | Test Microsoft's provider contracts. Local embeddings by default; `--live` makes two NVIDIA calls. |
| `index_graph.py` | Sandbox | Stage input by default; `--execute` invokes native Standard GraphRAG with explicit budgets. |
| `query_graph.py` | Sandbox | Search an existing completed index using native Basic, Local or Global Search. Never indexes. |
| `evaluate.py` | Sandbox | Audit graph/source integrity offline; `--live` explicitly runs supplied question cases. |

Private helpers keep these entry points readable: `_common.py` handles paths and
configuration; `_providers.py` registers provider bridges and enforces/logs remote
work; `_embedding_worker.py` runs local Granite; `_sources.py` maps native records
and citations back to Docling. None implements a replacement semantic extractor
or custom graph retrieval algorithm.

Our completion bridge uses Microsoft's public provider protocol. GraphRAG still
creates the prompts and parses/merges entities and relationships. Generated
responses are fetched non-streaming so finish reasons and complete JSON can be
checked; the native streaming query interface receives the validated response
as one chunk. This sandbox does not claim live token streaming.

## Input preparation and inspection

Set these PowerShell variables once for the following commands:

```powershell
$sandbox = 'C:\Santio\playground\docling-graph\microsoft-graphrag'
$graphPython = "$sandbox\.venv\Scripts\python.exe"
$doclingPython = 'C:\Santio\.venv\Scripts\python.exe'
```

Prepare a saved document; use a new output folder each time:

```powershell
& $doclingPython "$sandbox\prepare_input.py" 'C:\Santio\outputs\2610.10539v1.json'
```

The command prints its output directory. It contains:

- `input/documents.json`: the real records Microsoft will read, with a readable
  `text` field, title, source record ID and metadata.
- `preview.md`: an inspectable text view, including headings and tables.
- `source_map.json`: original document hash, item references, PDF pages,
  provenance coordinates, caption associations and source table cells.
- `headings.json`: exact available headings for a section-scoped pilot.
- `preparation_report.json`: every source item's included/context/excluded/
  unresolved status, table-render warnings, integrity and configuration.

Author captions stay with figures/tables. Text extracted inside images stays
with its figure and is labelled as diagram text. No new picture interpretation
is performed. AI descriptions are excluded unless `--include-ai-descriptions`
is explicitly supplied. Bibliography and page furniture are excluded with a
recorded reason; `--include-bibliography` includes references for a separate run.
Formula items use saved original text; this does not certify recognition quality.

Input records are logical source blocks. Microsoft performs its own subsequent
chunking. We prepend the source record ID so split text units can still map
back to the original block. Source mappings are whole-record mappings, not a
claim that every word of a generated answer has been independently verified.

## Check local and NVIDIA providers

```powershell
& $graphPython "$sandbox\check_connection.py"
& $graphPython "$sandbox\check_connection.py" --live
```

The output directory contains `connection_report.json` and model usage records.
The check includes local dimensions/normalization and a structured-response test.
Passing a tiny request is a compatibility smoke check, not a load/reliability test.

## Stage or execute a bounded pilot

Example using the already prepared survey input:

```powershell
& $graphPython "$sandbox\index_graph.py" "$sandbox\runs\survey-prepared-v1" --heading '3.2.2. Instruction-Tuning with LLMs Generated Datasets'
```

Without `--execute`, this only writes a versioned, reviewable workspace. Adding
`--execute` makes NVIDIA requests and builds Microsoft's native index:

```powershell
& $graphPython "$sandbox\index_graph.py" "$sandbox\runs\survey-prepared-v1" --heading '3.2.2. Instruction-Tuning with LLMs Generated Datasets' --execute --max-calls 20 --max-tokens 150000 --max-seconds 600
```

Use an exact heading from `headings.json`, repeat `--heading` to select several,
or omit it for the full prepared input. Full-paper indexing is a later testing
checkpoint. A selected section is always marked as partial document scope.
For a smaller test, `--item-ref '#/texts/303'` selects one exact survey item;
other documents have their own item references.

Each run has input/settings/prompt snapshots, `run.json`, `model_calls.json`,
native `output/*.parquet`, local `vectors/`, readable JSON/CSV tables, and cached
provider responses. `requests/` contains exact outgoing requests without the API
key. Prompt snapshots combine Microsoft's stock prompt with general instructions
about research roles, evidence ownership and untrusted document content.

Microsoft's native relationship output is a textual description, not our old
fixed `BUILT_ON` predicate schema. Display weights are not factual confidence.

Provider failures remain visible even if the native workflow catches an error
and writes a nonempty graph. A run with unresolved failures cannot be queried
through this runner. This prevents a partial graph from appearing completed.

Retry a partial run using successful exact-request cache entries:

```powershell
& $graphPython "$sandbox\index_graph.py" --resume '<actual-run-directory>' --execute --max-calls 20
```

Replace the placeholder with the printed run directory. Previous attempts count
toward the run's remote-call budget. A successful retry resolves the corresponding
failed request. Input/settings/prompt changes require a new run. Native output
tables are regenerated in a resumed workspace; save a separate experiment for
an immutable before/after comparison. Budget exhaustion is a partial result.

## Ask and inspect the evidence

Only use a run whose `run.json` says `completed`; this means indexing completed
for its selected scope, not that semantic accuracy has been certified.

```powershell
& $graphPython "$sandbox\query_graph.py" '<completed-run-directory>' --mode local --question 'Which base models are Vicuna and WizardCoder fine-tuned from?'
```

Modes:

- `basic`: Microsoft's vector-only retrieval over the native text units.
- `local`: semantic entity selection, graph relationships and linked context.
- `global`: synthesis over community reports.

The answer directory includes `answer.md`, `answer.json`, `context.json`,
`source_context.json` and its own model-call log. Citations resolve against the
selected native context, through text units/communities to Docling references
and pages. Community report links may cover several source passages. An existing
citation does **not** prove that the passage entails the model's interpretation.

## Evaluate and review

Offline audit:

```powershell
& $graphPython "$sandbox\evaluate.py" '<run-directory>' --reference "$sandbox\evaluation\survey_pilot.json"
```

Explicit paired Basic/Local question smoke tests:

```powershell
& $graphPython "$sandbox\evaluate.py" '<completed-run-directory>' --questions "$sandbox\evaluation\survey_pilot.json" --case bases --case ownership --live
```

Repeat `--case` or `--mode` to bound a test. The current fixture is a small
source-backed **development** set, not the full held-out benchmark from the plan.
The evaluator reports endpoint-pair candidates and required evidence coverage;
it deliberately does not turn those checks into semantic precision/recall or
answer accuracy. Each candidate/answer still requires source-based review.

Run the tests in their appropriate environments:

```powershell
& $graphPython -m unittest discover -s "$sandbox\tests" -p test_contracts.py -v
& $doclingPython -m unittest discover -s "$sandbox\tests" -p test_preparation.py -v
```

No changes to the original frontend are required to inspect these artifacts.
# Interactive graph room (full-paper experiment)

Read [VALIDATED_REBUILD_RESULTS.md](VALIDATED_REBUILD_RESULTS.md) for the completed
rebuild, source-backed quality review and actual question-test outcomes.
[FULL_PAPER_RESULTS.md](FULL_PAPER_RESULTS.md) preserves the original baseline.
Index completion is distinct from readiness for trusted website integration.

The isolated graph explorer uses the native entities, relationships, communities,
reports and source mappings from one selected run. It does not modify Santio's
React frontend, PostgreSQL database or previous graph viewer.

```powershell
cd C:\Santio
$box = "C:\Santio\playground\docling-graph\microsoft-graphrag"
& "$box\.venv\Scripts\python.exe" "$box\serve.py" "$box\runs\tetris-full-validated-v14" --port 8775
```

Open **http://127.0.0.1:8775/**. The selected PDF is
`C:\Santio\2610.10539v1.pdf` (30-page Tetris3D). Saved Docling JSON is reused;
the PDF is not uploaded to the answer endpoint. Main text and appendices are
included; the preparation ledger documents exclusions such as bibliography and
page furniture. Index completion is distinct from verified factual accuracy.

- Pan, zoom, drag nodes, filter entity types/communities, and search names.
- Select a node or edge to inspect its exact native description and source records.
- Open evidence beside the original PDF page; table mappings cover source records,
  rather than claiming word-level grounding.
- Ask in Local (entity/graph plus passages), Global (community synthesis), or
  Basic (vector passages) mode. Requests run on the server; keys stay private.
- Partial indexes can be inspected, but cannot answer questions. The progress bar
  reports failed attempts even if a later retry succeeds.
- The graph layout settles once; it does not run a permanent animation loop.

`serve.py` is an additional demonstration script beyond the five core pipeline
scripts. UI assets are under `web/`. The server binds only to localhost and is
intended as a research sandbox, not an internet deployment.

The current development fixture is `evaluation/tetris_semantic_v3.json`. It was
prepared from Docling source passages before reviewing the full extracted graph.
It is AI-prepared development evidence, not independently annotated ground truth.

