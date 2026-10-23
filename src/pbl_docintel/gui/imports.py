"""Persistent upload/preparation jobs; one owned worker at a time."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from threading import RLock
import uuid

ACTIVE = {"uploading", "queued", "processing", "cancelling"}


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def terminate_owned_process(process):
    if process.poll() is not None:
        return
    if sys.platform == "win32" and isinstance(process.pid, int):
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW, check=False)
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


class Imports:
    def __init__(self, workspace):
        self.workspace = workspace
        self.directory = workspace.path("data/import-jobs")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.jobs, self.processes, self.futures = {}, {}, {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="document-worker")
        for path in self.directory.glob("*.json"):
            job = json.loads(path.read_text(encoding="utf-8"))
            if job["status"] in ACTIVE:
                job.update(status="failed", stage="Interrupted", error="The service stopped during processing. Retry preparation, or choose the file again if upload was incomplete.")
                atomic_json(path, job)
                if job.get("paper_id"):
                    workspace.set_rag_status(job["paper_id"], status="failed", job_id=job["job_id"], error=job["error"])
            self.jobs[job["job_id"]] = job

    def update(self, job_id, **fields):
        with self.lock:
            job = self.jobs[job_id]
            job.update(fields, updated_at=datetime.now(timezone.utc).isoformat())
            atomic_json(self.directory / f"{job_id}.json", job)
            if job.get("paper_id") and job["status"] != "completed":
                self.workspace.set_rag_status(job["paper_id"], status=job["status"], job_id=job_id,
                                              stage=job["stage"], error=job.get("error"))
            return dict(job)

    def list(self):
        with self.lock:
            return [dict(j) for j in sorted(self.jobs.values(), key=lambda j: j["created_at"], reverse=True)]

    def get(self, job_id):
        with self.lock:
            return dict(self.jobs[job_id])

    def _new(self, job_id, filename, title, ocr, *, status, paper_id=None, size=None):
        self.jobs[job_id] = {"job_id": job_id, "filename": filename, "title": title, "ocr": ocr,
                            "status": status, "stage": "Uploading PDF" if status == "uploading" else "Waiting for worker",
                            "phase": "upload" if status == "uploading" else "extract", "size_bytes": size,
                            "completed_stages": [] if status == "uploading" else ["upload"],
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "paper_id": paper_id, "error": None, "attempt": 0}
        return self.update(job_id)

    def start_upload(self, job_id, filename, title, ocr, size):
        with self.lock:
            self.workspace.path(f"data/uploads/{job_id}").mkdir(parents=True)
            return self._new(job_id, filename, title, ocr, status="uploading", size=size)

    def create(self, job_id, filename, title, ocr):
        # Compatibility with the original one-request upload endpoint.
        with self.lock:
            self._new(job_id, filename, title, ocr, status="queued")
            return self._enqueue(job_id)

    def finish_upload(self, job_id):
        with self.lock:
            if self.jobs[job_id]["status"] != "uploading":
                raise ValueError("This upload is no longer active.")
            return self._enqueue(job_id)

    def _enqueue(self, job_id):
        job = self.update(job_id, status="queued", phase="extract", stage="Waiting for worker", error=None,
                          completed_stages=["upload"], done=None, total=None)
        self.futures[job_id] = self.executor.submit(self.run, job_id)
        return job

    def prepare(self, paper_id):
        with self.lock:
            for job in self.jobs.values():
                if job.get("paper_id") == paper_id and job["status"] in ACTIVE:
                    return dict(job)
            loaded = self.workspace.load(paper_id)
            job_id = new_upload_id()
            self._new(job_id, loaded.paper.get("original_filename", loaded.pdf.name), loaded.paper["title"], False,
                      status="queued", paper_id=paper_id)
            return self._enqueue(job_id)

    def retry(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            if job["status"] not in {"failed", "cancelled"}:
                raise ValueError("Only failed or cancelled jobs can be retried.")
            if not job.get("paper_id") and not self.workspace.path(f"data/uploads/{job_id}/source.pdf").is_file():
                raise ValueError("The upload was incomplete. Choose the PDF again.")
            return self._enqueue(job_id)

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            if job["status"] not in ACTIVE:
                return dict(job)
            future, process = self.futures.get(job_id), self.processes.get(job_id)
            if future:
                future.cancel()
            self.update(job_id, status="cancelling" if process else "cancelled", stage="Stopping worker" if process else "Cancelled")
        if process:
            terminate_owned_process(process)
        return self.update(job_id, status="cancelled", stage="Cancelled")

    def _extracted(self, job_id, event):
        job = self.jobs[job_id]
        fields = {"docling_json": event["document"], "evidence_index": event["evidence_index"],
                  "status": event["conversion_status"]}
        if not job.get("paper_id"):
            from .server import fingerprint
            relative = f"data/uploads/{job_id}"
            paper_id = f"upload:{job_id}"
            self.workspace.register({"paper_id": paper_id, "title": job["title"], "original_filename": job["filename"],
                                     "source_pdf": f"{relative}/source.pdf",
                                     "source_sha256": fingerprint(self.workspace.path(f"{relative}/source.pdf")),
                                     "role": "user_upload", **fields})
        else:
            paper_id = job["paper_id"]
            self.workspace.attach_extraction(paper_id, **fields)
        self.update(job_id, paper_id=paper_id, conversion_status=event["conversion_status"], pages=event["pages"])

    def run(self, job_id):
        process = None
        try:
            with self.lock:
                job = self.jobs[job_id]
                if job["status"] != "queued":
                    return
                attempt = job.get("attempt", 0) + 1
                self.update(job_id, status="processing", stage="Starting worker", attempt=attempt)
                if job.get("paper_id"):
                    loaded = self.workspace.load(job["paper_id"])
                    pdf = loaded.pdf.relative_to(self.workspace.root)
                    document = loaded.docling.relative_to(self.workspace.root) if loaded.docling else None
                    status = loaded.paper.get("status", "success")
                else:
                    pdf, document, status = Path(f"data/uploads/{job_id}/source.pdf"), None, "success"
                base = self.workspace.path(f"data/preparations/{job_id}")
                base.mkdir(parents=True, exist_ok=True)
                # Recover an export saved just before a worker interruption, even
                # when its 'extracted' event never reached the parent process.
                if document is None:
                    for previous in range(attempt - 1, 0, -1):
                        prior = base / f"attempt-{previous}.json"
                        if not prior.exists():
                            continue
                        previous_spec = json.loads(prior.read_text(encoding="utf-8"))
                        converted = self.workspace.path(previous_spec["output"]) / "converted"
                        report_path = converted / "conversion_report.json"
                        if not report_path.exists() or not (converted / "document.json").exists():
                            continue
                        report = json.loads(report_path.read_text(encoding="utf-8"))
                        if report["status"] in {"success", "partial_success"} and Path(report["source"]).resolve() == self.workspace.path(str(pdf)):
                            document = (converted / "document.json").relative_to(self.workspace.root)
                            status = report["status"]
                            break
                spec = {"pdf": str(pdf), "document": str(document) if document else None,
                        "chunks_file": job.get("chunks_file"),
                        "output": f"data/preparations/{job_id}/attempt-{attempt}-{uuid.uuid4().hex[:8]}",
                        "ocr": job["ocr"], "conversion_status": status}
                spec_path = base / f"attempt-{attempt}.json"
                atomic_json(spec_path, spec)
                command = [sys.executable, "-X", "utf8", "-u", "-m", "pbl_docintel.gui.rag_worker", "prepare",
                           "--workspace", str(self.workspace.root), "--input", str(spec_path)]
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, encoding="utf-8", errors="replace",
                                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
                self.processes[job_id] = process
            ready, error, tail = None, None, []
            with (base / f"attempt-{attempt}.log").open("w", encoding="utf-8") as log:
                for line in process.stdout:
                    log.write(line); log.flush()
                    tail = (tail + [line])[-8:]
                    if line.startswith("SANTIO_EVENT:"):
                        event = json.loads(line.split(":", 1)[1])
                        with self.lock:
                            if self.jobs[job_id]["status"] in {"cancelled", "cancelling"}:
                                continue
                            if event.get("kind") == "extracted":
                                self._extracted(job_id, event)
                            if event.get("kind") == "ready":
                                ready = event
                            elif event.get("kind") == "error":
                                error = event["error"]
                            if event.get("stage"):
                                self.update(job_id, **{k: v for k, v in event.items() if k in {
                                    "phase", "stage", "completed_stages", "done", "total", "chunk_count", "chunks_file"}})
                    elif line.startswith("SANTIO_STAGE:"):
                        self.update(job_id, stage=line.strip().split(":", 1)[1])
            code = process.wait()
            with self.lock:
                if self.jobs[job_id]["status"] in {"cancelled", "cancelling"}:
                    self.update(job_id, status="cancelled", stage="Cancelled")
                    return
                if code or not ready:
                    raise RuntimeError(error or ("Worker failed. " + "".join(tail)[-1000:]))
                paper_id = self.jobs[job_id]["paper_id"]
                self.workspace.set_rag_status(paper_id, status="ready", job_id=job_id, error=None,
                                              **{k: ready[k] for k in ["index_id", "chunk_count", "document_sha256", "source_sha256", "chunks_file"]})
                self.update(job_id, status="completed", phase="ready", stage="Ready to ask",
                            completed_stages=["upload", "extract", "chunk", "embed"], done=None, total=None)
        except Exception as exc:
            with self.lock:
                if self.jobs[job_id]["status"] not in {"cancelled", "cancelling"}:
                    self.update(job_id, status="failed", stage="Preparation failed", error=str(exc))
        finally:
            with self.lock:
                self.processes.pop(job_id, None)
            if process:
                terminate_owned_process(process)
                process.stdout.close()

    def close(self):
        for job in self.list():
            if job["status"] in ACTIVE:
                self.cancel(job["job_id"])
        self.executor.shutdown(wait=True, cancel_futures=True)


def new_upload_id():
    return uuid.uuid4().hex
