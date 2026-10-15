"""Local HTTP adapter over the evidence SDK and isolated PDF import jobs."""

from collections import Counter
from dataclasses import dataclass
import csv
import hashlib
import io
import json
import mimetypes
from pathlib import Path
import re
from threading import RLock
from contextlib import asynccontextmanager
import importlib.util
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .. import DoclingAdapter, EvidenceAdapter, index_document, rag_chunks, validate_results
from ..schema import EvidenceIndex, Location, ResultCollection

MAX_UPLOAD_BYTES = 100 * 1024 * 1024


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def display_rect(location: Location, pages: dict) -> dict | None:
    """Return an unrotated top-left rectangle in page fractions, not confidence."""
    box = location.bbox
    size = pages.get(str(location.page_no), {})
    width, height = size.get("width", 0), size.get("height", 0)
    if box is None or width <= 0 or height <= 0:
        return None
    left, right = sorted((box.l, box.r))
    top, bottom = sorted((box.t, box.b))
    if box.coord_origin == "BOTTOMLEFT":
        top, bottom = height - bottom, height - top
    # Keep broken or out-of-page locations inspectable, but do not invent a box.
    tolerance = 0.01
    if (left < -tolerance or top < -tolerance or right > width + tolerance
            or bottom > height + tolerance or right <= left or bottom <= top):
        return None
    return {"left": max(0, left) / width, "top": max(0, top) / height,
            "right": min(width, right) / width, "bottom": min(height, bottom) / height}


@dataclass
class LoadedPaper:
    paper: dict
    pdf: Path
    source_hash: str
    source_status: str
    index: EvidenceIndex | None
    results: ResultCollection | None
    checks: list[dict]
    docling: Path | None


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        manifest_path = self.root / "data/corpus.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"papers": []}
        library_path = self.path("data/gui-library.json")
        if library_path.exists():
            manifest["papers"] += json.loads(library_path.read_text(encoding="utf-8"))["papers"]
        self.papers = {}
        self.cache = {}
        self.lock = RLock()
        for paper in manifest["papers"]:
            key = paper["paper_id"]
            if key in self.papers or not isinstance(key, str) or not key:
                raise ValueError("Paper IDs must be unique, nonempty strings")
            for field in ("source_pdf", "docling_json", "evidence_index", "annotations"):
                if paper.get(field):
                    self.path(paper[field])
            self.papers[key] = paper

    def path(self, value: str) -> Path:
        path = (self.root / value).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Corpus paths must stay inside the workspace")
        return path

    def list_papers(self):
        with self.lock:
            return [{**p, "processed": bool(p.get("docling_json")),
                     "source_available": self.path(p["source_pdf"]).is_file()}
                    for p in self.papers.values()]

    def register(self, paper):
        from .imports import atomic_json
        with self.lock:
            if paper["paper_id"] in self.papers:
                raise ValueError("Paper already registered")
            for field in ("source_pdf", "docling_json", "evidence_index"):
                self.path(paper[field]).resolve(strict=True)
            library = self.path("data/gui-library.json")
            saved = json.loads(library.read_text(encoding="utf-8")) if library.exists() else {"papers": []}
            saved["papers"].append(paper)
            atomic_json(library, saved)
            self.papers[paper["paper_id"]] = paper

    def load(self, key: str) -> LoadedPaper:
        if key not in self.papers:
            raise KeyError("Paper not found")
        with self.lock:
            paper = self.papers[key]
            paths = [self.path(paper[field]) for field in
                     ("source_pdf", "docling_json", "evidence_index", "annotations") if paper.get(field)]
            signature = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
            if key in self.cache and self.cache[key][0] == signature:
                return self.cache[key][1]
            pdf = self.path(paper["source_pdf"])
            with pdf.open("rb") as stream:
                if not stream.read(1024).lstrip().startswith(b"%PDF-"):
                    raise ValueError("The source file is not a PDF")
            source_hash = fingerprint(pdf)
            expected = paper.get("source_sha256")
            if expected and expected != source_hash:
                raise ValueError("Source PDF fingerprint differs from the corpus manifest")
            docling = self.path(paper["docling_json"]) if paper.get("docling_json") else None
            index = None
            if docling:
                index = (index_document(self.path(paper["evidence_index"]), EvidenceAdapter())
                         if paper.get("evidence_index") else index_document(docling, DoclingAdapter(pdf)))
                if index.document.document_id != fingerprint(docling):
                    raise ValueError("Saved evidence does not match this Docling export")
                if index.document.source_filename != pdf.name:
                    raise ValueError("Saved evidence names a different source PDF")
                if index.document.source_sha256 and index.document.source_sha256 != source_hash:
                    raise ValueError("Saved evidence refers to a different source PDF fingerprint")
                expected = expected or index.document.source_sha256
            results = None
            checks = []
            if paper.get("annotations"):
                if index is None:
                    raise ValueError("Result annotations require an evidence index")
                results = ResultCollection.model_validate_json(self.path(paper["annotations"]).read_bytes())
                if results.document_id != index.document.document_id:
                    raise ValueError("Annotations refer to a different document conversion")
                checks = validate_results(results, index)
            loaded = LoadedPaper(paper, pdf, source_hash,
                                 "Stored source fingerprint matched" if expected else
                                 "Source fingerprint computed; no stored fingerprint available",
                                 index, results, checks, docling)
            self.cache[key] = (signature, loaded)
            return loaded

    def document(self, key: str) -> dict:
        loaded = self.load(key)
        index = loaded.index
        units = {}
        if index:
            for key, unit in index.units.items():
                data = unit.model_dump(mode="json")
                for location, original in zip(data["locations"], unit.locations):
                    location["display_rect"] = display_rect(original, index.document.pages)
                units[key] = data
        exports = ["evidence", "rag", "docling"] if index else []
        if loaded.results:
            exports += ["results", "csv", "markdown", "checks"]
        return {"paper": loaded.paper, "source_sha256": loaded.source_hash,
                "source_status": loaded.source_status,
                "document": index.document.model_dump(mode="json") if index else None,
                "units": units, "records": [r.model_dump(mode="json") for r in loaded.results.records]
                if loaded.results else [], "checks": loaded.checks,
                "run": loaded.results.run.model_dump(mode="json") if loaded.results else None,
                "counts": dict(Counter(u.kind for u in index.units.values())) if index else {},
                "exports": exports}


