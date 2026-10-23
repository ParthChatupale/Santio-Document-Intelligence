"""Private provider bridges, budgets and usage logging; native GraphRAG owns prompts.

NVIDIA is called through its OpenAI-compatible API. Local Granite runs in the
main environment via a persistent private worker. These are registered using
Microsoft's public completion/embedding provider extension points.
"""
import asyncio
import atexit
from collections.abc import Iterator
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
from time import monotonic, sleep

from _common import HERE, EMBEDDING_MODEL, connection, document_python, safe_error, write_json

_RUNTIME = None


def unresolved_failures(calls):
    resolved = {c["request_hash"] for c in calls if c["status"] in {"completed", "cache_hit"}}
    resolved_groups = {c["logical_request_hash"] for c in calls if c["status"] in {"completed", "cache_hit"}
                       and c.get("logical_request_hash")}
    return [c for c in calls if c["status"] in {"failed", "started"} and c["request_hash"] not in resolved
            and (not c.get("logical_request_hash") or c["logical_request_hash"] not in resolved_groups)]


class BudgetExceeded(RuntimeError):
    pass


class Runtime:
    def __init__(self, folder, *, max_calls=20, max_tokens=150000, max_seconds=600):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.model, self.base, self.key = connection()
        self.fallback_model = os.environ.get('SANTIO_GRAPH_FALLBACK_MODEL', 'nvidia/nemotron-3.5-lightning-30b-a3b')
        self.max_calls, self.max_tokens, self.max_seconds = max_calls, max_tokens, max_seconds
        self.started = monotonic()
        prior_path = self.folder / "model_calls.json"
        prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else {}
        self.prior_elapsed = prior.get("elapsed_seconds", 0)
        self.started -= self.prior_elapsed
        self.calls = prior.get("completion_calls", [])
        self.embedding_calls = prior.get("embedding_calls", [])
        self.worker = None
        self.lock = threading.RLock()
        self.request_locks = {}
        self.extraction_feedback = {}
        self.extraction_history = {}
        self.idle = threading.Condition(self.lock)
        self.active_requests = 0
        self.closing = False
        from openai import OpenAI
        self.client = OpenAI(base_url=self.base, api_key=self.key, timeout=90, max_retries=0)
        atexit.register(self.close)

    def save(self):
        with self.lock:
            write_json(self.folder / "model_calls.json", {"completion_calls": self.calls,
                       "embedding_calls": self.embedding_calls, "model": self.model,
                       "models_used": sorted({c.get('model', self.model) for c in self.calls}),
                       "limits": {"calls": self.max_calls, "tokens": self.max_tokens, "seconds": self.max_seconds},
                       "elapsed_seconds": round(monotonic() - self.started, 2)})

    def complete(self, messages, response_format=None, **kwargs):
        # Retry only transient transport/server failures; every attempt is budgeted.
        # Per-request locks deduplicate simultaneous identical native requests.
        key = hashlib.sha256(repr((messages, response_format, kwargs)).encode()).hexdigest()
        with self.lock:
            request_lock = self.request_locks.setdefault(key, threading.Lock())
        with request_lock:
            for attempt in range(3):
                try:
                    return self._complete_once(messages, response_format, **kwargs)
                except BudgetExceeded:
                    raise
                except RuntimeError:
                    with self.lock:
                        failed = next((c for c in reversed(self.calls) if c.get("thread") == threading.get_ident()), {})
                    if (failed.get('finish_reason') == 'length' and failed.get('response_schema') == 'CommunityReportResponse'
                            and attempt < 2 and self.fallback_model
                            and self.fallback_model != failed.get('model', self.model)):
                        kwargs = {**kwargs, '_provider_model_override': self.fallback_model,
                                  '_json_object_transport': False}
                        continue
                    if not failed.get("retryable") or attempt == 2:
                        raise
                    if failed.get("status_code") == 500 and failed.get("response_schema"):
                        # Preserve the full client schema check while avoiding
                        # an upstream constrained-decoder failure. This produces
                        # a distinct, saved API request, never a cache alias.
                        kwargs = {**kwargs, "_json_object_transport": True}
                    if (attempt == 1 and self.fallback_model
                            and self.fallback_model != self.model and failed.get('status_code') != 429):
                        kwargs = {**kwargs, '_provider_model_override': self.fallback_model,
                                  '_json_object_transport': False}
                    sleep(2 ** (attempt + 1))

    def _complete_once(self, messages, response_format=None, **kwargs):
        from graphrag_llm.types import LLMCompletionResponse
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        from _contracts import GraphRecords, source_text, project, SCHEMA_TRANSPORT_MARKER
        extraction_source = source_text(messages)
        if extraction_source is not None:
            response_format = GraphRecords
            # Feed deterministic validation failures into the native additional
            # extraction pass. Rejected candidates are never silently restored.
            if len(messages) > 1 and messages[-1].get("role") == "user":
                prior = next((m.get("content", "") for m in reversed(messages[:-1]) if m.get("role") == "assistant"), "")
                feedback = self.extraction_feedback.get((extraction_source, prior), [])
                if feedback:
                    messages = [dict(m) for m in messages]
                    messages[-1]["content"] += ("\nValidation withheld the following candidates. Correct their endpoint roles/quotations "
                        "only when SOURCE_TEXT supports them; otherwise omit them. Recover missing scientific relationships, "
                        "including initialization and training, using verbatim consecutive quotations.\n" + json.dumps(feedback))
                # Native GraphRAG sees canonical tuples. The JSON-constrained
                # model must see its original JSON response on later turns;
                # otherwise 'continue in the same format' conflicts with its
                # required schema and can fail constrained decoding upstream.
                messages = [dict(m) for m in messages]
                for message in messages:
                    if message.get("role") == "assistant":
                        message["content"] = self.extraction_history.get(
                            (extraction_source, message.get("content", "")), message.get("content", ""))
        schema = response_format.model_json_schema() if response_format else None
        report_request = response_format is not None and response_format.__name__ == 'CommunityReportResponse'
        output_cap = 8192 if extraction_source is not None or report_request else 4096
        options = {"model": self.model, "messages": messages, "temperature": 0,
                   "max_tokens": min(kwargs.get("max_completion_tokens") or kwargs.get("max_tokens") or output_cap, output_cap),
                   "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
        if schema:
            options["response_format"] = {"type": "json_schema", "json_schema": {
                "name": response_format.__name__, "strict": True, "schema": schema}}
        logical_request = {**options, "response_format": schema}
        logical_fingerprint = hashlib.sha256(json.dumps(logical_request, sort_keys=True).encode()).hexdigest()
        if kwargs.get('_provider_model_override'):
            options['model'] = kwargs['_provider_model_override']
        strict_options = dict(options)
        strict_fingerprint = hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()
        if schema:
            legacy_object_options = {**options, "response_format": {"type": "json_object"}}
            legacy_object_fingerprint = hashlib.sha256(json.dumps(legacy_object_options, sort_keys=True).encode()).hexdigest()
            schema_message = {"role": "system", "content": SCHEMA_TRANSPORT_MARKER
                + "Return only a JSON object matching this complete schema. Include every required field, including entity descriptions and relationship evidence.\n"
                + json.dumps(schema)}
            object_options = {**legacy_object_options, "messages": [schema_message] + messages}
            object_fingerprint = hashlib.sha256(json.dumps(object_options, sort_keys=True).encode()).hexdigest()
            has_strict_cache = (self.folder / "response_cache" / (strict_fingerprint + ".json")).exists()
            has_legacy_cache = (self.folder / "response_cache" / (legacy_object_fingerprint + ".json")).exists()
            if not has_strict_cache and has_legacy_cache:
                # Reuse the exact earlier request only if its response passed
                # the same full client schema. Do not create a cache alias.
                options = legacy_object_options
            elif kwargs.get("_json_object_transport") or (not has_strict_cache
                    and (self.folder / "response_cache" / (object_fingerprint + ".json")).exists()):
                options = object_options
            if (self.fallback_model and not kwargs.get('_provider_model_override')
                    and not (self.folder / 'response_cache' / (hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()+'.json')).exists()):
                fallback_options = {**object_options, 'model': self.fallback_model}
                fallback_strict_options = {**strict_options, 'model': self.fallback_model}
                fallback_strict_fingerprint = hashlib.sha256(json.dumps(fallback_strict_options, sort_keys=True).encode()).hexdigest()
                fallback_fingerprint = hashlib.sha256(json.dumps(fallback_options, sort_keys=True).encode()).hexdigest()
                if (self.folder / 'response_cache' / (fallback_strict_fingerprint+'.json')).exists():
                    options = fallback_strict_options
                elif (self.folder / 'response_cache' / (fallback_fingerprint+'.json')).exists():
                    options = fallback_options
        elif self.fallback_model and not kwargs.get('_provider_model_override'):
            primary_fingerprint = hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()
            fallback_options = {**options, 'model': self.fallback_model}
            fallback_fingerprint = hashlib.sha256(json.dumps(fallback_options, sort_keys=True).encode()).hexdigest()
            if (not (self.folder / 'response_cache' / (primary_fingerprint+'.json')).exists()
                    and (self.folder / 'response_cache' / (fallback_fingerprint+'.json')).exists()):
                options = fallback_options
        if report_request and options['max_tokens'] > 4096:
            # Earlier shorter-budget responses are reusable only when already
            # complete and schema-valid. Preserve their actual request body/hash.
            candidates = [options, strict_options, legacy_object_options, object_options]
            if self.fallback_model:
                candidates.extend({**candidate, 'model': self.fallback_model} for candidate in list(candidates))
            for candidate in candidates:
                legacy_budget = {**candidate, 'max_tokens': 4096}
                legacy_key = hashlib.sha256(json.dumps(legacy_budget, sort_keys=True).encode()).hexdigest()
                if (self.folder / 'response_cache' / (legacy_key+'.json')).exists():
                    options = legacy_budget
                    break
        fingerprint = hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()
        cache = self.folder / "response_cache" / (fingerprint + ".json")
        with self.lock:
            cached = cache.exists()
            if cached:
                raw = json.loads(cache.read_text(encoding="utf-8"))
                self.calls.append({"status": "cache_hit", "request_hash": fingerprint,
                                   "model": options['model'],
                                   "logical_request_hash": logical_fingerprint})
            else:
                actual = [c for c in self.calls if c["status"] != "cache_hit"]
                used = sum(c.get("usage", {}).get("total_tokens", c.get("reserved_tokens", 0)) for c in actual)
                # Conservative estimate plus maximum output reservation before starting a call.
                reserve = len(json.dumps(messages)) // 2 + options["max_tokens"]
                if self.closing or len(actual) >= self.max_calls or used + reserve > self.max_tokens or monotonic() - self.started >= self.max_seconds:
                    raise BudgetExceeded("Model-call, token-reservation or time budget reached; run remains partial.")
                import re
                row = {"status": "started", "request_hash": fingerprint, "reserved_tokens": reserve,
                       "model": options['model'],
                       "logical_request_hash": logical_fingerprint,
                       "thread": threading.get_ident(),
                       "source_record_ids": sorted(set(re.findall(r"[a-f0-9]{16}:(?:texts|tables|pictures):\d+", json.dumps(messages)))),
                       "response_schema": response_format.__name__ if response_format else None}
                self.calls.append(row)
                write_json(self.folder / "requests" / (fingerprint + ".json"), options)
                self.save()
                self.active_requests += 1
        if not cached:
            start = monotonic()
            try:
                request_timeout = 180 if response_format and response_format.__name__ == "CommunityReportResponse" else 90
                response = self.client.chat.completions.create(**options,
                    timeout=min(request_timeout, max(1, self.max_seconds - (monotonic() - self.started))))
                with self.lock:
                    row.update(status="returned", seconds=round(monotonic() - start, 2),
                               usage=response.usage.model_dump() if response.usage else {},
                               finish_reason=response.choices[0].finish_reason)
                    raw = response.model_dump(mode="json")
                    write_json(self.folder / "provider_responses" / (fingerprint + ".json"), raw)
                    if response.choices[0].finish_reason != "stop":
                        raise ValueError("Provider response did not finish normally; excluded from accepted output.")
                    if not response.choices[0].message.content:
                        raise ValueError("Provider returned empty answer content.")
                    if response_format:
                        response_format.model_validate_json(response.choices[0].message.content)
                    if extraction_source is not None:
                        records = GraphRecords.model_validate_json(response.choices[0].message.content)
                        canonical, audit = project(records, extraction_source)
                        write_json(self.folder / "validated_extractions" / (fingerprint + ".json"),
                                   {"request_hash": fingerprint, "records": records.model_dump(),
                                    "canonical_tuples": canonical, **audit})
                    write_json(cache, raw)
                    row["status"] = "completed"
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                with self.lock:
                    row.update(status="failed", status_code=status, error=safe_error(exc, self.key), seconds=round(monotonic() - start, 2),
                               retryable=status in {408, 429, 500, 502, 503, 504} or type(exc).__name__ in {"APITimeoutError", "APIConnectionError"})
                    self.save()
                raise RuntimeError(row["error"]) from None
            finally:
                with self.idle:
                    self.active_requests -= 1
                    self.idle.notify_all()
        result = LLMCompletionResponse.model_validate(raw)
        if response_format:
            result.formatted_response = response_format.model_validate_json(result.content)
        if extraction_source is not None:
            model_content = result.content
            canonical, audit = project(GraphRecords.model_validate_json(result.content), extraction_source)
            write_json(self.folder / "validated_extractions" / (fingerprint + ".json"),
                       {"request_hash": fingerprint, "records": result.formatted_response.model_dump(),
                        "canonical_tuples": canonical, **audit})
            result.choices[0].message.content = canonical
            with self.lock:
                self.extraction_feedback[(extraction_source, canonical)] = audit["withheld_records"]
                self.extraction_history[(extraction_source, canonical)] = model_content
        self.save()
        return result

    def embed(self, texts):
        from graphrag_llm.types import LLMEmbeddingResponse
        if isinstance(texts, str):
            texts = [texts]
        with self.lock:
            if self.worker is None or self.worker.poll() is not None:
                env = dict(os.environ)
                for k in ["NVIDIA_API_KEY", "OPENAI_API_KEY", "CUSTOM_LLM_API_KEY"]:
                    env.pop(k, None)
                env.update(PYTHONUTF8="1", HF_HUB_OFFLINE="1")
                self.worker = subprocess.Popen([document_python(), "-u", str(HERE / "_embedding_worker.py")],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
                    text=True, encoding="utf-8", env=env, cwd=str(HERE),
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            start = monotonic()
            self.worker.stdin.write(json.dumps({"texts": texts}) + "\n")
            self.worker.stdin.flush()
            # A reader future bounds initial model load and per-request inference.
            from concurrent.futures import ThreadPoolExecutor, TimeoutError
            pool = ThreadPoolExecutor(max_workers=1)
            future = pool.submit(self.worker.stdout.readline)
            try:
                line = future.result(timeout=180)
            except TimeoutError:
                self.worker.kill()
                self.worker.wait(timeout=10)
                raise RuntimeError("Local embedding worker timed out.") from None
            finally:
                pool.shutdown(wait=False)
            if not line:
                raise RuntimeError("Local embedding worker exited; inspect the terminal's model-loading error.")
            response = json.loads(line)
            if "error" in response:
                raise ValueError(response["error"])
            self.embedding_calls.append({"texts": len(texts), "tokens": response["tokens"], "device": response["device"],
                                         "seconds": round(monotonic() - start, 2), "remote_calls": 0})
            self.save()
            return LLMEmbeddingResponse(model=EMBEDDING_MODEL, object="list", usage={
                "prompt_tokens": response["tokens"], "total_tokens": response["tokens"]}, data=[
                    {"index": i, "object": "embedding", "embedding": vector} for i, vector in enumerate(response["vectors"])])

    def close(self):
        # Native asyncio.gather can stop on one error while other HTTP threads
        # still finish. Drain those requests before closing their shared client.
        with self.idle:
            self.closing = True
            self.idle.wait_for(lambda: self.active_requests == 0, timeout=195)
        if self.worker and self.worker.poll() is None:
            self.worker.stdin.close()
            try:
                self.worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.worker.kill()
                self.worker.wait(timeout=5)
        self.client.close()


def configure(folder, **limits):
    global _RUNTIME
    if _RUNTIME is not None:
        _RUNTIME.close()
    _RUNTIME = Runtime(folder, **limits)
    register()
    return _RUNTIME


def register():
    from graphrag_llm.completion import LLMCompletion, register_completion
    from graphrag_llm.embedding import LLMEmbedding, register_embedding
    from graphrag_llm.types import LLMCompletionChunk

    class NVIDIACompletion(LLMCompletion):
        def __init__(self, *, tokenizer, metrics_store, **kwargs):
            self._tokenizer, self._metrics_store = tokenizer, metrics_store

        @property
        def tokenizer(self): return self._tokenizer

        @property
        def metrics_store(self): return self._metrics_store

        def completion(self, **kwargs):
            stream = kwargs.pop("stream", False)
            response = _RUNTIME.complete(**kwargs)
            if not stream:
                return response
            # Native query APIs consume chunks; remote generation is intentionally
            # non-streaming so finish reason and full response can be validated first.
            chunk = LLMCompletionChunk(id=response.id, created=response.created, model=response.model,
                object="chat.completion.chunk", choices=[{"index": 0, "delta": {"content": response.content}, "finish_reason": "stop"}])
            return iter([chunk])

        async def completion_async(self, **kwargs):
            result = await asyncio.to_thread(self.completion, **kwargs)
            if not kwargs.get("stream"):
                return result
            async def chunks():
                for item in result:
                    yield item
            return chunks()

    class GraniteEmbedding(LLMEmbedding):
        def __init__(self, *, tokenizer, metrics_store, **kwargs):
            self._tokenizer, self._metrics_store = tokenizer, metrics_store

        @property
        def tokenizer(self): return self._tokenizer

        @property
        def metrics_store(self): return self._metrics_store

        def embedding(self, **kwargs):
            if kwargs.get("dimensions") not in {None, 384}:
                raise ValueError("Granite embeddings must use 384 dimensions.")
            return _RUNTIME.embed(kwargs["input"])

        async def embedding_async(self, **kwargs):
            return await asyncio.to_thread(self.embedding, **kwargs)

    register_completion("santio_nvidia", NVIDIACompletion)
    register_embedding("santio_granite", GraniteEmbedding)
