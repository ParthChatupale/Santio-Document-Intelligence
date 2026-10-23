# Microsoft GraphRAG sandbox: implementation and testing plan

Prepared 22 October 2026 as the design checkpoint. Implementation and measured
execution status are now recorded in README.md and RESULTS.md. This document
describes the complete testing plan, not a claim that every stage has passed.
The existing website, environments, databases and old graph outputs are unchanged.

## 1. What this experiment must establish

1. Can we reuse saved Docling documents without losing important context?
2. Does Microsoft GraphRAG recover useful entities and supported relationships,
   rather than merely producing a large connected visualization?
3. Can users ask ordinary-language, factual, comparison and overview questions
   and receive supported answers with inspectable original-paper evidence?
4. Where does graph retrieval improve on our existing retrieval, and what does
   that improvement cost in indexing time, query time and model usage?
5. Can this implementation handle another paper and recover from failures before
   we integrate it into Santio?

Node count, edge count, a successful HTTP response and an attractive graph are
diagnostics. None alone establishes correctness or a completed paper analysis.

## 2. Implementation boundaries and dependencies

The sandbox lives inside `playground/docling-graph/microsoft-graphrag/`, with
its own environment, configuration, run directories and evaluation artifacts.
It does not import the old sandbox's schema, relationship extractor or heuristic
graph retriever. Microsoft GraphRAG owns graph extraction, entity/relationship
summarization, community detection, community reports and native query methods.
Our scripts prepare inputs, configure/invoke the library, map evidence, and test
the resulting artifacts.

Use a separate Python 3.12 environment if a compatible interpreter is available.
The project's existing interpreter is Python 3.14; Microsoft's current package
source specifies Python >=3.11,<3.14. Resolve and pin a published package version,
its matching dependencies and configuration format at setup. Record package and
interpreter versions. Do not install a moving GitHub branch into the main app.

Use Standard GraphRAG first. Its LLM describes entity relationships. FastGraphRAG
uses entity co-occurrence for its edges, making it unsuitable as our primary test
of semantic relationship extraction. Fast mode and DRIFT are later experiments.

Start with the configured NVIDIA Nemotron 3.5 endpoint, after a real structured-
output compatibility test. Record the exact model, endpoint and settings without
credentials. An OpenAI-compatible URL alone does not establish compatibility.
Keep the existing local Granite embedding model as the intended common embedding
baseline; test a supported provider adapter before assuming it works in GraphRAG.
If incompatible, document the change and re-embed both compared retrieval indexes
with the same replacement. Never mix vector spaces from different models.

Microsoft currently describes GraphRAG as a research implementation largely in
maintenance mode, rather than a supported commercial product. Pinning, preserved
artifacts and an integration boundary therefore matter for this experiment.

## 3. Proposed files, in review order

These are the responsibilities agreed at design time. See README.md for the
implemented entry points and RESULTS.md for actual test coverage.

| File | Responsibility | Reviewable output |
|---|---|---|
| `prepare_input.py` | Read saved Docling JSON and serialize readable content with provenance | Input JSON, readable preview, source map, conversion audit |
| `check_connection.py` | Verify GraphRAG completion/embedding contracts with tiny requests | Redacted compatibility report |
| `index_graph.py` | Invoke Standard GraphRAG with bounded work and versioned artifacts | Native tables, logs, manifest and coverage report |
| `query_graph.py` | Run native Local/Global queries and preserve context/citation records | Answer, retrieved entities/relations/passages, source links |
| `evaluate.py` | Run frozen cases and compare retrieval/answer modes | Per-case results and failure report |
| `settings.yaml` | Inspectable model, input, chunking, extraction and query configuration | Effective non-secret configuration snapshot |
| `evaluation/` | Development cases, sealed evaluation cases and source-backed references | Versioned JSON/JSONL fixtures |
| `runs/` | Generated artifacts, isolated per experiment | Manifests, native outputs, readable exports and reports |

Add small helpers/tests only where needed for provenance, budget enforcement,
failure handling and evaluation. Keep prompts inspectable and record changes.
The first review checkpoint is the actual prepared input and its source mapping,
before any paid or quota-consuming indexing experiment.

