"""Offline safety/contract checks; --live also runs four actual paper questions.

Live cases use the existing NVIDIA connection and are smoke checks, not a
representative answer-accuracy benchmark. Reports include model text and quotes.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rag import (ROOT, prepare_evidence, build_messages, validate_answer,
                 call_answer_model, answer_question, render_answer)
from vector_index import connect_database


SOURCE = {"source_id": "S1", "chunk_id": "test-chunk", "pages": [17],
          "source_refs": ["#/texts/314"],
          "text": "Replay randomly selected pre-training samples in every iteration to reduce forgetting."}


def valid_payload():
    return {"status": "answered", "claims": [{"text": "Replay earlier training samples.",
            "evidence": [{"source_id": "S1", "quote": SOURCE["text"]}]}], "missing_information": ""}


class ContractChecks(unittest.TestCase):
    def test_accepted_citation_uses_server_pages(self):
        result = validate_answer(json.dumps(valid_payload()), [SOURCE])
        self.assertEqual(result["claims"][0]["evidence"][0]["pages"], [17])
        self.assertFalse(result["validation"]["semantic_entailment_verified"])

    def test_invented_quote_rejected(self):
        payload = valid_payload()
        payload["claims"][0]["evidence"][0]["quote"] = "Training without replay always prevents forgetting."
        with self.assertRaisesRegex(ValueError, "Quote not found"):
            validate_answer(json.dumps(payload), [SOURCE])

    def test_unknown_source_rejected(self):
        payload = valid_payload()
        payload["claims"][0]["evidence"][0]["source_id"] = "S99"
        with self.assertRaisesRegex(ValueError, "Unknown citation"):
            validate_answer(json.dumps(payload), [SOURCE])

    def test_model_cannot_supply_its_own_page_number(self):
        payload = valid_payload()
        payload["claims"][0]["evidence"][0]["pages"] = [999]
        with self.assertRaises(ValueError):
            validate_answer(json.dumps(payload), [SOURCE])

    def test_unsupported_and_partial_contracts(self):
        payload = {"status": "insufficient_evidence", "claims": [], "missing_information": "No GPT-5 result supplied."}
        self.assertEqual(validate_answer(json.dumps(payload), [SOURCE])["status"], "insufficient_evidence")
        payload["claims"] = valid_payload()["claims"]
        with self.assertRaises(ValueError):
            validate_answer(json.dumps(payload), [SOURCE])
        payload["status"] = "partial"
        self.assertEqual(validate_answer(json.dumps(payload), [SOURCE])["status"], "partial")

    def test_quote_whitespace_only_tolerance(self):
        payload = valid_payload()
        payload["claims"][0]["evidence"][0]["quote"] = SOURCE["text"].replace(" ", "\n")
        self.assertEqual(validate_answer(json.dumps(payload), [SOURCE])["status"], "answered")

    def test_context_not_silently_truncated(self):
        with self.assertRaisesRegex(ValueError, "nothing was truncated"):
            build_messages("question", [{**SOURCE, "text": "x" * 66000}])

    def test_source_policy_and_snapshot_guard(self):
        doc = {"pictures": [{"self_ref": "#/pictures/0", "meta": {"description": {"text": "Unverified generated description."}}}],
               "texts": [{"self_ref": "#/texts/0", "label": "formula", "text": "max(hat0,x)", "orig": "max(0,x)"}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "document.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            manifest = {"chunking_report": {"source": str(path)}, "identity": {"source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}
            hit = {"chunk_id": "c1", "contextualized_text": "Author sentence. Unverified generated description. max(hat0,x)",
                   "cosine_similarity": 0.8, "metadata": {"text_sources": ["ai_description", "extracted_document"],
                   "picture_links": [{"picture_ref": "#/pictures/0", "ai_description_included": True}],
                   "source_refs": ["#/pictures/0", "#/texts/0"], "pages": [1]}}
            sources, exclusions = prepare_evidence([hit], manifest)
            self.assertFalse(exclusions)
            self.assertNotIn("Unverified", sources[0]["text"])
            self.assertIn("max(0,x)", sources[0]["text"])
            self.assertEqual(sources[0]["source_refs"], ["#/texts/0"])
            hit["contextualized_text"] = "Only part of the unverified picture description."
            self.assertTrue(prepare_evidence([hit], manifest)[1])
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs from the indexed"):
                prepare_evidence([hit], manifest)

    def test_failed_model_output_repairs_once_then_fails(self):
        response = SimpleNamespace(id="test", usage=None, choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content="not JSON"))])
        with patch("openai.OpenAI") as client:
            create = client.return_value.__enter__.return_value.chat.completions.create
            create.return_value = response
            result, attempts = call_answer_model(build_messages("question", [SOURCE]), [SOURCE],
                {"api_key": "test-only", "model": "test", "base_url": "https://example.invalid"})
            self.assertEqual(result["status"], "error")
            self.assertEqual(create.call_count, 2)
            self.assertEqual(len(attempts), 2)

    def test_truncated_output_not_accepted_or_retried(self):
        response = SimpleNamespace(id="test", usage=None, choices=[SimpleNamespace(
            finish_reason="length", message=SimpleNamespace(content=json.dumps(valid_payload())))])
        with patch("openai.OpenAI") as client:
            create = client.return_value.__enter__.return_value.chat.completions.create
            create.return_value = response
            result, attempts = call_answer_model([], [SOURCE],
                {"api_key": "test-only", "model": "test", "base_url": "https://example.invalid"})
            self.assertEqual(result["status"], "error")
            self.assertEqual(create.call_count, 1)


def run_live(output: Path):
    cases = [
        ("forgetting", "While adapting a model to a new task, how can training prevent it from losing previously learned knowledge?", "answered"),
        ("bloomberg", "How many processing units and which GPU type does the model-configuration table list for BloombergGPT?", "answered"),
        ("unsupported", "What MMLU score does this paper report for GPT-5?", "insufficient_evidence"),
        ("two_passages", "Contrast replaying old pre-training examples with PanGu-Sigma's Random Routed Experts as approaches to reducing catastrophic forgetting.", "partial"),
    ]
    output.mkdir(parents=True, exist_ok=False)
    with connect_database(ROOT / ".env") as connection:
        before = connection.execute("SELECT count(*) FROM rag.chunks").fetchone()[0]
    checks = []
    for name, question, expected in cases:
        print(f"Live question: {name}", flush=True)
        report = answer_question("r2-3c63988f65eaf71161dafedc", question)
        (output / f"{name}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        (output / f"{name}.md").write_text(render_answer(report), encoding="utf-8")
        actual = report["answer"]["status"]
        checks.append({"case": name, "expected_status": expected, "actual_status": actual,
                       "status_check_passed": actual == expected,
                       "claim_count": len(report["answer"].get("claims", [])),
                       "provider_requests": len(report["attempts"])})
        print(json.dumps(checks[-1]), flush=True)
    with connect_database(ROOT / ".env") as connection:
        after = connection.execute("SELECT count(*) FROM rag.chunks").fetchone()[0]
    summary = {"scope": "Four live smoke cases; status expectations are AI-prepared, not an answer-accuracy benchmark.",
               "checks": checks, "database_rows_unchanged": before == after,
               "all_status_checks_passed": all(c["status_check_passed"] for c in checks)}
    (output / "checks.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if before != after or not summary["all_status_checks_passed"]:
        raise SystemExit("Live checks need review; outputs preserved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ContractChecks)
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)
    if args.live:
        if not args.output:
            parser.error("--live requires a new --output directory")
        run_live(args.output)
