"""Export evidence-aware chunks; optionally return real LangChain Documents."""

import argparse
from pathlib import Path

from pbl_docintel import index_document, rag_chunks, resolve_evidence, to_langchain_documents, write_rag_jsonl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docling_json", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/rag-example.jsonl"))
    parser.add_argument("--langchain", action="store_true")
    args = parser.parse_args()
    index = index_document(args.docling_json)
    chunks = rag_chunks(index)
    if args.output.resolve() == args.docling_json.resolve():
        parser.error("Output would overwrite the source JSON")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_rag_jsonl(chunks, args.output)
    print(f"Exported {len(chunks)} chunks to {args.output}")
    if chunks:
        print(f"First chunk resolves to {len(resolve_evidence(index, chunks[0]))} source units")
    if args.langchain:
        docs = to_langchain_documents(chunks)
        print(f"Built {len(docs)} LangChain Documents; no embeddings or model calls made")


if __name__ == "__main__":
    main()
