"""Read-only follow-up: locate the frozen reference passages below the top ten.

This does not change the original test set, metrics, index, or retrieval pipeline.
"""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vector_index import ROOT, connect_database, load_model, embed_texts
from evaluate_retrieval import matches


def main():
    from pgvector import Vector

    output = Path(__file__).with_name("retrieval-evaluation-v1")
    report = json.loads((output / "results.json").read_text(encoding="utf-8"))
    reference = json.loads((output / "frozen_reference.json").read_text(encoding="utf-8"))
    selected = [c for c in reference["cases"] if c["id"] in {"q05", "q13"}]
    tokenizer, model = load_model("cuda")
    vectors, _ = embed_texts([c["question"] for c in selected], tokenizer, model)
    diagnostics = []
    with connect_database(ROOT / ".env") as connection:
        for case, vector in zip(selected, vectors):
            rows = connection.execute("""
                SELECT chunk_id, contextualized_text, metadata, embedding <=> %s AS distance
                FROM rag.chunks WHERE index_id = %s ORDER BY distance, ordinal
            """, (Vector(vector), report["index_id"])).fetchall()
            hits = [{"chunk_id": r[0], "contextualized_text": r[1], "metadata": r[2],
                     "cosine_similarity": 1 - r[3]} for r in rows]
            original = next(c for c in report["cases"] if c["id"] == case["id"])
            assert [h["chunk_id"] for h in hits[:10]] == [h["chunk_id"] for h in original["results"]]
            evidence_ranks = []
            for evidence in case["evidence"]:
                rank, hit = next((i, h) for i, h in enumerate(hits, 1) if matches(h, evidence))
                evidence_ranks.append({"ref": evidence["ref"], "rank": rank, "hit": hit})
            diagnostics.append({"id": case["id"], "question": case["question"],
                                "evidence_ranks": evidence_ranks, "full_ranking": hits})
            print(case["id"], [(e["ref"], e["rank"]) for e in evidence_ranks], flush=True)
    (output / "miss_diagnostics.json").write_text(json.dumps({
        "scope": "Post-test read-only diagnosis; original top-ten scores remain unchanged.",
        "cases": diagnostics}, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
