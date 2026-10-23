"""Verify stored paper vectors, duplicate prevention, rollback and passage retrieval.

The three source-linked questions below are an AI-prepared smoke reference, not
an independently annotated benchmark. No answer model is used.
"""

import argparse
import copy
import json
from pathlib import Path
import sys
import uuid

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vector_index import ROOT, load_chunks, connect_database, load_model, embed_texts, store_embeddings, search


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chunks", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    chunks, manifest, index_id = load_chunks(args.chunks)
    source = json.loads(Path(manifest["chunking_report"]["source"]).read_text(encoding="utf-8"))
    source_texts = {item["self_ref"]: item for item in source["texts"]}
    cases = [
        {"question": "In retrieval-augmented LLMs, how does retrieved context reach the language model?",
         "expected_ref": "#/texts/326"},
        {"question": "Which modules does a tool-augmented LLM use when executing a plan?",
         "expected_ref": "#/texts/340"},
        {"question": "Which parameter-efficient fine-tuning methods fall in the adapter-tuning category?",
         "expected_ref": "#/texts/359"},
    ]
    for case in cases:
        item = source_texts[case["expected_ref"]]
        case["source_passage"] = item["text"]
        case["pages"] = sorted({p["page_no"] for p in item["prov"]})
    # Freeze source expectations before querying the model/database.
    (args.output / "retrieval_cases.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    checks = []
    with connect_database(ROOT / ".env") as connection:
        rows = connection.execute("SELECT embedding FROM rag.chunks WHERE index_id = %s ORDER BY ordinal",
                                  (index_id,)).fetchall()
        vectors = np.array([row[0].to_list() for row in rows], dtype=np.float32)
        assert vectors.shape == (len(chunks), 384)
        second = store_embeddings(connection, index_id, chunks, vectors, manifest)
        assert second["new_rows"] == 0 and second["stored_chunks"] == len(chunks)
        checks.append(f"Repeated storage reuses all {len(chunks)} existing rows without duplication")

        bad_chunks = copy.deepcopy(chunks)
        bad_chunks[-1]["chunk_id"] = bad_chunks[0]["chunk_id"]
        failed_id = "rollback-check-" + uuid.uuid4().hex
        try:
            store_embeddings(connection, failed_id, bad_chunks, vectors, manifest)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Invalid incomplete dataset was committed")
        assert connection.execute("SELECT count(*) FROM rag.vector_indexes WHERE index_id = %s",
                                  (failed_id,)).fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM rag.chunks WHERE index_id = %s",
                                  (failed_id,)).fetchone()[0] == 0
        checks.append("Failed read-back validation rolls back header and all inserted chunks")

        tokenizer, model = load_model("cuda")
        queries, _ = embed_texts([c["question"] for c in cases], tokenizer, model, batch_size=3)
        results = []
        for case, vector in zip(cases, queries):
            found = search(connection, index_id, vector, top_k=5)
            distances = 1 - (vectors @ vector) / (np.linalg.norm(vectors, axis=1) * np.linalg.norm(vector))
            assert abs(found[0]["cosine_distance"] - float(distances.min())) < 2e-6
            assert all(abs(hit["cosine_distance"] - float(distances[
                next(i for i, c in enumerate(chunks) if c["chunk_id"] == hit["chunk_id"])])) < 2e-6
                for hit in found)
            rank = next((i + 1 for i, hit in enumerate(found)
                         if case["expected_ref"] in hit["metadata"]["source_refs"]), None)
            results.append({**case, "expected_ref_rank_in_top5": rank, "results": found})
        checks.append("PostgreSQL cosine distances match independent NumPy calculations")
        count = connection.execute("SELECT count(*) FROM rag.chunks WHERE index_id = %s", (index_id,)).fetchone()[0]
        assert count == len(chunks)
    report = {"engineering_checks": "PASS", "index_id": index_id, "stored_chunks": count,
              "checks": checks, "source_ref_hits_in_top5": sum(r["expected_ref_rank_in_top5"] is not None for r in results),
              "questions": len(cases), "scope": "Three source-linked smoke questions; not general retrieval accuracy",
              "retrieval": results}
    (args.output / "checks.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "retrieval"}, indent=2), flush=True)
    print(json.dumps([{k: r[k] for k in ["question", "expected_ref_rank_in_top5"]} for r in results], indent=2))


if __name__ == "__main__":
    main()
