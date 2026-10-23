"""Live source-retrieval diagnostic, using unchanged indexes and frozen references.

This measures retrieval of AI-selected source passages, not answer accuracy.
References are written before retrieval. No extraction or embedding writes occur.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from pbl_docintel.vector_rag.vector_index import connect_database, load_model, embed_texts, search
from pbl_docintel.vector_rag.rag import load_answer_settings, prepare_evidence
from pbl_docintel.vector_rag.retrieval import (document_profile, plan_query, collect_candidates,
    assemble_sources, rerank_sources, section_kind)

ROOT = Path(__file__).resolve().parents[3]
CASES = [
    ("failed_overview","arxiv:2610.10539v1","can you tell me what paper is about ?",["#/texts/20","#/texts/25","#/texts/204"]),
    ("gist","arxiv:2610.10539v1","Give me the gist.",["#/texts/20","#/texts/25","#/texts/204"]),
    ("simple","arxiv:2610.10539v1","Explain this simply.",["#/texts/20","#/texts/25","#/texts/204"]),
    ("problem","arxiv:2610.10539v1","What are they trying to solve?",["#/texts/20","#/texts/25","#/texts/26"]),
    ("new","arxiv:2610.10539v1","What is new here?",["#/texts/20","#/texts/28","#/texts/204"]),
    ("inference","arxiv:2610.10539v1","How do they decide which object to generate first?",["#/texts/149"]),
    ("dataset","arxiv:2610.10539v1","How big is the ComOb dataset?",["#/texts/20","#/texts/28","#/texts/146","#/texts/333"]),
    ("lora_short","arxiv:2307.06435v10","What does LoRA stand for?",["#/texts/360"]),
    ("lora_paraphrase","arxiv:2307.06435v10","What is LoRA and how does it reduce fine-tuning costs?",["#/texts/360"]),
    ("lora_natural","arxiv:2307.06435v10","Explain the low-rank trick for adapting a big language model without updating all its weights.",["#/texts/360"]),
    ("bibliography","arxiv:2610.10539v1","Which publications by Xiang are cited in the references?",[]),
]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"tmp"/("retrieval-comparison-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")))
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/"reference_cases.json").write_text(json.dumps(CASES,indent=2),encoding="utf-8")
    bindings={s["paper_id"]:s for p in (ROOT/"data/rag-state").glob("*.json") if (s:=json.loads(p.read_text()))["status"]=="ready"}
    settings=load_answer_settings(ROOT/".env")
    tokenizer,model=load_model("auto")
    results=[]
    with connect_database(ROOT/"playground/vector-rag/.env") as connection:
        before=connection.execute("SELECT count(*) FROM rag.chunks").fetchone()[0]
        for name,paper,question,expected in CASES:
            index=bindings[paper]["index_id"]
            manifest=connection.execute("SELECT manifest FROM rag.vector_indexes WHERE index_id=%s",(index,)).fetchone()[0]
            document=json.loads(Path(manifest["chunking_report"]["source"]).read_text(encoding="utf-8"))
            profile=document_profile(document)
            # Use the actual source title rather than its filename, as the app does.
            titles=[t["text"] for t in document.get("texts",[]) if t.get("label")=="title"]
            if titles: profile["title"]=titles[0]
            plan,planning=plan_query(question,profile,settings)
            vectors,_=embed_texts([question],tokenizer,model,batch_size=1)
            baseline,_=prepare_evidence(search(connection,index,vectors[0],5),manifest)
            hits,structural,trace=collect_candidates(connection,index,question,plan,tokenizer,model,document=document)
            sources,excluded=prepare_evidence(hits,manifest)
            hybrid,_=assemble_sources(sources,structural,plan,5,question)
            ranked,ranking=rerank_sources(question,sources,settings,ROOT/".env")
            upgraded,_=assemble_sources(ranked,structural,plan,5,question)
            item={"case":name,"paper_id":paper,"index_id":index,"question":question,
                  "expected_any_source_ref":expected,"plan":plan,"planning":planning,
                  "reranking_status":ranking["status"],"excluded_candidates":excluded,"modes":{}}
            for mode,selected in [("vector",baseline),("hybrid",hybrid),("reranked",upgraded)]:
                refs={ref for s in selected for ref in s["source_refs"]}
                kinds=[section_kind({"metadata":{"headings":s["headings"]}}) for s in selected]
                success=bool(refs.intersection(expected)) if expected else "references" in kinds
                item["modes"][mode]={"selected_reference_found":success,"section_kinds":kinds,
                    "sources":[{k:s[k] for k in ["chunk_id","pages","source_refs","headings"]} for s in selected]}
            results.append(item)
            (args.output/(name+".json")).write_text(json.dumps(item,indent=2,ensure_ascii=False),encoding="utf-8")
            print(json.dumps({"case":name,"intent":plan["intent"],"planner":planning["mode"],"reranker":ranking["status"],
                              "found":{m:v["selected_reference_found"] for m,v in item["modes"].items()}}),flush=True)
        after=connection.execute("SELECT count(*) FROM rag.chunks").fetchone()[0]
    summary={"scope":"AI-prepared source-reference diagnostic on two papers; not verified ground truth or an answer-accuracy benchmark.",
             "top_k":5,"case_count":len(results),"embedding_rows_before":before,"embedding_rows_after":after,
             "selected_reference_found":{m:sum(r["modes"][m]["selected_reference_found"] for r in results) for m in ["vector","hybrid","reranked"]},
             "planner_fallbacks":sum(r["planning"]["mode"]!="llm" for r in results),
             "reranker_unavailable":sum(r["reranking_status"]!="applied" for r in results)}
    (args.output/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary),flush=True)


if __name__=="__main__": main()
