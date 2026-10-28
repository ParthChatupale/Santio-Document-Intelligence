"""Checkpoint 4: query an existing Microsoft GraphRAG index and expose its evidence.

No indexing occurs here. basic = native vector-only search, local = entity/graph
search, global = community-report synthesis. Each invocation saves its context.
"""
import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from _common import read_json, safe_error, stamp, supervise, write_json
from _sources import as_rows, check_citations, load_tables, resolve_context
from _config import load_config


async def ask(run, question, mode="local", *, max_calls=8, max_seconds=300, output=None, profile='native'):
    from graphrag import api
    from _providers import unresolved_failures
    from _query_runtime import configure
    run = Path(run).resolve(strict=True)
    manifest = read_json(run / "run.json")
    if manifest["status"] != "completed":
        raise ValueError("Only a completed native index can be queried; inspect the saved failure report.")
    if not question.strip() or len(question) > 6000:
        raise ValueError("Question must contain 1-6000 characters.")
    output = Path(output or run / "queries" / stamp())
    # Global search maps several report batches before reducing. Its conservative
    # token reservations include failed attempts, so it needs a larger finite cap
    # than a single Local/Basic answer. This does not change the indexed graph.
    runtime = configure(output, max_calls=max_calls,
                        max_tokens=250000 if mode == "global" else 100000,
                        max_seconds=max_seconds)
    before_calls = len(runtime.calls)
    result = {"question": question, "mode": mode, "index_directory": str(run),
              "source_sha256": manifest["source_sha256"], "partial_document_scope": manifest["partial_document_scope"],
              "status": "running", "source_entailment_verified": False}
    start = perf_counter()
    try:
        config = load_config(run)
        from _query_policy import apply_profile
        result.update(apply_profile(config, mode, output, profile))
        tables = load_tables(run)
        levels = tables["communities"]["level"].tolist() if "communities" in tables else []
        level = min(levels) if levels else 0
        common = {"config": config, "query": question, "response_type": "A concise explanation with source citations"}
        if mode == "basic":
            task = api.basic_search(**common, text_units=tables["text_units"])
        elif mode == "local":
            task = api.local_search(**common, entities=tables["entities"], communities=tables["communities"],
                community_reports=tables["community_reports"], text_units=tables["text_units"],
                relationships=tables["relationships"], covariates=None, community_level=level)
        elif mode == "global":
            task = api.global_search(**common, entities=tables["entities"], communities=tables["communities"],
                community_reports=tables["community_reports"], community_level=level, dynamic_community_selection=False)
        else:
            raise ValueError("Choose basic, local or global mode.")
        answer, context = await asyncio.wait_for(task, timeout=max_seconds)
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("Native GraphRAG returned an empty or unexpected answer.")
        if not isinstance(context, dict):
            raise ValueError("Native query context did not provide inspectable record tables.")
        write_json(output / "context.json", {k: as_rows(v) for k, v in context.items()})
        resolved = resolve_context(run, context)
        write_json(output / "source_context.json", resolved)
        checks = check_citations(answer, resolved)
        result.update(status="answered" if checks["all_cited_records_resolved"] else "answer_requires_citation_review",
                      answer=answer, citation_check=checks, context_tables={k: len(as_rows(v)) for k, v in context.items()})
        (output / "answer.md").write_text(answer, encoding="utf-8")
    except Exception as exc:
        result.update(status="failed", error=safe_error(exc, runtime.key))
    finally:
        runtime.close()
        unresolved = unresolved_failures(runtime.calls[before_calls:])
        if unresolved:
            result.update(status="failed", error="One or more native query requests failed; partial answers are not promoted.",
                          unresolved_provider_calls=unresolved)
        result.update(elapsed_seconds=round(perf_counter() - start, 2), output_directory=str(output.resolve()),
                      completion_model=runtime.model,
                      completion_models_used=sorted({c.get('model', runtime.model) for c in runtime.calls[before_calls:]
                                                    if c['status'] in {'completed', 'cache_hit'}}))
        runtime.save()
        write_json(output / "answer.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--question", required=True)
    parser.add_argument("--mode", choices=["basic", "local", "global"], default="local")
    parser.add_argument('--profile', choices=['native', 'source-focused'], default='native')
    parser.add_argument("--max-calls", type=int, default=8)
    parser.add_argument("--max-seconds", type=int, default=300)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.worker:
        output = args.output or args.run / "queries" / stamp()
        code = supervise(Path(__file__), [str(args.run), "--question", args.question, "--mode", args.mode,
            "--output", str(output), "--profile", args.profile, "--max-calls", str(args.max_calls), "--max-seconds", str(args.max_seconds), "--worker"],
            args.max_seconds)
        if code == 124:
            write_json(output / "answer.json", {"question": args.question, "mode": args.mode,
                "status": "failed", "error": "Question time budget exceeded; owned worker terminated.",
                "output_directory": str(output.resolve())})
            print("Question time budget exceeded. See the saved answer report.")
        report = output / "answer.json"
        if report.exists():
            print(json.dumps(read_json(report), indent=2, ensure_ascii=True))
        return code
    result = asyncio.run(ask(args.run, args.question, args.mode, max_calls=args.max_calls,
                            max_seconds=args.max_seconds, output=args.output, profile=args.profile))
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
