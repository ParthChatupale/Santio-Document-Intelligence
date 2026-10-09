"""Build an evidence index and check optional result annotations."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from .evidence import build_index
from .schema import EvidenceIndex, ResultCollection
from .validation import check_collection
from .rag import rag_chunks, write_rag_jsonl


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def export_results(collection, checks, index, output_dir):
    write_json(output_dir / "results.json", collection.model_dump(mode="json"))
    write_json(output_dir / "checks.json", {"document_id": collection.document_id, "checks": checks})
    rows = []
    for record, check in zip(collection.records, checks, strict=True):
        evidence = index.units[record.value_evidence.evidence_id] if record.value_evidence.evidence_id in index.units else None
        rows.append({
            "result_id": record.result_id, "method": record.method.reported,
            "dataset": record.benchmark.dataset.reported, "metric": record.metric.name.reported,
            "raw_value": record.value.raw, "numeric_value": record.value.numeric,
            "direction": record.metric.direction, "reported_scale": record.metric.reported_scale,
            "pages": ",".join(str(p) for p in sorted({l.page_no for l in evidence.locations})) if evidence else "",
            "evidence_id": record.value_evidence.evidence_id, "check_outcome": check["outcome"],
            "review_status": record.review.status,
            "issues": ";".join([*check["errors"], *check["warnings"]]),
        })
    fields = list(rows[0]) if rows else ["result_id"]
    with (output_dir / "results.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    def md(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["# Annotated result evidence", "",
             "These are curated sample annotations, not automatically extracted results.",
             "Checks establish limited source attribution, not scientific correctness or fair comparability.",
             "Review status is preserved; machine checks never grant human approval.", "",
             "| Method | Dataset | Metric | Source value | Page | Check | Review |",
             "|---|---|---|---|---|---|---|"]
    for row in rows:
        lines.append("| " + " | ".join(md(row[k]) for k in
                     ("method", "dataset", "metric", "raw_value", "pages", "check_outcome", "review_status")) + " |")
    lines += ["", "## Evidence details", ""]
    for record, check in zip(collection.records, checks, strict=True):
        lines += [f"### {md(record.result_id)}", "",
                  f"Value evidence: `{record.value_evidence.evidence_id}`."]
        evidence_ids = dict.fromkeys([record.value_evidence.evidence_id,
                                    record.method_evidence.evidence_id,
                                    *(link.evidence_id for link in record.metric_evidence),
                                    *(link.evidence_id for link in record.benchmark.evidence),
                                    *(link.evidence_id for link in record.metric.definition_evidence),
                                    *(link.evidence_id for c in record.conditions for link in c.evidence)])
        for evidence_id in evidence_ids:
            unit = index.units.get(evidence_id)
            lines += ["", f"- `{evidence_id}`: {md(unit.text) if unit else 'Unresolved evidence'}"]
        lines += ["", "Check findings: " + (", ".join([*check["errors"], *check["warnings"]]) or "No attribution issues found."), ""]
    (output_dir / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path, help="Saved Docling JSON")
    parser.add_argument("--source-pdf", type=Path, help="Optional PDF to fingerprint; filename must match origin")
    parser.add_argument("--results", type=Path, help="Optional curated result collection")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/intelligence"))
    parser.add_argument("--rag-max-text-chars", type=int, default=2000)
    args = parser.parse_args()
    try:
        index = build_index(args.document, args.source_pdf)
        collection = ResultCollection.model_validate_json(args.results.read_bytes()) if args.results else None
        checks = check_collection(collection, index) if collection else []
        chunks = rag_chunks(index, max_text_chars=args.rag_max_text_chars, results=collection)
        out = args.output_dir.resolve()
        inputs = {p.resolve() for p in (args.document, args.source_pdf, args.results) if p is not None}
        names = ("evidence.index.json", "result.schema.json", "evidence.schema.json", "summary.json",
                 "results.json", "results.csv", "results.md", "checks.json", "rag_chunks.jsonl")
        if any(out / name in inputs for name in names):
            raise ValueError("Output paths would overwrite an input")
        if collection is None and any((out / name).exists() for name in
                                      ("results.json", "results.csv", "results.md", "checks.json")):
            raise ValueError("Output directory contains result exports; pass --results or use a fresh --output-dir")
        out.mkdir(parents=True, exist_ok=True)
        write_json(out / "evidence.index.json", index.model_dump(mode="json"))
        write_json(out / "result.schema.json", ResultCollection.model_json_schema())
        write_json(out / "evidence.schema.json", EvidenceIndex.model_json_schema())
        write_rag_jsonl(chunks, out / "rag_chunks.jsonl")
        if collection:
            export_results(collection, checks, index, out)
        summary = {
            "document_id": index.document.document_id,
            "source_sha256": index.document.source_sha256,
            "units_by_kind": dict(Counter(u.kind for u in index.units.values())),
            "unit_issues": dict(Counter(issue for u in index.units.values() for issue in u.issues)),
            "annotated_results": len(checks),
            "rag_chunks": len(chunks),
            "check_outcomes": dict(Counter(check["outcome"] for check in checks)),
            "output_dir": str(out),
        }
        write_json(out / "summary.json", summary)
        print(json.dumps(summary, indent=2))
        return 2 if any(check["outcome"] == "invalid" for check in checks) else 0
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Evidence build failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
