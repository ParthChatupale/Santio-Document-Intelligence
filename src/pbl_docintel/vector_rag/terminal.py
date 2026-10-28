"""Readable local RAG diagnostics, with credentials removed before printing."""
import json
import os
from pathlib import Path
import re
import sys


def trace_enabled():
    return os.getenv("SANTIO_RAG_TRACE", "1").casefold() not in {"0", "false", "off", "no"}


class TerminalTrace:
    def __init__(self, env_files=(), *, stream=None):
        from dotenv import dotenv_values
        values = {}
        for path in env_files:
            if path and Path(path).is_file():
                values.update(dotenv_values(path))
        values.update(os.environ)
        self.secrets = sorted({str(value) for key, value in values.items() if value and
            (key.upper().endswith(("API_KEY", "PASSWORD", "ACCESS_TOKEN", "SECRET"))
             or key.upper() in {"PGPASSWORD", "DATABASE_URL"})}, key=len, reverse=True)
        self.stream = stream

    def redact_text(self, text):
        for secret in self.secrets:
            text = text.replace(secret, "[REDACTED]")
        # Do not let captured library output clear/rewrite terminal history.
        return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)

    def _safe_data(self, value):
        if isinstance(value, dict):
            hidden = {"api_key", "authorization", "password", "pgpassword", "access_token", "secret"}
            return {key: "[REDACTED]" if str(key).casefold() in hidden else self._safe_data(item)
                    for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._safe_data(item) for item in value]
        if isinstance(value, str):
            return self.redact_text(value)
        return value

    def write_line(self, line, prefix=""):
        stream = self.stream or sys.stderr
        text = prefix + self.redact_text(line.rstrip("\r\n")).replace("\r", "\\r")
        try:
            print(text, file=stream, flush=True)
        except UnicodeEncodeError:
            try:
                print(text.encode(stream.encoding or "ascii", errors="backslashreplace").decode(stream.encoding or "ascii"),
                      file=stream, flush=True)
            except (OSError, ValueError):
                pass
        except (OSError, ValueError):
            pass  # A closed terminal must not fail a question.

    def __call__(self, stage, data):
        if not trace_enabled():
            return
        self.write_line("\n=== RAG / " + stage + " ===")
        for line in json.dumps(self._safe_data(data), ensure_ascii=False, indent=2, default=str).splitlines():
            self.write_line(line)
