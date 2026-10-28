"""Regression checks for combined schema/quote failures and safe partial output."""
from contextlib import redirect_stderr
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pbl_docintel.vector_rag.rag import (AnswerValidationError, call_answer_model,
                                        retain_cited_claims, restore_answer_status, validate_answer)


SOURCES = [
    {"source_id":"S1", "chunk_id":"main", "pages":[2], "source_refs":["#/texts/1"],
     "text":"The method retains observations after objects leave the camera view."},
    {"source_id":"S3", "chunk_id":"limits", "pages":[11], "source_refs":["#/texts/3"],
     "text":"Counting remains unresolved. The poses are calibrated. Construction is offline."},
]
VALID = {"text":"The method retains observations.", "evidence":[{"source_id":"S1", "quote":SOURCES[0]["text"]}]}
INVALID = {"text":"Counting is unresolved and construction is offline.", "evidence":[
    {"source_id":"S3", "quote":"Counting remains unresolved. ... Construction is offline."}]}
SETTINGS = {"api_key":"test-only", "base_url":"https://example.invalid", "model":"test"}


def payload(*claims, status="answered", **extra):
    return {"status":status, "claims":list(claims), "missing_information":"", **extra}


def response(value):
    return SimpleNamespace(id="test", usage=None, choices=[SimpleNamespace(finish_reason="stop",
        message=SimpleNamespace(content=json.dumps(value)))])


