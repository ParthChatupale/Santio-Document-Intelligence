# Research evidence workspace: GUI plan

Status: first read-only GUI milestone implemented, 8 October 2026. See
[the usage guide](GUI_USAGE.md). Saved corrections, compatibility assessment and
RAG answering remain later milestones.

## Recommendation

Build an optional browser-based research workspace over the Python library. Its central interaction is **select a result → inspect its source → understand its conditions → review it → export it**. The Python/RAG integration remains independently usable.

Use an evidence-first layout for the initial screen. Keep a table-first layout as a later presentation option for users checking many results. The accompanying interactive design preview uses a small selection of existing records; its source pane is a schematic, not the original PDF viewer, and it does not save decisions.

## Desktop layout

| Area | Content | Purpose |
|---|---|---|
| Top bar | Project name; Inspect, Review, Compare | Switch tasks while keeping document and result selection |
| Library, left | Paper titles, processing state, corpus role | Distinguish comparison papers from ingestion tests and references |
| Source, center | Original PDF page, selectable regions, zoom and page navigation | See the actual evidence in context |
| Evidence inspector, right | Reported method, dataset, metric, raw value, conditions, checks, review state | Understand the selected result without reading JSON |
| Local source controls | Text/table/picture/formula overlays; extraction/original view | Inspect detections and extraction failures |

Target approximately 18% library, 50% source and 32% inspector on a large screen, with resizable panes. At smaller desktop widths, collapse the library into a document picker. On mobile, stack the content and switch between Source and Evidence; do not shrink an entire PDF page until its text is unreadable. Maintain the selection when changing layouts.

Use restrained neutral surfaces, readable typography, clear borders and one active-selection accent. Pair every colored region or status with a text label. Avoid a graph as the landing screen: a dense graph does not answer whether a reported number is supported or comparable.

## Main screens

### Inspect: first implementation milestone

Open a processed paper directly from its saved outputs. Show its original PDF and the indexed evidence together. Selecting a table cell highlights its value, row label and metric header, and exposes its caption, footnotes and relevant passages. Selecting evidence from the inspector moves the PDF to its page; selecting a PDF region opens the corresponding evidence item.

Provide a document-local list of tables, figures and equations. Pictures are labeled “Detected picture”; diagram interpretation is a separate future capability. A formula with empty extracted text is labeled “Formula region detected; transcription unavailable.” Display the source crop and any available text without inventing a transcription.

Display friendly labels first. Put document fingerprints, evidence IDs, item references, coordinates and chunk metadata in expandable “Technical details.” The numbers in bounding boxes are coordinates, not confidence scores.

Show raw table cells even when no result record exists. For the two additional PDFs, state “No result annotations yet.” Ingestion success must not imply successful experiment extraction.

### Review: second milestone

Use a queue of concrete issues, each linked to the affected source region. Start with the two existing Tetris3D annotations whose F1 values were merged. The original extracted value stays visible beside a proposed correction. A reviewer can correct the mapping, retain the ambiguity, or reject a derived record.

Save reviews only after an explicit user action. A saved correction must include reviewer identity, timestamp, reason, before/after values and source links. Keep immutable Docling output and derived annotations separate. An append-only revision log and persistence layer must be added; the current schema has review fields but no correction history.

Separate these states:

| State | Meaning |
|---|---|
| Processed | Docling outputs and index exist |
| Evidence checks passed | Current automated attribution checks passed |
| Needs review | A detected issue or ambiguity needs inspection |
| Human reviewed | A reviewer explicitly assessed the record |
| Comparison pending / compatible / incompatible | Outcome of a separate comparison assessment |

Do not rename “Evidence checks passed” to “Verified,” and do not manufacture confidence percentages. Review completion and comparison compatibility are different decisions.

### Compare: after extraction and compatibility rules

Present a comparison matrix grouped by benchmark and metric. Clicking any value opens its source and context. Preserve reported values and reported scales; show any normalization separately with its rule and evidence.

Before ranking across papers, assess dataset/version, task, split, subset, metric definition, direction, units, scale, input access and evaluation protocol. Missing information gives “Comparison pending,” not automatic compatibility. Explain incompatible conditions, such as video access versus no video access. Support an exploratory view of unresolved rows, but keep them out of a ranked comparison.

