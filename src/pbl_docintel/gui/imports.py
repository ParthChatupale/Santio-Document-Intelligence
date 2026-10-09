"""Persistent local import jobs; one isolated conversion at a time."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from threading import RLock
import uuid


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class Imports:
    def __init__(self, workspace):
        self.workspace = workspace
        self.directory = workspace.path("data/import-jobs")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.jobs = {}
        self.processes = {}
        self.futures = {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pdf-import")
        for path in self.directory.glob("*.json"):
            job = json.loads(path.read_text(encoding="utf-8"))
            if job["status"] in {"queued", "processing"}:
                job.update(status="failed", stage="Interrupted", error="The service stopped during processing. Upload again to retry.")
                atomic_json(path, job)
            self.jobs[job["job_id"]] = job

    def update(self, job_id, **fields):
        with self.lock:
            job = self.jobs[job_id]
            job.update(fields)
            atomic_json(self.directory / f"{job_id}.json", job)
            return dict(job)

    def list(self):
        with self.lock:
            return [dict(job) for job in sorted(self.jobs.values(), key=lambda j: j["created_at"], reverse=True)]

    def create(self, job_id, filename, title, ocr):
        job = {"job_id": job_id, "filename": filename, "title": title,
               "ocr": ocr, "status": "queued", "stage": "Waiting for converter",
               "created_at": datetime.now(timezone.utc).isoformat(),
               "paper_id": None, "error": None}
        with self.lock:
            self.jobs[job_id] = job
            self.update(job_id)
            self.futures[job_id] = self.executor.submit(self.run, job_id)
        return dict(job)

    def cancel(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError("Import not found")
            if self.jobs[job_id]["status"] not in {"queued", "processing"}:
                return dict(self.jobs[job_id])
            self.update(job_id, status="cancelled", stage="Cancelled")
            future = self.futures.get(job_id)
            if future:
                future.cancel()
            process = self.processes.get(job_id)
            if process:
                process.terminate()
            return dict(self.jobs[job_id])

    def run(self, job_id):
        try:
            with self.lock:
                if self.jobs[job_id]["status"] == "cancelled":
                    return
                self.update(job_id, status="processing", stage="Starting converter")
                directory = self.workspace.path(f"data/uploads/{job_id}")
                output = directory / "converted"
                command = [sys.executable, "-m", "pbl_docintel.gui.import_worker", str(directory / "source.pdf"), str(output)]
                if self.jobs[job_id]["ocr"]:
                    command.append("--ocr")
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, encoding="utf-8", errors="replace",
                                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
                self.processes[job_id] = process
            log = directory / "conversion.log"
            with log.open("w", encoding="utf-8") as stream:
                for line in process.stdout:
                    stream.write(line)
                    stream.flush()
                    if line.startswith("SANTIO_STAGE:"):
                        with self.lock:
                            if self.jobs[job_id]["status"] != "cancelled":
                                self.update(job_id, stage=line.strip().split(":", 1)[1])
            code = process.wait()
            with self.lock:
                if self.jobs[job_id]["status"] == "cancelled":
                    return
                if code:
                    tail = log.read_text(encoding="utf-8")[-1800:]
                    raise RuntimeError(f"Conversion exited with code {code}. {tail}")
                receipt = json.loads((output / "receipt.json").read_text(encoding="utf-8"))
                from .server import fingerprint
                paper_id = f"upload:{job_id}"
                relative = f"data/uploads/{job_id}"
                self.workspace.register({
                    "paper_id": paper_id, "title": self.jobs[job_id]["title"],
                    "original_filename": self.jobs[job_id]["filename"],
                    "source_pdf": f"{relative}/source.pdf",
                    "source_sha256": fingerprint(directory / "source.pdf"),
                    "docling_json": f"{relative}/converted/document.json",
                    "evidence_index": f"{relative}/converted/evidence.index.json",
                    "rag_chunks": f"{relative}/converted/rag.jsonl",
                    "role": "user_upload", "status": receipt["status"],
                })
                self.update(job_id, status="completed", stage="Ready in library", paper_id=paper_id,
                            conversion_status=receipt["status"], pages=receipt["pages"])
        except Exception as error:
            with self.lock:
                if self.jobs[job_id]["status"] != "cancelled":
                    self.update(job_id, status="failed", stage="Processing failed", error=str(error))
        finally:
            with self.lock:
                process = self.processes.pop(job_id, None)
            if process:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                if process.stdout:
                    process.stdout.close()

    def close(self):
        for job in self.list():
            if job["status"] in {"queued", "processing"}:
                self.cancel(job["job_id"])
        self.executor.shutdown(wait=True, cancel_futures=True)


def new_upload_id():
    return uuid.uuid4().hex
