"""HTTP model adapters configured explicitly by the local application user."""

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_NVIDIA_MODEL = "nvidia/nemotron-3-super-120b-a12b"
CONFIG_NAMES = ("PBL_MODEL_PROVIDER", "PBL_MODEL_URL", "PBL_MODEL_NAME", "PBL_MODEL_API_KEY", "NVIDIA_API_KEY")


def model_configuration(workspace=None):
    """Load owner configuration as data; never execute or interpolate .env."""
    values = {}
    path = Path(workspace) / ".env" if workspace is not None else None
    if path is not None and path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, separator, value = line.partition("=")
            name, value = name.strip(), value.strip()
            if name not in CONFIG_NAMES:
                continue
            if not separator:
                raise ValueError("Invalid model configuration in .env; use NAME=value")
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            values[name] = value
    values.update({name: os.environ[name] for name in CONFIG_NAMES if name in os.environ})
    return values


class HTTPJSONModel:
    def __init__(self, provider="ollama", url="http://127.0.0.1:11434", model="", key=""):
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Use a plain HTTP(S) model endpoint without credentials or query parameters")
        if provider not in {"ollama", "compatible", "nvidia"}:
            raise ValueError("Unknown model provider")
        if provider == "nvidia" and url.rstrip("/") != "https://integrate.api.nvidia.com/v1":
            raise ValueError("The NVIDIA preset uses https://integrate.api.nvidia.com/v1")
        if provider == "ollama" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("The Ollama option uses a local endpoint. Choose a hosted compatible API for a remote service.")
        if provider in {"compatible", "nvidia"} and parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Remote model services must use HTTPS")
        self.provider, self.url, self.name, self.key = provider, url.rstrip("/"), model.strip(), key

    @classmethod
    def from_env(cls, workspace=None):
        config = model_configuration(workspace)
        provider = config.get("PBL_MODEL_PROVIDER", "nvidia")
        url = "https://integrate.api.nvidia.com/v1" if provider == "nvidia" else "http://127.0.0.1:11434"
        return cls(provider, config.get("PBL_MODEL_URL", url),
                   config.get("PBL_MODEL_NAME", DEFAULT_NVIDIA_MODEL if provider == "nvidia" else ""),
                   config.get("PBL_MODEL_API_KEY", config.get("NVIDIA_API_KEY", "")))

    @property
    def analysis_batch_chars(self):
        # Conservative request size for the default long-context model. Other
        # providers retain the smaller bound because their context varies.
        return 96000 if self.provider == "nvidia" and self.name == DEFAULT_NVIDIA_MODEL else 24000

    def public(self):
        return {"provider": self.provider, "url": self.url, "model": self.name,
                "configured": bool(self.name) and (bool(self.key) if self.provider == "nvidia" else True), "key_present": bool(self.key),
                "remote": urlparse(self.url).hostname not in {"localhost", "127.0.0.1", "::1"}}

    def generate(self, system, payload, schema):
        if not self.name:
            raise ValueError("Connect a model before generating paper understanding")
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": json.dumps({**payload, "output_schema": schema}, ensure_ascii=False)}]
        if self.provider == "ollama":
            endpoint = self.url + "/api/chat"
            body = {"model": self.name, "messages": messages, "stream": False,
                    "format": schema, "options": {"temperature": 0, "num_ctx": 32768}}
        else:
            endpoint = self.url + "/chat/completions"
            body = {"model": self.name, "messages": messages,
                    "max_tokens": 4096, "stream": False}
            if self.provider == "compatible":
                body["response_format"] = {"type": "json_object"}
            if self.provider == "nvidia" and self.name == DEFAULT_NVIDIA_MODEL:
                body.update(max_tokens=8192, temperature=1.0, top_p=0.95,
                            reasoning_effort="none")
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        try:
            with urlopen(Request(endpoint, json.dumps(body).encode(), headers), timeout=180) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError("Model response exceeds the configured size limit")
            data = json.loads(raw)
            content = data["message"]["content"] if self.provider == "ollama" else data["choices"][0]["message"]["content"]
            content = content.strip()
            # Accept a complete Markdown JSON wrapper, not partial output or
            # arbitrary prose around a guessed JSON substring.
            if content.startswith(("```json\n", "```\n")) and content.endswith("\n```"):
                content = content.split("\n", 1)[1][:-4]
            return json.loads(content)
        except HTTPError as error:
            # Do not echo provider response bodies: they can contain credentials
            # or document content. The original source stays on disk.
            raise ValueError(f"Model endpoint returned HTTP {error.code}. Check the endpoint, model, key and JSON-output support.") from None
        except (URLError, TimeoutError) as error:
            raise ValueError("Cannot reach the configured model endpoint, or the model request timed out.") from None
        except (KeyError, IndexError, TypeError, AttributeError, json.JSONDecodeError):
            raise ValueError("Model returned an unexpected response or invalid JSON.") from None
