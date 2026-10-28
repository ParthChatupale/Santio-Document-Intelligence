"""Small shared file/config helpers. No graph extraction or retrieval logic."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from time import sleep

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("SANTIO_WORKSPACE", str(HERE.parents[3]))).resolve()
EMBEDDING_MODEL = "ibm-granite/granite-embedding-small-english-r2"
EMBEDDING_REVISION = "2ab6fa8ea2d674564defd37171ae19079b864b33"
EMBEDDING_DIMENSIONS = 384


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        # Windows readers briefly deny replacement of an open file. Keep writes
        # atomic while tolerating that sharing window; never fall back to truncation.
        for attempt in range(40):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 39:
                    raise
                sleep(.025)
    finally:
        temporary.unlink(missing_ok=True)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relationship_key(row):
    return hashlib.sha256(json.dumps([row["source"], row["target"], row.get("description", "")],
                         ensure_ascii=False).encode("utf-8")).hexdigest()


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def connection():
    from dotenv import dotenv_values
    values = {**dotenv_values(ROOT / ".env"), **dotenv_values(HERE / ".env"), **os.environ}
    key = values.get("NVIDIA_API_KEY", "")
    if not key:
        raise ValueError("NVIDIA_API_KEY is missing from the project or sandbox .env.")
    model = (values.get("NVIDIA_MODEL") or values.get("PBL_MODEL_NAME")
             or "nvidia/nemotron-3.5-super-vl-120b-a12b").removeprefix("openai/")
    base = values.get("NVIDIA_BASE_URL") or "https://integrate.api.nvidia.com/v1"
    # GraphRAG substitutes this value at runtime. Never save the expanded config.
    os.environ["NVIDIA_API_KEY"] = key
    return model, base, key


def document_python():
    return os.environ.get("SANTIO_DOCUMENT_PYTHON") or str(ROOT / ".venv/Scripts/python.exe")


def safe_error(error, secret=""):
    message = str(error) or type(error).__name__
    if secret:
        message = message.replace(secret, "[REDACTED]")
    return re.sub(r"nvapi-[A-Za-z0-9_-]+", "[REDACTED]", message)


def select_records(prepared, headings=None):
    records = read_json(Path(prepared) / "input/documents.json")
    if headings:
        wanted = {h.strip().casefold() for h in headings}
        records = [r for r in records if wanted.intersection(h.casefold() for h in r["headings"])]
        found = {h.casefold() for r in records for h in r["headings"]}
        if not wanted.issubset(found):
            raise ValueError("A requested heading was not found. Inspect headings.json for exact names.")
    if not records:
        raise ValueError("No eligible input records selected.")
    return records


def supervise(script, arguments, timeout, stderr=None):
    """Bound an owned worker process, including its private embedding child."""
    kwargs = {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
              | getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {"start_new_session": True}
    child = subprocess.Popen([sys.executable, str(script), *arguments],
                             stdout=subprocess.DEVNULL, stderr=stderr or sys.stderr, **kwargs)
    try:
        return child.wait(timeout=max(0.1, timeout))
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                           capture_output=True, timeout=15, check=False)
        else:
            import signal
            os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=15)
        return 124
