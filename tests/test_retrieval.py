"""Contracts for query plans, fusion, section coverage and hosted reranking."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from pbl_docintel.vector_rag import retrieval as r
from pbl_docintel.vector_rag.rag import answer_question, build_messages, call_answer_model


SETTINGS = {"api_key":"test-only", "model":"test-model", "base_url":"https://example.invalid"}


def hit(key, heading="Body", score=None):
    return {"chunk_id":key, "contextualized_text":"Original passage " + key,
            "cosine_similarity":score, "metadata":{"headings":[heading],"pages":[1]}}


def source(key, text="Original author passage"):
    return {"source_id":"S9", "chunk_id":key, "text":text, "pages":[1], "source_refs":["#/texts/0"]}


class RetrievalTests(unittest.TestCase):
    def test_fallback_recognizes_broad_document_requests_but_preserves_specific_questions(self):
        for question in ["Tell me about the paper ?", "Please tell me about this paper",
                         "Could you explain the paper in simple terms?", "Describe the uploaded document",
                         "What is this paper about?", "What paper is about ?",
                         "Tell me what this document is about", "Give me the gist"]:
            with self.subTest(question=question):
                self.assertEqual(r.fallback_plan(question)["intent"], "overview")
        for question in ["Tell me about the paper's training costs", "What does this paper say about LoRA?",
                         "Tell me about the paper's Table 3", "How many GPUs does the paper use?"]:
            with self.subTest(question=question):
                self.assertEqual(r.fallback_plan(question)["intent"], "fact")

    def test_failed_planner_overview_pins_core_sections_even_if_reranker_prefers_appendix(self):
        with patch("openai.OpenAI") as client:
            client.return_value.__enter__.return_value.chat.completions.create.side_effect = RuntimeError("provider unavailable")
            plan, trace = r.plan_query("Tell me about the paper ?", {}, SETTINGS)
        self.assertEqual(trace["mode"], "fallback")
        self.assertEqual(plan["intent"], "overview")
        rows = [hit("abstract", "ABSTRACT"), hit("intro", "INTRODUCTION"),
                hit("end", "CONCLUSION"), hit("appendix", "B.2 TRAINING DETAILS")]
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = [(h["chunk_id"],h["contextualized_text"],h["metadata"]) for h in rows]
        with patch.object(r,"embed_texts",return_value=([[0]],None)), patch.object(r,"search",return_value=[rows[-1]]), \
             patch.object(r,"lexical_search",return_value=[]):
            candidates, structural, _ = r.collect_candidates(connection, "selected-index", "Tell me about the paper ?", plan, None, None)
        ranked = [source(h["chunk_id"], h["contextualized_text"]) for h in candidates]
        selected, _ = r.assemble_sources(ranked, structural, plan, 3, "Tell me about the paper ?")
        self.assertEqual([s["chunk_id"] for s in selected], ["abstract", "intro", "end"])

    def test_plan_preserves_original_and_rejects_invalid_output(self):
        plan = {"intent":"fact", "search_queries":["LoRA expansion"], "keywords":["LoRA"]}
        self.assertEqual(r.clean_plan(plan,"what is that called?")["search_queries"], ["what is that called?","LoRA expansion"])
        count_plan={**plan,"keywords":["ComOb","1.2M"]}
        self.assertEqual(r.clean_plan(count_plan,"How many scenes?")["keywords"],["ComOb"])
        self.assertEqual(r.clean_plan(count_plan,"Why 1.2M scenes?")["keywords"],["ComOb","1.2M"])
        for invalid in [{**plan,"answer":"invented"}, {**plan,"search_queries":[""]},
                        {**plan,"search_queries":["x"*601]}, {**plan,"intent":"other"}]:
            with self.assertRaises(ValueError): r.clean_plan(invalid,"q")

    def test_planner_success_history_is_data_and_failure_is_visible(self):
        response = SimpleNamespace(id="test", choices=[SimpleNamespace(finish_reason="stop",message=SimpleNamespace(
            content=json.dumps({"intent":"overview","search_queries":["Selected paper overview"],"keywords":[]})))])
        with patch("openai.OpenAI") as client:
            create = client.return_value.__enter__.return_value.chat.completions.create
            create.return_value = response
            plan, trace = r.plan_query("Give me the gist",{"title":"Selected"},SETTINGS,[{"question":"earlier"}])
            self.assertEqual(plan["intent"],"overview")
            self.assertEqual(trace["mode"],"llm")
            payload = json.loads(create.call_args.kwargs["messages"][1]["content"])
            self.assertEqual(payload["previous_turns"],[{"question":"earlier"}])
            create.side_effect = TimeoutError("private endpoint details")
            plan, trace = r.plan_query("Give me the gist",{},SETTINGS)
            self.assertEqual(trace["mode"],"fallback")
            self.assertNotIn("private",json.dumps(trace))
            self.assertEqual(plan["intent"],"overview")

    def test_fusion_deduplicates_uses_ranks_and_keeps_zero_similarity(self):
        a,b = hit("a",score=0),hit("b",score=.99)
        result = r.fuse_rankings({"vector":[b,a,a],"text":[a]})
        self.assertEqual([x["chunk_id"] for x in result],["a","b"])
        self.assertAlmostEqual(result[0]["rrf_score"],1/62+1/61)
        self.assertEqual(result[0]["cosine_similarity"],0)

    def test_section_classification_and_scoped_full_text_sql(self):
        for heading, expected in [("INTRODUCTION","introduction"),("1. Introduction","introduction"),
                                  ("IV. Conclusion","conclusion"),("REFERENCES","references"),
                                  ("3.5 Inference Pipeline","method"),("AI USE STATEMENT","backmatter")]:
            self.assertEqual(r.section_kind(hit("a",heading)),expected)
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = []
        r.lexical_search(connection,"selected-index",["LoRA","rank adaptation"])
        sql, params = connection.execute.call_args.args
        self.assertIn("index_id=%s",sql)
        self.assertEqual(params[1],"selected-index")
        self.assertNotIn("LoRA",sql)

    def test_overview_protects_section_coverage_and_sources_keep_original_text(self):
        rows = [hit("abstract","ABSTRACT"),hit("intro","INTRODUCTION"),hit("end","CONCLUSION"),hit("bib","References")]
        structural = r.structural_candidates(rows,"overview")
        ranked = [source("other"),source("end"),source("intro"),source("abstract")]
        selected,_ = r.assemble_sources(ranked,structural,{"intent":"overview"},3,"gist?")
        self.assertEqual([s["chunk_id"] for s in selected],["abstract","intro","end"])
        self.assertEqual([s["source_id"] for s in selected],["S1","S2","S3"])
        self.assertTrue(all(s["text"]=="Original author passage" for s in selected))

    def test_inline_abstract_is_recognized_without_an_abstract_heading(self):
        for marker in ["Abstract.","ABSTRACT:","Abstract —","Abstract\n"]:
            abstract=hit("a","Paper title")
            abstract["contextualized_text"]="Paper title\n"+marker+" We present an object memory."
            self.assertEqual(r.section_kind(abstract),"abstract")
            self.assertEqual(r.structural_candidates([abstract],"overview")[0]["chunk_id"],"a")
        ordinary=hit("ordinary","Abstract representations")
        ordinary["contextualized_text"]="Abstract representations\nAbstract concepts help describe the method."
        self.assertEqual(r.section_kind(ordinary),"body")

    def test_source_refs_recognize_an_abstract_inside_a_mixed_chunk(self):
        document={"texts":[{"self_ref":"#/texts/3","label":"text","text":"Abstract. Our study ..."},
                           {"self_ref":"#/texts/0","label":"page_header","text":"Version date"}]}
        original=hit("mixed","Paper title")
        original["metadata"]["source_refs"]=["#/texts/2","#/texts/3"]
        original["contextualized_text"]="Paper title\nAuthors\nAbstract. Our study ..."
        classified=r.with_document_role(original,r.document_section_roles(document))
        self.assertEqual(r.section_kind(classified),"abstract")
        self.assertNotIn("section_kind",original)
        self.assertEqual(classified["contextualized_text"],original["contextualized_text"])

    def test_headers_are_metadata_only_and_cannot_displace_overview_evidence(self):
        abstract=hit("abstract","Paper title"); abstract["metadata"]["source_refs"]=["#/texts/1"]
        abstract["contextualized_text"]="Paper title\nAbstract. A study of memory."
        header=hit("indexed-header","Running header"); header["metadata"]["source_refs"]=["#/texts/0"]
        header["contextualized_text"]="Version date"
        document={"texts":[{"self_ref":"#/texts/0","label":"page_header","text":"Version date","prov":[{"page_no":1}]},
                           {"self_ref":"#/texts/1","label":"text","text":"Abstract. A study of memory."}]}
        connection=MagicMock()
        connection.execute.return_value.fetchall.return_value=[(h["chunk_id"],h["contextualized_text"],h["metadata"]) for h in [header,abstract]]
        with patch.object(r,"embed_texts",return_value=([[0]],None)), patch.object(r,"search",return_value=[header,abstract]):
            for intent in ["overview","fact","method","contributions","references"]:
                candidates,structural,trace=r.collect_candidates(connection,"selected","q",
                    {"intent":intent,"search_queries":["q"],"keywords":[]},None,None,document=document)
                self.assertEqual([h["chunk_id"] for h in candidates],["abstract"])
                self.assertEqual(trace["document_item_candidates"],0)
            candidates,structural,trace=r.collect_candidates(connection,"selected","q",
                {"intent":"metadata","search_queries":["q"],"keywords":[]},None,None,document=document)
            self.assertEqual(trace["document_item_candidates"],1)
            self.assertTrue(any(h["chunk_id"]=="docling-item:#/texts/0" for h in structural))
            self.assertTrue(all(call.args[0].startswith("SELECT") for call in connection.execute.call_args_list))

    def test_budget_handles_escaped_text_without_truncation(self):
        large = source("huge",'"'*40000)
        small = source("small")
        selected, omitted = r.assemble_sources([large,small],[],{"intent":"fact"},5,"q")
        self.assertEqual(omitted,["huge"])
        self.assertEqual(selected[0]["text"],small["text"])
        build_messages("q",selected)

    def test_original_header_dates_are_available_without_reembedding(self):
        document={"texts":[
            {"self_ref":"#/texts/0","label":"page_header","text":"arXiv:1234.56789v2 [cs.CL] 17 Oct 2024","prov":[{"page_no":1}]},
            {"self_ref":"#/texts/1","label":"page_footer","text":"1","prov":[{"page_no":1}]},
            {"self_ref":"#/texts/2","label":"page_header","text":"Different running header","prov":[{"page_no":2}]},
            {"self_ref":"#/texts/3","label":"text","text":"Ordinary body text","prov":[{"page_no":1}]},
            {"self_ref":"#/texts/4","label":"page_footer","text":"October 18, 2024","prov":[{"page_no":1}]}]}
        hits=r.document_header_candidates(document)
        self.assertEqual(len(hits),2)
        self.assertEqual(hits[0]["contextualized_text"],document["texts"][0]["text"])
        self.assertEqual(hits[0]["metadata"]["source_refs"],["#/texts/0"])
        self.assertEqual(hits[0]["origin"],"docling_document")
        selected,_=r.assemble_sources([source("irrelevant"),*[source(h["chunk_id"],h["contextualized_text"]) for h in hits]],
                                      hits,{"intent":"metadata"},2,"when paper published?")
        self.assertIn("17 Oct 2024",selected[0]["text"])
        self.assertEqual(selected[1]["text"],"October 18, 2024")
        self.assertEqual(r.fallback_plan("when paper published ?")["intent"],"metadata")

    def test_reranker_reorders_only_known_sources_and_failures_preserve_fusion(self):
        sources = [source("a"),source("b")]
        response = MagicMock(is_success=True)
        response.json.return_value = {"rankings":[{"index":1,"logit":2},{"index":0,"logit":-1}]}
        with patch("httpx.post",return_value=response) as post, patch.dict("os.environ",{"SANTIO_RERANK_ENABLED":"true"}):
            ranked,trace = r.rerank_sources("q",sources,SETTINGS)
            self.assertEqual([s["chunk_id"] for s in ranked],["b","a"])
            self.assertEqual(trace["status"],"applied")
            self.assertEqual(post.call_args.kwargs["json"]["truncate"],"NONE")
            for rankings in [[{"index":0,"logit":1}], [{"index":0,"logit":1},{"index":0,"logit":2}],
                             [{"index":0,"logit":1},{"index":1,"logit":float("nan")}]]:
                response.json.return_value = {"rankings":rankings}
                ranked,trace = r.rerank_sources("q",sources,SETTINGS)
                self.assertEqual(ranked,sources)
                self.assertEqual(trace["status"],"unavailable")
            response.is_success=False; response.status_code=410
            self.assertEqual(r.rerank_sources("q",sources,SETTINGS)[1]["http_status"],410)
            post.side_effect=TimeoutError("secret")
            self.assertNotIn("secret",json.dumps(r.rerank_sources("q",sources,SETTINGS)[1]))

    def test_disabled_reranker_does_not_call_endpoint(self):
        with patch("httpx.post") as post, patch.dict("os.environ",{"SANTIO_RERANK_ENABLED":"false"}):
            self.assertEqual(r.rerank_sources("q",[source("a")],SETTINGS)[1]["status"],"disabled")
            post.assert_not_called()

    def test_followup_context_is_separate_from_source_evidence(self):
        messages=build_messages("How big is that?",[source("a")],["How big is ComOb?"])
        data=json.loads(messages[1]["content"])
        self.assertEqual(data["question"],"How big is that?")
        self.assertEqual(data["question_context"],["How big is ComOb?"])
        self.assertEqual(data["sources"][0]["text"],"Original author passage")

    def test_nemotron_uses_json_mode_and_schema_repair_identifies_field(self):
        evidence=source("a"); evidence["source_id"]="S1"
        good={"status":"answered","claims":[{"text":"Supported claim","evidence":[{"source_id":"S1","quote":evidence["text"]}]}],"missing_information":""}
        bad={**good,"unexpected":True}
        def response(payload):
            return SimpleNamespace(id="test",usage=None,choices=[SimpleNamespace(finish_reason="stop",message=SimpleNamespace(content=json.dumps(payload)))])
        with patch("openai.OpenAI") as client:
            create=client.return_value.__enter__.return_value.chat.completions.create
            create.side_effect=[response(bad),response(good)]
            result,attempts=call_answer_model(build_messages("q",[evidence]),[evidence],{**SETTINGS,"model":"nvidia/nemotron-3-super-120b-a12b"})
            self.assertEqual(result["status"],"answered")
            self.assertEqual(create.call_args.kwargs["response_format"],{"type":"json_object"})
            self.assertFalse(create.call_args.kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"])
            self.assertIn("unexpected",create.call_args.kwargs["messages"][-1]["content"])

    def test_source_guard_precedes_all_hosted_calls_and_clarification_skips_embedding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"document.json"
            path.write_text('{"texts":[]}',encoding="utf-8")
            manifest = {"identity":{"source_sha256":"wrong"}, "chunking_report":{"source":str(path)}}
            with patch("pbl_docintel.vector_rag.rag.load_answer_settings",return_value=SETTINGS), \
                 patch("pbl_docintel.vector_rag.rag.connect_database") as connect, \
                 patch.object(r,"plan_query") as planner, patch("pbl_docintel.vector_rag.rag.load_model") as model:
                connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value=(manifest,)
                with self.assertRaisesRegex(ValueError,"differs"):
                    answer_question("index","question")
                planner.assert_not_called()
                manifest["identity"]["source_sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
                planner.return_value=({"intent":"fact","search_queries":["q"],"clarification":"Which dataset?"},{"mode":"llm"})
                result=answer_question("index","question")
                self.assertEqual(result["answer"]["status"],"clarification_needed")
                self.assertFalse(result["attempts"])
                model.assert_not_called()

    def test_vector_baseline_does_not_call_planner_or_reranker(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"document.json"; path.write_text('{"texts":[]}',encoding="utf-8")
            manifest={"identity":{"source_sha256":hashlib.sha256(path.read_bytes()).hexdigest()},
                      "chunking_report":{"source":str(path)}}
            with patch("pbl_docintel.vector_rag.rag.load_answer_settings",return_value=SETTINGS), \
                 patch("pbl_docintel.vector_rag.rag.connect_database") as connect, \
                 patch("pbl_docintel.vector_rag.rag.load_model",return_value=(None,SimpleNamespace(device="cpu"))), \
                 patch("pbl_docintel.vector_rag.rag.embed_texts",return_value=([[0]],None)), \
                 patch("pbl_docintel.vector_rag.rag.search",return_value=[]), \
                 patch.object(r,"plan_query") as planner, patch.object(r,"rerank_sources") as reranker:
                connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value=(manifest,)
                result=answer_question("i","q",retrieval_mode="vector")
                self.assertEqual(result["answer"]["status"],"insufficient_evidence")
                planner.assert_not_called(); reranker.assert_not_called()


if __name__ == "__main__": unittest.main()
