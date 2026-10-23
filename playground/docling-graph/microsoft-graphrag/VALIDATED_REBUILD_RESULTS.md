# Validated Microsoft GraphRAG rebuild

23 October 2026. **The full index, graph room and answer tests are complete.**
The record-parsing fault is fixed. Semantic quality remains mixed, so this is
an inspectable sandbox, not a verified replacement for Santio's RAG.
`FULL_PAPER_RESULTS.md` records the original `tetris-full-v1` baseline.

## Source and implementation

- Paper: `C:/Santio/2610.10539v1.pdf`, Tetris3D, 30 pages.
- Saved Docling source: `C:/Santio/outputs/2610.10539v1.json`.
- Source SHA-256: `c7cca5c7618d084c22ec026bd53ac0848e19346af4109a4209c2f77b7ef7e58a`.
- Completed experiment: `runs/tetris-full-validated-v14`, 176 prepared records.
- Microsoft GraphRAG 3.3.0 owns Standard indexing, merging, community detection,
  reports, LanceDB storage, and Basic/Local/Global retrieval. Its installed code
  has not been modified. Our domain prompt and provider adapter are custom.
- NVIDIA Nemotron 3.5 Super VL is primary; Nemotron 3.5 Lightning is a disclosed
  failover after repeated upstream failures. Each request records its actual
  model. Local
  pinned Granite small English r2 provides 384-dimensional embeddings. A real
  CUDA smoke check passed on the RTX 3050. Native storage here is LanceDB.

Microsoft `graphrag==3.3.0` is an installed Python package; no clone was required.
Its installed implementation is unchanged. The scientific extraction contract,
context preparation and provider adapters are custom integrations.

The original website, PostgreSQL database, Docling source, and original native
graph tables are unchanged. Superseded attempts and their API ledgers remain
available. Only identical actual API requests reuse saved raw responses.
The final resume's 141-second duration and four fresh API attempts are not
full cold-index time or total project usage; much work reused saved responses.

## Repairs made

1. `prepare_context.py` repeats the paper title and local headings for each
   bounded passage. Each table row carries its caption, row label, table section,
   and hierarchical column headers. All source table-cell strings are accounted
   for; unresolved merged cells remain unresolved.
2. Figure captions enter the model-facing text. Diagram labels remain available
   in inspection metadata and the original PDF. Reading-order adjacency does
   not establish diagram arrows or tool roles. This avoids the observed false
   DINOv3-to-object-mask interpretation.
3. `_contracts.py` validates typed JSON, endpoint declarations, exact source
   quotations, selected role constraints and native record delimiters. Invalid
   candidates are retained with rejection reasons. A backbone/component can
   have a supported initialization link even if classified as Concept.
4. Canonical tuple responses close the completion record with a separator.
   The actual native two-pass extractor is tested to retain the first record
   of the additional pass. Checking each response in isolation was insufficient.
5. `_providers.py` keeps the model's original JSON in its continued conversation
   while returning validated tuples to Microsoft. Two failing continuation
   requests succeeded in a controlled JSON-history diagnostic.
6. An HTTP 500 on a structured request can retry using JSON-object transport. Full
   client schema and record checks remain mandatory. Every actual API request
   has its own fingerprint, payload and attempt record; there are no cache
   aliases. Equivalent validated retries share a logical request identifier so
   a recovered transport failure does not falsely fail the entire index.
   The fallback explicitly supplies the complete JSON schema as a system
   instruction. Two reproduced missing-field responses passed after that
   correction. Server error internals are unavailable, so these small diagnostics
   do not establish the cause of every NVIDIA 500 response.
   Two repeatedly failing requests also passed a Lightning failover diagnostic,
   including source review. This establishes feasibility, not comparative model
   accuracy. `SANTIO_GRAPH_FALLBACK_MODEL` can override or disable the failover
   (empty value disables it). No API key or project `.env` was changed.
   Failover covers plain-text description/answer generation as well as typed
   requests. For a typed request, the secondary model first uses schema-constrained
   output; a reproduced schema-echo failure passed this route in a live check.
7. `_query_runtime.py` enforces the native Global map response schema. Query
   failures cannot be silently promoted to a successful partial answer.
8. The graph room shows directed extracted assertions and their exact quotations
   separately from native merged edge summaries. Native weights remain
   occurrence weights, not confidence scores.
9. Report output budget is 8,192 tokens. Truncated responses are retained but
   cannot become successful reports. Valid legacy cached reports retain their
   actual original request settings. Code hashes prevent changed-code resumes.

## Evidence and limits

The original offline replay found 113 entity occurrences and 95 relationship
occurrences not separately parsed, plus 295 relationship weight fallbacks.
Those are occurrences before merging, not unique missing true scientific facts.
See `runs/tetris-full-v1/inspection/SEMANTIC_COMPLETENESS_AUDIT.md`.

The completed graph retains both Pixal3D component-initialization relationships
and Tetris3D training on ComOb. Root-method ownership remains incomplete; see
the semantic review below.

`inspect_validated.py` replays saved extraction records and, after completion,
the native initial-plus-additional-pass concatenation, merge and orphan filter.
It compares the rebuilt relationship pairs and weights with the native output.
It reports processing/format accounting, not semantic accuracy.

The source-backed development fixture is `evaluation/tetris_semantic_v3.json`.
It corrects one prior AI-reference overstatement: paragraph 358 names
Qwen3-VL-30B for object inventory, while physical-relation reasoning is attributed
there to a generic VLM. This is a documented source correction, not independent
human ground truth or a new held-out benchmark.

Exact quotation matching does not establish entailment. Rejection can also remove
recoverable valid facts. Full-PDF visual interpretation, exhaustive relationship
recall, multi-paper transfer, and an accuracy advantage over the old Docling Graph
sandbox or vector RAG have not been established by these engineering repairs.

