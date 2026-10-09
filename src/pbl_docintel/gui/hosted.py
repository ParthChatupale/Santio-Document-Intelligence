"""Hosted startup factory for a single API process with filesystem storage."""

import logging
import os
from pathlib import Path

from .server import create_app


def create_hosted_app():
    configured_workspace = os.getenv("SANTIO_WORKSPACE")
    workspace = Path(configured_workspace or "storage").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    if not configured_workspace:
        logging.getLogger(__name__).warning(
            "SANTIO_WORKSPACE is unset. Using %s; mount a persistent disk to retain uploads.", workspace)
    # Conversion subprocesses inherit this persistent model cache location.
    os.environ.setdefault("HF_HOME", str(workspace / "model-cache" / "huggingface"))
    os.environ.setdefault("XDG_CACHE_HOME", str(workspace / "model-cache"))
    hosts = ["127.0.0.1", "localhost"]
    render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
    if render_host:
        hosts.append(render_host)
    hosts.extend(value.strip() for value in os.getenv("SANTIO_ALLOWED_HOSTS", "").split(",") if value.strip())
    origins = tuple(value.strip().rstrip("/") for value in
                    os.getenv("SANTIO_ALLOWED_ORIGINS", "").split(",") if value.strip())
    app = create_app(workspace, allowed_hosts=hosts, allowed_origins=origins)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app
