# PBL Project

Document intelligence prototype using Docling for document conversion.

The staged roadmap for the intelligence layer is in [the project plan](docs/PROJECT_PLAN.md).
The proposed source viewer, review workflow, and comparison interface are in [the GUI plan](docs/GUI_PLAN.md).
The React workspace includes the Waves WebGL background, a document library,
PDF upload and Docling processing, source inspection, and evidence/RAG exports.
See [GUI setup and usage](docs/GUI_USAGE.md).
It now also includes model-assisted paper overviews, cited semantic relationships,
and retrieval-backed questions. NVIDIA is the default connection preset;
see [paper understanding and model setup](docs/PAPER_UNDERSTANDING.md).

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[gui,docling]"
npm ci
npm run dev
```

Open `http://127.0.0.1:5173` to upload PDFs and inspect original pages, source-linked results,
figures, equation regions, and extraction issues. The UI can export evidence
and RAG chunks; saved review decisions, automatic structured experiment extraction,
and compatibility-based rankings are pending. For a single Python service:
`npm run build`, then `.\.venv\Scripts\python.exe -m pbl_docintel.gui.cli --workspace C:\Santio`
serves the built app at `http://127.0.0.1:8765`.

The reusable Python library and optional LangChain bridge are described in
[Python/RAG integration](docs/PYTHON_RAG_INTEGRATION.md).

## Environment

The project uses Python 3.14 and a local `.venv`.

To recreate the environment from PowerShell in this folder:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

To activate it in a terminal:

```powershell
.\.venv\Scripts\Activate.ps1
```

You can also run `.\.venv\Scripts\python.exe` directly without activation.

Check the installation:

```powershell
.\.venv\Scripts\python.exe -c "from docling.document_converter import DocumentConverter; print('Docling is ready')"
```

The first PDF conversion may download model weights. Converted files should go in `outputs/`, which is ignored by Git.

## Convert a paper

```powershell
.\.venv\Scripts\python.exe src\ingestion.py 2610.10539v1.pdf
```

This saves a structured Docling JSON, readable Markdown, figure images, and an
extraction summary under `outputs/`. JSON retains document item references,
table structure, hierarchy, and page provenance for the intelligence layer.

The default run uses the PDF's selectable text, infers heading levels, and
extracts tables and figures. Add `--ocr` for scanned PDFs. Formula enrichment
is disabled in this first conversion; equations are not guaranteed to be LaTeX.

## Show the detected layout

`outputs/2610.10539v1.layout.pdf` displays the original pages with color-coded
boxes for figures, formula regions, tables, headings, text, captions, and other
detected elements. Each page includes a legend and detection counts. Its
companion `.layout.json` maps the printed tags to Docling item references.

To recreate this visual export without running document conversion again:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-visualization.txt
.\.venv\Scripts\python.exe src\visualize_layout.py 2610.10539v1.pdf outputs\2610.10539v1.json
```

Picture detection identifies image regions; it does not classify every image
as a diagram. Formula boxes show detection, not verified equation transcription.

## Build the intelligence-layer foundation

```powershell
.\.venv\Scripts\python.exe -X utf8 src\build_evidence.py outputs\2610.10539v1.json --source-pdf 2610.10539v1.pdf --results data\annotations\tetris3d.sample.json
```

This indexes source evidence and checks nine curated sample result records. It
saves JSON contracts, an evidence index, CSV/Markdown results, and check findings
under `outputs/intelligence/`. Sample results are manually annotated by Codex;
semantic extraction is not automated yet. Ambiguous merged cells remain flagged
for review. See [implementation details](docs/INTELLIGENCE_LAYER.md).

Run the attribution and schema tests:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```