The current nine annotations are provisional, manually curated examples. Seven pass limited evidence checks, two require review, and none has independent human review. They support an interface demonstration, not a validated cross-paper leaderboard. The survey and Never Look Back paper are ingestion stress tests and should not be grouped into a Toys4K leaderboard.

### Export and integration

Offer existing evidence JSON, result JSON/CSV/Markdown and RAG JSONL where available. Explain whether each export contains raw evidence, provisional annotations or reviewed records. An export preview should show provenance and flags before the user downloads it.

The library already exposes `index_document`, `rag_chunks`, `resolve_evidence`, `validate_results`, `write_rag_jsonl`, and an optional LangChain adapter. The GUI should use these interfaces rather than reimplementing parsing or RAG chunking. A retrieval/answer screen can follow later: each answer must link to supporting evidence and preserve unresolved issues. No answering model or vector database exists yet.

## Feature availability

| GUI feature | Existing foundation | Work still required |
|---|---|---|
| Browse papers and corpus roles | Implemented local library over corpus manifest | Import jobs and richer library management |
| Inspect detections | Implemented original-PDF viewer, overlays and crops | Resizable panes and broader viewer evaluation |
| Inspect result attribution | Implemented result selection and source navigation | Further comparable papers and semantic extraction |
| Show uncertainty | Implemented friendly findings and read-only review queue | Saved review decisions and correction history |
| Edit and save corrections | Typed result schema | Revision log, persistence, reviewer workflow |
| Compare compatible experiments | Result fields for metric/conditions | Semantic extraction, compatibility rules and evaluation |
| Integrate with Python/RAG | Packaged SDK plus read-only GUI adapter and downloads | Retriever / answer integration |
| Explain diagrams/equations | Picture/formula regions | Interpretation/transcription and their evaluation |
| Browse semantic relationships | Structural evidence context | Semantic relationship extraction and an evaluated graph |

## Application boundaries

Keep three parts distinct: the existing Python core, a thin local application service, and the viewer. A browser frontend is the recommended direction because source overlays and synchronized inspection need precise control. Choose the specific frontend/viewer libraries during implementation, after verifying their current APIs and licenses.

The local service should expose the SDK's existing contracts and return stable evidence IDs. Add only the routes needed for loading documents, retrieving evidence/checks and exporting files in the first milestone. Review persistence and import jobs follow separately. Conversion runs as a background job with stage and failure messages; avoid guessed progress percentages. Browsing a processed document should never reconvert it.

Coordinate handling must respect page dimensions, bounding-box origin and zoom. Preserve coarse or multi-page locations as such; do not draw a precise cell highlight when the extractor only supplied table-level provenance. Corrupt, missing or mismatched source files should be visible loading errors rather than silently showing the wrong PDF.

The initial deployment target is local use by one researcher. Authentication, collaboration and remote hosting are future scope. The optional UI must not add frontend dependencies to the core Python import path.

## Build order and acceptance criteria

1. **Read-only inspection — implemented.** Load the three converted papers. Select a result and jump to the correct original page/region. Display all nine provisional records, seven passing checks and two review cases accurately. Show figures, empty formulas and zero-cell tables without claiming semantic interpretation.
2. **Review persistence.** Save a source-backed correction as a new revision; reopen it; inspect the audit history; regenerate checks and exports from the selected revision. Original Docling output must remain unchanged.
3. **Useful comparison.** Add the remaining comparable papers and implement/evaluate extraction and compatibility rules. Show compatible groups, pending cases and exclusion reasons before offering rankings.
4. **Retrieval workspace.** Connect a chosen retriever through the SDK, show chunk-level evidence and evaluate supported answers. Add a small relationship view only when extracted relations help a real task.

Test the GUI on actual workflows: locate the source of 3.68; explain the merged F1 cell; inspect the survey's zero-cell table detection; distinguish Never Look Back's input conditions; export records with their evidence. Measure task completion and review time with a few prospective users before broadening the interface.

The next GUI implementation step is saved corrections with review history.
Automatic semantic extraction and comparison evaluation remain necessary project
milestones; the interface does not substitute for them.
