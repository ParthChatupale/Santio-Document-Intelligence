"""Isolated worker around the same vector RAG functions used in the playground."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def emit(**event):
    print("SANTIO_EVENT:" + json.dumps(event), flush=True)


def database_env(root):
    from dotenv import dotenv_values
    if os.getenv("SANTIO_DB_ENV_FILE"):
        return Path(os.environ["SANTIO_DB_ENV_FILE"]).resolve(strict=True)
    main = root / ".env"
    if dotenv_values(main).get("PGPASSWORD"):
        return main
    return root / "playground/vector-rag/.env"


def run_preparation(root, spec):
    from pbl_docintel import DoclingAdapter, index_document
    from pbl_docintel.vector_rag.converter import convert_pdf
    from pbl_docintel.vector_rag.chunker import chunk_document
    from pbl_docintel.vector_rag.vector_index import build_index, load_chunks

    pdf, output = root / spec["pdf"], root / spec["output"]
    output.mkdir(parents=True, exist_ok=False)
    document = root / spec["document"] if spec.get("document") else None
    emit(phase="extract", stage="Reading PDF" if document is None else "Reusing saved extraction", completed_stages=["upload"])
    if document is None:
        report = convert_pdf(pdf, output / "converted", ocr=spec.get("ocr", False))
        if report["status"] not in {"success", "partial_success"}:
            raise ValueError("Docling could not extract this document. Review the conversion log.")
        document = output / "converted/document.json"
        status, pages = report["status"], report["pages"]
    else:
        status = spec.get("conversion_status", "success")
        pages = len(json.loads(document.read_text(encoding="utf-8"))["pages"])
    # This is a viewer adapter over the SAME JSON, not another PDF conversion.
    evidence = output / "evidence.index.json"
    index = index_document(document, DoclingAdapter(pdf))
    evidence.write_text(index.model_dump_json(indent=2), encoding="utf-8")
    emit(kind="extracted", phase="chunk", stage="Preparing passages", completed_stages=["upload", "extract"],
         document=str(document.relative_to(root)), evidence_index=str(evidence.relative_to(root)),
         conversion_status=status, pages=pages)
    chunks = output / "chunks"
    if spec.get("chunks_file"):
        chunks = (root / spec["chunks_file"]).parent
        _, saved, _ = load_chunks(chunks / "chunks.jsonl")
        if saved["identity"]["source_sha256"] != hashlib.sha256(document.read_bytes()).hexdigest():
            raise ValueError("Saved passages no longer match the extraction. Prepare a new version.")
        report = saved["chunking_report"]
    else:
        report = chunk_document(document, chunks, include_ai_descriptions=True, formula_text="document")
    if report["violations"]:
        raise ValueError("Chunk validation failed. The extracted document remains available.")
    emit(phase="embed", stage="Making document searchable", completed_stages=["upload", "extract", "chunk"],
         chunk_count=report["chunks"], chunks_file=str((chunks / "chunks.jsonl").relative_to(root)))
    indexed = build_index(chunks / "chunks.jsonl", database_env(root),
                          progress=lambda done, total: emit(phase="embed", stage="Making document searchable",
                                                           completed_stages=["upload", "extract", "chunk"], done=done, total=total))
    (output / "index_report.json").write_text(json.dumps(indexed, indent=2), encoding="utf-8")
    emit(kind="ready", index_id=indexed["index_id"], chunk_count=indexed["stored_chunks"],
         document_sha256=hashlib.sha256(document.read_bytes()).hexdigest(),
         source_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
         chunks_file=str((chunks / "chunks.jsonl").relative_to(root)))


def run_question(root, spec):
    from pbl_docintel.vector_rag.rag import answer_question
    from pbl_docintel.vector_rag.vector_index import connect_database
    from pbl_docintel.vector_rag.terminal import TerminalTrace

    # Bind the server-selected paper to the index before sending passages to a model.
    if hashlib.sha256((root / spec["document"]).read_bytes()).hexdigest() != spec["document_sha256"]:
        raise ValueError("The extracted document changed. Prepare this paper again.")
    if hashlib.sha256((root / spec["pdf"]).read_bytes()).hexdigest() != spec["source_sha256"]:
        raise ValueError("The original PDF changed. Prepare this paper again.")
    with connect_database(database_env(root)) as connection:
        row = connection.execute("SELECT manifest FROM rag.vector_indexes WHERE index_id=%s", (spec["index_id"],)).fetchone()
        if not row or row[0]["identity"]["source_sha256"] != spec["document_sha256"]:
            raise ValueError("The stored index does not match this paper. Prepare it again.")
    emit(stage="Finding supporting passages")
    terminal = TerminalTrace([root / ".env", database_env(root)])
    def observe(stage, data):
        terminal(stage, data)
        if stage == "Provider retry waiting":
            emit(stage="Waiting to retry", retry=data)
        elif stage == "Provider retry resumed":
            emit(stage="Retrying " + data["stage"], retry=None)
        elif stage in {"Provider request succeeded", "Provider request stopped", "Provider retries exhausted"}:
            emit(stage=data["stage"].capitalize() + (" completed" if stage == "Provider request succeeded" else " stopped"), retry=None)
    report = answer_question(spec["index_id"], spec["question"], db_env=database_env(root), llm_env=root / ".env",
                             document_title=spec.get("document_title"), history=spec.get("history"),
                             progress=lambda stage: emit(stage=stage), on_trace=observe)
    (root / spec["trace"]).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    terminal("Saved question trace", {"path": str(root / spec["trace"])})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "ask"])
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve(strict=True)
    spec = json.loads(args.input.read_text(encoding="utf-8"))
    try:
        (run_preparation if args.mode == "prepare" else run_question)(root, spec)
    except Exception as exc:
        from pbl_docintel.vector_rag.vector_index import DatabaseConnectionError
        # Public job errors never include environment values/provider tracebacks.
        if isinstance(exc, DatabaseConnectionError):
            print("Database connection failed: " + str(exc), flush=True)
            emit(kind="error", error="Cannot connect to PostgreSQL. Start PostgreSQL in WSL and check the server database settings, then retry. Saved extraction and passages are retained.")
            return 1
        message = str(exc) if isinstance(exc, (ValueError, FileNotFoundError)) else (
            "This stage failed (" + type(exc).__name__ + "). Check the saved worker log and connection settings.")
        emit(kind="error", error=message)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
