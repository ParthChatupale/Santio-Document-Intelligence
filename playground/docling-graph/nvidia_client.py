"""NVIDIA request settings on top of Docling Graph's existing LiteLLM client.

This adapter does not extract documents, build prompts, parse records, or build
graphs. It sets the Nemotron reasoning flag and records request timing/usage.
Pinned to the Docling Graph 1.9.1 client interface.
"""

from threading import Lock
from time import perf_counter
import hashlib
import json
from pathlib import Path

from docling_graph.llm_clients.litellm import LiteLLMClient


class NvidiaClient(LiteLLMClient):
    def __init__(self, model_config, *, thinking=False, cache_dir=None, sdk_retries=None, max_calls=None):
        super().__init__(model_config=model_config)
        self.thinking = thinking
        self.calls = []
        self._call_lock = Lock()
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.sdk_retries=sdk_retries
        self.max_calls=max_calls
        self.budget_exhausted=False
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _build_request(self, *args, **kwargs):
        request = super()._build_request(*args, **kwargs)
        if "nemotron-3" in self.model.lower():
            request["extra_body"] = {"chat_template_kwargs": {"enable_thinking": self.thinking}}
        if self.sdk_retries is not None:
            request['max_retries']=self.sdk_retries
        return request

    def _call_api(self, messages, **params):
        cache = None
        if self.cache_dir:
            request = self._build_request(messages, **params)
            public = {k:request[k] for k in ("model","messages","temperature","top_p","max_tokens","response_format","extra_body") if k in request}
            digest = hashlib.sha256(json.dumps(public,sort_keys=True,default=str).encode()).hexdigest()
            cache = self.cache_dir / f"{digest}.json"
            if cache.is_file():
                saved = json.loads(cache.read_text(encoding="utf-8"))
                self.calls.append({"request":len(self.calls)+1,"status":"cached","elapsed_seconds":0,"model":saved["metadata"].get("model"),"finish_reason":saved["metadata"].get("finish_reason"),"cache_key":digest})
                print(f"NVIDIA request {len(self.calls)}: cache hit; no API request",flush=True)
                return saved["content"],saved["metadata"]
        with self._call_lock:
            if self.max_calls is not None and sum(c['status']!='cached' for c in self.calls)>=self.max_calls:
                self.budget_exhausted=True
                raise RuntimeError('The sandbox API call budget is exhausted; partial results are preserved.')
            record = {"request": len(self.calls) + 1, "status": "running"}
            record['max_output_tokens']=self.max_tokens
            self.calls.append(record)
        print(f"NVIDIA request {record['request']}: extracting structured information...", flush=True)
        started = perf_counter()
        try:
            content, metadata = super()._call_api(messages, **params)
            usage = metadata.get("usage") or {}
            if hasattr(usage, "model_dump"):
                usage = usage.model_dump()
            record.update(status="complete", elapsed_seconds=round(perf_counter() - started, 2), usage=usage)
            record.update(model=metadata.get("model"),finish_reason=metadata.get("finish_reason"))
            if cache and metadata.get("finish_reason") != "length":
                cache.write_text(json.dumps({"content":content,"metadata":{**metadata,"usage":usage}},ensure_ascii=False,default=str),encoding="utf-8")
            print(f"NVIDIA request {record['request']}: complete ({record['elapsed_seconds']} seconds)", flush=True)
            return content, metadata
        except Exception as error:
            record.update(status="failed", elapsed_seconds=round(perf_counter() - started, 2), error_type=type(error).__name__)
            print(f"NVIDIA request {record['request']}: failed ({type(error).__name__})", flush=True)
            raise
