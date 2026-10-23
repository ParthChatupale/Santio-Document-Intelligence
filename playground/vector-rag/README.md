# Vector RAG sandbox — review checkpoints

This folder calls the installed libraries directly. It does not change the main application.

1. `converter.py`: PDF → saved Docling document and readable Markdown.
2. `chunker.py`: saved document → HybridChunker text and source metadata.
3. `vector_index.py`: contextualized chunks → local R2 embeddings → PostgreSQL storage/search.
4. `rag.py`: question → vector retrieval → prepared evidence → NVIDIA answer with quotations and source metadata. **Current checkpoint.**

## PostgreSQL and pgvector setup

The sandbox uses the existing Python environment at `C:\Santio\.venv`. There is no new Python virtual environment. The database server runs separately in the existing Ubuntu WSL distribution.

Configured on this machine:

| Setting | Value |
| --- | --- |
| PostgreSQL | 18.6, WSL Ubuntu, existing `18/main` cluster |
| Host and port from Windows | `127.0.0.1:5432` |
| Database | `santio_vector_sandbox` |
| Application login | `santio_vector_app` |
| Default application schema | `rag` |
| pgvector server extension | 0.8.1, Ubuntu package `postgresql-18-pgvector` |

The application login has no superuser, role-creation or database-creation privileges. Its password is stored in this folder's ignored `.env` file; use `.env.example` to see the field names without credentials. This `.env` is a configuration file, not another Python environment. The root application's `.env` is separate.

The server extension lives inside WSL. The `psycopg` driver and `pgvector` Python adapter live in the existing Windows `.venv`; they let Python talk to the server. Their tested versions are in `requirements-db.txt`.

From `C:\Santio`, check the connection:

```powershell
.\.venv\Scripts\python.exe .\playground\vector-rag\database_check.py
```

The check uses a temporary table and three **synthetic** 384-dimensional vectors. It verifies vector insertion, metadata round-trip and cosine-distance ranking. The table is dropped on commit. It does not download an embedding model, index paper chunks, or evaluate semantic retrieval accuracy. The saved setup check is `diagnostics/database-check.json`.

If the WSL PostgreSQL cluster is stopped, start the existing cluster before running the check:

```powershell
wsl.exe -d Ubuntu -u root -- pg_ctlcluster 18 main start
```

Database creation and login provisioning have already been completed. `database_setup.sql` shows the extension/schema configuration applied by the PostgreSQL administrator in this dedicated database. Original PostgreSQL project databases were not changed, and no general network-listening or authentication rules were broadened.

The selected local embedding model, `ibm-granite/granite-embedding-small-english-r2`, is downloaded and GPU-tested. The chunker's tokenizer matches it. `vector_index.py` has now embedded and stored the paper's 292 chunks; see the indexing checkpoint below. `database_check.py` remains a synthetic connectivity check and does not itself index papers.