class AnswerRepairTests(unittest.TestCase):
    def test_only_absent_status_can_be_restored_from_complete_unambiguous_body(self):
        for value, expected in [({"claims":[VALID],"missing_information":""},"answered"),
                                ({"claims":[VALID],"missing_information":"Other requested details missing"},"partial"),
                                ({"claims":[],"missing_information":"No evidence"},"insufficient_evidence")]:
            with self.subTest(expected=expected):
                content, note = restore_answer_status(json.dumps(value))
                self.assertEqual(validate_answer(content,SOURCES)["status"],expected)
                self.assertEqual(note["field"],"status")
                self.assertEqual(json.loads(content)["claims"],value["claims"])
                self.assertEqual(json.loads(content)["missing_information"],value["missing_information"])
        for value in [payload(VALID,status="wrong"),{"claims":[VALID]}, {"claims":[],"missing_information":""},
                      {"claims":[VALID],"missing_information":"","unexpected":True},
                      {"claims":[{"text":"Missing citations"}],"missing_information":""}]:
            with self.subTest(value=value):
                _, note=restore_answer_status(json.dumps(value))
                self.assertIsNone(note)

    def test_missing_status_after_repair_does_not_discard_valid_citations(self):
        value=payload(VALID); value.pop("status")
        with patch("openai.OpenAI") as client, redirect_stderr(io.StringIO()):
            create=client.return_value.__enter__.return_value.chat.completions.create
            create.side_effect=[response(value),response(value)]
            answer, attempts=call_answer_model([],SOURCES,SETTINGS)
        self.assertEqual(answer["status"],"answered")
        self.assertEqual(answer["validation"]["normalizations"][0]["field"],"status")
        self.assertNotIn("status",json.loads(attempts[1]["content"]))
        self.assertEqual(attempts[1]["outcome"],"accepted_after_status_restoration")
        self.assertEqual(create.call_count,2)

    def test_restoring_status_does_not_accept_invalid_quotations(self):
        value=payload(INVALID); value.pop("status")
        with patch("openai.OpenAI") as client, redirect_stderr(io.StringIO()):
            create=client.return_value.__enter__.return_value.chat.completions.create
            create.side_effect=[response(value),response(value)]
            answer,_=call_answer_model([],SOURCES,SETTINGS)
        self.assertEqual(answer["status"],"error")
        self.assertEqual(answer["error_kind"],"answer_validation_failed")

    def test_missing_root_field_does_not_hide_invalid_quote_in_repair_feedback(self):
        first = payload(VALID,INVALID); first.pop("status")
        with self.assertRaises(AnswerValidationError) as caught:
            validate_answer(json.dumps(first),SOURCES)
        issues = caught.exception.issues
        self.assertTrue(any(i["path"]=="status" and i["kind"]=="schema" for i in issues))
        self.assertTrue(any(i["path"]=="claims.1.evidence.0" and i["kind"]=="quote_mismatch" for i in issues))
        self.assertIn("ellipsis",str(caught.exception))

    def test_one_repair_can_fix_status_and_split_quotation_together(self):
        first = payload(VALID,INVALID); first.pop("status")
        repaired = {**INVALID, "evidence":[{"source_id":"S3","quote":"Counting remains unresolved."},
                                          {"source_id":"S3","quote":"Construction is offline."}]}
        with patch("openai.OpenAI") as client, redirect_stderr(io.StringIO()):
            create = client.return_value.__enter__.return_value.chat.completions.create
            create.side_effect = [response(first),response(payload(VALID,repaired))]
            answer, attempts = call_answer_model([],SOURCES,SETTINGS)
        self.assertEqual(answer["status"],"answered")
        self.assertEqual(len(attempts),2)
        feedback = create.call_args.kwargs["messages"][-1]["content"]
        self.assertIn("status",feedback)
        self.assertIn("claims.1.evidence.0",feedback)
        self.assertIn("Split separated sentences",feedback)
        self.assertEqual(len(attempts[0]["validation_issues"]),2)
        self.assertEqual(len(answer["claims"]),2)

    def test_persistent_bad_quote_withholds_whole_claim_after_repair(self):
        first = payload(VALID,INVALID); first.pop("status")
        events=[]
        with patch("openai.OpenAI") as client, redirect_stderr(io.StringIO()):
            create=client.return_value.__enter__.return_value.chat.completions.create
            create.side_effect=[response(first),response(payload(VALID,INVALID))]
            answer, attempts=call_answer_model([],SOURCES,SETTINGS,on_trace=lambda n,d:events.append((n,d)))
        self.assertEqual(answer["status"],"partial")
        self.assertEqual([c["text"] for c in answer["claims"]],[VALID["text"]])
        self.assertEqual(answer["claims"][0]["evidence"][0]["chunk_id"],"main")
        self.assertIn("Withheld 1",answer["missing_information"])
        self.assertFalse(answer["validation"]["semantic_entailment_verified"])
        self.assertEqual(answer["validation"]["retained_claim_count"],1)
        self.assertEqual(answer["validation"]["withheld_claims"][0]["claim_index"],1)
        self.assertEqual(attempts[1]["outcome"],"partial_after_withholding_invalid_claims")
        self.assertEqual(json.loads(attempts[1]["content"])["claims"][1],INVALID)
        self.assertEqual(create.call_count,2)
        self.assertEqual(events[-1][0],"Partial answer retained; invalid claims withheld")

    def test_schema_errors_unknown_ids_and_wholly_invalid_answers_are_not_promoted(self):
        missing = payload(VALID); missing.pop("status")
        malformed = payload(VALID); malformed["claims"][0] = {"text":"no evidence"}
        unknown = {**INVALID,"evidence":[{"source_id":"S99","quote":SOURCES[0]["text"]}]}
        for value in [missing,malformed,payload(INVALID),payload(unknown),
                      payload(VALID,status="insufficient_evidence"),payload(VALID,status="partial")]:
            with self.subTest(value=value):
                self.assertIsNone(retain_cited_claims(json.dumps(value),SOURCES))
        self.assertIsNone(retain_cited_claims("not JSON",SOURCES))

    def test_one_valid_quote_does_not_rescue_an_invalid_claim_with_another_bad_quote(self):
        mixed = {**INVALID,"evidence":[*VALID["evidence"],*INVALID["evidence"]]}
        answer=retain_cited_claims(json.dumps(payload(VALID,mixed)),SOURCES)
        self.assertEqual(len(answer["claims"]),1)
        self.assertEqual(answer["claims"][0]["text"],VALID["text"])

    def test_numeric_changes_are_not_normalized_away(self):
        bad = {"text":"Incorrect numeric statement.","evidence":[{"source_id":"S3","quote":"The measured accuracy is 29.8 percent."}]}
        sources=[SOURCES[0],{**SOURCES[1],"text":"The measured accuracy is 29.7 percent."}]
        answer=retain_cited_claims(json.dumps(payload(VALID,bad)),sources)
        self.assertEqual(len(answer["claims"]),1)
        self.assertNotIn("29.8",json.dumps(answer["claims"]))

    def test_earlier_schema_failure_and_unrepaired_all_invalid_answer_keep_error_kind(self):
        with patch("openai.OpenAI") as client, redirect_stderr(io.StringIO()):
            create=client.return_value.__enter__.return_value.chat.completions.create
            create.side_effect=[response(payload(INVALID)),response(payload(INVALID))]
            answer, _=call_answer_model([],SOURCES,SETTINGS)
        self.assertEqual(answer["status"],"error")
        self.assertEqual(answer["error_kind"],"answer_validation_failed")


if __name__=="__main__":
    unittest.main()