## 4. Document set and reference preparation

Use the saved documents already present in `C:/Santio/outputs/`:

| Document | Purpose |
|---|---|
| Tetris3D (`2610.10539v1.json`, 30 pages) | Known model, component, training/evaluation and numeric-table cases |
| A Comprehensive Overview of Large Language Models (`2307.06435v10.json`, 47 pages) | Long survey, shared names, inherited clauses and missing-link regressions |
| Never Look Back (`2610.10538v1.json`) | Transfer to another research topic after settings are frozen |

Record each source hash and inventory before running. Existing vector-RAG
experiments include a differently processed survey snapshot: references and
chunk identifiers must be revalidated against the chosen source. A filename or
arXiv identifier is not sufficient proof that two experiments used the same data.

Prepare an AI-assisted, source-backed evaluation reference before new extraction:

- Target 60 positive relationship facts, distributed across the three papers
  and their methods, evaluation and limitations sections: 20 development and
  40 evaluation facts. Record actual counts if fewer unambiguous facts qualify.
- Target 30 entity/type examples, including aliases and easy-to-confuse names.
- Include 15 forbidden or unsupported relationship interpretations.
- Prepare 12 development questions and 48 evaluation questions.
- For every expected fact: store exact source passages, Docling item references,
  PDF pages, interpretation, acceptable aliases and any uncertainty.

Select the reference from source text, not from whatever the new graph happens
to contain. New evaluation examples are frozen before the first Microsoft run.
Old development examples remain explicitly marked as already seen. After tuning
against an evaluation failure, that case becomes a regression; a fresh untouched
set is needed for another held-out claim. Do not call this independently verified
ground truth: the reference is AI-prepared, with optional user spot checks.

## 5. Stage A: input fidelity, before model calls

Keep the original Docling JSON intact. Produce a derived GraphRAG text view and
a sidecar mapping; do not overwrite the structured source.

Initial representation: one input record per logical source block, such as a
paragraph, table with caption, or figure with its author caption. Preserve the
paper ID and heading breadcrumb on each record. Where adjacent paragraphs must
be grouped, preserve all original item boundaries in the sidecar. Never split a
sentence or combine unrelated table rows simply to reach a target record size.

This is a proposed structure-preserving representation, not a native Docling
importer. GraphRAG still creates its own text units. Inspect those actual text
units after import: a DataFrame input bypasses file loading, not chunking.

Each exported record needs a stable source ID, title, readable text and source
metadata. The sidecar records source-file hash, paper identity, original items,
headings, pages and text-span mappings. Verify how the pinned GraphRAG version
retains input IDs and propagates metadata, rather than assuming it does so.

Check all eligible body text, headings, tables, author captions and available
formula text against an explicit inclusion inventory. Log bibliography/header/
footer exclusions. Preserve caption-to-picture associations. Keep AI-generated
figure descriptions separately labelled; exclude them from the primary factual
benchmark and test their addition later. Image pixels are outside this text run.

Unresolved merged cells and empty formula regions stay labelled unresolved.
Do not turn a figure caption into an assertion that the pixels were understood.
Preserve differences between original formula text and enriched model output.

Acceptance: 100% of eligible source items accounted for as included or explicitly
excluded; no unexplained text loss or duplicate serialization; all input source
references resolve; numeric/caption spot checks match the PDF. Every exported
record can be traced back. Global community citations may later resolve to
multiple passages/pages; never manufacture one precise page for a summary.

## 6. Stage B: compatibility and bounded extraction pilot

First check imports and actual runtime versions. Then make at most three small
compatibility requests: ordinary completion, the structured output format used
by the pinned GraphRAG workflow, and an embedding request/batch through its
configured provider. Local embeddings need no remote request. Check nonempty
outputs, schema compliance, dimensions and model identity; redact errors/keys.

Use 2-4 selected sections, approximately 3,000-5,000 input tokens, for the first
indexing pilot. Include one survey paragraph with several model/data assignments
and a Tetris3D component passage. They may be separate per-paper pilot workspaces.
No full-paper run until input fidelity and the pilot pass.

