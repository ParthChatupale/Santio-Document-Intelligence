"""Compatibility conversion entry point; the GUI now uses rag_worker instead."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ocr", action="store_true")
    args = parser.parse_args()
    from pbl_docintel.vector_rag.converter import convert_pdf
    from pbl_docintel import DoclingAdapter, index_document, write_rag_jsonl, rag_chunks
    report = convert_pdf(args.source, args.output, ocr=args.ocr)
    if report["status"] not in {"success", "partial_success"}:
        raise RuntimeError("PDF conversion failed; review conversion_report.json")
    index = index_document(args.output / "document.json", DoclingAdapter(args.source))
    (args.output / "evidence.index.json").write_text(index.model_dump_json(indent=2), encoding="utf-8")
    write_rag_jsonl(rag_chunks(index), args.output / "rag.jsonl")
    (args.output / "receipt.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