def export(loaded: LoadedPaper, kind: str) -> tuple[bytes, str, str]:
    index, results = loaded.index, loaded.results
    def as_json(value):
        return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    if kind == "evidence" and index:
        return as_json(index.model_dump(mode="json")), "application/json", "evidence.json"
    if kind == "docling" and loaded.docling:
        return loaded.docling.read_bytes(), "application/json", "docling.json"
    if kind == "rag" and index:
        chunks = rag_chunks(index, results=results)
        raw = "".join(json.dumps(c, ensure_ascii=False, allow_nan=False) + "\n" for c in chunks)
        return raw.encode(), "application/x-ndjson", "rag.jsonl"
    if results:
        if kind == "results":
            return as_json(results.model_dump(mode="json")), "application/json", "results.json"
        if kind == "checks":
            return as_json({"document_id": results.document_id, "checks": loaded.checks}), "application/json", "checks.json"
        rows = []
        for record, check in zip(results.records, loaded.checks):
            value_unit = index.units.get(record.value_evidence.evidence_id)
            rows.append({"result_id": record.result_id, "method": record.method.reported,
                         "dataset": record.benchmark.dataset.reported, "metric": record.metric.name.reported,
                         "raw_value": record.value.raw, "numeric_value": record.value.numeric,
                         "reported_scale": record.metric.reported_scale,
                         "direction": record.metric.direction, "unit": record.metric.unit,
                         "conditions_json": json.dumps([c.model_dump(mode="json") for c in record.conditions], ensure_ascii=False),
                         "pages": ",".join(str(page) for page in sorted({loc.page_no for loc in value_unit.locations})) if value_unit else "",
                         "document_id": results.document_id, "source_filename": loaded.pdf.name,
                         "source_sha256": loaded.source_hash,
                         "evidence_id": record.value_evidence.evidence_id,
                         "check_outcome": check["outcome"], "review_status": record.review.status,
                         "issues": ";".join(check["errors"] + check["warnings"])})
        if kind == "csv":
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ["result_id"])
            writer.writeheader()
            for row in rows:
                # Prevent spreadsheet formulas in textual fields, retaining JSON as the exact export.
                writer.writerow({k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v)
                                 for k, v in row.items()})
            return stream.getvalue().encode("utf-8-sig"), "text/csv", "results.csv"
        if kind == "markdown":
            def md(value):
                return str(value or "").replace("|", "\\|").replace("\n", " ").replace("\r", " ")
            lines = ["# Provisional result annotations", "",
                     "Evidence checks are limited attribution checks. Review status is preserved.", "",
                     "| Method | Dataset | Metric | Raw value | Evidence | Check | Review |",
                     "|---|---|---|---|---|---|---|"]
            for row in rows:
                lines.append("| " + " | ".join(md(row[k]) for k in
                             ("method", "dataset", "metric", "raw_value", "evidence_id", "check_outcome", "review_status")) + " |")
            return ("\n".join(lines) + "\n").encode(), "text/markdown", "results.md"
    raise KeyError("This export is unavailable for this paper")


