# Document intelligence project plan

Created: 8 October 2026. Status: proposed implementation roadmap.

Implementation update: the schema, evidence index, limited attribution checks,
and nine provisional reference annotations are implemented. Independent human
review, additional corpus selection, and semantic extraction remain pending.
See [the evidence foundation](INTELLIGENCE_LAYER.md) for commands and limitations.

GUI update: the local read-only Inspect workspace is implemented with an original
PDF viewer, selectable evidence regions, a flagged-result queue, provisional
result browsing and source-aware exports. See [GUI usage](GUI_USAGE.md).
Saved corrections and comparison compatibility remain pending.

Python/RAG integration update: the core is packaged with an adapter boundary,
source-aware retrieval chunks, an optional LangChain bridge, and cached arXiv
downloads. Two added PDFs are converted as heterogeneous ingestion tests; they
do not replace the planned set of comparable experiment papers. See
[the integration guide](PYTHON_RAG_INTEGRATION.md).

## Product objective

Help researchers and research engineers compare experimental results across related technical papers, inspect the supporting evidence, and identify comparisons that need human review.

The first domain should be one narrow computer-vision topic, provisionally 3D scene generation because our existing paper is Tetris3D. Confirm that a small collection of papers has enough shared benchmarks to support meaningful comparisons before locking the topic.

Primary user question:

> Which methods can I fairly compare on this benchmark, what results do they report, and where is the evidence?

The commercial hypothesis is that this reduces time spent building and checking research comparison spreadsheets. Demand for document review is established; willingness to pay for this particular workflow still needs validation.

## Existing foundation

- Python environment and Docling ingestion script are available.
- The Tetris3D paper has saved Docling JSON, Markdown, figure images, extraction summary, and QA notes.
- A layout PDF displays the detected regions and source locations.
- An observed extraction issue merges F1-S and F1-O columns in Table 2. This is an initial case for testing uncertainty handling.
- Formula regions are detected, but formula transcription has not been verified. Picture regions are not automatically diagram interpretations.

Keep the existing Docling output as the source representation. Preserve it and store our derived records separately.

## Scope of the first prototype

Start with five related papers and expand to 20–30 only after the small prototype works.

Include:

- Methods, datasets, metrics, and reported experimental results.
- Table headers, captions, footnotes, and nearby passages needed to interpret results.
- Source evidence, missing-context flags, and review status.
- Comparisons with explicit compatibility checks.
- A simple review screen and exportable comparison table.

Defer general-purpose paper chat, autonomous recommendations, broad subject coverage, equation solving, comprehensive diagram understanding, and a large graph visualization. Add formula or figure interpretation only when a target result cannot be understood without it.

## Milestones

Effort estimates assume one contributor and are planning estimates, not deadlines. User validation can run alongside implementation; recruiting and interviews may take longer than the coding work.

| Stage | Work | Deliverable | Completion condition | Approximate effort |
|---|---|---|---|---|
| 1. Validate the task | Select five related papers; collect examples of useful comparisons; speak with 3–5 prospective users about their current workflow | Corpus manifest, user-task notes, and five representative questions | Enough benchmark overlap exists; users identify a recurring comparison or checking task | 2–3 working days plus interview scheduling |
| 2. Define records and evidence | Design the result schema; build an index over saved Docling items and table cells; manually annotate a sample | Schema, evidence index, initial gold-standard records | A result can be traced to a specific source location and its context; ambiguous examples are included | 3–4 days |
| 3. Build a baseline extractor | Use a schema-constrained extraction pass over relevant tables and passages; validate its output | Results JSON and CSV for five papers | Baseline performance is measured against manual records; failures are recorded | 4–5 days |
| 4. Add verification and comparison | Check values, evidence, context, and compatibility; flag ambiguity and missing information | Verified records, comparison decisions, review queue | The known merged-cell example is flagged; incompatible or underspecified comparisons are not ranked as valid | 4–6 days |
| 5. Make review usable | Display results beside supporting source content; allow corrections and export | Small local review interface and evidence-linked report | A user can inspect, correct, and export a comparison without editing raw JSON | 3–5 days |
| 6. Evaluate and decide | Expand the corpus; evaluate held-out papers; compare baseline and verified workflow; observe user task completion | Evaluation report, demo, and documented limitations | Results show whether verification improves correctness and saves review time; next scope follows the evidence | 4–6 days |

Expected implementation effort: roughly 4–6 working weeks, subject to paper complexity and extraction quality.

## Result record

Each experimental result should preserve:

| Field | Meaning |
|---|---|
| Paper identity | Source filename, document hash, and paper metadata |
| Method | Reported method name, variant, and whether the row is an ablation or baseline |
| Benchmark | Dataset, split, task, and evaluation subset where reported |
| Metric | Original name, normalized name, unit or scale, and whether higher or lower is better |
| Value | Original text and parsed numeric value; preserve uncertainty or ranges |
| Conditions | Relevant inputs, training data, preprocessing, or evaluation protocol |
| Evidence | Docling item reference, page and bounding box; table row/column or text span where available |
| Context evidence | Separate anchors for headers, captions, footnotes, and passages supporting the interpretation |
| Status | Unreviewed, needs review, or human reviewed; machine-check outcomes stored separately |
| Run metadata | Conversion identity, extraction model/version, configuration, and schema version |

