"""HTTP model adapters configured explicitly by the local application user."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


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
    def from_env(cls):
        provider = os.getenv("PBL_MODEL_PROVIDER", "nvidia")
        url = "https://integrate.api.nvidia.com/v1" if provider == "nvidia" else "http://127.0.0.1:11434"
        return cls(provider, os.getenv("PBL_MODEL_URL", url),
                   os.getenv("PBL_MODEL_NAME", ""), os.getenv("PBL_MODEL_API_KEY", os.getenv("NVIDIA_API_KEY", "")))

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
                    "max_tokens": 4096}
            if self.provider == "compatible":
                body["response_format"] = {"type": "json_object"}
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
            return json.loads(content)
        except HTTPError as error:
            # Do not echo provider response bodies: they can contain credentials
            # or document content. The original source stays on disk.
            raise ValueError(f"Model endpoint returned HTTP {error.code}. Check the endpoint, model, key and JSON-output support.") from None
        except (URLError, TimeoutError) as error:
            raise ValueError("Cannot reach the configured model endpoint, or the model request timed out.") from None
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            raise ValueError("Model returned an unexpected response or invalid JSON.") from None
