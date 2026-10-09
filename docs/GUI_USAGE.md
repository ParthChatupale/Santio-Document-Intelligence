# Santio local research workspace

The React + TypeScript interface is implemented over the Python evidence SDK.
It includes the supplied Waves WebGL1 shader, real PDF cover previews, a searchable
library, PDF upload and Docling processing, original-page inspection, detected
regions, provisional annotations, attribution findings, and evidence/RAG exports.
The paper workspace also includes Overview, Relationships, Read, and Ask.
See [model setup and paper understanding](PAPER_UNDERSTANDING.md) for NVIDIA,
local Ollama, and reusable Python APIs. Generated views require a connected model;
the extracted reading and evidence views work without one.

## Run from PowerShell

The project is at `C:\Santio`. Node 22.12+ and the existing Python environment
are required. On this machine both are already available.

```powershell
cd C:\Santio
.\.venv\Scripts\python.exe -m pip install -e ".[gui,docling]"
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. `npm run dev` starts the Python API on port 8766
and Vite on port 5173; Ctrl+C stops both. No environment activation is needed.
If dependencies are already installed, just run `npm run dev`.

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

1. Click **Add paper**; choose or drop a PDF up to 100 MB. The file card shows
   its filename, size and **Selected · not uploaded yet**. You can remove it.
2. Edit the title if desired. Enable OCR for scanned pages.
3. Click **Upload PDF**. The UI shows uploading until the server confirms receipt.
4. The form is replaced by **PDF uploaded**, preserving the filename and size,
   with separate **Uploaded / Extracting / Ready in library** steps for this job.
5. When extraction finishes, choose **Open paper**. It is registered automatically
   and survives a restart. AI paper analysis starts separately in Overview.

**Imports** in the top bar opens a separate view of other uploaded files and their
jobs. The new-file form never mixes those jobs into its upload state. Upload or
validation errors retain the selected file for retry and do not show a success
receipt. A failed extraction still acknowledges the completed upload and reports
the extraction error.

Conversion jobs run one at a time in a separate Python process. You may close
the dialog while conversion continues. Pending/running jobs can be cancelled.
A failed import preserves its error; upload again to retry. A service restart
marks interrupted jobs as failed rather than falsely reporting success. A partial
Docling conversion is marked as partial. First use may download model weights;
conversion runs locally and does not require an LLM API key.

Uploads are stored under `data/uploads/<id>/`, with original PDF, Docling JSON,
Markdown, referenced figures, evidence index, RAG JSONL, receipt and conversion log.
Library registrations are saved in `data/gui-library.json`; job states are in
`data/import-jobs/`. Existing `data/corpus.json` entries are read without being
rewritten. An empty workspace can accept uploads without a hand-written manifest.
User filenames are display metadata; storage paths use generated identifiers.

## Understand and read a paper

Open a paper to see **Overview** and its selected filename/page count. The app uses
the owner's server-configured NVIDIA Nemotron 3 Super connection by default.
The owner sets `NVIDIA_API_KEY` in the workspace's ignored `.env` file or backend
environment before startup. **AI settings · optional** permits a custom connection;
ordinary users do not need their own keys. Its connection test sends no
paper content. **Analyze this paper** then reads the extracted text in segments
and saves cited statements and semantic relationships. Generation sends the
excerpts to the configured provider; local Ollama is available as an alternative.

**Relationships** shows searchable subject–relation–object cards with supporting
quotes. **Ask** retrieves evidence from this paper and lets the model request
additional searches, up to three rounds. Partial answers and missing evidence
remain visible. Click a citation to open the source region in **Evidence**.
Source checks establish quote accuracy and location, not the correctness of
the model's interpretation.

**Read** displays the actual extracted prose with search, source-page links and
a download of the saved Docling Markdown. It does not require a model.

## Explore evidence

Select the **Evidence** workspace tab, then **Results, Tables, Figures, Equations, or
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

## Issues, results, and exports

Issues shows unresolved/failed attribution findings. Raw merged values remain
intact. Passing machine checks do not establish human review or scientific
correctness. Review decisions and corrections are currently read-only.

Results is a provisional source-linked result table. Experiment compatibility,
cross-paper ranking and automatic leaderboards are not implemented.

Export offers available evidence JSON, unchanged Docling JSON, RAG JSONL, and
result JSON/CSV/Markdown and attribution checks when annotations exist. The saved
Docling Markdown and extracted prose can also be downloaded. Generated understanding
has a separate JSON export in Overview. JSON
preserves exact text; CSV protects spreadsheet formula fields. Original source
fingerprints and evidence IDs remain in the SDK exports. RAG chunks can be used
by Python/retrieval systems; Ask now generates cited answers using lexical retrieval
and a connected model. Cross-paper question answering is not implemented.

## Implementation and validation

React/Vite source is in `frontend/`; `npm run build` writes the owned
`src/pbl_docintel/gui/static/react/` directory. PDF.js 6.4.299 and its resources are
vendored locally under `static/vendor/`, with license and source checksum.
The exact user-supplied fragment shader is in `frontend/src/shaders/waves.frag`.
It uses plain WebGL1, a fullscreen triangle, supplied packed uniforms, DPR capped
at 2, visibility-aware RAF, reduced-motion still rendering, context-loss handling,
and a static fallback. An absolutely positioned canvas fills a fixed viewport
backdrop, so long libraries do not stretch the wave field across the whole document.
Active wall time keeps the recipe speed even at low frame rates; hidden/paused
time is excluded. The navigation rail provides play/pause. System reduced-motion
preferences apply by default, while an explicit user play/pause choice overrides
them. See [hosting status](HOSTING.md) for Vercel deployment requirements.

```powershell
npm run check
npm test
npm run build
.\.venv\Scripts\python.exe -m pip install -e ".[gui,test]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The 81 Python tests cover the SDK, attribution, source identity, local HTTP
boundaries, persistent registrations/jobs, invalid/oversized uploads and foreign
origins, model request contracts, citation validation, question search rounds,
generation failures and report persistence. Five frontend tests cover animation timing, pause/resume, explicit
motion preferences and PDF coordinate projection including rotation/crop offsets.
Browser QA covers the actual library, result selection,
review ambiguity, original source/crops, exports, shader compilation, and narrow
layouts. A real one-page upload was converted and indexed in an isolated test
workspace without changing the main library. These checks do not establish
semantic extraction accuracy or hosted-product readiness. Model tests inject
explicit fixtures; a real NVIDIA generation requires an API key and has not
been evaluated for quality on this corpus.

`Architecture_Final.pptx` is unrelated and excluded from this implementation.
