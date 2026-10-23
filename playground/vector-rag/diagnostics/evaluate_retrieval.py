"""Evaluate an unchanged vector index against a frozen source-linked question set.

Scores reference evidence at ranks 1/5/10. Table checks require the selected row
fragments, not merely a table reference shared by many chunks. Unsupported and
source-quality probes are kept out of the answerable-question score.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vector_index import ROOT, load_chunks, connect_database, load_model, embed_texts, search


def normalized(text):
    return re.sub(r"\s+", " ", text).strip().casefold()


def matches(hit, evidence):
    return evidence["ref"] in hit["metadata"]["source_refs"] and all(
        normalized(p) in normalized(hit["contextualized_text"]) for p in evidence["phrases"]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chunks", type=Path)
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("retrieval_cases_v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    chunks, manifest, index_id = load_chunks(args.chunks)
    specification = json.loads(args.cases.read_text(encoding="utf-8"))
    source_path = Path(manifest["chunking_report"]["source"])
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == specification["source_sha256"]
    source = json.loads(source_path.read_text(encoding="utf-8"))
    text_lookup = {x["self_ref"]: x for x in source["texts"]}
    source_text = "\n".join(t["text"] for t in source["texts"]) + json.dumps(source["tables"], ensure_ascii=False)
    cases = specification["cases"]
    candidate_hits = [{"chunk_id":c["chunk_id"], "contextualized_text":c["contextualized_text"], "metadata":c} for c in chunks]
    for case in cases:
        if case["kind"] == "unsupported":
            for term in case["absent_terms"]:
                assert normalized(term) not in normalized(source_text), f"Absent-term assumption failed: {term}"
        for evidence in case.get("evidence", []):
            available = [c for c in candidate_hits if matches(c, evidence)]
            assert available, f"Frozen evidence is not present in indexed input: {case['id']} {evidence}"
            evidence["indexed_witness_chunk_ids"] = [c["chunk_id"] for c in available]
            if evidence["ref"] in text_lookup:
                item = text_lookup[evidence["ref"]]
                evidence["source_text"] = item["text"]
                evidence["source_original"] = item.get("orig")
                evidence["source_pages"] = sorted({p["page_no"] for p in item["prov"]})
            else:
                evidence["indexed_witness_text"] = available[0]["contextualized_text"]
    # Write expectations before running any retrieval. Do not tune the cases to results.
    frozen = {**specification, "index_id": index_id}
    (args.output / "frozen_reference.json").write_text(json.dumps(frozen, indent=2, ensure_ascii=False), encoding="utf-8")
    tokenizer, model = load_model("cuda")
    query_vectors, _ = embed_texts([c["question"] for c in cases], tokenizer, model, batch_size=8)
    results = []
    with connect_database(ROOT / ".env") as connection:
        before = connection.execute("SELECT count(*) FROM rag.chunks WHERE index_id=%s", (index_id,)).fetchone()[0]
        for case, vector in zip(cases, query_vectors):
            started = perf_counter()
            hits = search(connection, index_id, vector, top_k=10)
            ranks = [next((rank for rank, hit in enumerate(hits, 1) if matches(hit, e)), None)
                     for e in case.get("evidence", [])]
            all_rank = max(ranks) if ranks and all(rank is not None for rank in ranks) else None
            results.append({"id":case["id"],"kind":case["kind"],"category":case["category"],
                "question":case["question"],"evidence_group_ranks":ranks,
                "all_evidence_rank":all_rank,"any_evidence_rank":min((r for r in ranks if r),default=None),
                "top_similarity":hits[0]["cosine_similarity"] if hits else None,
                "database_search_ms":round((perf_counter()-started)*1000,3),"results":hits})
            print(f"{case['id']}: group ranks {ranks}; all evidence rank {all_rank}", flush=True)
        after = connection.execute("SELECT count(*) FROM rag.chunks WHERE index_id=%s", (index_id,)).fetchone()[0]
        assert before == after == len(chunks)
    scored = [r for r in results if r["kind"] == "answerable"]
    metrics = {
        "answerable_questions":len(scored),
        "all_required_evidence_hit_at_k":{str(k):sum(r["all_evidence_rank"] is not None and r["all_evidence_rank"]<=k for r in scored)/len(scored) for k in [1,5,10]},
        "any_required_evidence_hit_at_k":{str(k):sum(r["any_evidence_rank"] is not None and r["any_evidence_rank"]<=k for r in scored)/len(scored) for k in [1,5,10]},
        "mean_reciprocal_first_evidence_rank_at_10":sum(1/r["any_evidence_rank"] if r["any_evidence_rank"] else 0 for r in scored)/len(scored),
    }
    report = {"index_id":index_id,"reference_scope":specification["scope"],"reference_sha256":hashlib.sha256(args.cases.read_bytes()).hexdigest(),
              "query_model":"same pinned local R2 model as indexed chunks","top_k":10,
              "metrics":metrics,"database_rows_unchanged":True,"answer_generation_tested":False,
              "notes":["Single paper, small AI-prepared reference set; no population-level accuracy claim.",
                       "Phrase rules are transparent reference checks, not a semantic judge; equivalent unlisted evidence can be missed.",
                       "Any-evidence metrics do not establish that multi-part questions have enough support.",
                       "Unsupported probes show raw nearest-neighbor results; this retriever has no abstention mechanism."],"cases":results}
    (args.output / "results.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(metrics,indent=2),flush=True)


if __name__ == "__main__":
    main()