def create_app(root: Path) -> FastAPI:
    # Windows registry MIME settings can classify .mjs as text/plain. Module
    # scripts and workers require JavaScript MIME types with nosniff enabled.
    mimetypes.add_type("text/javascript", ".mjs")
    mimetypes.add_type("application/wasm", ".wasm")
    workspace = Workspace(root)
    from .imports import Imports, new_upload_id
    imports = Imports(workspace)
    @asynccontextmanager
    async def lifespan(app):
        yield
        imports.close()
    app = FastAPI(title="Research evidence workspace", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.workspace = workspace
    app.state.imports = imports
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    static = Path(__file__).parent / "static"

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; worker-src 'self' blob:; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            "connect-src 'self'; font-src 'self' data:; object-src 'none'; "
            "frame-ancestors 'none'; base-uri 'self'")
        return response

    def load(key):
        try:
            return workspace.load(key)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except (OSError, ValueError) as error:
            raise HTTPException(409, f"Cannot load source evidence: {error}") from error

    @app.get("/api/papers")
    def papers():
        return workspace.list_papers()

    def same_origin(request: Request):
        origin = request.headers.get("origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.netloc != request.headers.get("host") or parsed.scheme not in {"http", "https"}:
                raise HTTPException(403, "Uploads must originate from this application")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Cross-site writes are unavailable")

    @app.get("/api/imports")
    def jobs():
        return imports.list()

    @app.post("/api/imports", status_code=202)
    async def upload(request: Request, filename: str, title: str = "", ocr: bool = False):
        same_origin(request)
        if importlib.util.find_spec("docling") is None:
            raise HTTPException(503, 'PDF processing requires the Docling extra: pip install -e ".[gui,docling]"')
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        if not filename.lower().endswith(".pdf") or len(filename) > 240:
            raise HTTPException(400, "Choose a PDF file with a filename under 240 characters")
        title = title.strip() or Path(filename).stem
        if len(title) > 500:
            raise HTTPException(400, "The title must be under 500 characters")
        job_id = new_upload_id()
        directory = workspace.path(f"data/uploads/{job_id}")
        directory.mkdir(parents=True)
        source = directory / "source.pdf"
        total = 0
        try:
            with source.open("xb") as stream:
                async for block in request.stream():
                    total += len(block)
                    if total > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, "Maximum upload size is 100 MB")
                    stream.write(block)
            with source.open("rb") as stream:
                if not stream.read(1024).lstrip().startswith(b"%PDF-"):
                    raise HTTPException(400, "The file does not contain a PDF signature")
        except BaseException:
            source.unlink(missing_ok=True)
            directory.rmdir()
            raise
        return imports.create(job_id, filename, title, ocr)

    @app.post("/api/imports/{job_id}/cancel")
    def cancel(job_id: str, request: Request):
        same_origin(request)
        try:
            return imports.cancel(job_id)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error

    @app.get("/api/papers/{paper_id}")
    def document(paper_id: str):
        try:
            return workspace.document(paper_id)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except (OSError, ValueError) as error:
            raise HTTPException(409, f"Cannot load source evidence: {error}") from error

    @app.get("/api/papers/{paper_id}/pdf")
    def pdf(paper_id: str):
        return FileResponse(load(paper_id).pdf, media_type="application/pdf")

    @app.get("/api/papers/{paper_id}/exports/{kind}")
    def download(paper_id: str, kind: str):
        loaded = load(paper_id)
        try:
            data, mime, suffix = export(loaded, kind)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        name = re.sub(r"[^a-zA-Z0-9._-]", "_", paper_id) + "." + suffix
        return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/")
    def home():
        built = static / "react/index.html"
        return FileResponse(built if built.exists() else static / "index.html", media_type="text/html")

    app.mount("/static", StaticFiles(directory=static), name="static")
    return app
