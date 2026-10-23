"""Isolated runner around Docling Graph's existing pipeline and viewer."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path
import re
import sys
from time import perf_counter


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def inspect_source(source):
    """Check the saved representation, without a PDF converter or model call."""
    source = source.resolve(strict=True)
    raw = source.read_bytes()
    document = json.loads(raw.decode("utf-8-sig"))
    if document.get("schema_name") != "DoclingDocument":
        raise ValueError("Select the full DoclingDocument JSON, not a summary, layout, or exported graph JSON.")
    texts = document.get("texts", [])
    headings = [item for item in texts if item.get("label") == "section_header"]
    if not any(item.get("text", "").strip() for item in texts):
        raise ValueError("The document contains no extracted text.")
    return {
        "source": str(source),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "document_name": document.get("name"),
        "pages": len(document.get("pages", {})),
        "text_items": len(texts),
        "tables": len(document.get("tables", [])),
        "pictures": len(document.get("pictures", [])),
        "headings": len(headings),
        "heading_levels": dict(Counter(str(item.get("level", "unknown")) for item in headings)),
        "heading_examples": [{key: item.get(key) for key in ("self_ref", "text", "level")} for item in headings[:12]],
        "pdf_conversion": "skipped: use existing DoclingDocument JSON",
    }


def load_connection(model_override=None):
    """Read credentials into this process, never into output files."""
    from dotenv import dotenv_values

    values = {**dotenv_values(ROOT / ".env"), **dotenv_values(HERE / ".env"), **os.environ}
    key = values.get("NVIDIA_API_KEY", "")
    if not key:
        raise ValueError("NVIDIA_API_KEY is missing. Set it in the project .env, sandbox .env, or environment.")
    model = model_override or values.get("NVIDIA_MODEL") or values.get("PBL_MODEL_NAME") or "nvidia/nemotron-3-super-120b-a12b"
    model = model.removeprefix("openai/")
    base_url = values.get("NVIDIA_BASE_URL") or "https://integrate.api.nvidia.com/v1"
    # Docling Graph/LiteLLM reads the credential from the provider environment.
    # Do not place the key in PipelineConfig, whose effective settings are exported.
    os.environ["OPENAI_API_KEY"] = key
    os.environ["CUSTOM_LLM_API_KEY"] = key
    return model, base_url, key


def run(args):
    info = inspect_source(args.source)
    model, base_url, secret = load_connection(args.model)
    print(f"Source validated: {info['document_name']} ({info['pages']} pages, {info['headings']} headings)", flush=True)
    print("Loading Docling Graph. Existing PDF extraction will be reused.", flush=True)
    # Imports occur after setup so inspection stays quick and offline.
    import networkx as nx
    from docling_graph import PipelineConfig, run_pipeline
    from docling_graph.llm_clients.config import resolve_effective_model_config
    from nvidia_client import NvidiaClient
    from research_schema import ResearchPaper

    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", args.source.stem)[:70]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = HERE / "outputs" / f"{slug}-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    settings = {
        "source": str(args.source.resolve()),
        "template": ResearchPaper,
        "backend": "llm",
        "inference": "remote",
        "provider_override": "openai",
        "model_override": f"openai/{model}",
        "llm_overrides": {
            "connection": {"base_url": base_url},
            "generation": {"temperature": 0.0, "max_tokens": args.max_output_tokens},
            "reliability": {"timeout_s": args.timeout, "max_retries": 1},
            "context_limit": args.context_tokens,
            "max_output_tokens": args.max_output_tokens,
        },
        "processing_mode": "many-to-one",
        "extraction_contract": args.contract,
        "use_chunking": True,
        "chunk_max_tokens": args.chunk_tokens,
        "dense_skeleton_batch_tokens": args.batch_tokens,
        "llm_input_format": args.input_format,
        "parallel_workers": 1,
        "structured_output": not args.prompt_json,
        "provenance": "detailed",
        "dump_to_disk": True,
        "output_dir": str(run_dir / "artifacts"),
        "export_docling": False,
        "debug": False,
    }
    public_settings = {**settings, "template": "research_schema.ResearchPaper"}
    client = NvidiaClient(
        resolve_effective_model_config("openai", f"openai/{model}", overrides=settings["llm_overrides"]),
        thinking=args.thinking,
    )
    settings["llm_client"] = client
    manifest = {
        "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
        "input": info, "configuration": public_settings,
        "python_executable": sys.executable,
        "provider_settings": {"nemotron_thinking": args.thinking},
        "versions": {p: version(p) for p in ("docling-graph", "docling", "docling-core", "litellm", "pydantic")},
        "limitations": [
            "Model-generated graph; not independently verified ground truth.",
            "Schema validity and entity-name location matches do not establish relationship correctness.",
            "Detected figures and formula regions are not automatically interpreted.",
        ],
    }
    write_json(run_dir / "run.json", manifest)
    write_json(run_dir / "schema.json", ResearchPaper.model_json_schema())
    print("PDF conversion skipped. Docling Graph will prepare content and call NVIDIA.", flush=True)
    print(f"Run folder: {run_dir}", flush=True)
    started = perf_counter()
    try:
        context = run_pipeline(PipelineConfig(**settings), mode="api")
        graph = context.knowledge_graph
        if graph is None or graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
            raise RuntimeError("Docling Graph returned no connected knowledge graph. Inspect the library output before retrying.")
        records = [record.model_dump(mode="json") for record in context.extracted_models or []]
        write_json(run_dir / "extracted_records.json", records)
        graph_data = {
            "nodes": [{"id": node_id, **data} for node_id, data in graph.nodes(data=True)],
            "edges": [{"source": a, "target": b, **data} for a, b, data in graph.edges(data=True)],
        }
        write_json(run_dir / "graph.json", graph_data)
        if context.provenance is not None:
            write_json(run_dir / "provenance.json", context.provenance.model_dump(mode="json"))
        from viewer import render_viewer
        html_files = [render_viewer(graph_data, run_dir / "graph.html")]
        manifest.update(
            status="complete", elapsed_seconds=round(perf_counter() - started, 2),
            nodes=graph.number_of_nodes(), edges=graph.number_of_edges(),
            node_types=dict(Counter(str(d.get("label", d.get("type", "unknown"))) for _, d in graph.nodes(data=True))),
            edge_types=dict(Counter(str(d.get("label", d.get("type", "unknown"))) for _, _, d in graph.edges(data=True))),
            connected_components=nx.number_weakly_connected_components(graph),
            viewer=str(html_files[0]) if html_files else None,
            input_unchanged=hashlib.sha256(args.source.read_bytes()).hexdigest() == info["source_sha256"],
        )
        if not html_files:
            raise RuntimeError("The graph was extracted, but Docling Graph did not export its HTML viewer.")
        write_json(run_dir / "run.json", manifest)
        write_json(run_dir / "model_calls.json", client.calls)
        (HERE / "outputs" / "latest.json").write_text(json.dumps({"run_dir": str(run_dir), "viewer": str(html_files[0])}, indent=2), encoding="utf-8")
        print(f"Complete: {manifest['nodes']} nodes, {manifest['edges']} edges", flush=True)
        print(f"Viewer: {html_files[0]}", flush=True)
        print(f"Records: {run_dir / 'extracted_records.json'}", flush=True)
        return 0
    except (Exception, KeyboardInterrupt) as error:
        # Never write a provider error verbatim: it can contain request details.
        interrupted = isinstance(error, KeyboardInterrupt)
        manifest.update(status="interrupted" if interrupted else "failed", elapsed_seconds=round(perf_counter() - started, 2), error_type=type(error).__name__)
        write_json(run_dir / "run.json", manifest)
        write_json(run_dir / "model_calls.json", client.calls)
        message = str(error).replace(secret, "[REDACTED]")
        print(f"Run failed ({type(error).__name__}): {message[:1200]}", file=sys.stderr)
        print(f"Run metadata saved in {run_dir / 'run.json'}", file=sys.stderr)
        return 130 if interrupted else 1


def view(args):
    import webbrowser

    if args.run:
        files = list(args.run.resolve().rglob("graph.html"))
        if not files:
            raise ValueError("No graph.html found in the selected run folder.")
        target = files[0]
    else:
        target = Path(json.loads((HERE / "outputs" / "latest.json").read_text(encoding="utf-8"))["viewer"])
    if not target.is_file():
        raise ValueError("The graph viewer is missing. Generate a successful run first.")
    print(target)
    webbrowser.open(target.as_uri())
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Inspect saved Docling JSON without any model calls")
    inspect.add_argument("--source", required=True, type=Path)
    execute = commands.add_parser("run", help="Generate a graph using Docling Graph and NVIDIA")
    execute.add_argument("--source", required=True, type=Path)
    execute.add_argument("--model", help="Override the model in the .env configuration")
    execute.add_argument("--contract", choices=["auto", "direct", "dense"], default="direct")
    execute.add_argument("--input-format", choices=["doclang", "doclang-geo", "markdown"], default="markdown")
    execute.add_argument("--chunk-tokens", type=int, default=2048)
    execute.add_argument("--batch-tokens", type=int, default=8192, help="Token budget per dense discovery batch")
    execute.add_argument("--max-output-tokens", type=int, default=16384)
    execute.add_argument("--context-tokens", type=int, default=131072)
    execute.add_argument("--timeout", type=int, default=180)
    execute.add_argument("--prompt-json", action="store_true", help="Use prompt-based JSON instead of endpoint JSON-schema enforcement")
    execute.add_argument("--thinking", action="store_true", help="Enable Nemotron reasoning; default off for predictable extraction latency")
    viewer = commands.add_parser("view", help="Open Docling Graph's native HTML viewer")
    viewer.add_argument("--run", type=Path, help="Run directory; defaults to the latest successful run")
    args = parser.parse_args()
    if args.command == "run" and min(args.chunk_tokens, args.batch_tokens, args.max_output_tokens, args.context_tokens, args.timeout) <= 0:
        parser.error("Token budgets and timeout must be positive.")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.command == "inspect":
            print(json.dumps(inspect_source(args.source), indent=2, ensure_ascii=False))
            return 0
        return run(args) if args.command == "run" else view(args)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
