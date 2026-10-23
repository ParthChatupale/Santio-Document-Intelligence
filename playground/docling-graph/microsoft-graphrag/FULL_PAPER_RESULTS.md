# Full-paper Microsoft GraphRAG experiment

**Important follow-up audit:** [Semantic completeness and native-parser replay](runs/tetris-full-v1/inspection/SEMANTIC_COMPLETENESS_AUDIT.md) found 14 malformed responses with unparsed records, beyond the initial review. It also confirms SAM3/Qwen relationships through the inference-pipeline path; lack of a direct edge is not an omission. See the new audit for the corrected assessment.


23 October 2026. The isolated full-paper index, interactive graph and question room are implemented. **Processing coverage passed; semantic quality did not pass the gate for integration into the main website.**

Open the running room at **http://127.0.0.1:8773/**.

## Document and scope

- PDF: `C:\Santio\2610.10539v1.pdf`, the 30-page *Tetris3D: 3D Scene Generation With Objects That Fit Together* paper.
- Reused saved extraction: `C:\Santio\outputs\2610.10539v1.json`. No new PDF conversion and no PDF binary uploaded to NVIDIA.
- Source SHA256: `c7cca5c7618d084c22ec026bd53ac0848e19346af4109a4209c2f77b7ef7e58a`.
- Main text and appendices included. Bibliography/page furniture exclusions are documented in `runs/tetris-prepared-final/preparation_report.json`; all 498 source items are accounted for. This is full substantive-paper scope, not an assertion that every PDF element was sent to the model.
- The adapter preserves readable headings, table text, captions and figure child text, with original Docling references/pages in a sidecar. These are text-based graph inputs; this experiment does not embed image pixels or generate fresh figure descriptions.

## Actual index output

| Artifact | Count |
|---|---:|
| Input/native documents |147|
| Native text units |155|
| Text units with a successful extraction request |155|
| Entities |320|
| Relationships |439|
| Communities / reports |70 /70|
| Dangling relationships |0|
| Relationships missing a source mapping |0|

The run is `runs/tetris-full-v1`. Native Parquet tables are in `output/`; readable JSON/CSV is in `readable/`; LanceDB vectors are in `vectors/`. `graph-export.json` is the viewer export, including review annotations. Native records remain unchanged.

`coverage.json` and `run.json` record complete processing, no unmapped input records, no missing reports and an unchanged source hash. They deliberately retain `quality_verified:false`. Complete requests and valid references do not establish correct interpretation or relationship recall.

Microsoft GraphRAG 3.3.0 is installed as a Python package in the sandbox's Python 3.13 environment; no repository clone was needed. Native Microsoft code performs extraction orchestration, merging, communities, reports and Basic/Local/Global retrieval. Our provider bridge supplies NVIDIA completions and local Granite embeddings.

- Completion model: `nvidia/nemotron-3.5-super-vl-120b-a12b` through the NVIDIA endpoint.
- Embedding model: cached `ibm-granite/granite-embedding-small-english-r2`, revision `2ab6fa8ea2d674564defd37171ae19079b864b33`, 384 dimensions, CLS pooling and L2 normalization. Actual inference logs report CUDA.
- Indexing required 486 remote attempts: 345 completed and 141 failed, plus 716 separately counted cache hits. Failures/retries are retained in `model_calls.json`; cached responses are not counted as new API calls. Historical obsolete failed summary requests remain recorded; the final successful attempt passed its own coverage/failure checks.
- The 462.79 seconds in the final manifest describe the final recovery attempt, **not total indexing duration**. Cumulative call times overlap and must not be treated as wall-clock duration.

## What you can inspect

The graph room supports name/type/community filters, node dragging, pan/zoom, node and edge inspection, native descriptions, review warnings, graph download and original evidence beside the PDF. The layout settles once rather than animating permanently.

The question panel offers native **Local** (entities, relationships and source passages), **Basic** (vector passages), and **Global** (community map/reduce) modes. Saved answers expose exact retrieved context and clickable source mappings. The room serializes questions, keeps credentials on the server, and restores saved answers for this run after reload. Global is implemented but has not yet demonstrated reliable completion with this endpoint; see the execution record below.

