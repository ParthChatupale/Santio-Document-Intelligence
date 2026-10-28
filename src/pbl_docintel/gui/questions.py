"""Persistent question jobs over server-selected paper indexes."""
from datetime import datetime, timezone
import json
import os
import subprocess
import sys
from threading import RLock

from .imports import ACTIVE, atomic_json, new_upload_id, terminate_owned_process


class Questions:
    def __init__(self, workspace, executor):
        self.workspace, self.executor = workspace, executor
        self.directory = workspace.path("data/question-jobs")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.jobs, self.processes, self.futures = {}, {}, {}
        for path in self.directory.glob("*.job.json"):
            job = json.loads(path.read_text(encoding="utf-8"))
            if job["status"] in ACTIVE:
                job.update(status="failed", stage="Interrupted", retry=None, error="The service stopped. Ask this question again.")
                atomic_json(path, job)
            self.jobs[job["question_id"]] = job

    def update(self, question_id, **fields):
        with self.lock:
            job = self.jobs[question_id]
            job.update(fields, updated_at=datetime.now(timezone.utc).isoformat())
            atomic_json(self.directory / f"{question_id}.job.json", job)
            return dict(job)

    def get(self, question_id):
        with self.lock:
            return dict(self.jobs[question_id])

    def list(self, paper_id):
        with self.lock:
            return [dict(j) for j in sorted(self.jobs.values(), key=lambda j: j["created_at"], reverse=True)
                    if j["paper_id"] == paper_id][:10]

    def create(self, paper_id, question, context_question_id=None):
        with self.lock:
            loaded = self.workspace.load(paper_id)
            state = self.workspace.rag_status(paper_id)
            if state["status"] != "ready":
                raise ValueError("Prepare this paper for questions first.")
            context = []
            if context_question_id:
                previous = self.jobs.get(context_question_id)
                if (not previous or previous["paper_id"] != paper_id or previous["status"] != "completed"
                        or not previous.get("result")):
                    raise ValueError("Follow-up context must be a completed answer from this paper.")
                context = [previous]
                ancestor = self.jobs.get(previous.get("context_question_id"))
                if ancestor and ancestor["paper_id"] == paper_id and ancestor["status"] == "completed" and ancestor.get("result"):
                    context.insert(0, ancestor)
            question_id = new_upload_id()
            job = {"question_id": question_id, "paper_id": paper_id, "question": question.strip(),
                   "context_question_id": context_question_id,
                   "status": "queued", "stage": "Waiting for worker", "retry": None, "error": None, "result": None,
                   "created_at": datetime.now(timezone.utc).isoformat()}
            spec = {"pdf": str(loaded.pdf.relative_to(self.workspace.root)),
                    "document": str(loaded.docling.relative_to(self.workspace.root)),
                    "document_sha256": state["document_sha256"], "source_sha256": state["source_sha256"],
                    "index_id": state["index_id"], "question": question.strip(),
                    "document_title": loaded.paper["title"],
                    "history": [{"question":j["question"], "answer":" ".join(c["text"] for c in j["result"]["answer"]["claims"])[:1800]}
                                for j in context],
                    "trace": f"data/question-jobs/{question_id}.trace.json"}
            atomic_json(self.directory / f"{question_id}.input.json", spec)
            self.jobs[question_id] = job
            self.update(question_id)
            # Share the queue with conversion/indexing: no competing local GPU jobs.
            self.futures[question_id] = self.executor.submit(self.run, question_id)
            return dict(job)

    def cancel(self, question_id):
        with self.lock:
            job = self.jobs[question_id]
            if job["status"] not in ACTIVE:
                return dict(job)
            future, process = self.futures.get(question_id), self.processes.get(question_id)
            if future:
                future.cancel()
            self.update(question_id, status="cancelling" if process else "cancelled", stage="Cancelling", retry=None)
        if process:
            terminate_owned_process(process)
        return self.update(question_id, status="cancelled", stage="Cancelled", retry=None)

    def run(self, question_id):
        process = None
        try:
            from pbl_docintel.vector_rag.terminal import TerminalTrace, trace_enabled
            terminal = TerminalTrace([self.workspace.root / ".env", self.workspace.root / "playground/vector-rag/.env",
                                      os.getenv("SANTIO_DB_ENV_FILE")])
            prefix = f"[RAG {question_id[:8]}] "
            with self.lock:
                if self.jobs[question_id]["status"] != "queued":
                    return
                self.update(question_id, status="processing", stage="Finding supporting passages")
                process = subprocess.Popen([sys.executable, "-X", "utf8", "-u", "-m", "pbl_docintel.gui.rag_worker", "ask",
                    "--workspace", str(self.workspace.root), "--input", str(self.directory / f"{question_id}.input.json")],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
                self.processes[question_id] = process
            error = None
            with (self.directory / f"{question_id}.log").open("w", encoding="utf-8") as log:
                for line in process.stdout:
                    line = terminal.redact_text(line)
                    log.write(line); log.flush()
                    if line.startswith("SANTIO_EVENT:"):
                        event = json.loads(line.split(":", 1)[1])
                        if trace_enabled():
                            terminal.write_line(event.get("stage") or event.get("error") or event.get("kind", "event"), prefix)
                        with self.lock:
                            if self.jobs[question_id]["status"] in {"cancelled", "cancelling"}:
                                continue
                            if event.get("kind") == "error":
                                error = event["error"]
                            elif event.get("stage"):
                                self.update(question_id, stage=event["stage"],
                                            **({"retry": event["retry"]} if "retry" in event else {}))
                    elif trace_enabled():
                        terminal.write_line(line, prefix)
            code = process.wait()
            with self.lock:
                if self.jobs[question_id]["status"] in {"cancelled", "cancelling"}:
                    self.update(question_id, status="cancelled", stage="Cancelled", retry=None)
                    return
                if code:
                    raise ValueError(error or "The answer worker failed. Check model and database settings, then retry.")
                report = json.loads((self.directory / f"{question_id}.trace.json").read_text(encoding="utf-8"))
                if report["answer"]["status"] == "error":
                    raise ValueError(report["answer"]["error"])
                result = {"answer": report["answer"], "retrieval_info": {k: report["retrieval"].get(k) for k in ["method","intent","reranking_status","warnings","recovery"]}, "sources": [{k: s[k] for k in
                          ["source_id", "chunk_id", "text", "pages", "source_refs", "headings", "transformations"]}
                          for s in report["sources"]], "elapsed_seconds": report["total_seconds"]}
                self.update(question_id, status="completed", stage="Answer ready", retry=None, result=result)
        except Exception as exc:
            with self.lock:
                if self.jobs[question_id]["status"] not in {"cancelled", "cancelling"}:
                    self.update(question_id, status="failed", stage="Answer failed", retry=None,
                                error=str(exc) if isinstance(exc, ValueError) else "The answer worker failed. Try again.")
        finally:
            with self.lock:
                self.processes.pop(question_id, None)
            if process:
                terminate_owned_process(process)
                process.stdout.close()

    def close(self):
        for question_id in list(self.jobs):
            if self.jobs[question_id]["status"] in ACTIVE:
                self.cancel(question_id)
