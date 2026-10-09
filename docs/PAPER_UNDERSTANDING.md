# Paper understanding and NVIDIA setup

The intelligence layer adds interpretation over Docling's evidence representation.
It works with the indexed document produced from each uploaded PDF; it contains
no prepared paper summaries or PDF-specific relationship rules.

## Use the application

From PowerShell:

```powershell
cd C:\Santio
npm run dev
```

Open http://127.0.0.1:5173. For the existing built application, run:

```powershell
.\.venv\Scripts\python.exe -m pbl_docintel.gui.cli --workspace C:\Santio --port 8765
```

Open http://127.0.0.1:8765. Use one backend per workspace for jobs. If a server
was already running before these changes, restart it to load the new Python routes.
Install dependencies with the commands in [GUI usage](GUI_USAGE.md) if needed.

1. Open an indexed paper, or upload a PDF and wait for conversion.
2. In Overview, choose **Connect NVIDIA API**.
3. Enter a key obtained from [NVIDIA Build](https://build.nvidia.com) and the
   exact model ID. The editable starter is `meta/llama-3.3-70b-instruct`.
4. Choose **Save & test connection**. This sends a small JSON instruction, no
   document content. A successful test checks connectivity and JSON output only.
5. Choose **Analyze this paper**. Watch the actual evidence-reading and synthesis
   stages. When complete, Overview and Relationships display the saved outputs.
6. Use Ask for questions about this paper. Every retained answer statement links
   to an original evidence region. Use Read for searchable Docling prose, and
   Evidence for tables, figure crops, equation regions and source inspection.

NVIDIA's preset sends requests to `https://integrate.api.nvidia.com/v1`.
The model and API contract are documented in the [official inference reference](https://docs.api.nvidia.com/nim/reference/meta-llama-3_3-70b-instruct-infer).
Free access, model availability and rate limits depend on the account and endpoint;
the application makes no promise of unlimited free processing. Analysis can make
many requests for a long paper, rather than compressing it into a single top-k
retrieval result. Rate-limit errors stop the job and leave any prior saved report.

## Credentials and alternatives

UI keys live only in backend memory for the running session. The backend does not
return them, write them to its report files, or store them in browser storage.
After restarting, reconnect or configure environment variables before launch.
Do not put a key in frontend Vite variables or a tracked source file.

For NVIDIA, this PowerShell setup avoids putting a literal key in command history:

```powershell
$env:PBL_MODEL_PROVIDER = 'nvidia'
$env:PBL_MODEL_NAME = 'meta/llama-3.3-70b-instruct'
$env:NVIDIA_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'NVIDIA API key' -AsSecureString)).Password
npm run dev
```

The key is still an ordinary environment variable available to this process and
its children. The app does not automatically load `.env` files. Supported variables:
`PBL_MODEL_PROVIDER`, `PBL_MODEL_URL`, `PBL_MODEL_NAME`, `PBL_MODEL_API_KEY`, and
the fallback `NVIDIA_API_KEY`. The NVIDIA preset fixes its URL to the NVIDIA host.

**Local Ollama** uses its local `/api/chat` endpoint with JSON schema output.
Enter an installed model's exact name and, by default, `http://127.0.0.1:11434`.
**Compatible API** uses `/chat/completions`, bearer authentication when supplied,
and `response_format: {"type":"json_object"}`. Remote endpoints require HTTPS.
The selected provider receives extracted excerpts and questions when generation
starts. The uploaded PDF and Docling conversion remain local.

## What is implemented

| Output | Workflow |
|---|---|
| Overview | Reads all nonempty extracted evidence in bounded batches, then synthesizes supported candidates into problem, contribution, method, finding and limitation statements |
| Semantic relationships | Generates subject, predicate, object, explanation, reported/inferred basis, and source quotes |
| Answers | BM25 retrieval over text and table context; the model can request additional searches, with a maximum of three rounds |
| Source links | Checks evidence ID, location, exact quote in source, and occurrence in the context actually supplied to the model |
| Persistence | Analysis and question jobs/results under `data/understanding/`; reports bound to conversion identity and source fingerprint |
| Interoperability | JSON exports, reusable Python functions, and a model protocol without a vendor SDK dependency |

Invalid or unsupported citations are omitted and recorded in an audit. Invalid
JSON or schema failures stop generation; the UI shows the error. An unsuccessful
regeneration preserves the previous report. Interrupted jobs are marked failed
after restart. No fabricated summaries fill missing output.

Quote checks do **not** establish that a paraphrase follows logically from the
quote or that an inferred relationship is scientifically correct. The model's
reported/inferred labels are also interpretations, not independent verification.
Coverage describes supplied text, not proof that the model understood every page.

## Python integration

```python
from pbl_docintel import HTTPJSONModel, analyze, answer
from pbl_docintel.schema import EvidenceIndex
from pathlib import Path

index = EvidenceIndex.model_validate_json(
    Path('outputs/intelligence/evidence.index.json').read_text(encoding='utf-8')
)
model = HTTPJSONModel.from_env()
report = analyze(index, model, progress=print)
response = answer(index, model, 'What problem does the proposed method address?')
```

For another host system, implement `name` and
`generate(system: str, payload: dict, schema: dict) -> dict`, then pass that model
to `analyze` or `answer`. Return parsed JSON matching the supplied schema.
Original evidence IDs and quotes remain in the output for the host's source viewer.

Local HTTP routes:

| Method | Route | Purpose |
|---|---|---|
| GET / POST | `/api/model` | Read public connection metadata / configure the runtime connection |
| POST | `/api/model/test` | Test JSON output without sending document content |
| GET | `/api/papers/{paper_id}/understanding` | Saved report, current model metadata and recent jobs |
| POST | `/api/papers/{paper_id}/understanding` | Queue analysis; returns a job with HTTP 202 |
| POST | `/api/papers/{paper_id}/questions` | Queue a question using `{"question":"..."}` |
| GET | `/api/papers/{paper_id}/understanding/export` | Download the saved report JSON |

URL-encode paper IDs. Poll the GET understanding route while a job is queued or
processing. This service uses the existing local-origin boundaries and is not
a public authenticated multi-user API.

## Remaining work and validation

The NVIDIA request contract, job lifecycle, citation checks, exports and bounded
search loop have automated tests with explicit model fixtures. Browser checks
cover the real setup, reading and source navigation, plus generated overview,
relationship and answer rendering with an explicitly labeled fixture provider
in an isolated workspace. No API key was available
during implementation, so real NVIDIA inference and corpus-level answer quality
are **not yet evaluated**. Connecting a key and inspecting outputs on unfamiliar
papers is the next validation step.

This version does not interpret diagram pixels, transcribe empty formula regions,
repair merged numeric cells, populate structured experimental ResultRecords,
rank comparable experiments, save review corrections, search across papers, or
perform independent claim-entailment verification. Relationships are searchable
cards and JSON records, not a graph database or interactive graph canvas.