Browser verification passed for submitting a real Local question, receiving its answer, opening the TRELLIS.2 citation, displaying Docling paragraph31 beside PDF page2, and restoring the answer after reload. The answer correctly identified TRELLIS.2 and V2I but incompletely described the added mechanisms; the UI is not an accuracy guarantee. No browser console errors were observed. Screenshot: `runs/tetris-full-v1/graph-room.png`.

## Source-backed relationship review

The frozen development reference is `evaluation/tetris_full.json`: 12 relationship facts, 4 forbidden interpretations and 12 question scenarios, prepared from original passages before inspecting the full graph. This is AI-prepared development evidence, **not independent ground truth or a held-out benchmark**.

A fixed-seed uniform sample of 24 native relationships was compared with its source passages. 23 descriptions were broadly supported and 1 contained an unsupported claim. Several supported records were generic heading links, contextual links or numeric claims needing condition labels. **23/24 is not whole-graph precision**, especially because targeted checks found additional errors. Full recall has not been measured.

Review records are under `runs/tetris-full-v1/evaluations/source-review/`. There are 7 flagged relationship descriptions and 3 flagged entities, from sampling plus targeted checks. The native graph has not been silently corrected or filtered to improve its apparent score.

| Problem found | Source check and impact |
|---|---|
| WorldSculpt classified as a dataset | Paragraph 154 names it as a baseline method; 155 names the actual evaluation datasets. Five relationship descriptions inherit the dataset error; community summaries repeat it. |
| ComOb training/evaluation role confused | The Tetris3D→ComOb edge describes evaluation, while paragraph 315 establishes training on ComOb. |
| DINOv3 role confused with segmentation | DINOv3 supplies frozen image features (31, 120); SAM3 supplies masks (352). The native edge incorrectly assigns mask generation to DINOv3. |
| Provenance extracted as concepts | Two nodes are the paper hash/source-record identifier, rather than scientific concepts. Our metadata packaging must explicitly prevent extraction of these identifiers. |
| Possible alias duplication |19 punctuation/spelling collision groups, including self-attention and metric variants. These are candidates for review, not19 proven duplicate merges. |
| Missing/split scientific links | Exact Tetris3D→SAM3/Qwen links are absent although appendix text states the roles. V2I exists under a longer alias, so exact-name mismatch alone must not count as a miss. The Pixal3D edge mentions inspiration but misses the specific weight-initialization predicate. |
| Low-value structure/numeric scope | Heading nodes, a Toys4K self-loop and metric descriptions lacking dataset/depth conditions inflate or weaken the graph. |

The WorldSculpt error was traced to a real extraction response, not the drawing code: request hash `b0af0ded5481659ecc0c5ace78b2ecc20c1843dcfdbb63c66990596ca3b382b6`. A native 600-token chunk split Table 1 mid-row; that fragment lacked its caption/column headings. The model treated a method row as a dataset. The adapter's complete table was intact, but later generic chunking lost the local context.

## Answer tests and their limits

Eleven Local development questions produced nonempty answers: 10 had resolvable citation IDs and 1 required citation review. The original paragraphs and actual cited records were then reviewed separately:

| Scenario | Source-backed assessment |
|---|---|
| Cup/table generation order | Correct; supporting paragraph 149 cited. |
| Interaction signals | Correct geometry/relation details, but wording should explicitly avoid implying a hard physical guarantee. |
| Training versus evaluation | Correct dataset roles, but the training sentence cites qualitative comparison 159 rather than training 315. This is a citation failure. |
| Hidden-object completion | Correct V2I mechanism and query/key/value roles. |
| Conditioning labels versus ComOb construction labels | Correct distinction: none versus pile. |
| ComOb sizes | Correct 1.2M scenes and 3.4M annotated samples. |
| Training hardware/duration | Correct two H200 GPUs and 7/9 days, with appendix citation 315. |
| Preprocessing tool roles | Correct content, but an unresolved entity citation and misplaced source citation. Relationship citations do reach 352. |
| Limitations / false guarantee | Correctly denies a universal guarantee, but misses 411 and uses an agent-baseline failure as supporting evidence. Omits actual error-propagation limitations. |
| Invented price/warranty question | Appropriately refuses to invent commercial details. |
| Table 3 Toys4K PD | Correct 0.0192 full versus 0.4980 without interaction conditioning; correct table citation. |

