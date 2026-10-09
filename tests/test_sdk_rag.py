"""The public adapter and RAG boundary must preserve traceability."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_intelligence import make_document, sample_collection
from pbl_docintel import (EvidenceAdapter, index_document, rag_chunks, resolve_evidence,
                          to_langchain_documents, validate_results)
from pbl_docintel.schema import ResultCollection


class SDKTests(unittest.TestCase):
    def setUp(self):
        self.document = make_document()
        self.index = index_document(self.document)

    def test_in_memory_adaptation_has_deterministic_identity(self):
        reordered = dict(reversed(list(self.document.items())))
        self.assertEqual(self.index.document.document_id, index_document(reordered).document.document_id)

    def test_native_docling_object_interface(self):
        source = self.document
        class ExistingPipelineDocument:
            def export_to_dict(self):
                return source
        self.assertEqual(index_document(ExistingPipelineDocument()).model_dump(), self.index.model_dump())

    def test_custom_adapter_does_not_require_docling_fields(self):
        normalized = self.index.model_dump(mode="json")
        normalized["document"].pop("docling_json_filename")
        normalized["document"].pop("docling_schema_version")
        normalized["document"]["producer"] = "external-parser"
        class ExternalAdapter:
            def adapt(self, source):
                return EvidenceAdapter().adapt(source)
        index = index_document(normalized, adapter=ExternalAdapter())
        self.assertEqual(index.document.producer, "external-parser")
        self.assertTrue(rag_chunks(index))

    def test_broken_normalized_context_is_rejected(self):
        data = self.index.model_dump(mode="json")
        data["units"]["#/texts/0"]["context"] = {"captions": ["missing"]}
        with self.assertRaises(ValueError):
            index_document(data, adapter=EvidenceAdapter())

    def test_missing_external_row_context_requires_review(self):
        data = self.index.model_dump(mode="json")
        data["units"]["#/tables/0::cell:8"]["context"] = {}
        index = EvidenceAdapter().adapt(data)
        collection = ResultCollection.model_validate_json(json.dumps(sample_collection(index)))
        check = validate_results(collection, index)[0]
        self.assertEqual(check["outcome"], "needs_review")
        self.assertIn("method_row_context_missing", check["warnings"])
        self.assertIn("metric_column_context_missing", check["warnings"])

    def test_table_chunks_include_headers_caption_and_preserve_merged_value(self):
        chunks = rag_chunks(self.index)
        value = next(c for c in chunks if json.loads(c["metadata"]["evidence_ids_json"])[0] == "#/tables/0::cell:9")
        self.assertIn("0.7 0.8", value["page_content"])
        self.assertIn("Column: B / Score ↑", value["page_content"])
        self.assertIn("Row: Ours", value["page_content"])
        self.assertIn("Caption: Datasets A and B", value["page_content"])
        self.assertIn("multiple_numeric_values", json.loads(value["metadata"]["issues_json"]))
        resolved = resolve_evidence(self.index, value)
        self.assertEqual(resolved[0]["text"], "0.7 0.8")
        self.assertEqual(resolved[0]["locations"][0]["bbox"]["coord_origin"], "TOPLEFT")

    def test_text_spans_reconstruct_exact_source_without_dropped_characters(self):
        self.document["texts"][0]["text"] = "Long Unicode text αβγ. " * 45
        self.index = index_document(self.document)
        chunks = [c for c in rag_chunks(self.index, max_text_chars=128)
                  if json.loads(c["metadata"]["evidence_ids_json"])[0] == "#/texts/0"]
        self.assertEqual("".join(c["page_content"] for c in chunks), self.document["texts"][0]["text"])
        for c in chunks:
            span = json.loads(c["metadata"]["evidence_spans_json"])[0]
            self.assertEqual(c["page_content"], self.document["texts"][0]["text"][span["start"]:span["end"]])
            self.assertLessEqual(len(c["page_content"]), 128)

    def test_chunk_ids_are_stable_and_metadata_is_vector_store_friendly(self):
        chunks = rag_chunks(self.index)
        self.assertEqual(chunks, rag_chunks(self.index))
        self.assertEqual(len({c["metadata"]["chunk_id"] for c in chunks}), len(chunks))
        for chunk in chunks:
            self.assertTrue(all(isinstance(v, (str, int, float, bool)) for v in chunk["metadata"].values()))

    def test_empty_table_keeps_caption_and_warning_without_inventing_cells(self):
        self.document["tables"][0]["data"] = {"num_rows": 0, "num_cols": 0, "table_cells": []}
        index = index_document(self.document)
        chunk = next(c for c in rag_chunks(index) if c["metadata"]["kind"] == "table")
        self.assertIn("Table structure unavailable", chunk["page_content"])
        self.assertIn("Datasets A and B", chunk["page_content"])
        self.assertIn("empty_table_structure", json.loads(chunk["metadata"]["issues_json"]))

    def test_annotations_keep_machine_checks_separate_from_review(self):
        collection = ResultCollection.model_validate_json(json.dumps(sample_collection(self.index)))
        chunk = next(c for c in rag_chunks(self.index, results=collection)
                     if json.loads(c["metadata"]["result_ids_json"]))
        self.assertEqual(json.loads(chunk["metadata"]["check_outcomes_json"]), ["evidence_checks_passed"])
        self.assertEqual(json.loads(chunk["metadata"]["review_statuses_json"]), ["unreviewed"])

    def test_mixing_documents_or_foreign_annotation_identity_is_rejected(self):
        chunk = copy.deepcopy(rag_chunks(self.index)[0])
        chunk["metadata"]["document_id"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "different conversion"):
            resolve_evidence(self.index, chunk)
        other = copy.deepcopy(self.document)
        other["name"] = "different"
        collection = ResultCollection.model_validate_json(json.dumps(sample_collection(index_document(other))))
        with self.assertRaises(ValueError):
            rag_chunks(self.index, results=collection)

    @unittest.skipUnless(importlib.util.find_spec("langchain_core"), "Optional LangChain dependency absent")
    def test_real_langchain_documents_preserve_metadata(self):
        chunks = rag_chunks(self.index)
        docs = to_langchain_documents(chunks)
        self.assertEqual(len(docs), len(chunks))
        self.assertEqual(docs[0].page_content, chunks[0]["page_content"])
        self.assertEqual(docs[0].metadata, chunks[0]["metadata"])

    def test_sdk_import_does_not_import_docling_or_langchain(self):
        result = subprocess.run([sys.executable, "-c",
                                 "import pbl_docintel, pbl_docintel.gui, sys; assert 'docling' not in sys.modules; assert 'langchain_core' not in sys.modules; assert 'fastapi' not in sys.modules; assert 'uvicorn' not in sys.modules"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
