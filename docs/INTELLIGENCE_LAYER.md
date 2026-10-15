# Evidence foundation, version 0.1

The first implementation adds strict result contracts, an evidence index over saved Docling output, and limited attribution checks. It does not run an LLM or automatically extract semantic result records yet.

The core now lives in the installable `pbl_docintel` package. See
[Python/RAG integration](PYTHON_RAG_INTEGRATION.md) for adapter and chunk APIs.
The existing script commands below remain supported.

## Run

From the repository root, using the existing environment:

```powershell
.\.venv\Scripts\python.exe -X utf8 src\build_evidence.py outputs\2610.10539v1.json --source-pdf 2610.10539v1.pdf --results data\annotations\tetris3d.sample.json
```

For a new document, omit `--results` to build only its evidence index and contracts. Use a separate `--output-dir` for each document. The default directory is `outputs/intelligence/`. A directory containing result exports requires `--results` on subsequent runs, preventing old reports from silently accompanying a new index.

The CLI returns 0 for completed builds, including cases needing review; 2 when annotations have invalid evidence assignments; and 1 for invalid input or a build failure. It validates the result collection before writing outputs and rejects paths that would overwrite inputs.

## Outputs

| File | Contents |
|---|---|
| `evidence.index.json` | Text, tables, pictures, individual table cells, original coordinates, structural context, and ambiguity flags |
| `result.schema.json` | Generated JSON Schema for result collections |
| `evidence.schema.json` | Generated JSON Schema for evidence indexes |
| `results.json` | Typed sample annotations with their original review status |
| `checks.json` | Per-record attribution errors and review warnings |
| `results.csv` | Flat result table for spreadsheet inspection |
| `results.md` | Readable table with supporting source excerpts |
| `summary.json` | Counts, document fingerprints, and check outcomes |
| `rag_chunks.jsonl` | Source-aware text/table chunks with scalar metadata for RAG hosts |

The sample run indexes 482 text items, 5 tables, 11 pictures, and 517 cells. Fourteen formula items have empty extracted text. Eighteen cells contain multiple numeric values; this flag signals ambiguity, not necessarily an extraction error.

Nine provisional sample annotations are provided: seven scalar results from Table 1 and two merged F1 cells from Table 2. They were curated by Codex against original PDF pages 6–7. Seven pass the implemented attribution checks; two need review. These nine examples are not a held-out accuracy benchmark, and none is marked as independently human reviewed.

## Identity and coordinates

- `document_id` is the SHA-256 of the exact saved Docling JSON bytes. Reformatting or reconverting changes this identity and invalidates annotation binding intentionally.
- `source_sha256` fingerprints the PDF supplied with `--source-pdf`. Its filename is checked against the Docling origin. This does not independently prove that the JSON was generated from those exact PDF bytes; add ingestion-manifest binding before production use.
- Native item references, such as `#/tables/0`, are retained in `item_ref`.
- IDs such as `#/tables/0::cell:96` are our evidence identifiers, not Docling JSON pointers. The cell index refers to the serialized `table_cells` list.
- Row and column offsets are zero-based and use exclusive ends. They describe the extracted table, which may differ from the source layout.
- Bounding boxes retain their original coordinate origin. Table-level boxes may use BOTTOMLEFT while cell boxes use TOPLEFT; consumers must account for that before drawing overlays.
- For a table spanning multiple pages, an unassigned cell box is not arbitrarily attached to a page. Table locations are retained with `granularity=table` and a review flag.
- Captions, footnotes, row labels, and headers are structural context. Their presence alone does not establish a semantic relationship.

## Checks and limits

Checks currently establish that:

1. Records refer to the indexed conversion and all evidence identifiers exist.
2. Optional quoted excerpts occur exactly in the cited unit.
3. A scalar value matches the full source cell and the parsed number matches its text.
4. Method evidence comes from the value's row and its label matches the reported method.
5. Metric evidence comes from its column and the header label is unambiguous; direction is checked against explicit arrows.
6. A dataset name occurs in its evidence. Where named dataset headers exist, its column association is checked too.

If Docling omitted a row-header flag, the first-column label can serve as a candidate with a review warning. Whole-table metric evidence is allowed for damaged headers but always needs layout review. Multi-number cells remain unsplit and cannot pass as clean scalar evidence.

`evidence_checks_passed` means only that these attribution checks found no issue. It does not verify normalized names, metric units/scales, interpretation of protocol text, experimental comparability, or scientific truth. Human review status stays separate from machine outcomes.

Schema validation rejects unknown fields, duplicate record IDs, inconsistent document identities, nonfinite numeric values, and human-review status lacking a reviewer identity.

## Tests

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

Tests cover wrong-row assignments despite identical numeric values, identical headers in different columns, wrong dataset ownership, invented quotes, missing references, reconversion identity, merged numbers, coordinate origins, multi-page uncertainty, schema failures, and input preservation.

## Next implementation

Select four additional papers using `data/corpus.json`'s criteria, extend the reference annotations with independent review, and add a schema-constrained result extractor. Use this evidence index as its input and run the same checks on its output. Add experimental compatibility rules and a review interface after measuring extraction failures. Model choice remains open; this foundation requires no API key or model download.
