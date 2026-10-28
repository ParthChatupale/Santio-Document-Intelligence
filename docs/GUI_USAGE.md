# Santio local research workspace

The React + TypeScript interface is implemented over the Python evidence SDK.
It includes the supplied Waves WebGL1 shader, real PDF cover previews, a searchable
library, PDF upload and Docling processing, original-page inspection, detected
regions, provisional annotations, attribution findings, and evidence/RAG exports.

## Run from PowerShell

The project is at `C:\Santio`. Node 22.12+ and the existing Python environment
are required. On this machine both are already available.

```powershell
cd C:\Santio
.\.venv\Scripts\python.exe -m pip install -e ".[gui,docling,vector]"
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. `npm run dev` starts the Python API on port 8766
and Vite on port 5173; Ctrl+C stops both. No environment activation is needed.
If dependencies are already installed, just run `npm run dev`.

The startup output shows one application link, labelled **Open Santio**. Port
8766 is the internal API used through Vite's proxy, not a second development UI
to open. The backend can serve the last built UI when run standalone; during
development that build can lag behind Vite. API logs remain in the same terminal.

For a build served entirely by Python:

```powershell
npm run build
.\.venv\Scripts\python.exe -m pbl_docintel.gui.cli --workspace C:\Santio --port 8765
```

Open **http://127.0.0.1:8765**. Built React assets are included in the Python
package. Node is needed to rebuild or develop the interface, not to serve an
existing build. The optional GUI extra alone supports viewing; the Docling extra
is required for conversion. A new environment can be created with
`py -3.14 -m venv .venv` before installing the dependencies above.

Run one service per workspace when importing PDFs. This is a local application,
not a hosted multi-user service. The CLI binds to 127.0.0.1.

## Add a paper

1. Click **Add paper**; choose or drop a PDF up to 100 MB.
2. Edit the title if desired. Enable OCR for scanned pages.
3. Click **Upload & prepare**. A separate in-app progress page opens immediately.
4. The upload meter shows actual bytes transferred. Only server confirmation marks
   the upload step complete. Extraction, chunking and embedding follow separately.
5. Click **Ask this paper** when preparation completes, or **Read extracted paper**
   as soon as extraction is saved. Imports in the top bar reopens saved progress.

Add paper in the sticky top bar is the upload entry point. There is no automatic
analysis when selecting a file or opening a paper. Once upload is accepted,
preparation continues while browsing. Refresh restores server progress; refreshing
before transfer completes can interrupt that transfer and requires choosing the
PDF again. Keep the local backend running.

Conversion, indexing and questions share one worker queue to avoid competing local
GPU jobs. Cancel stops the owned worker process. Retry reuses saved Docling output
and validated chunks when available. An indexing failure preserves the extracted
paper. Interrupted jobs become failed after restart, with retry available. Partial
Docling conversion stays visibly partial.

The PDF is saved under `data/uploads/<id>/source.pdf`. Conversion JSON/Markdown,
figure files, evidence index, contextual chunks and worker logs live under
`data/preparations/<id>/attempt-*/`. Library entries and derived-file overrides are
saved in `data/gui-library.json` and `data/gui-overrides.json`; the original corpus
manifest is not rewritten. Progress is in `data/import-jobs/`, paper/index bindings
in `data/rag-state/`, and question jobs/traces in `data/question-jobs/`.

## Ask questions

Open a paper and select **Ask**. Existing papers offer **Prepare for questions**;
saved Docling JSON is reused, so PDF conversion is not repeated. Newly uploaded
papers are prepared automatically after transfer. The backend selects the paper's
index; users never supply index IDs, database passwords or API keys in the UI.

The pipeline is the tested playground implementation, moved into
`src/pbl_docintel/vector_rag/`. Playground files are command-line entry points into
that same package. The GUI never imports playground Python files.

- Docling extracts locally, using captions first and local Granite Vision only for
  pictures lacking captions; formula enrichment follows the reviewed converter.
- HybridChunker uses the pinned R2 tokenizer and preserves heading/source context.
- Local `ibm-granite/granite-embedding-small-english-r2` embeddings use PostgreSQL
  with pgvector. The default retrieves candidates using vector similarity and
  PostgreSQL native full-text search, combined with reciprocal rank fusion (RRF).
- A bounded NVIDIA call interprets normal-language questions and creates search
  variants while preserving the original wording. Overview/problem/contribution
  requests also select original abstract, introduction and concluding passages
  when those sections exist. Inline `Abstract.`/`Abstract:` paragraphs are recognized
  by source references and their opening label even when Docling labels them as
  ordinary text. The extraction and embedding rows remain unchanged. This is not
  a generated whole-paper summary index. Overview instructions ask for a concise
  explanation of the problem, approach, findings and limitations where supported.
- Metadata questions also use original page-one headers/footers from the
  fingerprint-checked Docling JSON. HybridChunker normally omits these as running
  page furniture. Supplemental items retain their exact text, references and page
  positions; they are not generated metadata or new embedding rows. The trace
  marks their origin `docling_document` and IDs `docling-item:<reference>`.
  Metadata requests retain these items together so a footer date is not separated
  from a nearby submission label. Version, manuscript and journal dates must be
  distinguished; a PDF version date alone does not establish first publication.
  Header/footer supplements are not supplied for overview or content questions;
  pure header/footer chunks are also filtered from those candidate pools.
- NVIDIA `nvidia/llama-nemotron-rerank-vl-1b-v2` ranks sanitized text candidates.
  Up to five complete passages reach the answer model by default. Overview
  selection preserves section coverage; passage text is not silently truncated.
- The NVIDIA answer endpoint reads retrieved evidence. Quotes and citation IDs are
  validated; page numbers and PDF regions come from saved source metadata.
  Nemotron-3 uses JSON object response mode with thinking output disabled for this
  structured step. One bounded repair identifies the actual failing schema fields;
  validation is not weakened to accept malformed answers.
- Answered, partial, insufficient-evidence, clarification-needed and failed responses remain distinct.
  Matching quotes do not independently prove the interpretation is correct.
  A live integration check exposed a training-versus-inference conflation; the
  shared answer instructions now explicitly distinguish stages, resource types
  and causal mechanisms. The extraction and embedding model/settings are unchanged.

Click **Page …** below a quotation to open its source in the adjacent PDF viewer.
On narrow displays, this switches to Original source. Expand Retrieved passages to
inspect the context sent for answering. How evidence was selected explains the
retrieval stages, and visible notices identify unavailable interpretation/ranking.
Completed answers remain saved under **Previous questions**. Opening/reopening a
paper starts a blank Ask form; an active question resumes. Switching papers resets
the form and visible answer, and history is scoped to the selected paper. A fresh
question has no hidden conversation context. A follow-up can use the displayed or
explicitly selected completed answer and its preceding turn, with server checks
that both belong to this paper. Previous answers and
search variants are not factual evidence; the answer still requires source quotes.

Configuration stays server-side. Root `.env` supplies `NVIDIA_API_KEY` and optionally
`NVIDIA_MODEL`/`PBL_MODEL_NAME`. PostgreSQL settings (`PGHOST`, `PGPORT`, `PGDATABASE`,
`PGUSER`, `PGPASSWORD`) may live in root `.env`; the existing
`playground/vector-rag/.env` remains a compatibility fallback. Set
`SANTIO_DB_ENV_FILE` before starting the service to select another configuration
file. No new Python environment is required. PostgreSQL/WSL must be running.

The reranker uses the same NVIDIA key. Optional server settings are
`NVIDIA_RERANK_MODEL`, `NVIDIA_RERANK_URL`, and `SANTIO_RERANK_ENABLED=false`.
Unavailable ranking falls back to fused search/section order with a visible notice;
an unavailable planner falls back to the original question and conservative intent
classification. The formerly documented text-only reranker endpoint returned HTTP
410 during verification, so the tested default is its VL successor, used with text.
These additional calls add latency and depend on NVIDIA account availability.

Broad requests such as "Tell me about the paper?" now retain overview intent
when the hosted planner fails, so existing abstract, introduction and conclusion
coverage remains active. Specific requests such as "What does this paper say
about LoRA?" remain fact queries in this fallback. Overview instructions prioritize
the research idea and contribution rather than appendix settings or section lists.

New indexes include an additive GIN full-text index. On this existing database it
was created without changing the 976 stored embedding rows. Native PostgreSQL
full-text ranking is not BM25. No re-conversion or re-embedding is required.

For a controlled CLI comparison, append `--retrieval-mode vector` (original
question, exact cosine search), `--retrieval-mode hybrid` (planning plus combined
search/sections), or `--retrieval-mode reranked` (the new default) to `rag.py`.
All modes use the same index, embedding model, answer model and quote checks.
Full traces record the plan, fallback state, candidate ranks, selected source
identifiers and timings under `data/question-jobs/<id>.trace.json` in the GUI.

### Watch questions in the terminal

Question diagnostics are printed in the same terminal that runs `npm run dev`
(or the Python backend directly). Restart that session after updating the code.
Worker output was previously saved only to a per-question log; it is now also
forwarded to the backend terminal with a `[RAG <question-id>]` prefix.

The output includes the selected document/index and model, actual planner/answer
prompts, raw model replies, token usage and finish reasons, candidate rankings,
selected source passages and page references, API failures, validation failures,
JSON repairs, retrieval recovery and the final accepted answer. Rejected replies
remain visible so an empty UI result does not hide what the model returned.
API keys, configured passwords and authentication headers are redacted/omitted.
Raw replies are model outputs, not verified claims. Logs show submitted prompts
and returned content, not private model reasoning.

The same diagnostics apply to the RAG CLI. To silence detailed terminal tracing:

```powershell
$env:SANTIO_RAG_TRACE = "0"
npm run dev
```

Use `"1"` to enable it again (the default). Full JSON traces and per-question
`.log` files under `data/question-jobs/` remain available with terminal tracing
disabled. Detailed logging does not make additional API requests.

### One evidence-recovery attempt

The main hybrid/reranked question path now makes at most one additional search
when there are no usable passages, or the first valid answer returns
`insufficient_evidence`. A bounded NVIDIA call reformulates the search using the
original question, document headings, previous queries and missing-evidence
feedback. It returns queries, not an answer or new document facts. This uses the
same configured model, endpoint and API key; no additional connection is required.

The second search remains scoped to the selected paper/index. It keeps usable
original evidence in contention, sanitizes new evidence, and reranks when enabled.
Only if the selected answer context adds passages does it request another cited
answer. The same schema, source-ID and exact-quote checks apply. If it still lacks
evidence, it stops; there is no third search. Partial answers and clarification
requests do not trigger recovery. API/authentication errors and database outages
are not treated as evidence misses, and this is not a model failover mechanism.

The existing progress area shows the extra search, and completed results explain
when recovery was used or unavailable. If recovery fails, the original
insufficient-evidence result and its source IDs are retained. Each round's plan,
sources, answer prompt, result and answer-call attempts are saved separately in
`retrieval_rounds`; `retrieval.recovery` summarizes the outcome. A repaired JSON
answer can make one extra answer call per round, independently of search recovery.
This can add API latency/cost and does not guarantee a better answer. It is not
an independent detector of incorrect answers: a valid `answered` response does
not trigger another search simply because its interpretation might be wrong.

Use `--no-retrieval-recovery` to disable it in the CLI. Explicit
`--retrieval-mode vector` remains a single-pass comparison baseline automatically.
The recovery tests cover empty/unchanged evidence, a second miss, endpoint/planner
failures, retained source identity, unknown citations and the one-retry limit.

### Temporary provider failures and waiting

Question planning, relevance ranking, answer generation/repair, and recovery
planning each allow at most **two additional transport attempts** for HTTP 408,
429, 500, 502, 503, 504, connection failures, and timeouts. A single retry controller
shares **60 seconds of total retry waiting per question**, including any answer
repair or retrieval-recovery round. This is a waiting budget, not an overall
question deadline: conversion, model loading and request execution take separate
time. SDK automatic retries remain disabled to avoid hidden nested attempts.

`Retry-After` seconds or HTTP-date is respected. Without it, waits are 4 and 8
seconds plus up to one second of jitter. A requested delay exceeding the remaining
budget is not shortened: that stage stops or uses its existing degraded fallback.
Credential/access errors, missing endpoints, bad requests and malformed model
content do not trigger transport retries. Planning still has its conservative
local fallback; unavailable reranking still preserves fused search order. Answer
generation reports a specific final error when retries cannot complete. There is
no automatic local LLM fallback in this change.

While waiting, the question remains active and its persisted `retry` metadata
includes the affected stage, reason, retry count and UTC retry deadline. The Ask
panel renders a live countdown and keeps Cancel available. Cancellation terminates
the owned worker, clears the countdown and prevents it from making another attempt.
Restarting the backend marks an interrupted job as failed rather than silently
continuing it. Retry only repeats the failed provider request with the same input;
an answer-generation rate limit does not re-extract, re-embed or retrieve again.

Terminal traces distinguish provider attempts, answer schema/citation repair,
and retrieval recovery. The saved report's `provider_retries` records safe event
metadata and waiting totals; `attempts` continues to identify generation/repair
rounds. Existing citation checks apply after a successful retry.

### Answer repair and partial output

An answer repair reuses the same retrieved passages; it is not another retrieval
round. JSON-object transport alone does not enforce our required response fields.
The client checks the complete schema and every parsable citation before asking
for its single repair. A missing `status` therefore no longer hides quotation
errors until that repair is exhausted. Feedback identifies all detected paths
and asks for separated verbatim quotations when the model joins sentences with
ellipses. Retrieval rounds and generation/repair attempts are labeled separately
in terminal output.

If the repaired response has a valid schema but only some claims pass citation
checks, the server withholds each entire invalid claim and returns a **partial**
answer containing only the remaining claims. It explicitly says how many generated
statements were withheld. This does not assert that the paper lacks those facts.
Original raw replies, rejected claims and reasons remain in the trace. Matching
quotes are still not independent semantic verification. No partial output is
promoted when root fields/state are invalid or no claim has usable citations,
except for the explicit missing-status normalization described below.

After the single repair, a still-absent `status` can be restored only when the
otherwise valid `claims` and `missing_information` unambiguously determine it
under the existing state contract. This restores result metadata, not facts or
quotations; it never overwrites an explicit status or fills other missing fields.
The restored object must still pass citation checks, and the raw reply plus the
normalization are recorded. Remaining invalid claims may only yield a labeled
partial answer. Malformed or entirely uncitable answers still fail.

Generation/validation errors are labeled `not_attempted_answer_validation_failed`
(or the corresponding API/incomplete-response reason) in retrieval recovery,
rather than misleadingly saying `not_needed`. Finding more passages is reserved
for insufficient-evidence results; it does not fix a model miscopying passages
already supplied. No quote matching or numeric checking has been relaxed.

An October 17 diagnostic froze AI-selected source references before testing 11
questions across the two prepared papers. At five passages, vector-only search
found a selected supporting reference in 5/11 cases, hybrid selection in 10/11,
and reranked selection in 11/11. The exact failing overview question and short
LoRA expansion question were recovered. No planner/reranker fallback occurred.
This is a small source-retrieval diagnostic, not verified ground truth, an answer
accuracy percentage or evidence of universal improvement. The reproducible runner
is `playground/vector-rag/diagnostics/check_retrieval_upgrade.py`; results from this
run are in `tmp/retrieval-comparison/`.
Two additional answer checks reused the retrieved passages: the short LoRA question
returned its correct expansion with a source quote, and a GPT-5 MMLU question against
Tetris3D passages returned insufficient evidence. Both used one request. They test
generation from these passages, not fresh retrieval or general hallucination rates.
In the browser, the formerly failing overview question produced a cited answer;
its citation opened the abstract on PDF page 1. A subsequent “How many scenes does
that new dataset have?” resolved ComOb from recent context and answered 1.2M with
original source quotes. These full question jobs took approximately 32 and 34
seconds, including worker/model startup. The follow-up needed one quote repair;
an inexact quotation was rejected before the corrected answer was accepted.

## Explore evidence

Open a paper from the library. Select **Results, Tables, Figures, Equations, or
Text** in the evidence explorer. Use its picker, search, or expandable list.
The original PDF opens at the selected evidence location. On a narrow display,
use **Original source / Evidence** tabs; selection is preserved between them.
On desktop the evidence panel can be resized using its divider or arrow keys.

Page navigation and zoom operate on the actual PDF. Highlights show the selected
region and supporting evidence. Enable All regions to browse detections, or turn
highlights off to select the original PDF text. Source navigation scrolls the PDF
pane without moving the whole page. Figure, table and equation selections show
crops from the rendered original. Table cells expose available headers/captions
and a parent-table link. Coordinates are positions, not confidence values.
Missing/invalid coordinates never gain fabricated highlights; coarse table-level
locations retain their stated granularity.

Detected picture regions are not interpreted diagrams. Empty equations are
explicitly labeled as lacking transcription. Semantic experiment extraction is
not implemented. The existing nine Tetris3D annotations are manually curated;
new uploads receive detected evidence, not invented experiment annotations.

## Review, comparison, and exports

Review shows unresolved/failed attribution findings. Raw merged values remain
intact. Passing machine checks do not establish human review or scientific
correctness. Review decisions and corrections are currently read-only.

Compare is a provisional source-linked result table. Experiment compatibility,
cross-paper ranking and automatic leaderboards are not implemented.

Export offers available evidence JSON, unchanged Docling JSON, RAG JSONL, and
result JSON/CSV/Markdown and attribution checks when annotations exist. After search preparation, Indexed passages exports the exact contextual JSONL used by the vector index; Evidence SDK chunks are a separate integration export. JSON
preserves exact text; CSV protects spreadsheet formula fields. Original source
fingerprints and evidence IDs remain in the SDK exports. RAG chunks can be used
by Python/retrieval systems; the Ask view now generates source-linked vector RAG answers separately.

## Implementation and validation

React/Vite source is in `frontend/`; `npm run build` writes the owned
`src/pbl_docintel/gui/static/react/` directory. PDF.js 6.4.299 and its resources are
vendored locally under `static/vendor/`, with license and source checksum.
The exact user-supplied fragment shader is in `frontend/src/shaders/waves.frag`.
It uses plain WebGL1, a fullscreen triangle and the unchanged supplied shader and
packed uniforms. The canvas is mounted only inside the library's top hero, not
across the library or PDF workspace. GPU drawing is capped at 24 frames/second;
the drawing buffer uses at most DPR 1 and 600,000 pixels. Layout is measured on
resize rather than on every frame. The WebGL context requests low-power mode,
which is a browser hint, not a guarantee about GPU selection or energy savings.

Motion is managed automatically: it pauses when the hero scrolls out of view,
the tab is hidden, an upload dialog is open or imports are processing. System
reduced-motion preferences receive a still frame. Opening a paper unmounts the
shader and deletes its WebGL resources. The visible play/pause control is removed;
old saved motion overrides are no longer used. Active wall time keeps the recipe
speed despite the lower draw rate, and hidden/paused time is excluded. Context-loss
handling and the static CSS fallback remain. See [hosting status](HOSTING.md) for
Vercel deployment requirements.

```powershell
npm run check
npm test
npm run build
.\.venv\Scripts\python.exe -m pip install -e ".[gui,test]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The Python tests cover the SDK, attribution, source identity, local HTTP
boundaries, persistent registrations/jobs, invalid/oversized uploads and foreign
origins, transfer confirmation, restart/retry recovery, retained extraction,
server-selected question indexes, snapshot guards and indexed-passage export. Seven frontend tests cover animation timing, pause/resume, automatic
motion policy, drawing-buffer limits, frame pacing and PDF coordinate projection
including rotation/crop offsets.
Browser QA covers the actual library, result selection,
review ambiguity, original source/crops, exports, shader compilation, and narrow
layouts. A real 47-page upload was converted and indexed in an isolated test workspace.
The existing survey in the main library was separately prepared from its saved
JSON. Retry after an unavailable database retained extraction and reused chunks.
Workers explicitly use UTF-8 so Windows pipes preserve mathematical symbols.
A short acronym-only LoRA query missed the relevant passage in its first five
vector results and returned insufficient evidence. The fuller LoRA question
retrieved supporting passages. A fresh-upload answer still combined training and inference benefits in one
sentence despite the clarified prompt. Answer wording remains model-dependent;
quote validation is not semantic verification. These are smoke checks, not an
accuracy benchmark. These checks do not establish
semantic extraction accuracy or hosted-product readiness.

The retrieval upgrade and history/metadata/inline-abstract fixes add 17 checks (80 Python tests total): validated
query plans, explicit fallbacks, rank fusion, section coverage, parameterized
document-scoped text search, source budgets, malformed reranker output, preserved
vector-only mode, follow-up context boundaries, pre-API source guards and the
Nemotron structured-output request/repair. The 10 existing RAG contracts, seven
frontend tests, type check and production build also pass.

`Architecture_Final.pptx` is unrelated and excluded from this implementation.