Configure research-oriented entity types, initially Method, Dataset, Concept,
Metric and Experiment. Keep the library's extraction machinery. Avoid forcing
our previous nested research template or hand-inserting expected edges.

Inspect the actual native entities, relationship descriptions, text units,
communities, community reports and vectors. Native outputs are usually Parquet;
add readable CSV/JSON exports for inspection without altering native results.

Important: Microsoft's native relationship table describes a relation between
two entities; it does not promise our old `BUILT_ON`/`TRAINED_ON` predicate schema.
Evaluate the factual meaning, ownership and direction expressed in its description.
The graph edge weight is not calibrated confidence or factual probability.
An arrow in a visualization does not by itself establish a semantic direction.

Review aliases, duplicate nodes, metric-as-method mistakes, training-vs-evaluation
confusion, wrong-clause ownership, missing dependencies and unsupported claims.
Graph communities organize the knowledge graph; they are not Docling's section
hierarchy. A small pilot need not produce many meaningful communities.

## 7. Stage C: extraction tests and scaling

| Scenario | Concrete source-backed check |
|---|---|
| Dependency | Tetris3D uses TRELLIS.2; WizardCoder is fine-tuned StarCoder |
| Shared base | Alpaca and Vicuna are derived from LLaMA |
| Dataset ownership | ShareGPT samples belong to Vicuna in the cited survey paragraph |
| Training versus evaluation | ComOb is training data; Toys4K is evaluation data in the cited Tetris3D protocol |
| Missing components | Recover MoGe3, SAM3 and Qwen3-VL roles from Tetris3D's preprocessing passage |
| Similar names | Distinguish LLaMA from LLaMA-GPT-4 and SAM3 from SAM-3D |
| Concept aliases | Recognize V2I Attention and its expanded name without inventing different mechanisms |
| Retrieval versus training | RETRO's MassiveText retrieval database does not alone establish a training-data assignment |
| Numeric scope | Keep table, dataset, row/configuration and metric with each value |
| Qualifications | Preserve nonguarantees, error propagation and metric-specific exceptions |
| Absent relations | Withhold Alpaca-trained-on-ShareGPT and unsupported reversed dependencies |
| Source boundaries | Figure descriptions and bibliography mentions do not become author-established facts |

For extraction recall, check every positive reference fact against native relation
descriptions and their actual source text units. For precision, audit all pilot
relationships and a reproducibly sampled 50 relationships per full-paper run, or
all if fewer exist. Stratify by section/relation type. Report supported,
unsupported and uncertain counts, denominators and sampling limits. Do not
interpret one correct clause as validating every clause in a long description.

Inspect entity references and graph endpoints for integrity over the complete
output, not just the sample. Check orphaned IDs and accidental alias collapses.
Sparse source coverage is a diagnostic; mention every empty/failed section rather
than silently calling it irrelevant. Coverage is not a demand for a fixed number
of nodes per page, and no relationship must be invented to satisfy a count.

Scale in order: Tetris3D full paper, survey full paper, then the third paper with
the model, prompts and extraction settings frozen. Keep their indexes separate
for the initial per-paper tests. A later combined index is a separate experiment.

## 8. Stage D: retrieval and answer evaluation

The 48 evaluation questions should cover the following categories:

| Category | Count | Example or expected behavior |
|---|---:|---|
| Direct facts | 8 | What dataset was Tetris3D trained on? |
| Ordinary-language paraphrases | 8 | Where does it get a sense of depth from one photo? |
| Connected/comparison questions | 10 | Which models share Vicuna's base, and do they use the same instruction data? |
| Overview and synthesis | 6 | What problem does the paper solve, how, and what remains unresolved? |
| Numerical/table context | 6 | Compare full-model and no-interaction-conditioning PD under the same ablation protocol |
| Ambiguity and source disagreement | 4 | If prose and a table report different sample counts, cite both with their contexts |
| Unsupported questions | 6 | An unreported warranty, absent model result or our project's retrieval accuracy |

Counts are targets to freeze before testing, not measured results. Verify each
example against the selected snapshot. Include exact-term/paraphrase pairs,
questions requiring two distinct passages, and questions whose premise is wrong.

