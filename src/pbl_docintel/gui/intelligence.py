"""Persistent background understanding and question jobs for the local GUI."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from threading import RLock
import uuid

from ..models import HTTPJSONModel
from ..understanding import analyze, answer
from .imports import atomic_json


class Intelligence:
    def __init__(self, workspace):
        self.workspace = workspace
        self.directory = workspace.path("data/understanding")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.model = HTTPJSONModel.from_env()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paper-understanding")
        self.jobs = {}
        for path in self.directory.glob("job-*.json"):
            job = json.loads(path.read_text(encoding="utf-8"))
            if job["status"] in {"queued", "processing"}:
                job.update(status="failed", stage="Interrupted", error="Service restarted during generation. Run the request again.")
                atomic_json(path, job)
            self.jobs[job["job_id"]] = job

    def configure(self, provider, url, model, key="", keep_key=False):
        with self.lock:
            if keep_key and (provider != self.model.provider or url.rstrip("/") != self.model.url):
                raise ValueError("Enter a new key when changing the model destination")
            self.model = HTTPJSONModel(provider, url, model, self.model.key if keep_key else key)
            return self.model.public()

    def report_path(self, index):
        return self.directory / (index.document.document_id + ".json")

    def state(self, key):
        loaded = self.workspace.load(key)
        report = None
        if loaded.index:
            path = self.report_path(loaded.index)
            if path.exists():
                report = json.loads(path.read_text(encoding="utf-8"))
                if report["document_id"] != loaded.index.document.document_id:
                    raise ValueError("Understanding belongs to a different conversion")
                if report.get("source_sha256") != loaded.index.document.source_sha256:
                    report = None
        with self.lock:
            jobs = [dict(j) for j in self.jobs.values() if j["paper_id"] == key and
                    loaded.index and j["document_id"] == loaded.index.document.document_id]
            return {"model": self.model.public(), "report": report,
                    "jobs": sorted(jobs, key=lambda j: j["created_at"], reverse=True)[:30]}

    def update(self, job_id, **fields):
        with self.lock:
            self.jobs[job_id].update(fields)
            atomic_json(self.directory / ("job-" + job_id + ".json"), self.jobs[job_id])
            return dict(self.jobs[job_id])

    def start(self, paper_id, kind, question=""):
        loaded = self.workspace.load(paper_id)
        if loaded.index is None:
            raise ValueError("Convert this PDF before running paper understanding")
        with self.lock:
            if not self.model.public()["configured"]:
                raise ValueError("Connect a model and API key before generating understanding")
            active = [j for j in self.jobs.values() if j["status"] in {"queued", "processing"}]
            if len(active) >= 5:
                raise ValueError("Five requests are already queued. Wait for them to finish.")
            for job in active:
                if job["paper_id"] == paper_id and job["kind"] == kind and job.get("question", "") == question:
                    return dict(job)
            model = self.model  # Capture configuration for this run.
            job_id = uuid.uuid4().hex
            job = {"job_id": job_id, "paper_id": paper_id, "document_id": loaded.index.document.document_id,
                   "kind": kind, "question": question, "status": "queued", "stage": "Waiting for analysis",
                   "created_at": datetime.now(timezone.utc).isoformat(), "model": model.name,
                   "error": None, "result": None}
            self.jobs[job_id] = job
            self.update(job_id)
            self.executor.submit(self.run, job_id, loaded.index, model)
            return dict(job)

    def run(self, job_id, index, model):
        self.update(job_id, status="processing", stage="Starting paper analysis")
        try:
            progress = lambda stage: self.update(job_id, stage=stage)
            job = self.jobs[job_id]
            result = analyze(index, model, progress) if job["kind"] == "analysis" else answer(index, model, job["question"], progress)
            current = self.workspace.load(job["paper_id"]).index
            if current is None or current.document.document_id != index.document.document_id or current.document.source_sha256 != index.document.source_sha256:
                raise ValueError("Source changed during generation. Open the current document and run analysis again.")
            if job["kind"] == "analysis":
                atomic_json(self.report_path(index), result)
            self.update(job_id, status="completed", stage="Paper understanding ready" if job["kind"] == "analysis" else "Answer ready", result=result)
        except Exception as error:
            # Validation diagnostics are deliberately not exposed: Pydantic's
            # error rendering may include document/model response content.
            from pydantic import ValidationError
            message = "Model output did not match the required schema. Try again or choose a model with reliable JSON output." if isinstance(error, ValidationError) else str(error)
            self.update(job_id, status="failed", stage="Generation failed", error=message[:1000])

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
