"""Local graph explorer and question room for one explicit Microsoft GraphRAG run.

No main-application imports or changes. Query jobs invoke query_graph.py with its
owned-process timeout. Only completed indexes can answer; partial graphs remain
inspectable. Credentials and arbitrary filesystem routes are never exposed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib
from io import BytesIO
from pathlib import Path
import re
import secrets
import sys
import threading
from urllib.parse import parse_qs, urlparse

from _common import HERE, ROOT, read_json, relationship_key, safe_error, stamp, supervise, write_json
from _sources import as_rows, load_tables, source_ledger


def web_evidence(context):
    """Keep the UI payload small; full provenance stays in saved query artifacts."""
    return {name: [{**{key: row.get(key) for key in ["citation_id", "native_id", "resolved", "docling_refs", "pages"]},
                   "source_records": [{key: source.get(key) for key in ["record_id", "item_refs", "pages"]}
                                      for source in row.get("source_records", [])]} for row in rows]
            for name, rows in context.items()}


def graph_payload(run):
    tables = load_tables(run)
    sources, ledger = source_ledger(run, tables)
    reports = as_rows(tables.get("community_reports", []))
    review_file = Path(run) / "evaluations/source-review/semantic_review.json"
    reviews = read_json(review_file) if review_file.exists() else {}
    edge_reviews = {r["key"]: r for r in reviews.get("relationship_reviews", [])}
    node_reviews = {r["label"]: r for r in reviews.get("entity_reviews", [])}
    report_titles = {str(r["community"]): r["title"] for r in reports}
    membership = {}
    communities = sorted(as_rows(tables.get("communities", [])), key=lambda c: c.get("level", 0))
    for community in communities:
        for ident in community.get("entity_ids") or []:
            membership.setdefault(str(ident), community["community"])

    def evidence(table, row):
        ids = sorted(ledger.get((table, str(row["id"])), set()))
        return {"source_ids": ids, "pages": sorted({p for key in ids for p in sources[key]["pages"]})}

    nodes = [{"id": r["id"], "label": r["title"], "type": r.get("type") or "Other",
              "description": r.get("description", ""), "degree": r.get("degree", 0),
              "review": node_reviews.get(r["title"]),
              "community": membership.get(str(r["id"])), **evidence("entities", r)}
             for r in as_rows(tables.get("entities", []))]
    titles = {n["label"]: n["id"] for n in nodes}
    # Keep validated, directed assertions separate from native undirected merged
    # edges. A native summary can combine several roles between the same pair.
    assertions = {}
    sidecars = list((Path(run) / "validated_extractions").glob("*.json"))
    if sidecars:
        from _contracts import source_text
        from graphrag.index.utils.string import clean_str
        source_ids = {r["text"].strip(): r["id"] for r in read_json(Path(run) / "input/documents.json")}
        for path in sidecars:
            saved = read_json(path)
            request = read_json(Path(run) / "requests" / path.name)
            ident = source_ids.get((source_text(request["messages"]) or "").strip())
            for assertion in saved.get("relationship_evidence", []):
                pair = tuple(sorted(clean_str(assertion[k].upper()) for k in ["source", "target"]))
                entry = {**assertion, "source_record_id": ident, 'model': request.get('model')}
                entries = assertions.setdefault(pair, [])
                if entry not in entries:
                    entries.append(entry)
    edges = [{"id": r["id"], "source": titles.get(r["source"]), "target": titles.get(r["target"]),
              "source_label": r["source"], "target_label": r["target"],
              "description": r.get("description", ""), "weight": r.get("weight"),
              "review": edge_reviews.get(relationship_key(r)),
              "assertion_evidence": assertions.get(tuple(sorted([r["source"], r["target"]])), []),
              **evidence("relationships", r)} for r in as_rows(tables.get("relationships", []))]
    return {"nodes": nodes, "edges": edges, "communities": [
        {**{k: c.get(k) for k in ["community", "level", "size"]}, "title": report_titles.get(str(c["community"]), c.get("title"))} for c in communities],
        "reports": [{k: r.get(k) for k in ["community", "title", "summary", "full_content"]}
                    for r in reports],
        "note": "Model-extracted relationships. Native weights are not confidence scores; links have no fixed predicate direction."}


class Explorer:
    def __init__(self, run, pdf):
        self.run, self.pdf = Path(run).resolve(strict=True), Path(pdf).resolve(strict=True)
        self.token = secrets.token_urlsafe(32)
        self.jobs, self.lock = {}, threading.Lock()
        self.pdf_lock, self.page_cache = threading.Lock(), {}
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.graph_cache = (None, None)

    def page_image(self, number):
        """Render an original page without relying on a browser PDF plug-in."""
        import pypdfium2 as pdfium
        # PDFium calls must be serialized across the HTTP server's threads.
        with self.pdf_lock:
            if number in self.page_cache:
                return self.page_cache[number]
            document = pdfium.PdfDocument(str(self.pdf))
            try:
                if not 1 <= number <= len(document):
                    raise ValueError("Page outside this PDF.")
                page = document[number - 1]
                try:
                    bitmap = page.render(scale=1.6)
                    try:
                        buffer = BytesIO()
                        bitmap.to_pil().save(buffer, format="PNG")
                        data = buffer.getvalue()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
            finally:
                document.close()
            if len(self.page_cache) >= 8:
                self.page_cache.pop(next(iter(self.page_cache)))
            self.page_cache[number] = data
            return data

    def status(self):
        manifest = read_json(self.run / "run.json")
        usage = read_json(self.run / "model_calls.json") if (self.run / "model_calls.json").exists() else {}
        calls = usage.get("completion_calls", [])
        source_map = read_json(self.run / "source_map.json")
        successful = [c for c in calls if c["status"] == "completed"]
        seen = {ident for c in successful for ident in c.get("source_record_ids", [])}
        coverage = read_json(self.run / "coverage.json") if (self.run / "coverage.json").exists() else {}
        seen.update(ident for unit in coverage.get("units", []) if unit.get("successful_extraction_request")
                    for ident in unit.get("source_ids", []))
        if not coverage.get("processing_complete"):
            # V2 keeps provenance outside model text. Count validated initial
            # requests, including exact cache hits, before final coverage exists.
            from _contracts import source_text, native_messages
            by_text = {}
            for record in read_json(self.run / 'input/documents.json'):
                by_text.setdefault(record['text'].strip(), set()).add(record['id'])
            for key in {c['request_hash'] for c in calls if c['status'] in {'completed', 'cache_hit'}}:
                audit = self.run / 'validated_extractions' / (key + '.json')
                request = self.run / 'requests' / (key + '.json')
                if not audit.exists() or not request.exists() or not read_json(audit).get('all_records_consumed'):
                    continue
                messages = native_messages(read_json(request)['messages'])
                if len(messages) == 1:
                    text = source_text(messages)
                    seen.update(by_text.get((text or '').strip(), set()))
        ready = manifest["status"] == "completed" and coverage.get("processing_complete", False)
        return {"title": "Tetris3D · 3D scene generation" if "2610.10539" in self.pdf.name else self.pdf.stem,
                "pdf": self.pdf.name, "status": "coverage_review" if manifest["status"] == "completed" and not ready else manifest["status"], "can_ask": ready,
                "partial_document_scope": manifest["partial_document_scope"],
                "records": len(source_map), "records_with_successful_requests": len(seen.intersection(source_map)),
                "input_pages": sorted({p for s in source_map.values() for p in s["pages"]}),
                "requests": len([c for c in calls if c["status"] != "cache_hit"]),
                "failed_attempts": sum(c["status"] == "failed" for c in calls),
                "reported_tokens": sum(c.get("usage", {}).get("total_tokens", 0) for c in calls),
                "elapsed_seconds": usage.get("elapsed_seconds", 0),
                "stage": read_json(self.run / "progress.json") if (self.run / "progress.json").exists() else {},
                "error": manifest.get("error"), "native_tables": manifest.get("native_tables", {}),
                "quality_verified": manifest.get("quality_verified", False)}

    def saved_job(self, ident):
        if not re.fullmatch(r"\d{8}T\d{12}Z", ident):
            return None
        folder = self.run / "queries" / ("web-" + ident)
        if not (folder / "answer.json").exists():
            return None
        result = read_json(folder / "answer.json")
        return {"id": ident, "status": "failed" if result["status"] == "failed" else "done",
                "question": result["question"], "mode": result["mode"], "result": result,
                "evidence": web_evidence(read_json(folder / "source_context.json")) if (folder / "source_context.json").exists() else {},
                "native_context": read_json(folder / "context.json") if (folder / "context.json").exists() else {}}

    def graph(self):
        signature = tuple((p.name, p.stat().st_mtime_ns) for p in sorted((self.run / "output").glob("*.parquet")))
        review_file = self.run / "evaluations/source-review/semantic_review.json"
        if review_file.exists():
            signature += (("source-review", review_file.stat().st_mtime_ns),)
        with self.lock:
            if self.graph_cache[0] != signature:
                value = graph_payload(self.run)
                value["revision"] = hashlib.sha256(repr(signature).encode()).hexdigest()[:16]
                self.graph_cache = signature, value
            return self.graph_cache[1]

    def submit(self, question, mode):
        if not self.status()["can_ask"]:
            raise ValueError("Indexing must finish successfully before questions can be answered.")
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 6000:
            raise ValueError("Enter a question of 1–6000 characters.")
        if mode not in {"basic", "local", "global"}:
            raise ValueError("Unknown query mode.")
        with self.lock:
            if any(j["status"] in {"queued", "running"} for j in self.jobs.values()):
                raise ValueError("A question is already running. Please wait for its result.")
            ident = stamp()
            self.jobs[ident] = {"id": ident, "status": "queued", "question": question.strip(), "mode": mode}
        self.pool.submit(self.answer, ident)
        return {"id": ident, "status": "queued"}

    def answer(self, ident):
        with self.lock:
            job = self.jobs[ident]
            job["status"] = "running"
        folder = self.run / "queries" / ("web-" + ident)
        try:
            # Global performs multiple map requests plus a reduction. Keep it
            # bounded, while allowing the same budget as the full-paper test.
            seconds = 600 if job["mode"] == "global" else 300
            calls = 24 if job["mode"] == "global" else 12
            log = folder / "worker.log"
            folder.mkdir(parents=True)
            with log.open("w", encoding="utf-8") as handle:
                code = supervise(HERE / "query_graph.py", [str(self.run),
                    "--question", job["question"], "--mode", job["mode"], "--output", str(folder),
                    "--max-calls", str(calls), "--max-seconds", str(seconds), "--worker"], seconds, stderr=handle)
            if code == 124:
                write_json(folder / "answer.json", {"question": job["question"], "mode": job["mode"],
                    "status": "failed", "error": "Question time limit reached; the owned worker was terminated."})
            answer = read_json(folder / "answer.json")
            context = read_json(folder / "source_context.json") if (folder / "source_context.json").exists() else {}
            with self.lock:
                job.update(status="done" if answer["status"] != "failed" else "failed", result=answer, evidence=web_evidence(context),
                    native_context=read_json(folder / "context.json") if (folder / "context.json").exists() else {})
        except Exception as exc:
            with self.lock:
                job.update(status="failed", error=safe_error(exc))


def handler(explorer):
    class Handler(BaseHTTPRequestHandler):
        def local_host(self):
            host = urlparse("//" + self.headers.get("Host", ""))
            try:
                return host.hostname in {"127.0.0.1", "localhost"} and host.port == self.server.server_port
            except ValueError:
                return False

        def send(self, status, body, content_type="application/json; charset=utf-8", headers=None):
            if content_type.startswith("application/json"):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.local_host():
                return self.send(403, {"error": "Use this server's localhost address."})
            url = urlparse(self.path)
            try:
                if url.path == "/api/status":
                    return self.send(200, {**explorer.status(), "session": explorer.token})
                if url.path == "/api/graph":
                    return self.send(200, explorer.graph())
                if url.path == "/api/validation":
                    report = explorer.run / "inspection/validated_record_audit.json"
                    return self.send(200, read_json(report)) if report.exists() else self.send(404, {"error": "Validation audit has not been generated for this run."})
                if url.path == "/api/source":
                    ident = parse_qs(url.query).get("id", [""])[0]
                    sources = read_json(explorer.run / "source_map.json")
                    if ident not in sources:
                        return self.send(404, {"error": "Unknown source record."})
                    record = next(r for r in read_json(explorer.run / "input/documents.json") if r["id"] == ident)
                    return self.send(200, {**sources[ident], "text": record["text"]})
                if url.path == "/api/history":
                    history = []
                    for folder in sorted((explorer.run / "queries").glob("web-*"), reverse=True)[:10]:
                        job = explorer.saved_job(folder.name.removeprefix("web-"))
                        if job:
                            history.append({k: job[k] for k in ["id", "question", "mode", "status"]})
                    return self.send(200, history)
                if url.path.startswith("/api/jobs/"):
                    with explorer.lock:
                        job = dict(explorer.jobs.get(url.path.rsplit("/", 1)[1], {}))
                    job = job or explorer.saved_job(url.path.rsplit("/", 1)[1])
                    return self.send(200 if job else 404, job or {"error": "Unknown question."})
                if url.path == "/api/page":
                    try:
                        page = int(parse_qs(url.query).get("number", ["0"])[0])
                        return self.send(200, explorer.page_image(page), "image/png")
                    except ValueError as exc:
                        return self.send(400, {"error": str(exc)})
                if url.path == "/pdf":
                    total = explorer.pdf.stat().st_size
                    match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
                    if match:
                        start, end = int(match[1]), min(int(match[2]) if match[2] else total - 1, total - 1)
                        if start > end:
                            return self.send(416, b"", "application/pdf", {"Content-Range": f"bytes */{total}"})
                        with explorer.pdf.open("rb") as handle:
                            handle.seek(start)
                            body = handle.read(end - start + 1)
                        return self.send(206, body, "application/pdf", {"Content-Range": f"bytes {start}-{end}/{total}", "Accept-Ranges": "bytes"})
                    return self.send(200, explorer.pdf.read_bytes(), "application/pdf", {"Accept-Ranges": "bytes"})
                static = {"/": ("explorer.html", "text/html; charset=utf-8"),
                          "/explorer.js": ("explorer.js", "text/javascript; charset=utf-8"),
                          "/explorer.css": ("explorer.css", "text/css; charset=utf-8")}
                if url.path in static:
                    name, kind = static[url.path]
                    return self.send(200, (HERE / "web" / name).read_bytes(), kind)
                return self.send(404, {"error": "Not found."})
            except Exception as exc:
                return self.send(503, {"error": safe_error(exc)})

        def do_POST(self):
            if not self.local_host():
                return self.send(403, {"error": "Use this server's localhost address."})
            if self.path != "/api/questions":
                return self.send(404, {"error": "Not found."})
            origin = self.headers.get("Origin")
            if (origin and origin != "http://" + self.headers.get("Host", "")) or not secrets.compare_digest(
                self.headers.get("X-Graph-Session", ""), explorer.token):
                return self.send(403, {"error": "Use the question form in this local explorer."})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 32000:
                    raise ValueError("Invalid request size.")
                payload = json.loads(self.rfile.read(size))
                return self.send(202, explorer.submit(payload.get("question"), payload.get("mode", "local")))
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return self.send(400, {"error": str(exc)})

        def log_message(self, fmt, *args):
            # Question text is deliberately not written to access logs.
            if not self.path.startswith("/api/status") and not self.path.startswith("/api/jobs/"):
                super().log_message(fmt, *args)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--port", type=int, default=8773)
    args = parser.parse_args()
    manifest = read_json(args.run / "run.json")
    pdf = args.pdf or ROOT / (Path(manifest["source"]).stem + ".pdf")
    explorer = Explorer(args.run, pdf)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(explorer))
    print(f"Microsoft GraphRAG explorer: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        explorer.pool.shutdown(wait=True)


if __name__ == "__main__":
    main()