Unknown fields remain unknown. Store reported information separately from inferred or normalized information. A source match verifies attribution, not the scientific truth of a paper's claim. Docling item references are local to a conversion; do not assume they remain stable after reconversion.

## Verification behavior

1. Check that the numeric value appears in the referenced cell or passage.
2. Check that row and column context supports the assigned method and metric. Matching a number alone is insufficient.
3. Check metric scale, direction, and benchmark identity using cited definitions; do not guess them from abbreviations.
4. Flag suspicious merged cells, conflicting context, and unsupported assignments for review.
5. Compare results only when the required dataset, split, task, metric definition, and evaluation conditions are sufficiently aligned.
6. Classify each requested comparison as comparable, incompatible, or insufficient information, with reasons and evidence.
7. Preserve the original extraction and record human corrections as an auditable change history.

Start with deterministic checks and explicit rules. Introduce additional model calls only when a measured failure justifies them. Schema validation confirms format and types; it does not confirm factual correctness.

## Evaluation

Create approximately 100–150 manually checked result records across the corpus, including difficult tables and missing context. Split development and evaluation by paper. Reserve genuinely unseen papers for final evaluation and have a second reviewer check a subset when possible.

Compare two systems using the same input documents, schema, and extraction model:

- Baseline: Docling plus schema-constrained extraction.
- Proposed layer: the baseline plus context verification, compatibility rules, and selective review.

Measure:

- Numeric result precision: correctness of the entire method–benchmark–metric–value assignment.
- Coverage: how many target results are captured; count omissions and abstentions.
- Evidence support: whether anchors support the extracted result and its interpretation.
- Comparison correctness: agreement with manual judgments about compatibility, including insufficient information.
- Human effort: time to finish a correct comparison, including checking and corrections.
- Operational cost: processing time and model cost per paper.

Initial design targets, to validate rather than advertise: at least 95% precision among machine-accepted result assignments, source anchors for every accepted record, and fewer incorrect accepted comparisons than the baseline. Always report coverage alongside precision so rejecting most results cannot disguise weak performance. Publish sample size and uncertainty; a small benchmark cannot establish general reliability.

Do not expand to autonomous agents unless the underlying records and comparisons are dependable. If verification provides little benefit, simplify it. If five papers lack useful benchmark overlap, change the corpus before scaling extraction.

## Architecture and implementation order

```text
PDF -> existing Docling ingestion -> saved DoclingDocument JSON
                                     |
                                     v
                              Evidence index
                                     |
                                     v
                           Structured result extraction
                                     |
                                     v
                        Verification + compatibility checks
                                     |
                                     v
                           Human review + corrections
                                     |
                                     v
                        Comparison table + evidence report
```

Begin with JSON records and a command-line workflow. A graph can later express relations such as method evaluated-on dataset or result measured-by metric, if it improves queries. Choose storage based on those queries; a graph database is not an initial requirement.

Before model-dependent extraction, choose a local model or hosted API based on available hardware, budget, and document privacy. Avoid making that choice a dependency for schema design and evidence indexing.

## Immediate next step

Implement Stage 2's schema and evidence index using the existing Tetris3D conversion while selecting the remaining four papers. Manually annotate a small set of results, including the merged F1-S/F1-O case. This establishes the contract that the extractor and verification layer must satisfy.

Stage 1's user interviews should test the need before substantial interface work. Ask users to walk through their most recent comparison, show where they checked evidence, describe costly mistakes, and explain what would justify replacing their current tools.

## Market context informing this plan

- [Elicit](https://elicit.com/solutions/systematic-review) already offers structured research extraction and evidence synthesis. Specialization must go beyond generic comparison tables and citations.
- [Docling Graph provenance](https://github.com/docling-project/docling-graph/blob/main/docs/fundamentals/graph-management/provenance.md) already connects graph entities to source locations. Reuse or assess this capability before rebuilding it.
- [Independent Elicit feasibility study](https://www.cambridge.org/core/journals/research-synthesis-methods/article/using-elicit-ai-research-assistant-for-data-extraction-in-systematic-reviews-a-feasibility-study-across-environmental-and-life-sciences/C97DAEC70C3173A260F0B12E729E7250) motivates task-specific evaluation; it describes earlier workflows, not a current product ranking.
- [EviSearch preprint](https://arxiv.org/abs/2604.14165) shows that attributed extraction, verification, and selective review are already active research directions.
- [Adobe April 2026 report](https://business.adobe.com/resources/sdk/.state-of-ai-in-documents-adoption-soars-across-key-lines-of-business/state-of-ai-in-documents-april-2026-short.pdf) provides a vendor-survey demand signal for inconsistency checking and measurable workflow value.

The project's differentiation is a hypothesis: experimental-context-aware comparison for a narrow technical domain, with measured reliability and review effort. Validate that hypothesis against existing tools and real user tasks.
