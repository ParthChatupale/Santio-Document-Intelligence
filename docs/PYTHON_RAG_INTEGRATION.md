# Python/RAG integration, version 0.2

The project is an installable Python component, `pbl_docintel`. Host applications can keep their document conversion, embeddings, vector store, retriever, and LLM. Our component supplies normalized evidence, source-aware retrieval chunks, and limited result-attribution checks.

## Install and use

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
# Optional LangChain bridge:
.\.venv\Scripts\python.exe -m pip install -e ".[langchain]"
```

The core depends on Pydantic and does not import Docling, LangChain, or a model runtime. The `docling` extra can install Docling for applications that also need conversion. This environment was tested with Docling 2.135.0 and LangChain Core 1.6.8.

```python
from pathlib import Path
from pbl_docintel import index_document, rag_chunks, resolve_evidence

index = index_document(Path("outputs/2610.10539v1.json"))
chunks = rag_chunks(index)
# Feed each page_content and metadata into your existing embedding/vector store.
# Retain original metadata when retrieving a chunk, then resolve its source:
source_units = resolve_evidence(index, chunks[0])
```

An existing in-memory `DoclingDocument`, its exported dictionary, or exported JSON bytes can be supplied instead. Paths and bytes preserve exact JSON-byte identity. Dictionaries and in-memory objects use canonical serialization, so their document identity may differ from a saved export. Use the same representation when binding annotations and retrieving evidence.

Native LangChain documents:

```python
from pbl_docintel import to_langchain_documents
documents = to_langchain_documents(chunks)
# The host application chooses its embedding model, vector store, and retriever.
```

Runnable example:

```powershell
.\.venv\Scripts\python.exe examples\rag_integration.py outputs\2610.10539v1.json --langchain
```

This exports chunks and constructs LangChain Documents; it does not create a vector store or generate answers.

## Add checks to a host extractor

```python
from pbl_docintel import ResultCollection, validate_results

# Host extraction output must follow the generated result.schema.json.
results = ResultCollection.model_validate_json(extractor_json)
checks = validate_results(results, index)
enriched_chunks = rag_chunks(index, results=results)
```

Check outcomes and review status remain separate. A machine attribution pass never becomes human approval. Raw source evidence remains available; the host decides how to filter or route needs-review and invalid results.

## Other parsers

`DocumentAdapter` has one method: `adapt(source) -> EvidenceIndex`. A host can implement it without changing our checks or chunk exporter:

```python
from pbl_docintel import EvidenceAdapter, index_document

class MyParserAdapter:
    def adapt(self, source):
        normalized = normalize_my_parser_output(source)
        return EvidenceAdapter().adapt(normalized)

index = index_document(upstream_output, adapter=MyParserAdapter())
```

`normalize_my_parser_output` is the host's mapping function, not a supplied implementation. It must follow `evidence.schema.json`, provide source identity, and preserve actual evidence precision. `producer` identifies the provider; Docling-specific identity fields can be omitted. No ready-made Azure, LlamaParse, or Unstructured adapter is claimed.

Indexes are validated for evidence IDs, context references, parent tables, cell coordinates, and page references. Missing row/column associations produce review warnings. New providers need normalization tests.

## Chunk contract and limitations

- Each chunk is a plain dictionary with `page_content` and `metadata`.
- Text chunks preserve exact character offsets into source text. Headers/footers and empty formula text are omitted from prose retrieval.
- Table-cell chunks retain available row labels, grouped headers, sections, captions, and footnotes. Multi-number cells stay unsplit.
- Tables without cells can retain their captions with an unavailable-structure warning. A survey diagram misclassified as a table triggered this behavior.
- Picture regions remain indexed; captions can be retrieved as text. The exporter adds no image understanding or equation transcription.
- `max_text_chars` limits prose. Full table-cell context can exceed it to avoid losing headers or splitting values; it is not a model-token budget.
- IDs, geometry, source flags, and result/review associations travel with chunks. Page ranges include cited context, not just the value cell.
- Nested metadata is serialized into fields ending in `_json`, keeping metadata scalar-valued for common vector stores. Decode these fields when inspecting evidence.
- Keep the matching evidence index alongside the vector store. Stripping document/evidence IDs prevents source resolution.
- `rag_chunks.jsonl` supports frameworks without LangChain. No server, database, API key, or hosted model is required by this release.

## Features added to host systems

| Capability | State |
|---|---|
| Reusable Python package; existing script still works | Implemented |
| Docling file, bytes, dictionary, or in-memory input | Implemented |
| External-parser adapter boundary | Implemented; specific provider mappings remain to build |
| Source-aware prose and table-cell chunks | Implemented |
| LangChain Document bridge | Implemented and tested |
| Wrong-row, wrong-column, value, quote, and identity checks | Implemented with documented limits |
| Missing structure and ambiguous-number flags | Implemented |
| Automatic semantic result extraction | Pending |
| Experimental-condition compatibility before ranking | Pending; next intelligence priority |
| Scope-aware conflicting-claim checks | Pending; depends on extraction and compatibility |
| Correction history and incremental document updates | Pending |

Chunking, citations, and graph provenance already exist elsewhere. Our proposed contribution combines experimental context, conservative verification, and measured reduction in review effort for a specific task. Integrations alone do not establish novelty.

## Lessons from the added papers

The [LLM survey](https://arxiv.org/abs/2307.06435v10) covers architectures, datasets, and benchmarks. It is background and a stress test for varied layouts and large tables; it is not a Tetris3D benchmark paper.

[Never Look Back](https://arxiv.org/abs/2610.10538v1) stores persistent object records and descriptions to answer questions without replaying video. The design lesson we can adapt is retaining structured, queryable records with context. Applying that to document evidence is our architectural inference. Ledger's Table 2 distinguishes video access and differing answerers/protocols, illustrating why comparisons must inspect conditions before ranking numbers.

## arXiv downloads

```powershell
.\.venv\Scripts\pbl-arxiv.exe https://arxiv.org/abs/2501.17887v1
```

The downloader accepts IDs or arXiv URLs, checks PDF content, records a checksum receipt, caches files, and spaces requests. Use explicit versions for reproducibility. Unversioned requests are cached snapshots, not automatically refreshed latest versions. It does not crawl references or circumvent blocks.

Live access was checked by downloading the [Docling report](https://arxiv.org/abs/2501.17887v1) into `data/pdfs/`. This is a parser reference, not a comparison experiment. PDFs stay local research inputs; the module does not serve them publicly. Follow the [arXiv terms](https://info.arxiv.org/help/api/tou.html) for use and redistribution. Request spacing is per process; multiple processes must coordinate externally.