References: [pgvector installation and SQL usage](https://github.com/pgvector/pgvector), [Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html), [Windows-to-WSL networking](https://learn.microsoft.com/windows/wsl/networking).

## Vector indexing checkpoint

From `C:\Santio` in Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe .\playground\vector-rag\vector_index.py index ".\playground\vector-rag\outputs\chunker-r2-reviewed\document-formulas\chunks.jsonl"
```

This reads `chunks.jsonl` and its neighbouring `chunking_report.json`, loads the pinned local R2 model, embeds `contextualized_text` in batches of eight, and saves all vectors/text/metadata. It uses CUDA automatically when available (`--device cpu` is available). It never silently truncates input text. It does not run the converter, vision model or answer model. The path is an example input, not a paper hardcoded in the implementation.

`vector_schema.sql` defines two application tables: `rag.vector_indexes` records each dataset/model configuration, and `rag.chunks` stores its chunk text, evidence metadata and `vector(384)` values. An index ID fingerprints the exact chunk file, model revision, pooling and normalization. The primary key includes both index ID and chunk ID so different chunk configurations/models cannot overwrite each other. Identical reruns reuse existing rows; currently they recompute embeddings and verify the saved rows rather than acting as a generation cache.

All rows are inserted and read back inside a transaction. Text, metadata and vector values must match before commit. An invalid partial insertion is rolled back. No tables or vectors in other project databases are modified. With this small dataset, searches use exact cosine distance without an approximate vector index.

### Every function in vector_index.py

| Function | Responsibility |
| --- | --- |
| `load_chunks(path)` | Reads chunks and their report, rejects invalid/old-tokenizer inputs, and creates a reproducible index ID and manifest. |
| `connect_database(env_file)` | Loads sandbox connection settings, connects with Psycopg and registers pgvector's Python adapter. Passwords are not printed. |
| `load_model(device)` | Loads the pinned cached R2 tokenizer and model. Selects GPU/CPU and puts the model in inference mode. |
| `embed_texts(texts, tokenizer, model, batch_size)` | Tokenizes without truncation, checks limits, runs the model in batches, takes the CLS-token representation, normalizes it, and returns a vector matrix plus actual token counts. |
| `store_embeddings(connection, index_id, chunks, vectors, manifest)` | Creates sandbox tables if needed, inserts the manifest and chunk records, checks every saved row, and commits only a complete matching dataset. |
| `search(connection, index_id, query_vector, top_k)` | Checks model compatibility, performs exact PostgreSQL cosine-distance search, and returns passage text with source metadata and distances/similarities. |
| `build_index(chunks_file, env_file, device, batch_size)` | Coordinates the preceding functions, compares actual token counts with the chunker, checks a stored vector's nearest neighbour, reports timing/memory, and releases model resources. |
| `main()` | Reads the `index`/`search` terminal commands, calls the appropriate functions and saves/prints results. |

The CLS token is the first token's learned representation; the model's published pooling configuration uses it as the text embedding. L2 normalization scales each vector to length one. Similarity scores measure proximity in embedding space and are not probabilities that a passage or answer is correct.

### Query the stored paper

The reviewed index ID is `r2-3c63988f65eaf71161dafedc`:

```powershell
.\.venv\Scripts\python.exe .\playground\vector-rag\vector_index.py search --index-id r2-3c63988f65eaf71161dafedc --query "How do retrieval augmented language models use external documents?" --top-k 5
```

The command embeds the question with the same model, then returns passages. It does not generate an answer. Keep the index ID printed by the indexing command for other documents/configurations.

Inside `psql`, inspect the saved data:

```sql
SELECT index_id, model_name, chunk_count FROM rag.vector_indexes;

SELECT count(*), min(vector_dims(embedding)), max(vector_dims(embedding))
FROM rag.chunks
WHERE index_id = 'r2-3c63988f65eaf71161dafedc';

SELECT chunk_id, metadata->'pages' AS pages,
       left(contextualized_text, 120) AS passage
FROM rag.chunks
WHERE index_id = 'r2-3c63988f65eaf71161dafedc'
ORDER BY ordinal LIMIT 3;
```

### Verification

`outputs/vector-index-reviewed/index_report.json` records 292 newly stored vectors, all read back with their text/metadata verified. The RTX 3050 run used batch size eight, spent 4.818 seconds in the embedding loop, and peaked at 326.69 MiB GPU allocation. Its reported 39.521 seconds covers the timed build operation, not all Python process startup/import overhead.

`diagnostics/check_vector_index.py` verifies duplicate prevention, transaction rollback on incomplete data, and PostgreSQL distances against NumPy calculations. It also tests three source-linked questions prepared from the actual paper before querying. All three target passages appeared in the top five (ranks 4, 1, 1). This small, AI-prepared smoke set is not an independently annotated benchmark or a general accuracy claim. Details and passages are in `diagnostics/vector-index-review/checks.json`; CLI search output is `cli-search.json`.

The extraction's empty table and possible errors in generated descriptions/formulas remain source-quality limitations. This step stores those selected inputs faithfully; it does not validate their truth. Retrieval evaluation and the new `rag.py` answering checkpoint are described below.

## Ask a question with rag.py

From `C:\Santio`, using the existing environment and saved index:

```powershell
.\.venv\Scripts\python.exe .\playground\vector-rag\rag.py --index-id r2-3c63988f65eaf71161dafedc --question "How can fine-tuning avoid forgetting previously learned knowledge?"
```

Replace the question with your own. The example index ID identifies the previously indexed survey; the implementation accepts any compatible index ID and has no paper-specific questions or answers built in. No reindexing is needed. The database must be running. `--top-k 5` is the default; use `--top-k 10` to supply up to ten retrieved chunks. This is the same vector ranking evaluated earlier, without a reranker, keyword/graph additions, or query decomposition. More chunks do not guarantee enough evidence for every question.

The local R2 model embeds only the question on GPU (or `--device cpu`). Answer generation uses the configured NVIDIA-hosted model. The default model is `nvidia/nemotron-3-super-120b-a12b`. Nemotron-3 requests use low reasoning effort with a 1024-token reasoning budget and a default 4096-token output allowance; reasoning text is not included in the saved answer trace. The default endpoint is NVIDIA's [documented chat-completions endpoint](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-super-120b-a12b-infer). The existing `C:\Santio\.env` supplies `NVIDIA_API_KEY`; model selection uses `NVIDIA_MODEL`, then `PBL_MODEL_NAME`, then the default. Process environment variables override the selected file. `--model` overrides only the answer model. `--llm-env-file` selects another answer configuration file; database configuration independently uses `--db-env-file` (sandbox `.env` by default). Credentials are never written into reports.

The SDK and other required packages already exist in this environment. `requirements-rag.txt` records the additional answer-stage dependencies for reproducing the setup.

Each run prints the answer and writes a new `outputs/rag-<timestamp>/` directory:

- `answer.md`: readable claims, supporting quotations, page numbers, chunk IDs and Docling references.
- `answer.json`: retrieved/prepared passages, exclusions and transformations, original request messages, model response attempts, finish reasons, token usage, timing and validation results. A failed response remains an error rather than being presented as an answer.

The three model answer states are `answered`, `partial`, and `insufficient_evidence`. For a comparison, partial means some requested support is missing from the retrieved passages. Insufficient evidence does not prove that the entire paper lacks an answer. Provider/network failures, truncated responses and repeated invalid structured output produce the separate `error` state and CLI exit code 2.

**Evidence preparation and citation checks**

Before calling the answer model, `prepare_evidence` verifies the indexed source JSON's hash. That saved snapshot must remain accessible at the manifest path. It removes exact AI picture-description spans while retaining surrounding author prose/captions. It substitutes saved original formula text for differing enriched formula spans. Every substitution is recorded with both versions; original formula text is not guaranteed correct either. A chunk is excluded if such a span cannot be safely isolated. There is no automatic backfill beyond the requested top-k. The existing vectors, database text and source JSON remain unchanged: ranking still uses the indexed text, while the answer model sees the prepared text.

The model supplies statements and quotations identified by local source IDs such as `S1`. The code checks the JSON structure, status consistency, known source IDs, and that every quote occurs continuously in its supplied passage (allowing whitespace changes). It attaches pages and document references from stored metadata, not model-generated page numbers. Pages and references are chunk-level provenance, not an exact mapping of each quoted character to a PDF region. One repair request is allowed for invalid structure/citations; SDK network retries are disabled. There is no silent truncation or acceptance of output that ended at a token limit.

Matching quotations does not prove they support the attached claim. The answering model is instructed to check support, but semantic entailment and factual accuracy remain unverified. Similarity is not confidence, source extraction gaps remain, and this is not yet the production frontend or a graph comparison.

**Every function in rag.py**

| Function | Purpose |
| --- | --- |
| `load_answer_settings` | Reads the configured answer-model connection without hardcoding a key. |
| `prepare_evidence` | Verifies the source snapshot, removes unverified descriptions, handles formula differences, and preserves provenance/audit details. |
| `build_messages` | Packages the question and prepared passages with evidence-only answering instructions and the required response format. |
| `validate_answer` | Checks response structure, status consistency, source IDs and quotations; resolves citation details from our own metadata. |
| `call_answer_model` | Calls the endpoint, records public response metadata, rejects unfinished responses, and allows one validation repair. |
| `answer_question` | Coordinates local embedding, database retrieval, evidence preparation and hosted answering. Returns the complete trace. |
| `render_answer` | Makes accepted answers, quotes and citation details readable. |
| `main` | Reads terminal arguments, saves the report and prints the answer. |

`EvidenceQuote`, `Claim` and `ModelAnswer` are Pydantic data contracts for a quotation, supported statement, and complete response. They validate structure; they do not perform retrieval or generate facts.

Offline contract checks (no NVIDIA calls):

```powershell
.\.venv\Scripts\python.exe .\playground\vector-rag\diagnostics\check_rag.py
```

Add `--live --output <new-directory>` to run four real paper questions through retrieval and the configured endpoint. Live reports contain actual generated text and citations for review; passing these smoke checks is not a general answer-accuracy claim.

## Converter picture-model update

`converter.py` runs Docling extraction first (including formula enrichment by default), releases its cached models, then calls `granite_picture_descriptions.py`. The helper first resolves each picture's `captions` references into actual text. A nonempty caption is reused; only pictures without usable linked captions are sent to Granite. Empty, whitespace-only and broken caption references count as missing; broken references are recorded in the report.

When every picture has a usable caption, the helper returns without importing the model runtime or loading Granite. When needed, it uses locally cached Granite Vision 3.3 2B, CUDA, NF4 4-bit language layers, and unquantized bfloat16 vision/projector/output layers. It does not use SmolVLM or a hosted API.

Small picture-only check, from `C:\Santio`:

```powershell
.\.venv\Scripts\python.exe .\playground\vector-rag\converter.py ".\2307.06435v10.pdf" --page-range 1 1 --no-formulas
```

Full conversion (formula enrichment enabled):

```powershell
.\.venv\Scripts\python.exe .\playground\vector-rag\converter.py ".\2307.06435v10.pdf"
```

Each run creates a new directory. By default, every captionless picture is eligible for Granite regardless of size. An optional `--min-picture-area .05` skips captionless pictures occupying less than 5% of a page; this filter never prevents reuse of an existing caption. Skips are listed explicitly. Saved crops use `images_scale=2.0`.

`picture_descriptions_report.json` records each picture's source reference, outcome and text source. Captioned entries have `status: caption_reused`, `text_source: extracted_caption` and their caption references. Author captions stay in their native text items linked by `pictures[].captions`; they are not copied into the AI-description field. Generated fallback entries have `text_source: ai_description`, model attribution, timing and peak GPU allocation. These fallbacks are saved in `pictures[].meta.description` and included by Docling's Markdown export.

The report gives separate `captions_reused`, `generated`, `failed`, `skipped` and `needs_review` counts, plus `model_loaded`. `status: captions_only` means all pictures used extracted captions and no Granite load was needed. Token/time-limited answers are flagged `needs_review`; failures and these limits make the overall conversion `partial_success`, while preserving extraction output. The report retains `extraction_status` separately. A successful generation status does not certify factual accuracy. The existing baseline chunker continues to exclude generated picture metadata while keeping author captions.

The model ID, pinned revision, prompt and generation limits are visible at the top of `granite_picture_descriptions.py`. This helper is a converter support file, not another retrieval stage. The old diagnostic probe remains separate as a historical test.

### Integration checks

The previous all-picture mode passed a small-chart integration test, but the subsequent 47-page run showed hallucinations, truncations and a GPU memory failure on a larger figure. Those historical outputs remain unchanged. Caption-first fallback reduces the number of AI calls; it does not guarantee that an uncaptained figure will fit GPU memory or receive an accurate description.

The saved 47-page document has 14 pictures: 13 have nonempty linked captions and one has no caption link (`#/pictures/3`, page 5). Routing checks use these real objects plus missing, whitespace-only and broken-reference cases. Checks and results are in `diagnostics/check_caption_fallback.py` and `diagnostics/caption-fallback-verified/`. This is a routing/integration check, not a new document-understanding accuracy benchmark.

These checks passed: the 13 captions were reused and only the actual captionless picture received a generated description on CUDA. Missing, blank and broken references correctly selected the fallback. A fresh page-1 PDF conversion (`outputs/caption-first-converter-page1-review`) also passed: it reused the caption, recorded `model_loaded: false`, and generated no AI description. The 47-page routing check reused saved extraction; the entire PDF was not reconverted for this test.

## Run the chunker

From `C:\Santio`, in PowerShell:

```powershell
.\.venv\Scripts\python.exe .\playground\vector-rag\chunker.py ".\playground\vector-rag\outputs\2307.06435v10-20261016T184342431534Z\document.json"
```

The positional argument can be any saved Docling document JSON. A fresh timestamped output folder is created by default. `--output-dir` accepts a new folder only. The tokenizer revision is pinned to the tested commit by default; `--revision` can override it.

The default is the author-text baseline: author captions are included, AI figure descriptions are excluded, and original PDF formula text is preferred. Add `--include-ai-descriptions` to include completed captionless fallback descriptions with explicit attribution. Truncated/time-limited AI descriptions are excluded even with this flag. Add `--formula-text document` to use Docling's exported formula representation (including enriched LaTeX when present). Neither formula mode certifies mathematical accuracy. Empty exported formula text falls back to a nonempty original in either mode.

Example using the one AI fallback and Docling's exported formula text:

```powershell
.\.venv\Scripts\python.exe .\playground\vector-rag\chunker.py ".\playground\vector-rag\outputs\2307.06435v10-20261016T184342431534Z\document.json" --include-ai-descriptions --formula-text document
```

## Inspect the result

- `chunks.md`: readable contextualized text, page numbers, references, token counts.
- `chunks.jsonl`: the same chunks as records for the next pipeline stage; includes raw text, heading context, source bounding boxes, text-source attribution and picture links.
- `chunking_report.json`: settings, tokenizer revision, coverage, token-limit checks and review notes.
- `excluded_enrichments.json`: source picture metadata/annotations and both formula variants for review. The per-picture flag records whether its description was included in chunks.

HybridChunker is supplied by Docling. It starts from document structure, splits oversized content, and merges compatible neighbouring pieces. Table content uses Docling's table serializer; it may appear as row/column/value statements rather than the original table layout. `contextualized_text` adds heading context and is the proposed input to the embedding model.

The tokenizer is now from `ibm-granite/granite-embedding-small-english-r2`, pinned to revision `2ab6fa8ea2d674564defd37171ae19079b864b33`. Its model window is 8192 tokens. Only tokenizer files are loaded by the chunker, not embedding model weights. The default chunking target remains 480 tokens for focused retrieval; the final encoding is checked independently, including special tokens, against the model's 8192-token limit. Native chunking may exceed its target slightly, so the final check matters. Oversized output is flagged and the command exits with code 2; content is never silently truncated. The reviewed default outputs all fit within 512 tokens as an additional diagnostic check.

Author captions are kept. Each caption chunk now carries `picture_links` to its associated image; the report also lists every picture, including those excluded from searchable text. Generated picture metadata and legacy annotations are removed from the in-memory document by default and saved separately. In AI mode only the completed captionless fallback description is retained; `text_sources` and `ai_created_by` distinguish it from author text. Picture bytes are not embedded into chunk text. Source boxes describe original document items, not newly computed bounds for each split text fragment.

For formula items, the chosen policy controls original versus exported text; both versions are recorded for review when different. Original extraction and generated LaTeX can both contain errors. Source JSON is never rewritten, and no new vision/formula inference is performed by chunking.

Coverage measures representation, not factual accuracy or complete extraction. Pages represented does not mean every item on each page was extracted. Empty source tables cannot be repaired by chunking. Review reported gaps before embedding.

## Earlier 30M-tokenizer example

The 47-page survey produced 291 chunks, each carrying heading context. The largest final encoding was 493 tokens including the two special tokens. All 47 pages and all 26 caption references were represented. Fourteen of 15 table references were represented; `#/tables/0` already has zero rows, zero columns and no cells in the source JSON, so its contents remain an extraction gap.

Both the original export and the enriched export were processed. After excluding 11 pictures' generated metadata and restoring six original formula texts, their contextualized chunk text and source references matched exactly. This checks baseline isolation, not the accuracy of the original formulas. Tokenizer revision: `9b5b096411652ec1189c68fcfb90d0a82c5b45af`.

The tokenizer may warn about a long intermediate sequence while HybridChunker is measuring content before splitting it. The report checks final chunks separately; the example's final chunks all fit within 512 tokens.

The earlier artifacts remain under `outputs/chunker-enriched-review/` and `outputs/chunker-reviewed/`. They were prepared with the old tokenizer and should not be confused with the regenerated R2 input below.

### Latest caption-first chunking check

`diagnostics/check_chunker_output.py` runs the latest caption-first extraction through baseline, AI-enabled and document-formula modes. Reviewed artifacts are under `outputs/chunker-reviewed/`; `checks.json` records integration checks and per-mode counts. It checks final token sizes, all pages/captions, caption-to-picture links, AI attribution, selected formula text, and that the source JSON remains unchanged. This is a chunk preparation check, not a retrieval accuracy evaluation.

### R2 model and matching chunks

The R2 download contains the 95.3 MB safetensors weights plus tokenizer/configuration files. `diagnostics/embedding_probe.py` loads only cached files using the existing Transformers and CUDA-enabled PyTorch installations; Sentence Transformers is not required for this diagnostic. It follows the model's documented CLS-token pooling and applies L2 normalization for cosine similarity. The pinned model configuration confirms CLS pooling and 384 output dimensions.

The GPU probe passed on the RTX 3050: four short texts produced a `(4, 384)` matrix, finite normalized values, matching single/batched embeddings, and the expected passage ranking for two synthetic questions. Loading took 3.32 seconds and computation (including the single-input comparison) took 1.03 seconds. Peak GPU allocation was 196.23 MiB for this small test, not a full-paper memory estimate. See `diagnostics/r2-embedding-check/report.json` and `sample_embeddings.json`. No database rows were written; this is not a paper retrieval accuracy evaluation.

Matching R2 chunks are under `outputs/chunker-r2-reviewed/`. All three reviewed modes produced 292 chunks, with 493 tokens at most. All 47 pages and all 26 caption references were represented, picture links and AI attribution passed, and source JSON stayed unchanged. `document-formulas/` contains the previously selected configuration with the one AI fallback plus Docling's exported formula text. The empty `#/tables/0` extraction gap remains visible in each report.

The tokenizer may warn about an oversized intermediate sequence before splitting. Every final reviewed R2 chunk is checked separately and fits its model window. Model/tokenizer version and chunk configuration must accompany future database indexes; vectors from different embedding models must not be mixed just because their dimensions match.

Reference for pooling and normalization: [IBM R2 model usage](https://huggingface.co/ibm-granite/granite-embedding-small-english-r2).

## GPU and model roles

CUDA-enabled PyTorch is installed, and the RTX 3050 passed a CUDA calculation. HybridChunker/tokenization is primarily CPU work. The implemented vector index uses CUDA automatically when available and also accepts an explicit device selection. NVIDIA-hosted answer models run on NVIDIA's servers, not this laptop.

Granite Vision 3.3 2B was first tested separately in `diagnostics/granite_vision_probe.py`: 4-bit language layers and unquantized bfloat16 vision layers fit the 6 GB GPU in the single-chart test. That loading configuration is now integrated through the converter helper. Switching the vision model does not change the embedding tokenizer. Allocating approximately 3.5 GB in that test does not imply a 3.5 GB card or that more memory use would improve accuracy. Accuracy still needs source checks; the earlier chart probe contained a wrong comparison.

**Source-linked retrieval evaluation**

The read-only evaluation in [diagnostics/retrieval-evaluation-v1/REVIEW.md](diagnostics/retrieval-evaluation-v1/REVIEW.md) tests 13 answerable questions, three unsupported questions, and two source-quality probes against the 292-chunk index. All selected evidence was in the first five results for 10/13 questions and the first ten for 11/13. These are strict hits on AI-prepared reference passages, not answer accuracy; a useful alternative scaling-law passage is excluded by one reference rule. The review preserves this grading limitation, the genuine multi-passage miss, weak Vicuna row ranking, and incorrect enriched source text. No answer generation or automatic refusal has been tested. The original questions, retrieved passages, and full-ranking diagnosis are saved alongside the review; the existing index remains unchanged.

## Shared implementation

The four playground commands now delegate to `src/pbl_docintel/vector_rag/`.
That package contains the reviewed pipeline; the main app uses it directly.
No app code imports these playground entry-point files. CLI arguments and the
existing sandbox configuration remain supported.