Detailed Local review: `evaluations/source-review/answer_review.json`. Raw question artifacts: `evaluations/20261022T145311946368Z/`.

Three paired Basic tests (generation order, training/evaluation, numeric table) all returned correct answers with appropriate supporting sources. Unlike the Local training answer, Basic cited the actual training paragraph 315. These three development comparisons do **not** demonstrate a GraphRAG advantage, statistical significance or general accuracy.

The posthoc WorldSculpt diagnostic is explicitly separate in `evaluation/tetris_diagnostics.json`. Basic correctly said baseline method and named Toys4K, Picasso and MessyKitchens. The first Local attempt failed because overlapping embedding workers made CUDA unavailable; a serialized retry successfully embedded the question but then received two NVIDIA 500 errors and a timeout. There is no Local answer to score for this diagnostic. Do not interpret a transport failure as evidence that the model answered incorrectly.

Global overview initially failed after timeouts exhausted the 100K conservative reservation budget. Its query cap was raised to a finite 250K (Local/Basic remain 100K) and an explicitly bounded cached retry was run. The final retry result is recorded in the execution addendum below. This change affects question execution only, not the indexed graph or its quality.

The diagnostic/evaluation directories retain every failure. Question timings include model loading, retrieval, requests and retries; they are not isolated generation latency.

## Automated checks

- 11 provider/source contracts passed.
- 12 explorer/retry/HTTP/coverage/page-preview contracts passed.
- 1 real-document preparation regression passed in the main Docling environment, including table values, captions/figure text, source mappings and original-file immutability.
- JavaScript syntax check passed; sandbox `pip check` found no broken requirements.
- Cross-origin question submissions and arbitrary filesystem routes are rejected; incomplete indexes cannot answer; PDF byte ranges and source routes were checked.

Tests establish these implementation contracts, not scientific answer accuracy. Use one evaluation worker on this 6GB GPU; the room already queues one question at a time. Avoid overlapping multiple benchmark processes that each load their own CUDA embedding worker.

## Decision and next work

**Ready for inspection and experimental questions. Not ready to present the graph as verified knowledge or integrate it as a trusted main-site feature.**

Before another full index: make every table fragment retain caption, headers and dataset/configuration labels; keep provenance identifiers outside extractable semantic text; supply actual paper-name context for appendix pronouns; canonicalize aliases; validate entity types and role predicates against sources before generating community reports. Then rebuild affected graph/reports and rerun the same frozen tests, retaining this run as the baseline. Review warnings are diagnostic annotations, not fixes to the native graph.

No changes from this task were made to the main React frontend, main API or PostgreSQL. Existing unrelated working-tree changes were preserved.

## Run it again

No indexing is required to reopen this saved room:

```powershell
$box = "C:\Santio\playground\docling-graph\microsoft-graphrag"
& "$box\.venv\Scripts\python.exe" "$box\serve.py" "$box\runs\tetris-full-v1" --port 8773
```

If the room is already running, simply open its link. Local/Basic questions use a 300-second watchdog; Global allows 600 seconds and 24 calls, but remains unreliable with the current endpoint. Server logs stay in the terminal that starts it; each saved question includes its own `worker.log`, `model_calls.json`, answer and context files.

## Execution addendum

Both Global attempts failed. The cached retry ended with `Model-call, token-reservation or time budget reached; run remains partial.` after 359.56 seconds for the retry invocation (604.02 seconds accumulated across the two attempts). The finite retry limits were 24 calls, 250000 reserved tokens and 600 cumulative seconds. Several map batches succeeded, but there is **no completed Global overview answer to assess**. Increasing a budget did not make an unstable endpoint reliable; no further automatic retries were launched.

The original failed answer is retained as `initial-answer.json`; the latest retry answer and complete request ledger are beside it under `evaluations/20261022T190703164783Z/overview/global/`. The parent `questions.json` retains the initial evaluation outcome. `evaluations/execution_summary.json` explicitly records both attempts, the Basic/Local diagnostics, browser question and 24 automated checks.

The source inspector was also visually checked after replacing the blank browser PDF plug-in with a PDFium-rendered original-page preview. It supports navigation between the pages belonging to a source record and keeps a direct original PDF link. A regression checks actual PNG output and page bounds; render calls are serialized and the memory cache is bounded to 8 pages. Native PDF byte-range serving is retained.