## Final processing and replay

| Check | Result |
| --- | ---: |
| Prepared records / documents / text units | 176 / 176 / 176 |
| Text units with successful initial extraction | 176 |
| Native entities / relationships | **334 / 425** |
| Communities / completed reports | 45 / 45 |
| Initial and additional-pass responses replayed | 352 |
| Accepted entity occurrences / native parsed occurrences | 1,466 / 1,466 |
| Accepted relationship occurrences / native parsed occurrences | 979 / 979 |
| Native orphan pairs dropped | 0 |
| Native relationship pairs and weights | Exact replay match |
| Unresolved provider calls at completion | 0 |

See [the replay audit](runs/tetris-full-validated-v14/inspection/validated_record_audit.json).
Occurrences can repeat across passes; they are not independent facts. The old
graph had 320 entities and 439 edges. Those counts alone do not measure quality.

## Source-backed semantic review

The 12 selected scientific facts received AI-assisted source review:
**10 supported and two partially supported** in the merged graph.

- ComOb training; Toys4K, Picasso and MessyKitchens evaluation; MoGe3 depth/camera;
  SAM3 masks; Qwen object inventory; DINOv3 features; and V2I completion are present.
  WorldSculpt is now a method rather than a dataset.
- Both component-to-Pixal3D initialization edges survive. The direct
  Tetris3D–Pixal3D summary only says inspiration/comparison, and explicit root
  ownership links to both initialized components remain incomplete.
- ComOb's merged description blurs its training dataset with the scene generator
  used to construct Toys4K evaluation scenes. These scopes must stay distinct.

A uniform seed-42 sample of **24 native relationships** received source-backed
AI review: **18 supported, four partially supported, two unsupported claims**.
The wrong claims assign dataset containment primitives and a comparison-baseline
prompt to Tetris3D itself. Partial cases include imprecise formula predicates
and treating prompt instructions as observed implementation facts.
The sample was reviewed on v13 and transferred only after verifying identical
source/input hashes and exact source/target/description keys for all 24 v14 edges.
It was not reviewed again blind. These are development judgements, not independent
human ground truth or a population accuracy estimate. Native output was annotated,
not edited to fit the reference.

The validator withheld 250 relationship occurrences with undeclared endpoints;
some could be valid facts whose endpoints appeared in a previous pass. Rejection
can reduce recall. Complex Table 2 merged-header paths from Docling also remain
ambiguous for some individual numeric cells. Not all important relationships
or table assignments have been verified.

See [sample review](runs/tetris-full-validated-v14/evaluations/source-review/semantic_review.json)
and [core review](runs/tetris-full-validated-v14/evaluations/source-review/core_relationship_review.json).

## Actual question tests

All 21 CLI trials completed operationally: 12 native Local, three native Basic,
two native Global and four experimental source-focused Local trials. One further
posthoc Local question was submitted through the browser and its PDF citation opened.
An answered status or resolving citation ID is not a semantic pass.

| Test | Observed result |
| --- | --- |
| Local: order, V2I, relation labels, counts, hardware, preprocessing | Correct central facts on the selected questions |
| Local: overview | Correct mechanism, but overstates physical validity as ensured |
| Local: training versus evaluation | ComOb and Toys4K correct; Picasso/MessyKitchens omitted |
| Local: limitations | Correct no-guarantee conclusion; some cited context concerns related work |
| Local: unsupported pricing/warranty | Correct refusal |
| Local: Table 3 PD | Misses the relevant table and abstains |
| Basic: training/evaluation, preprocessing | Correct on both shared questions |
| Basic: Table 3 PD | **Correct: 0.0192 full model versus 0.4980 without interaction** |
| Global: overview | Correct main idea mixed with wrong component ownership propagated from reports |
| Global: limitations | Correct main conclusion; additional causal interpretations need source review |
| Experimental source-focused Local | Completes dataset list, but gives table numbers from other experiments; **not promoted** |
| Browser: DINOv3 versus SAM3 | Correct roles; citation opens paragraph 352 on PDF page 18 |

The default remains Microsoft's native query profile. Optional
`--profile source-focused` is a recorded development experiment, not a recommended
fix or held-out benchmark. Its prompt and hash are saved with each query.
No expected-answer numbers were injected into retrieval, graph data or prompts.

Basic is Microsoft's legitimate vector-only baseline. On these three shared
questions it is at least as useful and handles the numeric-table case better.
This small test does not establish general superiority over Local, Santio's main
hybrid vector RAG or Docling Graph. Global report synthesis can amplify wrong
graph interpretations. Direct selected-source coverage is reported separately
from graph provenance coverage; neither is an entailment score.

Answers, selected contexts, requests and individual verdicts are in
[the answer review](runs/tetris-full-validated-v14/evaluations/source-review/answer_review.json).
**48 sandbox regression tests and one Docling preparation test passed**; JavaScript
syntax checking passed. Logs are in the final run's `verification/` directory.

## Open or restart the graph room

The current room is **http://127.0.0.1:8775/**, serving the completed v14 graph.
Select Basic, Local or Global when asking. Original PDF links and exact retrieved
context remain available. This isolated localhost sandbox does not need WSL
PostgreSQL running and has not been integrated into the main website.

To restart after stopping the existing server:

```powershell
cd C:\Santio
$box = "C:\Santio\playground\docling-graph\microsoft-graphrag"
& "$box\.venv\Scripts\python.exe" "$box\serve.py" "$box\runs\tetris-full-validated-v14" --port 8775
```

Keep the working vector pipeline available. Before website integration, address
entity ownership/alias consolidation and explicit table scope, then evaluate new
questions and papers with independently reviewed evidence. Completed processing
does not remove these remaining quality limits.