Run Local Search first. It locates entities using embeddings and collects graph
and source context. Test Global Search separately for overview/synthesis using
community reports. Do not aggregate its results as though it used the same
retrieval path as Local Search. Try DRIFT only after these modes are dependable.

Save the question, query mode, selected entities, relationship descriptions,
text units/community reports, underlying source mappings, final answer, citations,
latency and token usage. A supported answer reached through ordinary source text
is not proof that the graph supplied its reasoning. Include evidence ablations.

Score retrieval before generation: was each required evidence group found within
the actual context budget? For paired facts, both must be present. Report top-1,
top-5 and top-10 source retrieval where comparable, but also report the final
context actually supplied to the model. More retrieved items are not automatically
better. Global report retrieval uses a separate measure and source drill-down.

Score answers for required facts, unsupported claims, correct numeric context,
appropriate abstention, citation resolution and citation entailment. A citation
that exists is not sufficient: inspect whether it supports the actual statement.
Use AI-assisted review with saved reasons and a deterministic citation resolver;
report disputed/uncertain judgments explicitly. Retain raw answers and contexts.

## 9. Fair comparison with our current RAG

Two comparisons answer different questions; label them separately.

1. Practical system comparison: current tested hybrid retrieval (vector + text
   search + reranking) versus Microsoft Local Search, using the same source
   snapshot, questions, final answer model/settings and total context allowance.
   This compares complete pipelines, not the isolated effect of a graph. Record
   differences in chunking, prompts and candidate selection. Avoid writing new
   results into the user's existing production/sandbox index IDs.
2. Controlled evidence ablation: take the same GraphRAG-selected source passages
   and answer prompt, once with source passages only and once with the selected
   graph descriptions added. Reserve an equal total context budget and record
   any displaced text. This tests the effect of adding graph descriptions after
   selection; it does not measure the benefit of graph-based retrieval itself.

For stronger retrieval attribution, later add a vector-only baseline over the
same native GraphRAG text units with the same embedding model. Distinguish that
controlled baseline from our current application, whose chunking differs.

Compare paired per-question results and per-category scores. Randomize/blind
answer order during review. Repeat a small representative subset three times
to expose variability. Freeze prompts/settings before evaluation. Do not declare
GraphRAG superior if the observed gains are absent, marginal or outweighed by
errors/cost. A small benchmark supports an engineering decision, not a market-
wide accuracy claim. Keep model-provider comparison separate from retrieval tests.

## 10. Failure, performance and isolation tests

- Completion key missing/invalid, retired model, rate limit and request timeout:
  clear stage-specific failure, bounded retries, no credential leakage.
- Malformed/truncated model response: save diagnostic status, do not count the
  text unit as fully analyzed, and do not promote an incomplete run as successful.
- Interrupted indexing: retain completed artifacts; verify native cache/resume
  behavior before promising that reruns avoid all requests.
- Long source block or oversized table: explicitly split with mappings, mark
  unsupported, or stop; never silently discard overflow or split merged values.
- Empty or relationship-free output: distinguish legitimately sparse content
  from failed extraction with the source-backed reference and coverage report.
- Source text containing quoted prompts: treat document instructions as data.
- Repeat question and repeated index: distinguish warm-cache performance from
  uncached requests and record input/configuration fingerprints.
- Paper switch and per-paper scope: no previous paper's answer or source leaks.
  A joint-index query is separate from a per-paper query and needs explicit scope.
- Local artifact serving after indexing: opening a graph does not make model calls.
- Optional source unavailable: diagnose the missing PDF/JSON rather than claiming
  that a citation was verified.

Record elapsed time, per-stage calls/tokens, uncached and cached request counts,
artifact size, peak resource usage where practical and query latency by mode.
Keep remote inference usage distinct from local embedding computation. A free
endpoint still has quotas and is not an unlimited workload budget.

Proposed initial limits: pilot at most 20 remote calls, 150,000 total reported
input/output tokens and 10 minutes; full-paper run at most 250 remote calls,
1.5 million reported tokens and 45 minutes per paper. Use one concurrent request,
zero automatic retries and zero optional gleaning for the initial pilot; tune
only with recorded evidence. Per-request timeout starts at 90 seconds.
These are test limits, not forecasts of required resources or expected accuracy.
Check/reserve request budgets before calls, stop scheduling new work at the cap,
and flag usage unknown for failures lacking provider accounting. Record unavoidable
in-flight overshoot. Budget exhaustion remains a partial run, not a success.

