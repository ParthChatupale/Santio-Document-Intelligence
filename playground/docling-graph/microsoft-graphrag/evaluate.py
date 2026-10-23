"""Checkpoint 5: auditable native-output checks and bounded paired question runs.

Default: offline graph/reference review only. --live explicitly generates answers
in native basic/local modes for the supplied question fixture. No accuracy is
inferred from entity counts, citation existence or word matches alone.
"""
import argparse
import asyncio
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import re

from _common import digest, read_json, stamp, write_json
from _sources import as_rows, load_tables, source_ledger


def audit(run, reference=None):
    run = Path(run)
    tables = load_tables(run)
    manifest = read_json(run / "run.json")
    source_map, ledger = source_ledger(run, tables)
    scoped_refs = {r for s in source_map.values() for r in s["item_refs"]}
    entities = as_rows(tables.get("entities", []))
    relationships = as_rows(tables.get("relationships", []))
    names = {str(e.get("title", "")).casefold() for e in entities}
    invalid = [r.get("id") for r in relationships if str(r["source"]).casefold() not in names or str(r["target"]).casefold() not in names]
    unresolved = [r.get("id") for r in relationships if not ledger.get(("relationships", str(r["id"])))]
    aliases = {}
    for entity in entities:
        key = re.sub(r"[^a-z0-9]", "", str(entity.get("title", "")).casefold())
        aliases.setdefault(key, []).append(entity.get("title"))
    result = {"status": "offline_audit", "native_tables": {k: len(v) for k, v in tables.items()},
              "entity_types": dict(Counter(e.get("type") for e in entities)),
              "dangling_relationships": invalid, "relationships_without_source_mapping": unresolved,
              "possible_alias_collisions": [values for values in aliases.values() if len(values) > 1],
              "relationship_precision": "not_scored_without_source_entailment_review",
              "relationship_recall": "not_scored_without_adjudicated_reference_matching"}
    if reference:
        ref = read_json(reference)
        if ref["source_sha256"] != manifest["source_sha256"]:
            raise ValueError("Reference belongs to a different source snapshot.")
        checks = []
        for fact in ref.get("relationships", []):
            candidates = []
            for relation in relationships:
                endpoints = {str(relation["source"]).casefold(), str(relation["target"]).casefold()}
                if {fact["subject"].casefold(), fact["object"].casefold()}.issubset(endpoints):
                    records = ledger.get(("relationships", str(relation["id"])), set())
                    candidates.append({"native_record": relation,
                        "docling_refs": sorted({r for i in records for r in source_map[i]["item_refs"]}),
                        "verdict": "requires_semantic_review"})
            in_scope = bool(scoped_refs.intersection(fact.get("refs", [])))
            checks.append({**fact, "in_selected_source_scope": in_scope,
                           "candidates": candidates if in_scope else [],
                           "endpoint_pair_present": bool(candidates) if in_scope else None,
                           "note": "Matching endpoints alone does not validate predicate, ownership or direction."})
        result.update(reference_checks=checks, reference_sha256=digest(reference))
    return result


def review_sample(run, size=24, seed=42):
    """Freeze a reproducible edge sample with actual passages for semantic review."""
    import random
    run = Path(run)
    tables = load_tables(run)
    sources, ledger = source_ledger(run, tables)
    text = {r["id"]: r["text"] for r in read_json(run / "input/documents.json")}
    # Native UUIDs can change on a cached rebuild; sample stable relationship text.
    edges = sorted(as_rows(tables.get("relationships", [])), key=lambda r: (r["source"], r["target"], r.get("description", "")))
    chosen = random.Random(seed).sample(edges, min(size, len(edges)))
    return {"seed": seed, "sampling": "uniform native relationship records; not stratified by scientific importance",
            "verdicts": "pending source-backed semantic review", "total_relationships": len(edges),
            "sample": [{"relationship": edge, "sources": [{"record_id": ident, "pages": sources[ident]["pages"],
                "refs": sources[ident]["item_refs"], "text": text.get(ident, "")}
                for ident in sorted(ledger.get(("relationships", str(edge["id"])), set()))]} for edge in chosen]}