## 11. Proposed acceptance gates

These are engineering targets to freeze before evaluation, not existing scores.
Report raw counts next to percentages and the actual evaluated scope.

| Gate | Initial target |
|---|---|
| Input accounting and source IDs | 100% eligible items accounted for; all references resolve |
| Native artifact integrity | No dangling graph/text-unit IDs or cross-paper contamination |
| Audited relationship precision | At least 90% supported in the declared sample; uncertainty reported separately |
| Reference relationship recall | At least 80% of evaluable positive reference facts recovered |
| Critical false links | None of the named wrong-ownership, train/evaluate or reversed-dependency regressions accepted as established facts |
| Final evidence coverage | At least 85% of answerable questions contain all required evidence groups |
| Answer correctness | At least 90% of answerable questions meet the source-backed rubric |
| Citation support | All cited IDs resolve; at least 95% of audited factual claims have supporting citations |
| Unsupported questions | All six receive appropriate abstention rather than invented facts |
| Failure handling | Each defined failure remains visible and cannot become a completed run |
| Practical benefit | No more than one additional direct/paraphrase failure versus baseline; useful gains on connected/synthesis cases, or explicitly no demonstrated improvement |

Any critical wrong dataset/model attribution, invented numerical assignment or
cross-paper evidence leak blocks website integration regardless of averages.
If other targets fail, publish the failure breakdown and fix/retest in development.
Do not repeatedly tune on the same evaluation set and retain its held-out label.
Latency is measured before setting a product promise; unavailable or slow free
endpoints must remain distinguishable from defects in retrieval or extraction.

## 12. User review checkpoints and deliverables

1. Input checkpoint: source JSON versus actual GraphRAG input, exclusions, and
   a figure/table example traced back to the PDF. No indexing yet.
2. Compatibility checkpoint: actual configured models, successful tiny responses,
   embedding dimensions, package versions and request budget.
3. Pilot checkpoint: readable entity and relationship tables; correct/missing/
   unsupported examples; native visualization based on those same saved records.
4. Full-paper checkpoint: coverage, precision/recall sample, uncertainty and cost.
5. Retrieval checkpoint: question, selected evidence and cited answer side by side.
6. Comparison checkpoint: paired results, practical limitations and a concrete
   integration recommendation.

Keep each checkpoint concrete and inspectable so the user can follow the code
and results before dependent stages expand. These are the user-requested review
points, not additional approval rules imposed by a tool or external document.

Final artifacts: versioned input/source maps; exact configuration and prompt
snapshots; package lock/version record; native Parquet tables and vectors;
readable entity/relation/source exports; source-backed evaluation fixtures;
per-question evidence and answer records; timings/token accounting; failure
reproductions; and `RESULTS.md` with a pass/partial/fail decision for each gate.

Integration comes afterward through a backend service boundary, preserving
per-paper job progress, errors, source links and the current retrieval fallback.
The website should expose graph retrieval as a distinct tested option only when
this evaluation supports it. Until then the original app remains unchanged.

## Official references checked for this plan

- [Inputs and metadata](https://microsoft.github.io/graphrag/index/inputs/)
- [Standard versus FastGraphRAG](https://microsoft.github.io/graphrag/index/methods/)
- [Native output schemas](https://microsoft.github.io/graphrag/index/outputs/)
- [Model/provider requirements](https://microsoft.github.io/graphrag/config/models/)
- [Local Search](https://microsoft.github.io/graphrag/query/local_search/)
- [Global Search](https://microsoft.github.io/graphrag/query/global_search/)
- [DRIFT Search](https://microsoft.github.io/graphrag/query/drift_search/)
- [Python compatibility](https://github.com/microsoft/graphrag/blob/main/packages/graphrag/pyproject.toml)
- [Research project and maintenance status](https://github.com/microsoft/graphrag#readme)