async def evaluate_questions(run, fixture, output, modes, case_ids=None, *, max_calls=4, max_seconds=180, concurrency=1, profile='native'):
    source_hash = read_json(Path(run) / "run.json")["source_sha256"]
    reference = read_json(fixture)
    if reference["source_sha256"] != source_hash:
        raise ValueError("Question fixture belongs to another source snapshot.")
    cases = reference["questions"]
    if case_ids:
        if not set(case_ids).issubset({c["id"] for c in cases}):
            raise ValueError("Unknown evaluation case ID.")
        cases = [c for c in cases if c["id"] in case_ids]
    rows = []
    semaphore = asyncio.Semaphore(concurrency)
    scoped_refs = {r for s in read_json(Path(run) / "source_map.json").values() for r in s["item_refs"]}
    async def one(case, mode):
        async with semaphore:
            if any(not set(g).intersection(scoped_refs) for g in case.get("required_evidence_groups", [])):
                rows.append({"case_id": case["id"], "mode": mode, "status": "outside_selected_source_scope",
                             "note": "Required evidence was not included in this partial-document experiment; no model call made."})
                write_json(Path(output) / "questions.json", rows)
                return
            target = Path(output) / case["id"] / mode
            target.mkdir(parents=True, exist_ok=True)
            with (target / "worker.log").open("w", encoding="utf-8") as log:
                await asyncio.to_thread(subprocess.run, [sys.executable, str(Path(__file__).with_name("query_graph.py")),
                    str(run), "--question", case["question"], "--mode", mode,
                    "--max-calls", str(max_calls), "--max-seconds", str(max_seconds), "--profile", profile, "--output", str(target)],
                    check=False, stdout=log, stderr=subprocess.STDOUT)
            result = read_json(target / "answer.json") if (target / "answer.json").exists() else {
                "status": "failed", "error": "Question worker exited before saving an answer.",
                "output_directory": str(target.resolve())}
            source_path = Path(result["output_directory"]) / "source_context.json"
            refs = set()
            if source_path.exists():
                refs = {ref for records in read_json(source_path).values() for row in records for ref in row["docling_refs"]}
            groups = case.get("required_evidence_groups", [])
            resolved_context = read_json(source_path) if source_path.exists() else {}
            direct_refs = {ref for row in resolved_context.get('sources', []) for ref in row['docling_refs']}
            rows.append({"case_id": case["id"], "mode": mode, "category": case["category"],
                "status": result["status"], "answer": result.get("answer"), "error": result.get("error"),
                "query_profile": profile,
                "all_evidence_groups_retrieved": all(set(g) & refs for g in groups) if groups else None,
                "all_evidence_groups_in_direct_sources": all(set(g) & direct_refs for g in groups) if groups else None,
                "coverage_note": "Legacy retrieved flag includes graph provenance; direct-sources flag checks selected passages. Neither establishes answer entailment.",
                "retrieved_refs": sorted(refs), "elapsed_seconds": result.get("elapsed_seconds"),
                "answer_quality": "requires_source_backed_review", "output_directory": result["output_directory"]})
            write_json(Path(output) / "questions.json", rows)
            print(f"Question check: {case['id']} / {mode} / {result['status']}", flush=True)
    await asyncio.gather(*(one(case, mode) for case in cases for mode in modes))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--questions", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--mode", choices=["basic", "local", "global"], action="append")
    parser.add_argument("--case", action="append", help="Restrict live testing to named cases")
    parser.add_argument("--sample-size", type=int, default=24, help="Reproducible source-backed edge review sample")
    parser.add_argument("--question-max-calls", type=int, default=4)
    parser.add_argument("--question-max-seconds", type=int, default=180)
    parser.add_argument("--concurrency", type=int, choices=[1, 2], default=1)
    parser.add_argument('--profile', choices=['native', 'source-focused'], default='native')
    args = parser.parse_args()
    output = args.run / "evaluations" / stamp()
    result = audit(args.run, args.reference)
    write_json(output / "graph_audit.json", result)
    write_json(output / "relationship_review_sample.json", review_sample(args.run, max(0, min(args.sample_size, 200))))
    if args.live:
        if not args.questions:
            parser.error("--live requires --questions pointing to a source-matched fixture")
        rows = asyncio.run(evaluate_questions(args.run, args.questions, output, args.mode or ["basic", "local"], args.case,
            max_calls=args.question_max_calls, max_seconds=args.question_max_seconds, concurrency=args.concurrency, profile=args.profile))
        result["query_tests"] = len(rows)
    print(json.dumps({"output_directory": str(output.resolve()), **result}, indent=2))
    return 1 if result["dangling_relationships"] or result["relationships_without_source_mapping"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
